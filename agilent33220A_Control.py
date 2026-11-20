# -*- coding: utf-8 -*-
"""
Agilent / Keysight 33220A function generator, driving the 365 nm LED head's
current driver (BuiltLightSourceFor_O-DLTS_MCTS) for O-DLTS / MCTS.

Wiring: 33220A Output -> driver CTRL IN (50 ohm terminated, 0-4 V sets 0 to
full-scale current); MFIA Trigger Out 2 -> 33220A rear Trig In; USB or LAN to
the PC (VISA). What to output comes from excitationTools.awg_settings().

Safety: the output is switched off on connect, before every reconfiguration,
on disconnect and by led_off(), which never raises so it can be called from
any error/close path. The instrument's own voltage limits (VOLT:LIM) clamp the
output to the requested level, never above the driver's 4 V full scale. The
driver's arming switch remains the hardware interlock.

EXAMPLE
# import agilent33220A_Control as awgC
# awg = awgC.awgDevice()
# awg.connect_device('USB0::0x0957::0x0407::MY12345678::INSTR')
# awg.configure_pulse(highV=0.4, widthS=1e-3, delayS=0.0, cycleS=0.009)
# awg.output(True); ...; awg.led_off(); awg.disconnect_device()
"""
import excitationTools as exT

import dltsConfig as dltsc

MODEL = '33220A'
MIN_AMPLITUDE_V = 0.01          # 33220A minimum 10 mVpp into 50 ohm
MIN_PULSE_PERIOD_S = 200e-9
EDGE_TIME_S = 5e-9              # fastest edge; the LED driver sets the real edges


def list_resources():
    """VISA resource names currently visible (empty on any VISA error)."""
    try:
        import pyvisa
        return list(pyvisa.ResourceManager().list_resources('?*::INSTR'))
    except Exception:
        return []


class awgDevice:

    def __init__(self, resource=None, instrument=None):
        self.resource = resource
        self.dev = instrument            # pyvisa resource (or a test double)
        self.rm = None
        self.idn = None
        self.state = instrument is not None
        self.outputOn = False
        self.params = dict(exT.DEFAULT_LIGHT_PARAMS)

    # --- connection -------------------------------------------------------
    def connect_device(self, resource=None):
        """Open the VISA resource, check it is a 33220A, switch the output off
        and set the 50 ohm load. Returns 0, or -1 with the reason logged."""
        if resource:
            self.resource = resource
        if not self.resource:
            dltsc.log_to_textbox("Light source: no VISA resource selected.")
            return -1
        try:
            import pyvisa
            self.rm = pyvisa.ResourceManager()
            self.dev = self.rm.open_resource(self.resource)
            self.dev.timeout = 5000
            self.idn = self.dev.query('*IDN?').strip()
        except Exception as exc:
            dltsc.log_to_textbox(f"Light source: cannot open {self.resource}: {exc}")
            self._close_quietly()
            return -1
        if MODEL not in self.idn:
            dltsc.log_to_textbox(f"Light source: {self.resource} is '{self.idn}', not a {MODEL}; not used.")
            self._close_quietly()
            return -1
        self.state = True
        self.initialize()
        return 0

    def initialize(self):
        """Known safe state: output off, errors cleared, 50 ohm load, normal polarity."""
        self.write('OUTP OFF')
        self.outputOn = False
        self.write('*CLS')
        self.write('OUTP:LOAD 50')
        self.write('OUTP:POL NORM')

    def disconnect_device(self):
        self.led_off()
        self._close_quietly()
        return 0

    def _close_quietly(self):
        try:
            if self.dev is not None:
                self.dev.close()
        except Exception:
            pass
        self.dev = None
        self.state = False

    def set_param_value(self, pName, valueDict):
        """GUI sync hook (runParamsTab._sync_param_values_to_device)."""
        if pName in self.params:
            self.params[pName] = valueDict.get(pName)
        return 0

    # --- low level --------------------------------------------------------
    def write(self, cmd):
        if self.dev is None:
            raise RuntimeError(f"{MODEL} not connected")
        self.dev.write(cmd)

    def query(self, cmd):
        if self.dev is None:
            raise RuntimeError(f"{MODEL} not connected")
        return self.dev.query(cmd).strip()

    def check_errors(self):
        """Drain the instrument's error queue; returns the error strings."""
        errors = []
        for _ in range(20):
            reply = self.query('SYST:ERR?')
            if reply.startswith('+0') or reply.startswith('0,'):
                break
            errors.append(reply)
        return errors

    # --- output -----------------------------------------------------------
    def _set_limits(self, highV):
        """Clamp the output to [CTRL_LOW_LIMIT_V, highV] (never above 4 V).
        Set after the levels, as the instrument refuses limits that exclude
        the present output levels."""
        high = min(max(highV, MIN_AMPLITUDE_V), exT.CTRL_FULL_SCALE_V)
        self.write(f'VOLT:LIM:HIGH {high:.6g}')
        self.write(f'VOLT:LIM:LOW {exT.CTRL_LOW_LIMIT_V:.6g}')
        self.write('VOLT:LIM:STAT ON')

    def configure_pulse(self, highV, widthS, delayS, cycleS):
        """One LED pulse of height highV (V at CTRL IN), width widthS, delayS
        after each rising edge at Trig In (MFIA Trigger Out 2). cycleS is the
        MFIA cycle (trigger interval); the pulse's own period is kept inside
        it so no trigger is missed. Output stays off; call output(True)."""
        if not MIN_AMPLITUDE_V <= highV <= exT.CTRL_FULL_SCALE_V:
            raise ValueError(f"LED pulse level {highV:.4g} V outside {MIN_AMPLITUDE_V}-{exT.CTRL_FULL_SCALE_V} V")
        if cycleS is None or not (widthS > 0 and delayS >= 0 and delayS + widthS < cycleS):
            raise ValueError("LED pulse must fit in the MFIA cycle (delay + width < cycle)")
        gap = cycleS - delayS - widthS
        period = max(widthS + min(widthS, 0.5 * gap), MIN_PULSE_PERIOD_S)
        self.output(False)
        self.write('VOLT:LIM:STAT OFF')
        self.write('BURS:STAT OFF')
        self.write('FUNC PULS')
        self.write('VOLT:LOW 0')
        self.write(f'VOLT:HIGH {highV:.6g}')
        self.write(f'PULS:PER {period:.9g}')
        self.write(f'PULS:WIDT {widthS:.9g}')
        self.write(f'PULS:TRAN {EDGE_TIME_S:.3g}')
        self.write('BURS:MODE TRIG')
        self.write('BURS:NCYC 1')
        self.write('TRIG:SOUR EXT')
        self.write('TRIG:SLOP POS')
        self.write(f'TRIG:DEL {delayS:.9g}')
        self.write('BURS:STAT ON')
        self._set_limits(highV)
        return self._raise_on_errors('pulse setup')

    def configure_dc(self, dcV):
        """Constant CTRL IN level dcV (steady light). Output stays off."""
        if not 0 <= dcV <= exT.CTRL_FULL_SCALE_V:
            raise ValueError(f"LED DC level {dcV:.4g} V outside 0-{exT.CTRL_FULL_SCALE_V} V")
        self.output(False)
        self.write('VOLT:LIM:STAT OFF')
        self.write('BURS:STAT OFF')
        self.write('FUNC DC')
        self.write(f'VOLT:OFFS {dcV:.6g}')
        self._set_limits(dcV)
        return self._raise_on_errors('DC setup')

    def apply_settings(self, settings, cycleS=None):
        """Configure from excitationTools.awg_settings(); 'off' just switches
        the output off."""
        if settings['mode'] == 'pulse':
            return self.configure_pulse(settings['highV'], settings['widthS'], settings['delayS'], cycleS)
        if settings['mode'] == 'dc':
            return self.configure_dc(settings['dcV'])
        self.output(False)
        return 0

    def output(self, on):
        self.write('OUTP ON' if on else 'OUTP OFF')
        self.outputOn = bool(on)

    def led_off(self):
        """Switch the output off; never raises (safe in every error/close path).
        Returns True if the command was sent."""
        try:
            if self.dev is None:
                return False
            self.dev.write('OUTP OFF')
            self.outputOn = False
            return True
        except Exception:
            return False

    def _raise_on_errors(self, what):
        errors = self.check_errors()
        if errors:
            self.led_off()
            raise RuntimeError(f"{MODEL} {what} rejected: {'; '.join(errors)}")
        return 0

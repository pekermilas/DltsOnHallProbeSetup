# -*- coding: utf-8 -*-
"""
Driver for the HDS-4 Hall/DLTS selector (hardware/hallDltsSelector/), the
planned relay box that replaces the four manual A/B boxes between the Instec
stage contacts P1-P4 and the instruments:

    position A = Hall  (Keithley 2450 through the Arduino switch box)
    position B = DLTS  (MFIA: P1 HCUR, P2 LCUR, P3 LPOT, P4 free)
    OPEN       = disconnected from both (power-up state)

Imports no app config (dltsConfig / hallProbeConfig), so the DLTS and the Hall
software can both use it. Not yet wired into either GUI.

Example:
    import hallDltsSelector_Control as hdsC
    sel = hdsC.selectorDevice()
    if sel.connect_device('COM8') != 0: print(sel.lastError)
    sel.set_mode('dlts')
    sel.get_state()          # {'P1': 'B', 'P2': 'B', 'P3': 'B', 'P4': 'B'}
    sel.disconnect_device()
"""

import threading
import time

import serial
import serial.tools.list_ports

BAUD = 115200
TIMEOUT_S = 2.0
BOOT_WAIT_S = 2.0          # opening the port resets the Nano (DTR); wait for its boot
IDN_TAG = 'HDS4'
CHANNELS = ('P1', 'P2', 'P3', 'P4')
MODES = ('hall', 'dlts', 'open')
POSITIONS = ('A', 'B', 'OPEN')
# What each DLTS-side (B) jack is cabled to on the MFIA (2-terminal setup).
DLTS_CABLING = {'P1': 'MFIA Signal Output HCUR', 'P2': 'MFIA Signal Input LCUR',
                'P3': 'MFIA Signal Input LPOT', 'P4': 'free'}


class SelectorError(RuntimeError):
    """The box answered ERR, or did not answer."""


def list_ports():
    """Serial port names Windows reports, sorted."""
    try:
        return sorted(p.device for p in serial.tools.list_ports.comports())
    except Exception:
        return []


class selectorDevice:

    def __init__(self, port=None, instrument=None):
        """instrument: an already-open serial-like object (tests pass a simulator)."""
        self.port = port
        self.dev = instrument
        self.state = instrument is not None
        self.idn = ''
        self.lastError = ''
        self._ioLock = threading.RLock()

    # ---- connection --------------------------------------------------------
    def connect_device(self, port=None):
        """Open the port and check *IDN?. Returns 0, or -1 with self.lastError set.
        The box resets to all OPEN when the port is opened."""
        if port:
            self.port = port
        self.lastError = ''
        if self.dev is None:
            if not self.port:
                self.lastError = 'no serial port given'
                return -1
            try:
                self.dev = serial.Serial(self.port, BAUD, timeout=TIMEOUT_S,
                                         write_timeout=TIMEOUT_S)
                time.sleep(BOOT_WAIT_S)
            except Exception as e:
                self.dev = None
                self.state = False
                self.lastError = f'could not open {self.port}: {e}'
                return -1
        self.state = True
        try:
            self.idn = self.query('*IDN?')
        except Exception as e:
            self.idn = ''
            self.lastError = f'no answer to *IDN? on {self.port}: {e}'
        if IDN_TAG not in self.idn:
            if not self.lastError:
                self.lastError = f'{self.port} is not an HDS-4 selector (IDN {self.idn!r})'
            self._close()
            return -1
        return 0

    def disconnect_device(self, open_all=False):
        """Close the port. The routing is left as it is unless open_all=True.
        (Closing does not reset the Nano; the next open does.)"""
        if self.dev is None:
            self.state = False
            return 0
        status = 0
        if open_all and self.state:
            try:
                self.set_mode('open')
            except Exception as e:
                self.lastError = f'could not open all channels: {e}'
                status = -1
        self._close()
        return status

    def _close(self):
        try:
            if self.dev is not None:
                self.dev.close()
        except Exception:
            pass
        self.dev = None
        self.state = False

    # ---- low level -----------------------------------------------------------
    def query(self, cmd):
        """Send one command, return the reply line. Raises SelectorError on
        ERR or silence."""
        if self.dev is None or not self.state:
            raise SelectorError('selector is not connected')
        with self._ioLock:
            self.dev.reset_input_buffer()
            self.dev.write((cmd.strip() + '\n').encode())
            reply = self.dev.readline().decode(errors='replace').strip()
        if not reply:
            raise SelectorError(f'no reply to {cmd!r} within {TIMEOUT_S:g} s')
        if reply.startswith('ERR'):
            raise SelectorError(f'{cmd!r}: {reply}')
        return reply

    def _command(self, cmd):
        reply = self.query(cmd)
        if reply != 'OK':
            raise SelectorError(f'{cmd!r}: unexpected reply {reply!r}')

    # ---- routing -------------------------------------------------------------
    def set_mode(self, mode):
        """'hall' (all A), 'dlts' (all B) or 'open'. Switch only with the
        instrument outputs off (see the README)."""
        mode = str(mode).lower()
        if mode not in MODES:
            raise ValueError(f'mode must be one of {MODES}, not {mode!r}')
        self._command(f'MODE {mode.upper()}')

    def set_channel(self, channel, position):
        """channel 1-4 (or 'P1'..'P4'); position 'A', 'B' or 'OPEN'."""
        ch = int(str(channel).upper().lstrip('P'))
        if ch not in (1, 2, 3, 4):
            raise ValueError(f'channel must be 1-4, not {channel!r}')
        pos = str(position).upper()
        if pos not in POSITIONS:
            raise ValueError(f'position must be one of {POSITIONS}, not {position!r}')
        self._command(f'CH {ch} {pos}')

    def get_mode(self):
        """'hall', 'dlts', 'open' or 'mixed'."""
        return self.query('MODE?').lower()

    def get_state(self):
        """{'P1': 'A'|'B'|'OPEN', ...}"""
        reply = self.query('STATE?')
        state = {}
        for item in reply.split(','):
            name, _, pos = item.partition('=')
            state[name.strip()] = pos.strip()
        if set(state) != set(CHANNELS):
            raise SelectorError(f'unexpected STATE? reply {reply!r}')
        return state

    def relay_power(self):
        """True if the RELAY POWER switch is on (relays can close)."""
        return self.query('PWR?') == 'ON'

    def require_mode(self, mode):
        """Return None if the box is in `mode` with relay power on, else a
        message saying why not. For a run's setup check (planned)."""
        try:
            current = self.get_mode()
            if current != mode:
                return f'selector is in {current.upper()} mode, not {mode.upper()}'
            if not self.relay_power():
                return 'selector RELAY POWER switch is off (all channels open)'
        except Exception as e:
            return f'selector: {e}'
        return None

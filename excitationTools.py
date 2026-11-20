# -*- coding: utf-8 -*-
"""
Excitation methods: how a DLTS run excites the sample (electrical fill pulse,
LED light pulse from the 365 nm head, or both), and the pure functions the GUI,
the run sequence and the analysis share to set it up and to read it back.

Hardware (BuiltLightSourceFor_O-DLTS_MCTS): an Agilent 33220A drives the LED
driver's CTRL IN (0-4 V into its 50 ohm termination sets 0 to full-scale
current: 1 A on the 1 ohm range, 100 mA on the 10 ohm range, a jumper on the
driver). The 33220A is triggered by MFIA Trigger Out 2, which follows the
same threshold unit (Threshold 1) that triggers the DAQ, so every LED pulse
sits at a fixed delay after the acquisition's trigger edge. The driver's
I_MON (1 V/A on the 1 ohm range, 10 V/A on the 10 ohm range) can be recorded
on MFIA Aux In 2. The driver's arming switch is a hardware interlock the
software cannot override.

Adding an excitation method later is a new METHODS row; the run sequence and
the analysis read what a method needs from its row, not from its number.

Pure computation (no Tk, no instruments), so everything here is unit-tested.
"""
import numpy as np

# --- Methods -------------------------------------------------------------------
METHOD_ELECTRICAL = 0
METHOD_OPTICAL = 1
METHOD_ELECTRICAL_OPTICAL = 2
METHOD_STEADY_LIGHT = 3

# biasPulsed: the MFIA's own fill / reverse-bias pulse reaches the sample.
# awg: what the 33220A outputs during an acquisition (None, 'pulse', 'dc').
# opticalReference: the analysis finds the pulses from the LED, not the bias.
METHODS = {
    METHOD_ELECTRICAL: dict(name='Electrical DLTS', biasPulsed=True, awg=None,
                            opticalReference=False),
    METHOD_OPTICAL: dict(name='Optical Fill (O-DLTS/MCTS)', biasPulsed=False, awg='pulse',
                         opticalReference=True),
    METHOD_ELECTRICAL_OPTICAL: dict(name='Electrical + Optical', biasPulsed=True, awg='pulse',
                                    opticalReference=False),
    METHOD_STEADY_LIGHT: dict(name='Electrical + Steady Light', biasPulsed=True, awg='dc',
                              opticalReference=False),
}

# --- LED driver ----------------------------------------------------------------
RANGE_1A = 0
RANGE_100MA = 1
RANGE_FULL_SCALE_A = {RANGE_1A: 1.0, RANGE_100MA: 0.1}
IMON_V_PER_A = {RANGE_1A: 1.0, RANGE_100MA: 10.0}
CTRL_FULL_SCALE_V = 4.0          # CTRL IN volts at full-scale current
CTRL_LOW_LIMIT_V = -0.1          # the AWG may go slightly negative, never further

# Thermal limits of the driver's MOSFET (about 4 W at 1 A; build guide).
MAX_AVERAGE_CURRENT_A = 0.3      # pulse current x duty cycle
MAX_STEADY_CURRENT_A = 0.2       # Electrical + Steady Light DC level

REF_IMON = 0                     # Optical Timing Reference: I_MON on Aux In 2
REF_COMMANDED = 1                # ... or rebuilt from the commanded timing

# Channel an optical run's step files carry for the analysis: a 0/1 marker,
# high while the LED is on (the same polarity as the electrical fill level in
# AuxInput1, so the same falling-edge search finds the transient starts).
PULSE_REFERENCE_CHANNEL = 'PulseReference'
IMON_CHANNEL = 'AuxInput2'
BIAS_CHANNEL = 'AuxInput1'

# Light Source parameter names (runParamsTab's group; bare names, units in the
# GUI labels) and their typed defaults.
DEFAULT_LIGHT_PARAMS = {
    'Excitation Method': METHOD_ELECTRICAL,
    'LED Driver Range': RANGE_100MA,
    'LED Pulse Current': 10.0,        # mA
    'LED Pulse Width': 0.001,         # s
    'LED Pulse Delay': 0.0,           # s after the trigger edge
    'LED Steady Current': 5.0,        # mA
    'Optical Timing Reference': REF_IMON,
    'Commanded Timing Offset': 0.0,   # s, calibrated once against I_MON
    'Record I_MON': 1,
    'AWG VISA Resource': '',
}


def _num(params, name, default=None):
    value = params.get(name, DEFAULT_LIGHT_PARAMS.get(name) if default is None else default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(DEFAULT_LIGHT_PARAMS.get(name, 0.0) if default is None else default)


def method_of(lightParams):
    """The run's excitation method; runs from before the light source existed
    have no such parameter and are electrical."""
    try:
        method = int((lightParams or {}).get('Excitation Method', METHOD_ELECTRICAL))
    except (TypeError, ValueError):
        return METHOD_ELECTRICAL
    return method if method in METHODS else METHOD_ELECTRICAL


def method_info(lightParams):
    return METHODS[method_of(lightParams)]


def needs_awg(lightParams):
    return method_info(lightParams)['awg'] is not None


def records_imon(lightParams):
    """Whether pull_data() should record I_MON on Aux In 2. Always for the
    I_MON optical reference, otherwise when 'Record I_MON' is on."""
    lightParams = lightParams or {}
    if method_info(lightParams)['opticalReference'] and \
            int(_num(lightParams, 'Optical Timing Reference')) == REF_IMON:
        return True
    return needs_awg(lightParams) and bool(int(_num(lightParams, 'Record I_MON')))


def driver_range(lightParams):
    code = int(_num(lightParams, 'LED Driver Range'))
    return code if code in RANGE_FULL_SCALE_A else RANGE_100MA


def ctrl_volts(current_mA, rangeCode):
    """CTRL IN voltage for an LED current (mA) on the driver's range."""
    return CTRL_FULL_SCALE_V * (float(current_mA) * 1e-3) / RANGE_FULL_SCALE_A[rangeCode]


def cycle_period_s(zParams):
    """Length of one MFIA threshold-unit cycle (State Enable + State Disable)."""
    return float(zParams['State Enable Time']) + float(zParams['State Disable Time'])


def validate(lightParams, zParams):
    """Problems that must stop a run (or an Apply) with these settings; [] if
    none. zParams are the MFIA parameters (State Enable/Disable Time, Aux
    Output Scale/Offset/limits)."""
    errors = []
    lightParams = lightParams or {}
    info = method_info(lightParams)
    if info['awg'] is None:
        return errors
    rangeCode = driver_range(lightParams)
    fullScale_mA = RANGE_FULL_SCALE_A[rangeCode] * 1e3
    try:
        period = cycle_period_s(zParams)
    except (KeyError, TypeError, ValueError):
        return ["MFIA State Enable / Disable Time must be set before the light source."]

    if info['awg'] == 'pulse':
        current = _num(lightParams, 'LED Pulse Current')
        width = _num(lightParams, 'LED Pulse Width')
        delay = _num(lightParams, 'LED Pulse Delay')
        if not 0 < current <= fullScale_mA:
            errors.append(f"LED Pulse Current must be above 0 and at most {fullScale_mA:g} mA "
                          f"on the {'1 A' if rangeCode == RANGE_1A else '100 mA'} driver range.")
        if width <= 0:
            errors.append("LED Pulse Width must be above 0 s.")
        if delay < 0:
            errors.append("LED Pulse Delay must not be negative.")
        if width > 0 and delay >= 0 and delay + width >= period:
            errors.append(f"LED Pulse Delay + Width ({(delay + width) * 1e3:g} ms) must end before the next "
                          f"MFIA cycle starts ({period * 1e3:g} ms = State Enable + Disable Time).")
        if method_of(lightParams) == METHOD_ELECTRICAL_OPTICAL and width > float(zParams['State Disable Time']):
            errors.append("Electrical + Optical: the LED pulse must fit inside the electrical fill pulse "
                          "(LED Pulse Width <= State Disable Time).")
        if width > 0 and period > 0:
            average = current * 1e-3 * width / period
            if average > MAX_AVERAGE_CURRENT_A:
                errors.append(f"Average LED current {average * 1e3:.0f} mA (pulse current x duty cycle) is above "
                              f"the driver's {MAX_AVERAGE_CURRENT_A * 1e3:.0f} mA thermal limit; "
                              "shorten the pulse or lower the current.")
    else:
        current = _num(lightParams, 'LED Steady Current')
        limit_mA = min(fullScale_mA, MAX_STEADY_CURRENT_A * 1e3)
        if not 0 < current <= limit_mA:
            errors.append(f"LED Steady Current must be above 0 and at most {limit_mA:g} mA "
                          "(driver thermal limit for continuous light).")

    if info['opticalReference'] and int(_num(lightParams, 'Optical Timing Reference')) not in (REF_IMON, REF_COMMANDED):
        errors.append("Optical Timing Reference must be I_MON or Commanded Timing.")
    if not str(lightParams.get('AWG VISA Resource', '') or '').strip():
        errors.append("Select the 33220A's VISA resource and connect it on the Light Source panel.")
    return errors


def effective_mfia_params(zParams, lightParams):
    """The MFIA parameters actually pushed for this excitation method. For an
    optical fill the bias must not pulse: Aux Output 1 is held at the
    reverse-bias level the electrical settings define (Offset + Scale, within
    the aux output limits) by pushing Scale 0. The threshold unit keeps
    running, so the cycle timing and the DAQ / AWG trigger are unchanged.
    The GUI's own values are never modified."""
    effective = dict(zParams)
    if not method_info(lightParams)['biasPulsed']:
        reverse = float(zParams['Aux Output Offset']) + float(zParams['Aux Output Scale'])
        lower = float(zParams.get('Aux Output Lower Limit', -10.0))
        upper = float(zParams.get('Aux Output Upper Limit', 10.0))
        effective['Aux Output Scale'] = 0.0
        effective['Aux Output Offset'] = min(max(reverse, lower), upper)
    return effective


def mfia_override(zParams, lightParams):
    """effective_mfia_params() when the method changes any MFIA value, else
    None (electrical-bias methods push the GUI values unchanged)."""
    if method_info(lightParams)['biasPulsed']:
        return None
    return effective_mfia_params(zParams, lightParams)


def awg_settings(lightParams, zParams=None):
    """What the 33220A should do during an acquisition:
    {'mode': 'off'} or
    {'mode': 'pulse', 'highV', 'widthS', 'delayS', 'limitHighV'} or
    {'mode': 'dc', 'dcV', 'limitHighV'}.
    limitHighV is the instrument's own output clamp: the requested level, never
    above the driver's full-scale 4 V."""
    lightParams = lightParams or {}
    kind = method_info(lightParams)['awg']
    if kind is None:
        return {'mode': 'off'}
    rangeCode = driver_range(lightParams)
    if kind == 'pulse':
        highV = ctrl_volts(_num(lightParams, 'LED Pulse Current'), rangeCode)
        return {'mode': 'pulse', 'highV': highV, 'widthS': _num(lightParams, 'LED Pulse Width'),
                'delayS': _num(lightParams, 'LED Pulse Delay'),
                'limitHighV': min(highV, CTRL_FULL_SCALE_V)}
    dcV = ctrl_volts(_num(lightParams, 'LED Steady Current'), rangeCode)
    return {'mode': 'dc', 'dcV': dcV, 'limitHighV': min(dcV, CTRL_FULL_SCALE_V)}


def commanded_marker(timeS, lightParams, zParams):
    """0/1 marker of when the LED was commanded on, on an acquisition's time
    axis (s from the DAQ trigger edge, which also triggers the AWG): on during
    [offset + delay + k*period, ... + width). 'Commanded Timing Offset'
    absorbs any fixed lag between the trigger and the grid's t = 0 (calibrate
    it once against I_MON)."""
    t = np.asarray(timeS, dtype=np.float64)
    period = cycle_period_s(zParams)
    start = _num(lightParams, 'Commanded Timing Offset') + _num(lightParams, 'LED Pulse Delay')
    width = _num(lightParams, 'LED Pulse Width')
    # A pulse shorter than the sample spacing still marks one sample.
    steps = np.diff(t)
    steps = steps[np.isfinite(steps) & (steps > 0)]
    if steps.size:
        width = max(width, float(np.median(steps)))
    phase = np.mod(t - start, period)
    return (phase < width).astype(np.float64)


def imon_marker(imonV, lightParams):
    """I_MON (V) as a 0/1 marker: divided by the level the commanded pulse
    current gives, so 1 = LED at the set current, 0 = off. A LED that never
    fired (arming switch off) stays near 0 and the analysis reports no pulses."""
    rangeCode = driver_range(lightParams)
    expectedV = _num(lightParams, 'LED Pulse Current') * 1e-3 * IMON_V_PER_A[rangeCode]
    return np.asarray(imonV, dtype=np.float64) / expectedV


def build_pulse_reference(data, lightParams, zParams):
    """The PulseReference channel an optical-fill step file carries, or None
    for methods whose pulses are found from the bias (AuxInput1)."""
    if not method_info(lightParams)['opticalReference']:
        return None
    if int(_num(lightParams, 'Optical Timing Reference')) == REF_IMON:
        if IMON_CHANNEL not in data:
            raise KeyError("I_MON (Aux In 2) was not recorded; wire I_MON to MFIA Aux In 2 "
                           "or choose Optical Timing Reference = Commanded Timing.")
        return imon_marker(data[IMON_CHANNEL], lightParams)
    t = np.asarray(data['timeStampImps'], dtype=np.float64)
    return commanded_marker(t - t[0], lightParams, zParams)


def pulse_reference(channels):
    """(signal, channel name) a step record's pulses are found from: its
    PulseReference (optical fill) when it has one, else the bias AuxInput1.
    Both are higher during the fill, so a falling edge starts a transient."""
    if PULSE_REFERENCE_CHANNEL in channels:
        return channels[PULSE_REFERENCE_CHANNEL], PULSE_REFERENCE_CHANNEL
    return channels[BIAS_CHANNEL], BIAS_CHANNEL


def run_timing(runParams):
    """(fill ms, transient window ms) of a run from its runParams.txt dict, or
    None. Electrical: the MFIA's State Disable / Enable Time. Optical fill: the
    LED pulse width and the rest of the cycle (the bias never changes)."""
    try:
        enable = float(runParams['State Enable Time'])
        disable = float(runParams['State Disable Time'])
    except (KeyError, TypeError, ValueError):
        return None
    if method_info(runParams)['opticalReference']:
        width = _num(runParams, 'LED Pulse Width')
        fillMs, rbMs = width * 1e3, (enable + disable - width) * 1e3
    else:
        fillMs, rbMs = disable * 1e3, enable * 1e3
    if not (fillMs > 0 and rbMs > 0):
        return None
    return fillMs, rbMs


def is_optical_fill(runParams):
    return method_info(runParams or {})['opticalReference']

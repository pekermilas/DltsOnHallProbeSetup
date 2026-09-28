"""Shared setup for the real-hardware benchmark: a headless stand-in for the GUI's
Input Parameters tab (the same dltsConfig state, filled with the GUI's default
values) and log_to_textbox() redirected to a log file."""
import os, sys, time, json
from datetime import datetime
os.environ.setdefault('LOKY_MAX_CPU_COUNT', str(os.cpu_count()))
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import matplotlib; matplotlib.use('Agg')
import dltsConfig as dltsc

# Everything a benchmark writes goes here (git-ignored), one subfolder per run.
DEFAULT_OUTPUT = os.path.join(HERE, 'output')


class Var:
    """Minimal tk.StringVar stand-in: .get()/.set()."""
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


# Exactly runParamsTab.construct_runParamsTab()'s defaults.
Z_DEFAULTS = [
    ('Oscillation Amplitude', '0.300'), ('Oscillation Frequency', '501000'),
    ('Oscillation ON/OFF', '1 - On'), ('Max bandwidth', '10000'), ('Input Control', '0 - Manual'),
    ('Current Range', '0.010'), ('Voltage Range', '3'), ('Omega Suppression', '80'),
    ('Filter Harmonic', '1'), ('Filter Bandwidth', '2'), ('Data Transfer Rate', '60000'),
    ('Equivalent Circuit Mode', '0 - 4-Terminal'), ('Threshold Input Signal', '59 - TU Output Value'),
    ('State Enable Time', '0.006'), ('State Disable Time', '0.003'), ('Logic Unit Not', '1 - On'),
    ('Aux Output Signal', '13 - TU Output Value'), ('Aux Output Scale', '-1'),
    ('Aux Output Offset', '-0.5'), ('Aux Output Lower Limit', '-10'), ('Aux Output Upper Limit', '0'),
    ('Signal Output Add', '1 - True'), ('Trigger Source Signal', '36 - Threshold 1')]
T_DEFAULTS = [('Initial Temperature (C)', '25'), ('Final Temperature (C)', '25'),
              ('Temperature Step (C)', '5'), ('Temperature Ramp (C/min)', '5'),
              ('Stability Delay (s)', '0'), ('Room Temperature (C)', '25'), ('Room Ramp (C/min)', '10')]
D_DEFAULTS = [('Number of Points (power of 2)', 16), ('Number of Reps', 500),
              ('Data File Format', 'TXT'), ('Data Root Folder', '')]


def setup_gui_state(logPath, z_overrides=None, t_overrides=None, d_overrides=None):
    dltsc.init()
    dltsc.z_params_vars = {k: Var(v) for k, v in Z_DEFAULTS}
    dltsc.t_params_vars = {k: Var(v) for k, v in T_DEFAULTS}
    dltsc.d_params_vars = {k: Var(v) for k, v in D_DEFAULTS}
    for k, v in (z_overrides or {}).items(): dltsc.z_params_vars[k].set(v)
    for k, v in (t_overrides or {}).items(): dltsc.t_params_vars[k].set(v)
    for k, v in (d_overrides or {}).items(): dltsc.d_params_vars[k].set(v)

    os.makedirs(os.path.dirname(logPath), exist_ok=True)
    logFile = open(logPath, 'a', encoding='utf-8', buffering=1)
    def log(msg):
        line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
        print(line, flush=True)
        logFile.write(line + '\n')
    dltsc.log_to_textbox = log
    return log


def connect_impedance(log):
    """runParamsTab 'Connect + Get Params' then 'Apply + Push Params' (impedance)."""
    import runParamsTab as rpT
    import zurichInstruments_Control as ziC
    dltsc.impDev = ziC.ziDevice()
    dltsc.impDev.connect_device()
    if dltsc.impDev.device is None:
        raise RuntimeError('MFIA connection failed')
    time.sleep(1)
    dltsc.z_params_for_push = rpT._sync_param_values_to_device(dltsc.impDev, dltsc.z_params_vars, 'impDev')
    for pName in dltsc.impDev.params:
        if pName in dltsc.z_params_for_push:
            dltsc.impDev.push_param_to_device(pName)
    log('MFIA connected, params pushed: ' + json.dumps(dltsc.z_params_for_push))


def connect_temperature(log):
    """runParamsTab 'Connect + Get Params' then 'Apply + Push Params' (temperature)."""
    import runParamsTab as rpT
    import instecTempStage_Control as tsC
    dltsc.tempDev = tsC.mK2000B()
    dltsc.tempDev.connect_temp_controller()
    if not dltsc.tempDev.state:
        raise RuntimeError('temperature controller connection failed')
    time.sleep(1)
    dltsc.t_params_for_push = rpT._sync_param_values_to_device(dltsc.tempDev, dltsc.t_params_vars, 'tempDev')
    dltsc.tempDev.load_params(dltsc.t_params_for_push)
    log('Temperature controller connected, params: ' + json.dumps(dltsc.t_params_for_push))

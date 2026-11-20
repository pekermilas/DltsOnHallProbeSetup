"""The 365 nm LED light source (Agilent 33220A) for O-DLTS / MCTS: excitation
methods (excitationTools), the 33220A driver against a fake VISA instrument,
the run sequence switching the LED around each acquisition, and the analysis
finding optical-fill transients from PulseReference."""
import json
import os
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

import dltsConfig as dltsc
import excitationTools as exT
import agilent33220A_Control as awgC
import runDlts_Tools as rdT
import zurichInstruments_Control as ziC
import impedanceAnalysis_Tools as iaT
import liveDataTab as ldT
import detailedAnalysisTab as daT
from conftest import SAMPLE_DT_S, make_step, step_file_name

Z = {'State Enable Time': 0.5, 'State Disable Time': 0.001, 'Aux Output Scale': -5.0,
     'Aux Output Offset': 0.0, 'Aux Output Lower Limit': -10.0, 'Aux Output Upper Limit': 5.0}


def light(method, **over):
    return {**exT.DEFAULT_LIGHT_PARAMS, 'Excitation Method': method,
            'AWG VISA Resource': 'USB0::FAKE::INSTR', **over}


# --- excitationTools -----------------------------------------------------------

def test_electrical_method_needs_nothing_and_changes_nothing():
    params = light(exT.METHOD_ELECTRICAL, **{'AWG VISA Resource': ''})
    assert exT.validate(params, Z) == []
    assert exT.awg_settings(params) == {'mode': 'off'}
    assert exT.mfia_override(Z, params) is None
    assert exT.effective_mfia_params(Z, params) == Z
    assert not exT.records_imon(params)


def test_optical_fill_holds_the_bias_at_the_reverse_level():
    eff = exT.effective_mfia_params(Z, light(exT.METHOD_OPTICAL))
    assert eff['Aux Output Scale'] == 0.0
    assert eff['Aux Output Offset'] == -5.0          # Offset + Scale: the reverse-bias level
    assert Z['Aux Output Scale'] == -5.0            # the GUI's values are untouched


def test_optical_fill_reverse_level_respects_the_aux_limits():
    eff = exT.effective_mfia_params({**Z, 'Aux Output Lower Limit': -3.0}, light(exT.METHOD_OPTICAL))
    assert eff['Aux Output Offset'] == -3.0


@pytest.mark.parametrize('current,rangeCode,volts', [(10.0, exT.RANGE_100MA, 0.4), (100.0, exT.RANGE_100MA, 4.0),
                                                     (100.0, exT.RANGE_1A, 0.4), (1000.0, exT.RANGE_1A, 4.0)])
def test_current_to_ctrl_volts(current, rangeCode, volts):
    settings = exT.awg_settings(light(exT.METHOD_OPTICAL, **{'LED Pulse Current': current,
                                                            'LED Driver Range': rangeCode}))
    assert settings['mode'] == 'pulse'
    assert settings['highV'] == pytest.approx(volts)
    assert settings['limitHighV'] <= exT.CTRL_FULL_SCALE_V


def test_steady_light_is_a_dc_level():
    settings = exT.awg_settings(light(exT.METHOD_STEADY_LIGHT, **{'LED Steady Current': 5.0}))
    assert settings == {'mode': 'dc', 'dcV': pytest.approx(0.2), 'limitHighV': pytest.approx(0.2)}


@pytest.mark.parametrize('method,over,fragment', [
    (exT.METHOD_OPTICAL, {'LED Pulse Current': 150.0}, 'at most 100 mA'),
    (exT.METHOD_OPTICAL, {'LED Pulse Width': 0.0}, 'Width must be above 0'),
    (exT.METHOD_OPTICAL, {'LED Pulse Delay': 0.4, 'LED Pulse Width': 0.2}, 'must end before the next'),
    (exT.METHOD_OPTICAL, {'LED Driver Range': exT.RANGE_1A, 'LED Pulse Current': 1000.0, 'LED Pulse Width': 0.2},
     'thermal limit'),
    (exT.METHOD_ELECTRICAL_OPTICAL, {'LED Pulse Width': 0.002}, 'fit inside the electrical fill'),
    (exT.METHOD_STEADY_LIGHT, {'LED Driver Range': exT.RANGE_1A, 'LED Steady Current': 500.0}, 'at most 200 mA'),
    (exT.METHOD_OPTICAL, {'AWG VISA Resource': ''}, 'VISA resource'),
])
def test_validate_refuses_unsafe_or_inconsistent_settings(method, over, fragment):
    errors = exT.validate(light(method, **over), Z)
    assert any(fragment in e for e in errors), errors


def test_validate_accepts_a_normal_optical_setting():
    assert exT.validate(light(exT.METHOD_OPTICAL, **{'LED Pulse Width': 0.001}), Z) == []


def test_i_mon_reference_always_records_aux_in_2():
    assert exT.records_imon(light(exT.METHOD_OPTICAL, **{'Record I_MON': 0}))
    assert not exT.records_imon(light(exT.METHOD_OPTICAL, **{'Record I_MON': 0,
                                                             'Optical Timing Reference': exT.REF_COMMANDED}))
    assert exT.records_imon(light(exT.METHOD_ELECTRICAL_OPTICAL, **{'Record I_MON': 1}))


def test_commanded_marker_marks_each_led_pulse():
    params = light(exT.METHOD_OPTICAL, **{'LED Pulse Delay': 0.002, 'LED Pulse Width': 0.001,
                                         'Commanded Timing Offset': 0.0005})
    t = np.arange(0, 1.5, 1e-4)
    marker = exT.commanded_marker(t, params, Z)
    rising = t[1:][np.diff(marker) > 0]
    assert rising == pytest.approx([0.0025, 0.5035, 1.0045], abs=1.5e-4)   # every 501 ms cycle
    assert marker.sum() * 1e-4 == pytest.approx(3 * 0.001, rel=0.15)


def test_commanded_marker_never_loses_a_pulse_shorter_than_a_sample():
    params = light(exT.METHOD_OPTICAL, **{'LED Pulse Width': 1e-6})
    t = np.arange(0, 1.6, SAMPLE_DT_S)
    assert np.count_nonzero(np.diff(exT.commanded_marker(t, params, Z)) > 0) >= 3


def test_run_timing_electrical_and_optical():
    assert exT.run_timing(Z) == pytest.approx((1.0, 500.0))
    optical = {**Z, **light(exT.METHOD_OPTICAL, **{'LED Pulse Width': 0.0002})}
    assert exT.run_timing(optical) == pytest.approx((0.2, 500.8))
    assert exT.run_timing({}) is None


def test_old_run_params_read_as_electrical():
    assert exT.method_of({'State Enable Time': 0.5}) == exT.METHOD_ELECTRICAL
    assert exT.method_of({'Excitation Method': 'nonsense'}) == exT.METHOD_ELECTRICAL


# --- 33220A driver ---------------------------------------------------------------

class FakeInstrument:
    def __init__(self, idn='Agilent Technologies,33220A,MY44012345,2.02-2.02-22-2', errors=()):
        self.writes = []
        self.idn = idn
        self.errors = list(errors)
        self.closed = False
        self.failWrites = False

    def write(self, cmd):
        if self.failWrites:
            raise IOError('VISA timeout')
        self.writes.append(cmd)

    def query(self, cmd):
        if cmd == '*IDN?':
            return self.idn + '\n'
        if cmd == 'SYST:ERR?':
            return self.errors.pop(0) if self.errors else '+0,"No error"\n'
        raise AssertionError(cmd)

    def close(self):
        self.closed = True


@pytest.fixture
def quiet_log(monkeypatch):
    log = []
    monkeypatch.setattr(dltsc, 'log_to_textbox', log.append)
    return log


def test_pulse_setup_sequence(quiet_log):
    inst = FakeInstrument()
    awg = awgC.awgDevice(instrument=inst)
    awg.configure_pulse(highV=0.4, widthS=1e-3, delayS=2e-3, cycleS=0.501)
    w = inst.writes
    assert w[0] == 'OUTP OFF'                                   # off before anything changes
    for cmd in ('FUNC PULS', 'VOLT:LOW 0', 'VOLT:HIGH 0.4', 'PULS:WIDT 0.001', 'BURS:MODE TRIG',
                'BURS:NCYC 1', 'TRIG:SOUR EXT', 'TRIG:SLOP POS', 'TRIG:DEL 0.002', 'BURS:STAT ON',
                'VOLT:LIM:HIGH 0.4', 'VOLT:LIM:STAT ON'):
        assert cmd in w, cmd
    assert w.index('VOLT:HIGH 0.4') < w.index('VOLT:LIM:STAT ON')   # limits after the levels
    period = float(next(c for c in w if c.startswith('PULS:PER')).split()[1])
    assert 1e-3 < period < 0.501 - 2e-3                        # inside the trigger interval
    assert 'OUTP ON' not in w and not awg.outputOn


@pytest.mark.parametrize('kwargs', [dict(highV=5.0, widthS=1e-3, delayS=0, cycleS=0.5),
                                    dict(highV=0.4, widthS=0.3, delayS=0.3, cycleS=0.5),
                                    dict(highV=0.4, widthS=1e-3, delayS=0, cycleS=None)])
def test_pulse_setup_refuses_out_of_range(kwargs):
    with pytest.raises(ValueError):
        awgC.awgDevice(instrument=FakeInstrument()).configure_pulse(**kwargs)


def test_dc_setup_and_output(quiet_log):
    inst = FakeInstrument()
    awg = awgC.awgDevice(instrument=inst)
    awg.apply_settings({'mode': 'dc', 'dcV': 0.2, 'limitHighV': 0.2})
    assert 'FUNC DC' in inst.writes and 'VOLT:OFFS 0.2' in inst.writes and 'BURS:STAT OFF' in inst.writes
    awg.output(True)
    assert inst.writes[-1] == 'OUTP ON' and awg.outputOn


def test_instrument_error_switches_off_and_raises(quiet_log):
    inst = FakeInstrument(errors=['-222,"Data out of range"'])
    awg = awgC.awgDevice(instrument=inst)
    with pytest.raises(RuntimeError, match='Data out of range'):
        awg.configure_dc(0.2)
    assert inst.writes[-1] == 'OUTP OFF'


def test_led_off_never_raises():
    inst = FakeInstrument()
    inst.failWrites = True
    assert awgC.awgDevice(instrument=inst).led_off() is False
    assert awgC.awgDevice().led_off() is False


@pytest.mark.parametrize('idn,ok', [('Agilent Technologies,33220A,MY1,2.02', True),
                                    ('Keysight Technologies,33500B,MY1,1.0', False)])
def test_connect_checks_the_model_and_starts_safe(monkeypatch, quiet_log, idn, ok):
    inst = FakeInstrument(idn=idn)
    import pyvisa
    monkeypatch.setattr(pyvisa, 'ResourceManager', lambda: SimpleNamespace(open_resource=lambda r: inst))
    awg = awgC.awgDevice()
    assert (awg.connect_device('USB0::FAKE::INSTR') == 0) is ok
    assert awg.state is ok
    if ok:
        assert inst.writes[:3] == ['OUTP OFF', '*CLS', 'OUTP:LOAD 50']
    else:
        assert inst.closed and inst.writes == []


# --- run sequence ------------------------------------------------------------------

class RecordingAwg:
    """Stands in for awgDevice in a run: records the order of calls."""
    def __init__(self, events):
        self.events = events
        self.state = True

    def apply_settings(self, settings, cycleS=None):
        self.events.append(('apply', settings['mode'], cycleS))

    def output(self, on):
        self.events.append(('output', on))

    def led_off(self):
        self.events.append(('off',))
        return True


class StepImpDev(ziC.ziDevice):
    def __init__(self, steps, events, fail=False):
        self.steps, self.events, self.fail = list(steps), events, fail
        self.device = SimpleNamespace(factory_reset=lambda: None)
        self.session = None

    def reload_params(self):
        pass

    def pull_data(self, plot=False, trigger=True, numPoints=None, numReps=None, recordAuxIn2=False):
        self.events.append(('pull', recordAuxIn2))
        if self.fail:
            raise IOError('DAQ failed')
        return self.steps.pop(0)


class FakeTempDev:
    tRamp, tStableDelay = 5, 0

    def __init__(self, grid):
        self.tempGrid = grid

    def go_to_temp(self, T, ramp, delay):
        pass

    def read_temp(self):
        return None


@pytest.fixture
def run_state(monkeypatch):
    monkeypatch.setattr(dltsc, 'log_to_textbox', lambda m: None)
    monkeypatch.setattr(dltsc, 'recast_param_type', lambda dev, name: 6 if 'Points' in name else 1)
    monkeypatch.setattr(dltsc, 'run_abortRequested', False)
    monkeypatch.setattr(dltsc, 'run_pauseRequested', False)


def optical_step(T, seed=0, imon_level=None):
    """An optical-fill acquisition: constant reverse bias in AuxInput1, the LED
    pulses (where make_step's electrical fill was) in AuxInput2 = I_MON."""
    step = make_step(T, n=2 ** 15, seed=seed, rb_ms=50.0)
    ledOn = step['AuxInput1'] > -2.5
    step['AuxInput2'] = np.where(ledOn, imon_level if imon_level is not None else 0.01, 0.0)
    step['AuxInput1'] = np.full_like(step['AuxInput1'], -5.0)
    return step


def make_optical_run(folder, grid, steps, events, params, fail=False):
    run = rdT.dltsRun()
    run.tempDevice = FakeTempDev(grid)
    run.impDevice = StepImpDev(steps, events, fail=fail)
    run.lightDevice = RecordingAwg(events)
    run.lightParams = params
    run.runOutputFileType = 'hdf5'
    run.dataFileNames = [os.path.join(folder, step_file_name(T, '.h5')) for T in grid]
    run.impDeviceParams = {**Z, 'State Enable Time': 0.05}
    run.tempDeviceParams, run.outputParams = {}, {'Data File Format': 'HDF5'}
    return run


def test_led_is_on_only_during_each_acquisition(run_state, tmp_path):
    events = []
    params = light(exT.METHOD_OPTICAL)
    run = make_optical_run(str(tmp_path), [25.0, 50.0], [optical_step(25.0), optical_step(50.0, 1)], events, params)
    assert run.run_experiment() == 'completed'
    assert events == [('apply', 'pulse', pytest.approx(0.051)), ('output', True), ('pull', True), ('off',)] * 2


def test_led_is_switched_off_when_the_acquisition_fails(run_state, tmp_path):
    events = []
    run = make_optical_run(str(tmp_path), [25.0], [], events, light(exT.METHOD_OPTICAL), fail=True)
    assert run.run_experiment() == 'error'
    assert events[-1] == ('off',) and ('output', True) in events


def test_electrical_run_never_switches_the_led_on(run_state, tmp_path):
    events = []
    run = make_optical_run(str(tmp_path), [25.0], [make_step(25.0, n=64)], events, light(exT.METHOD_ELECTRICAL))
    assert run.run_experiment() == 'completed'
    assert ('output', True) not in events and ('pull', False) in events


def test_optical_files_carry_imon_and_the_pulse_reference(run_state, tmp_path):
    events = []
    params = light(exT.METHOD_OPTICAL)          # 10 mA on the 100 mA range -> I_MON 0.1 V... at 10 V/A
    step = optical_step(25.0, imon_level=0.1)
    run = make_optical_run(str(tmp_path), [25.0], [step], events, params)
    assert run.run_experiment() == 'completed'
    rec = iaT.read_h5_record(run.dataFileNames[0])
    assert np.array_equal(rec['AuxInput2'], step['AuxInput2'])
    assert set(np.unique(np.round(rec['PulseReference'], 6))) == {0.0, 1.0}   # normalized to the set current


def test_imon_reference_without_imon_fails_the_step(run_state, tmp_path):
    events = []
    step = optical_step(25.0)
    del step['AuxInput2']
    run = make_optical_run(str(tmp_path), [25.0], [step], events, light(exT.METHOD_OPTICAL))
    assert run.run_experiment() == 'error'


def test_commanded_reference_is_written_without_imon(run_state, tmp_path):
    events = []
    step = optical_step(25.0)
    del step['AuxInput2']
    params = light(exT.METHOD_OPTICAL, **{'Optical Timing Reference': exT.REF_COMMANDED, 'Record I_MON': 0})
    run = make_optical_run(str(tmp_path), [25.0], [step], events, params)
    assert run.run_experiment() == 'completed'
    assert ('pull', False) in events
    assert iaT.read_h5_record(run.dataFileNames[0])['PulseReference'].max() == 1.0


def test_run_params_are_written_at_the_start_with_the_light_settings(tmp_path, monkeypatch):
    class Var:
        def __init__(self, v): self.v = v
        def get(self): return self.v

    class GridStage:
        tempGrid = np.array([25.0])
        def set_temp_grid(self): pass

    monkeypatch.setattr(dltsc, 'log_to_textbox', lambda m: None)
    monkeypatch.setattr(dltsc, 'impDev', object(), raising=False)
    monkeypatch.setattr(dltsc, 'tempDev', GridStage(), raising=False)
    monkeypatch.setattr(dltsc, 'lightDev', RecordingAwg([]), raising=False)
    monkeypatch.setattr(dltsc, 'z_params_vars', {k: Var(str(v)) for k, v in Z.items()}, raising=False)
    monkeypatch.setattr(dltsc, 'z_params_for_push', dict(Z), raising=False)
    monkeypatch.setattr(dltsc, 'z_params_effective', None, raising=False)
    monkeypatch.setattr(dltsc, 't_params_vars', {'Initial Temperature (C)': Var('25')}, raising=False)
    monkeypatch.setattr(dltsc, 'd_params_vars', {'Data File Format': Var('HDF5'), 'Data Root Folder': Var(str(tmp_path))},
                        raising=False)
    params = light(exT.METHOD_OPTICAL)
    monkeypatch.setattr(dltsc, 'l_params_vars', {}, raising=False)
    monkeypatch.setattr(dltsc, 'l_params_for_push', params, raising=False)

    run = rdT.dltsRun()
    assert run.init_experiment() == 0
    with open(run.paramsFileName) as f:
        saved = json.load(f)
    assert saved['Excitation Method'] == exT.METHOD_OPTICAL and saved['LED Pulse Width'] == 0.001
    # The MFIA keeps the optical override on every reload after a factory reset.
    assert dltsc.z_params_effective['Aux Output Scale'] == 0.0


def test_optical_run_refuses_to_start_without_the_awg(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr(dltsc, 'log_to_textbox', log.append)
    monkeypatch.setattr(dltsc, 'lightDev', None, raising=False)
    monkeypatch.setattr(dltsc, 'l_params_vars', {}, raising=False)
    monkeypatch.setattr(dltsc, 'l_params_for_push', light(exT.METHOD_OPTICAL), raising=False)
    run = rdT.dltsRun()
    run.impDeviceParams = dict(Z)
    assert run.check_light_source() > 0
    assert any('not connected' in m for m in log)


# --- analysis ----------------------------------------------------------------------

@pytest.fixture
def optical_and_electrical_folders(tmp_path):
    """The same acquisitions stored as an electrical run and as an optical-fill
    run (bias constant, the fill timing only in PulseReference)."""
    dev = ziC.ziDevice.__new__(ziC.ziDevice)
    temps = [-10.0, 25.0, 50.5]
    folders = {}
    for kind in ('electrical', 'optical'):
        folder = tmp_path / kind
        folder.mkdir()
        for i, T in enumerate(temps):
            step = make_step(T, n=2 ** 17, seed=i)
            if kind == 'optical':
                step['PulseReference'] = (step['AuxInput1'] > -2.5).astype(float)
                step['AuxInput1'] = np.full_like(step['AuxInput1'], -5.0)
            dev.writeDataH5(step, str(folder / step_file_name(T, '.h5')), setpoint_C=T)
        params = {'State Enable Time': 0.5, 'State Disable Time': 0.001}
        if kind == 'optical':
            params.update({'Excitation Method': exT.METHOD_OPTICAL, 'LED Pulse Width': 0.001})
        (folder / 'runParams.txt').write_text(json.dumps(params))
        folders[kind] = str(folder)
    return folders, temps


def extract(folder):
    registry = ldT._compute_legacy_dataset(folder, [])
    return ldT._compute_legacy_transients(sorted(registry), 500.0, 450.0, registry, SAMPLE_DT_S)


def test_qualitative_extraction_finds_optical_fill_transients(optical_and_electrical_folders):
    folders, temps = optical_and_electrical_folders
    electrical, eErrors = extract(folders['electrical'])
    optical, oErrors = extract(folders['optical'])
    assert eErrors == [] and oErrors == []
    assert sorted(optical) == temps
    for T in temps:
        assert np.array_equal(optical[T]['avg_cap_pf'], electrical[T]['avg_cap_pf'])


def test_optical_run_timing_comes_from_the_led(optical_and_electrical_folders):
    folders, _ = optical_and_electrical_folders
    assert ldT._legacy_run_timing(folders['optical']) == pytest.approx((1.0, 500.0))


def test_constant_bias_without_a_reference_reports_no_pulses(optical_and_electrical_folders, tmp_path):
    folders, temps = optical_and_electrical_folders
    with h5py.File(os.path.join(folders['optical'], step_file_name(temps[0], '.h5')), 'a') as f:
        del f['PulseReference']
    optical, errors = extract(folders['optical'])
    assert temps[0] not in optical and errors


def test_impd_clustering_uses_the_pulse_reference(optical_and_electrical_folders):
    folders, temps = optical_and_electrical_folders
    labels = {}
    for kind, folder in folders.items():
        impd = iaT.impdData(fName=[os.path.join(folder, step_file_name(T, '.h5')) for T in temps])
        assert impd.read_data() == 0
        impd.cleanup_data()
        means, stds, labels[kind] = impd.find_data_levels_scikit(dataType='excitation', model='hybrid')
        assert np.all(np.isfinite(means))
    # Same fill / reverse split: label 0 = fill (bias high / LED on).
    assert np.array_equal(labels['optical'], labels['electrical'])


def test_detailed_analysis_marks_optical_fill(optical_and_electrical_folders):
    folders, temps = optical_and_electrical_folders
    registry = ldT._compute_legacy_dataset(folders['optical'], [])
    loadInfo = {'optical_fill': False}
    out = daT._read_step_records(folders['optical'], temps, registry, [], loadInfo)
    assert loadInfo['optical_fill'] is True
    assert all(info is None for _, info in out.values())

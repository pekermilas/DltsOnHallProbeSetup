"""dltsRun writing HDF5 per temperature step, including Redo and Remove & Retake,
driven through the real _run_single_step() / run_experiment() with fake devices."""
import os
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

import dltsConfig as dltsc
import runDlts_Tools as rdT
import zurichInstruments_Control as ziC
import impedanceAnalysis_Tools as iaT
from conftest import make_step, step_file_name


class FakeTempDev:
    def __init__(self, tempGrid, readings=None):
        self.tempGrid = tempGrid
        self.tRamp = 5
        self.tStableDelay = 0
        self.readings = list(readings or [])

    def go_to_temp(self, T, ramp, delay):
        pass

    def read_temp(self):
        if not self.readings:
            raise IOError('controller not responding')
        return self.readings.pop(0)


class FakeImpDev(ziC.ziDevice):
    """Real file writers, fake acquisition: each pull returns the next queued step."""
    def __init__(self, steps):
        self.steps = list(steps)
        self.device = SimpleNamespace(factory_reset=lambda: None)
        self.onPull = None

    def reload_params(self):
        pass

    def pull_data(self, plot=False, trigger=True, numPoints=None, numReps=None):
        if self.onPull is not None:
            self.onPull()
        return self.steps.pop(0)


@pytest.fixture
def gui_state(monkeypatch):
    """The dltsConfig globals _run_single_step() reads, without a GUI."""
    log = []
    monkeypatch.setattr(dltsc, 'log_to_textbox', log.append)
    monkeypatch.setattr(dltsc, 'recast_param_type', lambda dev, name: 6 if 'Points' in name else 1)
    monkeypatch.setattr(dltsc, 'run_abortRequested', False)
    monkeypatch.setattr(dltsc, 'run_pauseRequested', False)
    return log


def make_run(folder, tempGrid, steps, readings=None):
    run = rdT.dltsRun()
    run.tempDevice = FakeTempDev(tempGrid, readings)
    run.impDevice = FakeImpDev(steps)
    run.runOutputFileType = 'hdf5'
    run.dataFileNames = [os.path.join(folder, step_file_name(T, '.h5')) for T in tempGrid]
    run.impDeviceParams = {'Frequency (Hz)': 1e6}
    run.tempDeviceParams = {'Ramp Rate (C/min)': 5}
    run.outputParams = {'Data File Format': 'HDF5'}
    return run


def test_full_run_writes_one_file_per_step(gui_state, tmp_path):
    grid = [-10.0, 25.0, 50.5]
    steps = [make_step(T, n=64, seed=i) for i, T in enumerate(grid)]
    run = make_run(str(tmp_path), grid, steps, readings=[-10.1, -9.9, 24.9, 25.1, 50.4, 50.6])

    assert run.run_experiment() == 'completed'

    assert sorted(os.listdir(tmp_path)) == sorted(step_file_name(T, '.h5') for T in grid)
    for i, T in enumerate(grid):
        with h5py.File(run.dataFileNames[i], 'r') as f:
            assert f.attrs['setpoint_C'] == T
            # Mean of the readings taken before and after the acquisition.
            assert f.attrs['stage_temperature_C'] == pytest.approx(T)
            assert '"Data File Format": "HDF5"' in f.attrs['run_params']
        assert np.array_equal(iaT.read_h5_record(run.dataFileNames[i])['ImpedanceIm'],
                              steps[i]['ImpedanceIm'])
    assert all(status == 'done' for status in run.stepStatus.values())


def test_step_succeeds_when_stage_temperature_cannot_be_read(gui_state, tmp_path):
    run = make_run(str(tmp_path), [25.0], [make_step(25.0, n=64)], readings=[])
    assert run.run_experiment() == 'completed'
    with h5py.File(run.dataFileNames[0], 'r') as f:
        assert np.isnan(f.attrs['stage_temperature_C'])


def test_step_uses_single_stage_reading_if_other_fails(gui_state, tmp_path):
    run = make_run(str(tmp_path), [25.0], [make_step(25.0, n=64)], readings=[25.3])
    assert run.run_experiment() == 'completed'
    with h5py.File(run.dataFileNames[0], 'r') as f:
        assert f.attrs['stage_temperature_C'] == 25.3


def _read_cap(path):
    return iaT.read_h5_record(path)['ImpedanceIm']


@pytest.mark.parametrize('deleteFirst', [False, True], ids=['redo', 'remove-and-retake'])
def test_redo_and_retake_replace_only_the_selected_steps(gui_state, tmp_path, deleteFirst):
    grid = [25.0, 50.0, 75.0]
    first = [make_step(T, n=64, seed=i) for i, T in enumerate(grid)]
    retaken = [make_step(T, n=128, seed=10 + i) for i, T in enumerate(grid)]
    run = make_run(str(tmp_path), grid, first)
    assert run.run_experiment() == 'completed'

    # Out of order on purpose: steps are re-run in ascending temperature order.
    run.impDevice.steps = [retaken[0], retaken[2]]
    assert run.run_experiment(indices=[2, 0], deleteFirst=deleteFirst) == 'completed'

    assert np.array_equal(_read_cap(run.dataFileNames[0]), retaken[0]['ImpedanceIm'])
    assert np.array_equal(_read_cap(run.dataFileNames[1]), first[1]['ImpedanceIm'])
    assert np.array_equal(_read_cap(run.dataFileNames[2]), retaken[2]['ImpedanceIm'])
    assert sorted(os.listdir(tmp_path)) == sorted(step_file_name(T, '.h5') for T in grid)
    removed = [m for m in gui_state if m.startswith('Removed existing data file')]
    assert len(removed) == (2 if deleteFirst else 0)
    # A redo doesn't move the point the main sequence resumes from.
    assert run.currentStepIndex == len(grid)


def test_gui_closed_during_acquisition_writes_nothing(gui_state, tmp_path):
    run = make_run(str(tmp_path), [25.0], [make_step(25.0, n=64)])
    run.impDevice.onPull = lambda: setattr(dltsc, 'run_abortRequested', True)

    assert run.run_experiment() == 'aborted'
    assert os.listdir(tmp_path) == []
    assert run.stepStatus[0] == 'aborted'


def test_gui_closed_during_retake_leaves_step_missing(gui_state, tmp_path):
    """Remove & Retake deletes the old file first, so a close part-way through
    loses that step (and only that step) rather than leaving stale data."""
    grid = [25.0, 50.0]
    run = make_run(str(tmp_path), grid, [make_step(T, n=64, seed=i) for i, T in enumerate(grid)])
    assert run.run_experiment() == 'completed'

    run.impDevice.steps = [make_step(25.0, n=64, seed=5)]
    run.impDevice.onPull = lambda: setattr(dltsc, 'run_abortRequested', True)
    assert run.run_experiment(indices=[0], deleteFirst=True) == 'aborted'

    assert os.listdir(tmp_path) == [step_file_name(50.0, '.h5')]


def test_write_failure_marks_step_failed_and_keeps_previous_file(gui_state, tmp_path):
    grid = [25.0]
    first = make_step(25.0, n=64)
    run = make_run(str(tmp_path), grid, [first])
    assert run.run_experiment() == 'completed'

    bad = make_step(25.0, n=64)
    bad['AuxInput1'] = ['not', 'a', 'number']
    run.impDevice.steps = [bad]
    assert run.run_experiment(indices=[0]) == 'error'

    assert run.stepStatus[0] == 'failed'
    assert np.array_equal(_read_cap(run.dataFileNames[0]), first['ImpedanceIm'])

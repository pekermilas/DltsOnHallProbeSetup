"""dltsRun.init_experiment()'s Data Root Folder check and run-folder paths, and
mK2000B's serial timeout."""
import os
import threading

import numpy as np
import pytest

import dltsConfig as dltsc
import instecTempStage_Control as tsC
import runDlts_Tools as rdT


class Var:
    def __init__(self, v): self.v = v
    def get(self): return self.v


class GridStage:
    def __init__(self):
        self.tempGrid = np.array([-10.0, 25.0])

    def set_temp_grid(self):
        pass


@pytest.fixture
def gui(monkeypatch):
    log = []
    monkeypatch.setattr(dltsc, 'log_to_textbox', log.append)
    monkeypatch.setattr(dltsc, 'impDev', object(), raising=False)
    monkeypatch.setattr(dltsc, 'tempDev', GridStage(), raising=False)
    monkeypatch.setattr(dltsc, 'z_params_vars', {'Oscillation Frequency': Var('501000')}, raising=False)
    monkeypatch.setattr(dltsc, 't_params_vars', {'Initial Temperature (C)': Var('25')}, raising=False)

    def set_root(root):
        monkeypatch.setattr(dltsc, 'd_params_vars', {'Data File Format': Var('HDF5'), 'Data Root Folder': Var(root)},
                            raising=False)
    return log, set_root


@pytest.mark.parametrize('root', ['', '   ', 'DATA\\DLTS'])
def test_empty_or_relative_root_refuses_to_start(gui, root, tmp_path, monkeypatch):
    log, set_root = gui
    set_root(root)
    monkeypatch.chdir(tmp_path)
    run = rdT.dltsRun()

    assert run.init_experiment() == -1
    assert run.dataFileNames is None
    assert os.listdir(tmp_path) == []
    assert any('Data Root Folder' in m for m in log)


def test_run_folder_paths(gui, tmp_path):
    log, set_root = gui
    set_root(str(tmp_path))
    run = rdT.dltsRun()

    assert run.init_experiment() == 0
    day, = os.listdir(tmp_path)
    clock, = os.listdir(tmp_path / day)
    folder = os.path.join(str(tmp_path), day, clock)
    assert len(day) == 6 and len(clock) == 6
    assert run.dataFolder == folder
    assert run.dataFileNames == [os.path.join(folder, 'n10p0.h5'), os.path.join(folder, 'p25p0.h5')]
    assert run.paramsFileName == os.path.join(folder, 'runParams.txt')
    assert '\\\\' not in folder[2:]
    assert dltsc.run_dataFileNames == run.dataFileNames


class FakeSerial:
    """Stands in for serial.Serial: replies come from a list; b'' = timeout."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.writes, self.resets = [], 0

    def reset_input_buffer(self):
        self.resets += 1

    def write(self, data):
        self.writes.append(data)

    def readline(self):
        return self.replies.pop(0) if self.replies else b''


def stage_with(replies):
    stage = tsC.mK2000B()
    stage.dev, stage.state = FakeSerial(replies), True
    return stage


def test_read_temp_parses_a_reply():
    stage = stage_with([b'25.0632\r\n'])
    assert stage.read_temp() == 25.0632
    assert stage.dev.resets == 1


def test_read_temp_asks_again_after_a_missed_reply():
    stage = stage_with([b'', b'30.01\r\n'])
    assert stage.read_temp() == 30.01
    assert len(stage.dev.writes) == 2


def test_read_temp_raises_when_the_controller_stays_silent():
    stage = stage_with([])
    with pytest.raises(TimeoutError, match='did not answer'):
        stage.read_temp()
    assert len(stage.dev.writes) == tsC.READ_RETRIES + 1


def test_read_temp_timeout_releases_the_lock():
    stage = stage_with([])
    with pytest.raises(TimeoutError):
        stage.read_temp()
    got = []

    def other_thread():
        # A second thread (e.g. the close dialog) must be able to talk to the controller.
        if stage._ioLock.acquire(timeout=1):
            got.append(True)
            stage._ioLock.release()
    t = threading.Thread(target=other_thread)
    t.start(); t.join()
    assert got == [True]


def test_go_to_temp_fails_instead_of_hanging():
    stage = stage_with([b'20.0\r\n'])            # one reading, then silence
    with pytest.raises(TimeoutError):
        stage.go_to_temp(30.0)


def test_connect_sets_serial_timeouts(monkeypatch):
    opened = []

    class PortStub:
        def __init__(self):
            self.port = self.timeout = self.write_timeout = None
        def open(self):
            opened.append((self.port, self.timeout, self.write_timeout))

    monkeypatch.setattr(tsC.serial, 'Serial', PortStub)
    monkeypatch.setattr(tsC.time, 'sleep', lambda s: None)
    stage = tsC.mK2000B(port='COM9')
    stage.connect_temp_controller()
    assert opened == [('COM9', tsC.SERIAL_TIMEOUT_S, tsC.SERIAL_TIMEOUT_S)] and stage.state

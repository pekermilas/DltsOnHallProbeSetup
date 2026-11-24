"""mK2000B driver fixes: go_to_temp honours its arguments and refuses to run
unconnected, waits end promptly on abort(), disconnect always releases the
port, connect reports failures, and the Input Parameters tab reconnects
without leaving the old port open."""
import threading
import time

import pytest

import dltsConfig as dltsc
import instecTempStage_Control as tsC


class FakeSerial:
    """Stands in for an open serial.Serial: replies come from a list (b'' = timeout)."""
    def __init__(self, replies=(), failWrite=False):
        self.replies = list(replies)
        self.writes = []
        self.failWrite = failWrite
        self.is_open = True

    def reset_input_buffer(self):
        pass

    def write(self, data):
        if self.failWrite:
            raise OSError('write failed')
        self.writes.append(data)

    def readline(self):
        return self.replies.pop(0) if self.replies else b''

    def close(self):
        self.is_open = False


def stage_with(replies=(), **kw):
    stage = tsC.mK2000B()
    stage.dev, stage.state = FakeSerial(replies, **kw), True
    return stage


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(tsC.time, 'sleep', lambda s: None)
    monkeypatch.setattr(tsC, 'WAIT_SLICE_S', 0.0)


def test_go_to_temp_uses_its_ramp_argument(no_sleep):
    stage = stage_with([b'30.0\r\n'])
    stage.tRamp = 5
    assert stage.go_to_temp(30.0, 2.5, 0) == 0
    assert stage.dev.writes[0] == b'TEMPerature:RAMP 30.0,2.5\n'


def test_go_to_temp_defaults_to_the_stage_settings(no_sleep):
    stage = stage_with([b'30.0\r\n'])
    stage.tRamp = 7.0
    assert stage.go_to_temp(30.0) == 0
    assert stage.dev.writes[0] == b'TEMPerature:RAMP 30.0,7.0\n'


def test_go_to_temp_waits_its_delay_argument(monkeypatch):
    waited = []
    stage = stage_with([b'30.0\r\n'])
    stage.tStableDelay = 999
    monkeypatch.setattr(stage, '_wait', lambda s: waited.append(s) or False)
    stage.go_to_temp(30.0, 5, 12)
    assert waited[-1] == 12


def test_go_to_temp_refuses_when_not_connected():
    with pytest.raises(RuntimeError, match='not connected'):
        tsC.mK2000B().go_to_temp(30.0)
    stage = stage_with()
    stage.state = False
    with pytest.raises(RuntimeError, match='not connected'):
        stage.go_to_temp(30.0)


def test_abort_ends_the_stability_delay_promptly():
    stage = stage_with([b'30.0\r\n'])
    threading.Timer(0.3, stage.abort).start()
    t0 = time.monotonic()
    assert stage.go_to_temp(30.0, 5, 60) == -1
    assert time.monotonic() - t0 < 5


def test_reset_abort_lets_the_stage_move_again(no_sleep):
    stage = stage_with([b'30.0\r\n'])
    stage.abort()
    assert stage.go_to_temp(30.0, 5, 0) == -1
    stage.reset_abort()
    assert stage.go_to_temp(30.0, 5, 0) == 0


def test_disconnect_sends_stop_and_releases_the_port(no_sleep):
    stage = stage_with()
    ser = stage.dev
    assert stage.disconnect_temp_controller() == 0
    assert ser.writes == [b':TEMPerature:STOP\n'] and not ser.is_open
    assert stage.dev is None and not stage.state


def test_disconnect_closes_the_port_even_if_stop_fails(no_sleep):
    stage = stage_with(failWrite=True)
    ser = stage.dev
    assert stage.disconnect_temp_controller() == -1
    assert not ser.is_open
    assert stage.dev is None and not stage.state
    assert 'STOP not sent' in stage.lastError
    # The lock was released too.
    assert stage._ioLock.acquire(timeout=1)
    stage._ioLock.release()


def test_disconnect_without_stop_sends_nothing(no_sleep):
    stage = stage_with()
    ser = stage.dev
    stage.disconnect_temp_controller(stopControl=False)
    assert ser.writes == [] and not ser.is_open


def test_connect_failure_returns_minus_one_with_the_reason(monkeypatch):
    class BusyPort:
        def __init__(self):
            self.port = self.timeout = self.write_timeout = None
            self.is_open = False
        def open(self):
            raise OSError('Access is denied.')

    monkeypatch.setattr(tsC.serial, 'Serial', BusyPort)
    stage = tsC.mK2000B(port='COM9')
    assert stage.connect_temp_controller() == -1
    assert not stage.state and stage.dev is None
    assert 'COM9' in stage.lastError and 'Access is denied' in stage.lastError


def test_connect_success_returns_zero(monkeypatch):
    class PortStub:
        def __init__(self):
            self.port = self.timeout = self.write_timeout = None
        def open(self):
            pass

    monkeypatch.setattr(tsC.serial, 'Serial', PortStub)
    monkeypatch.setattr(tsC.time, 'sleep', lambda s: None)
    stage = tsC.mK2000B(port='COM9')
    assert stage.connect_temp_controller() == 0 and stage.state and stage.lastError == ''


def test_query_returns_the_reply_line():
    stage = stage_with([b'24.5\r\n'])
    assert stage.query(':TEMPerature:CTEMperature?') == '24.5'
    assert stage.dev.writes == [b':TEMPerature:CTEMperature?\n']


def test_write_accepts_str_and_reports_unconnected():
    stage = stage_with()
    assert stage.write(':TEMPerature:STOP\n') == 0
    assert stage.dev.writes == [b':TEMPerature:STOP\n']
    assert tsC.mK2000B().write(b'x') == -1


def test_measure_proxy_temp_refuses_when_not_connected():
    with pytest.raises(RuntimeError, match='not connected'):
        tsC.mK2000B().measure_proxy_temp(30.0)


def test_set_temp_grid_needs_no_connection():
    stage = tsC.mK2000B()
    stage.load_params({'Initial Temperature (C)': 25, 'Final Temperature (C)': 35,
                       'Temperature Step (C)': 5})
    stage.set_temp_grid()
    assert list(stage.tempGrid) == [25.0, 30.0, 35.0] and stage.numTemps == 3


# ---- Input Parameters tab: connect / reconnect ------------------------------

class FakeStage:
    """mK2000B stand-in that records connects and disconnects."""
    made = []

    def __init__(self, port=None):
        self.port = port or tsC.DEFAULT_PORT
        self.state = False
        self.lastError = ''
        self.stops = []
        FakeStage.made.append(self)

    def connect_temp_controller(self):
        if self.port == 'COM99':
            self.lastError = 'could not open COM99: busy'
            return -1
        self.state = True
        return 0

    def disconnect_temp_controller(self, stopControl=True, lockTimeout=5.0):
        self.stops.append(stopControl)
        self.state = False
        return 0


class PortVar:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


@pytest.fixture
def tab(monkeypatch):
    import runParamsTab as rpT
    logs = []
    FakeStage.made = []
    monkeypatch.setattr(rpT.tsC, 'mK2000B', FakeStage)
    monkeypatch.setattr(dltsc, 'log_to_textbox', logs.append)
    monkeypatch.setattr(dltsc, 'tempDev', None, raising=False)
    monkeypatch.setattr(dltsc, 'run_busy', False, raising=False)
    monkeypatch.setattr(dltsc, 't_portVar', PortVar('COM7'), raising=False)
    return rpT, logs


def test_connect_uses_the_serial_port_box(tab):
    rpT, logs = tab
    assert rpT.connect_temperature_controller() == 0
    assert dltsc.tempDev.port == 'COM7' and dltsc.tempDev.state


def test_reconnect_on_the_same_port_keeps_the_connection(tab):
    rpT, logs = tab
    rpT.connect_temperature_controller()
    first = dltsc.tempDev
    assert rpT.connect_temperature_controller() == 0
    assert dltsc.tempDev is first and len(FakeStage.made) == 1


def test_switching_port_closes_the_old_one_without_stop(tab):
    rpT, logs = tab
    rpT.connect_temperature_controller()
    first = dltsc.tempDev
    dltsc.t_portVar = PortVar('COM3')
    assert rpT.connect_temperature_controller() == 0
    assert first.stops == [False] and not first.state
    assert dltsc.tempDev.port == 'COM3'


def test_switching_port_is_refused_during_a_run(tab):
    rpT, logs = tab
    rpT.connect_temperature_controller()
    first = dltsc.tempDev
    dltsc.run_busy = True
    dltsc.t_portVar = PortVar('COM3')
    assert rpT.connect_temperature_controller() == -1
    assert dltsc.tempDev is first and first.state and first.stops == []


def test_failed_connect_is_reported_and_leaves_no_device(tab):
    rpT, logs = tab
    dltsc.t_portVar = PortVar('COM99')
    assert rpT.connect_temperature_controller() == -1
    assert dltsc.tempDev is None
    assert any('NOT connected' in m and 'COM99' in m for m in logs)

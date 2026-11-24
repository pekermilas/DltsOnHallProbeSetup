"""HDS-4 Hall/DLTS selector driver (StandardFirmata + pyfirmata2, the same
structure as HallProbe_Software/switchBox.py), against a fake pyfirmata2 board."""
import pytest

import hallDltsSelector_Control as hdsC


class FakePin:
    def __init__(self, log, n):
        self.log, self.n = log, n
        self.value = None
        self.callback = None
        self.reporting = False

    def write(self, value):
        self.value = value
        self.log.append((self.n, value))

    def register_callback(self, cb):
        self.callback = cb

    def enable_reporting(self):
        self.reporting = True


class FakeSerial:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeBoard:
    """Stands in for pyfirmata2.Arduino: StandardFirmata boots with every pin LOW."""
    made = []

    def __init__(self, port):
        self.port = port
        self.writes = []
        self.digital = [FakePin(self.writes, n) for n in range(20)]
        self.analog = [FakePin(self.writes, 100 + n) for n in range(6)]
        self.sp = FakeSerial()
        self.sampling = None
        self.exited = False
        FakeBoard.made.append(self)

    def samplingOn(self, ms):
        self.sampling = ms

    def exit(self):
        self.exited = True


@pytest.fixture
def sel():
    s = hdsC.HallDltsSelector(boardFactory=FakeBoard)
    assert s.connect_arduino('COM8') == 0
    return s


def levels(s):
    return {c: s.board.digital[p].value for c, p in s.CONTROL_PINS.items()}


def test_connect_puts_every_contact_on_hall(sel):
    assert sel.connected and sel.board.port == 'COM8'
    assert levels(sel) == dict.fromkeys(hdsC.CONTROL_PINS, 0)
    assert sel.get_mode() == 'hall'
    assert sel.board.digital[10].value == 1 and sel.board.digital[11].value == 0   # HALL LED on


def test_connect_starts_power_sensing(sel):
    a0 = sel.board.analog[0]
    assert a0.reporting and a0.callback is not None and sel.board.sampling == 100
    assert sel.relay_power() is None              # no sample yet
    a0.callback(0.9)
    assert sel.relay_power() is True
    a0.callback(0.0)
    assert sel.relay_power() is False


def test_configurations_table():
    s = hdsC.HallDltsSelector(boardFactory=FakeBoard)
    assert s.configurations('hall') == dict.fromkeys(hdsC.CONTROL_PINS, 'A')
    assert s.configurations('DLTS') == dict.fromkeys(hdsC.CONTROL_PINS, 'B')
    with pytest.raises(ValueError):
        s.configurations('open')


def test_set_pins_maps_positions_to_levels():
    s = hdsC.HallDltsSelector(boardFactory=FakeBoard)
    pinsDict, pinMap = s.set_pins({'P1': 'B', 'P3': 'b'})
    assert pinsDict == {2: 1, 3: 0, 4: 1, 5: 0}
    assert pinMap == {'P1': 'B', 'P2': 'A', 'P3': 'B', 'P4': 'A'}
    with pytest.raises(ValueError):
        s.set_pins({'P5': 'A'})
    with pytest.raises(ValueError):
        s.set_pins({'P1': 'OPEN'})


def test_modes_and_single_channels(sel):
    sel.set_mode('dlts')
    assert levels(sel) == dict.fromkeys(hdsC.CONTROL_PINS, 1) and sel.get_mode() == 'dlts'
    assert sel.board.digital[10].value == 0 and sel.board.digital[11].value == 1
    sel.set_channel(4, 'A')
    assert sel.get_state()['P4'] == 'A' and sel.get_mode() == 'mixed'
    assert sel.board.digital[5].value == 0
    sel.set_channel('P4', 'B')
    assert sel.get_mode() == 'dlts'


def test_bad_arguments_write_nothing(sel):
    before = len(sel.board.writes)
    with pytest.raises(ValueError):
        sel.set_mode('both')
    with pytest.raises(ValueError):
        sel.set_channel(5, 'A')
    with pytest.raises(ValueError):
        sel.set_channel(1, 'C')
    assert len(sel.board.writes) == before


def test_require_mode(sel):
    assert 'HALL mode, not DLTS' in sel.require_mode('dlts')
    assert sel.require_mode('hall') is None
    sel.set_mode('dlts')
    assert sel.require_mode('dlts') is None       # power unknown: not blocked
    sel.board.analog[0].callback(0.0)             # RELAY POWER off
    assert 'RELAY POWER' in sel.require_mode('dlts')
    sel.board.analog[0].callback(1.0)
    assert sel.require_mode('dlts') is None


def test_not_connected():
    s = hdsC.HallDltsSelector(boardFactory=FakeBoard)
    with pytest.raises(RuntimeError, match='not connected'):
        s.set_mode('dlts')
    assert 'not connected' in s.require_mode('dlts')
    assert s.connect_arduino('') == -1


def test_disconnect_leaves_routing_unless_asked(sel):
    sel.set_mode('dlts')
    board = sel.board
    sel.disconn_arduino()
    assert board.exited and board.sp.closed and not sel.connected
    assert board.digital[2].value == 1             # left on DLTS

    s = hdsC.HallDltsSelector(boardFactory=FakeBoard)
    s.connect_arduino('COM8')
    s.set_mode('dlts')
    board = s.board
    s.disconn_arduino(to_hall=True)
    assert board.digital[2].value == 0 and not s.connected


def test_routing_table_names_the_cabling(sel):
    sel.set_channel(1, 'B')
    table = sel.routing_table()
    assert 'P1' in table and 'HCUR' in table and 'switch box' in table


def test_module_wrappers_use_the_singleton(monkeypatch):
    monkeypatch.setattr(hdsC, 'selector', hdsC.HallDltsSelector(boardFactory=FakeBoard))
    assert hdsC.connect_arduino('COM8') == 0
    hdsC.set_mode('dlts')
    assert hdsC.get_mode() == 'dlts' and hdsC.require_mode('dlts') is None
    hdsC.disconn_arduino(to_hall=True)
    assert hdsC.get_state() == dict.fromkeys(hdsC.CONTROL_PINS, 'A')

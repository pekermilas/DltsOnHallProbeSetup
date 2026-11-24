"""HDS-4 Hall/DLTS selector driver, against a simulator that follows the
firmware's command table (hardware/hallDltsSelector/README.md)."""
import pytest

import hallDltsSelector_Control as hdsC


class SimulatedSelector:
    """Serial-like stand-in for the HDS-4 firmware."""

    def __init__(self, idn='HDS4,HallDltsSelector,0001,1.0', power=True):
        self.idn = idn
        self.power = power
        self.pos = ['OPEN'] * 4
        self.reply = b''
        self.log = []
        self.closed = False
        self.history = []          # every relay state applied, to check break-before-make

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True

    def readline(self):
        r, self.reply = self.reply, b''
        return r

    def _apply(self, target):
        if target != self.pos:
            # break: every changed channel open first, then the new positions
            self.history.append([p if p == t else 'OPEN' for p, t in zip(self.pos, target)])
            self.pos = list(target)
            self.history.append(list(target))

    def write(self, data):
        cmd = data.decode().strip().upper()
        self.log.append(cmd)
        parts = cmd.split()
        out = 'ERR unknown command'
        if cmd == '*IDN?':
            out = self.idn
        elif cmd == 'MODE?':
            out = ('HALL' if self.pos == ['A'] * 4 else 'DLTS' if self.pos == ['B'] * 4
                   else 'OPEN' if self.pos == ['OPEN'] * 4 else 'MIXED')
        elif parts[:1] == ['MODE'] and len(parts) == 2:
            p = {'HALL': 'A', 'DLTS': 'B', 'OPEN': 'OPEN'}.get(parts[1])
            if p is None:
                out = 'ERR mode must be HALL, DLTS or OPEN'
            else:
                self._apply([p] * 4)
                out = 'OK'
        elif parts[:1] == ['CH'] and len(parts) == 3:
            if parts[1] not in '1234' or len(parts[1]) != 1:
                out = 'ERR channel must be 1-4'
            elif parts[2] not in ('A', 'B', 'OPEN'):
                out = 'ERR position must be A, B or OPEN'
            else:
                target = list(self.pos)
                target[int(parts[1]) - 1] = parts[2]
                self._apply(target)
                out = 'OK'
        elif cmd == 'STATE?':
            out = ','.join(f'P{i + 1}={p}' for i, p in enumerate(self.pos))
        elif cmd == 'PWR?':
            out = 'ON' if self.power else 'OFF'
        self.reply = (out + '\r\n').encode()


def connected(**kw):
    sim = SimulatedSelector(**kw)
    sel = hdsC.selectorDevice(port='COM8', instrument=sim)
    assert sel.connect_device() == 0
    return sel, sim


def test_connect_checks_the_identity():
    sel, sim = connected()
    assert 'HDS4' in sel.idn and sel.state


def test_connect_refuses_another_device():
    sim = SimulatedSelector(idn='Arduino Uno')
    sel = hdsC.selectorDevice(port='COM6', instrument=sim)
    assert sel.connect_device() == -1
    assert 'not an HDS-4' in sel.lastError and sim.closed and not sel.state


def test_connect_reports_a_port_that_will_not_open(monkeypatch):
    def refuse(*a, **k):
        raise OSError('Access is denied.')
    monkeypatch.setattr(hdsC.serial, 'Serial', refuse)
    sel = hdsC.selectorDevice()
    assert sel.connect_device('COM8') == -1
    assert 'COM8' in sel.lastError and 'Access is denied' in sel.lastError


def test_power_up_state_is_open():
    sel, sim = connected()
    assert sel.get_mode() == 'open'
    assert sel.get_state() == {'P1': 'OPEN', 'P2': 'OPEN', 'P3': 'OPEN', 'P4': 'OPEN'}


def test_modes_route_all_channels():
    sel, sim = connected()
    sel.set_mode('hall')
    assert sel.get_state() == dict.fromkeys(hdsC.CHANNELS, 'A') and sel.get_mode() == 'hall'
    sel.set_mode('DLTS')
    assert sel.get_state() == dict.fromkeys(hdsC.CHANNELS, 'B') and sel.get_mode() == 'dlts'


def test_switching_is_break_before_make():
    sel, sim = connected()
    sel.set_mode('hall')
    sim.history.clear()
    sel.set_mode('dlts')
    # The intermediate state has every channel open: A and B never overlap.
    assert sim.history[0] == ['OPEN'] * 4 and sim.history[-1] == ['B'] * 4


def test_single_channel_and_mixed_mode():
    sel, sim = connected()
    sel.set_mode('dlts')
    sel.set_channel('P4', 'open')
    assert sel.get_state()['P4'] == 'OPEN' and sel.get_mode() == 'mixed'
    sel.set_channel(4, 'B')
    assert sel.get_mode() == 'dlts'


def test_bad_arguments_are_refused_before_sending():
    sel, sim = connected()
    sent = len(sim.log)
    with pytest.raises(ValueError):
        sel.set_mode('both')
    with pytest.raises(ValueError):
        sel.set_channel(5, 'A')
    with pytest.raises(ValueError):
        sel.set_channel(1, 'C')
    assert len(sim.log) == sent


def test_firmware_errors_raise():
    sel, sim = connected()
    with pytest.raises(hdsC.SelectorError, match='ERR'):
        sel.query('CH 9 A')


def test_silence_raises():
    sel, sim = connected()
    sim.write = lambda data: None          # box stops answering
    with pytest.raises(hdsC.SelectorError, match='no reply'):
        sel.get_mode()


def test_require_mode_reports_why_a_run_should_not_start():
    sel, sim = connected()
    assert 'OPEN mode, not DLTS' in sel.require_mode('dlts')
    sel.set_mode('dlts')
    assert sel.require_mode('dlts') is None
    sim.power = False
    assert 'RELAY POWER' in sel.require_mode('dlts')


def test_disconnect_leaves_routing_unless_asked():
    sel, sim = connected()
    sel.set_mode('hall')
    sel.disconnect_device()
    assert sim.pos == ['A'] * 4 and sim.closed and not sel.state

    sel, sim = connected()
    sel.set_mode('hall')
    sel.disconnect_device(open_all=True)
    assert sim.pos == ['OPEN'] * 4 and sim.closed


def test_not_connected_raises():
    with pytest.raises(hdsC.SelectorError, match='not connected'):
        hdsC.selectorDevice().get_mode()

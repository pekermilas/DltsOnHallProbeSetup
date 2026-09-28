"""Standalone (no-GUI) helpers: ziDevice.configure(), mK2000B.configure() and
dltsConfig.log_to_textbox()'s console fallback."""
from types import SimpleNamespace

import numpy as np
import pytest

import dltsConfig as dltsc
import instecTempStage_Control as tsC
import zurichInstruments_Control as ziC


class RecordingServer:
    def __init__(self):
        self.sets = {}

    def set(self, node, value):
        self.sets[node] = value


def test_mfia_configure_pushes_defaults_with_overrides():
    dev = ziC.ziDevice()
    server = RecordingServer()
    dev.session = SimpleNamespace(daq_server=server)

    params = dev.configure({'State Enable Time': 0.5, 'Aux Output Scale': -5.0})

    assert params['State Enable Time'] == 0.5 and params['Aux Output Scale'] == -5.0
    assert params['Oscillation Frequency'] == ziC.DEFAULT_PARAMS['Oscillation Frequency']
    assert set(params) == set(ziC.DEFAULT_PARAMS)
    assert server.sets['/dev32271/tu/thresholds/0/activationtime'] == 0.5
    assert server.sets['/dev32271/auxouts/0/scale'] == -5.0
    assert len(server.sets) == len(ziC.DEFAULT_PARAMS)


def test_reload_after_configure_uses_configured_values_not_prompts(monkeypatch):
    """After a factory reset, reload_params() re-sets every mismatching parameter;
    without a GUI that used to fall through to input() prompts."""
    monkeypatch.setattr(dltsc, 'z_params_for_push', {}, raising=False)
    monkeypatch.setattr(dltsc, 'z_params_vars', {}, raising=False)
    monkeypatch.setattr('builtins.input', lambda *a: pytest.fail('prompted for input'))
    dev = ziC.ziDevice()
    dev.session = SimpleNamespace(daq_server=RecordingServer())
    dev.configure({'State Enable Time': 0.5})
    dev.params = dict.fromkeys(dev.params, 0)          # as after a factory reset
    monkeypatch.setattr(dev, 'check_param', lambda name: False)
    dev.reload_params()
    assert dev.params['State Enable Time'] == 0.5
    assert dev.params['Oscillation Frequency'] == ziC.DEFAULT_PARAMS['Oscillation Frequency']


def test_mfia_configure_needs_a_connection_to_push():
    dev = ziC.ziDevice()
    with pytest.raises(RuntimeError, match='connect_device'):
        dev.configure()
    assert dev.configure(push=False)['Oscillation Amplitude'] == 0.3


def test_mfia_configure_rejects_unknown_names():
    with pytest.raises(KeyError, match='Oscilation'):
        ziC.ziDevice().configure({'Oscilation Frequency': 1e5}, push=False)


def test_stage_configure_sets_grid_and_motion_attributes():
    stage = tsC.mK2000B()
    stage.configure({'Initial Temperature (C)': 25, 'Final Temperature (C)': 50,
                     'Room Temperature (C)': 30, 'Stability Delay (s)': 5})

    assert np.array_equal(stage.tempGrid, [25, 30, 35, 40, 45, 50]) and stage.numTemps == 6
    assert (stage.tRamp, stage.tStableDelay, stage.Troom, stage.roomRamp) == (5.0, 5.0, 30.0, 10.0)
    assert np.array_equal(stage.params['Temperature Grid (C)'], stage.tempGrid)


def test_stage_configure_rejects_unknown_names():
    with pytest.raises(KeyError):
        tsC.mK2000B().configure({'Final Temp': 50})


def test_log_prints_without_a_gui(monkeypatch, capsys):
    monkeypatch.setattr(dltsc, 'textboxes', None, raising=False)
    monkeypatch.setattr(dltsc, 'textbox', None, raising=False)
    dltsc.log_to_textbox('Warning: DAQ acquisition did not complete')
    assert 'DAQ acquisition did not complete' in capsys.readouterr().out

"""impdData's temperature keys from file / ZI history names, and cleanup_data()'s
gap removal (_gap_remove)."""
import numpy as np
import pytest

import dataAnalysisTab as qaT
import dltsConfig as dltsc
import impedanceAnalysis_Tools as iaT
from conftest import SAMPLE_DT_S, TICKS_PER_SAMPLE, make_step


@pytest.mark.parametrize('name,kelvin', [
    ('p25p0.txt', 298.15), ('p50p5.h5', 323.65), ('n10p0.txt', 263.15), ('n10p5.json', 262.65),
    ('p120.txt', 393.15), ('p25C.txt', 298.15), ('p25p0_1.txt', 298.15), ('P25P0.TXT', 298.15),
    ('25p0.txt', 298.15), (r'C:\run\092826\114655\p0p0.h5', 273.15)])
def test_step_file_names(name, kelvin):
    assert iaT.impdData._extract_txt_temperature(name) == kelvin


@pytest.mark.parametrize('name', ['runParams.txt', 'x25p0.txt', 'p-3.h5', 'p25p0_export.txt', 'notes.txt', '.txt'])
def test_names_without_a_temperature(name):
    """'x25p0' used to read as -25 C, 'p-3' raised ValueError."""
    assert iaT.impdData._extract_txt_temperature(name) is None


@pytest.mark.parametrize('name,kelvin', [('25C_000', 298.15), ('p25C_001', 298.15), ('n10C_000', 263.15),
                                         ('p25p5C_000', 298.65), ('120C_003', 393.15)])
def test_zi_history_names(name, kelvin):
    assert iaT.impdData._extract_csv_temperature(name) == kelvin


@pytest.mark.parametrize('name', ['C_000', 'xyz', '25C', ''])
def test_zi_history_names_without_a_temperature(name):
    assert iaT.impdData._extract_csv_temperature(name) is None


def test_keys_convert_back_to_the_setpoint():
    for T in (-10.0, 0.0, 25.0, 50.5, 255.0):
        key = iaT.impdData._celsius_to_kelvin_key('n' if T < 0 else 'p', *f"{abs(T):.1f}".split('.'))
        assert round(key - 273.15, 6) == T


def test_quick_analysis_celsius_keys_are_clean(monkeypatch):
    x = np.linspace(0, 0.005, 50)
    monkeypatch.setattr(dltsc, 'livePlot_offlineAllEmissionsData',
                        {298.15: {'x': x, 'ymean': np.ones(50)}, 323.65: {'x': x, 'ymean': np.ones(50)}}, raising=False)
    assert sorted(qaT._processed_transients_from_automated('offline')) == [25.0, 50.5]


# --- _gap_remove -------------------------------------------------------------

def signal_with(tick):
    tick = np.asarray(tick)
    n = tick.size
    return {'tickStampImps': tick.copy(), 'tickStampDemods': tick.copy(),
            'timeStampImps': np.zeros(n), 'timeStampDemods': np.zeros(n), 'ImpedanceIm': np.arange(n, dtype=float)}


def test_forward_gap_is_closed():
    """[0..4480, 1e7..] used to become [10004480.., 10005600..]: overlapping segments."""
    tick = np.concatenate([np.arange(5) * TICKS_PER_SAMPLE, 10_000_000 + np.arange(5) * TICKS_PER_SAMPLE])
    out = iaT.impdData._gap_remove(signal_with(tick))
    assert np.array_equal(out['tickStampImps'], np.arange(10) * TICKS_PER_SAMPLE)
    assert np.allclose(out['timeStampImps'], np.arange(10) * TICKS_PER_SAMPLE / 60e6)
    assert np.array_equal(out['tickStampDemods'], out['tickStampImps'])


def test_backward_jump_from_an_appended_record_is_closed():
    """A second record of the same temperature restarts its clock; both old
    branches fired and the result was not monotonic."""
    first = 5_000_000 + np.arange(6) * TICKS_PER_SAMPLE
    second = 1_000 + np.arange(6) * TICKS_PER_SAMPLE
    out = iaT.impdData._gap_remove(signal_with(np.concatenate([first, second])))
    assert np.array_equal(out['tickStampImps'], first[0] + np.arange(12) * TICKS_PER_SAMPLE)
    assert np.all(np.diff(out['tickStampImps']) > 0)


def test_every_gap_is_closed_and_data_order_kept():
    tick = np.concatenate([np.arange(4), 1000 + np.arange(4), 50 + np.arange(4), 99999 + np.arange(4)]) * 10
    sig = signal_with(tick)
    out = iaT.impdData._gap_remove(sig)
    assert np.array_equal(out['tickStampImps'], np.arange(16) * 10)
    assert np.array_equal(out['ImpedanceIm'], np.arange(16.0))


def test_seconds_axis_gap():
    t = np.concatenate([np.arange(5), 400 + np.arange(5)]) * SAMPLE_DT_S
    out = iaT.impdData._gap_remove(signal_with(t))
    assert np.allclose(out['tickStampImps'], np.arange(10) * SAMPLE_DT_S)
    assert np.allclose(out['timeStampImps'], out['tickStampImps'])        # seconds stay seconds


def test_unsigned_ticks_do_not_wrap():
    first = np.uint64(9_000_000) + np.arange(4, dtype=np.uint64) * np.uint64(TICKS_PER_SAMPLE)
    second = np.arange(4, dtype=np.uint64) * np.uint64(TICKS_PER_SAMPLE)
    out = iaT.impdData._gap_remove(signal_with(np.concatenate([first, second])))
    assert np.array_equal(out['tickStampImps'], 9_000_000 + np.arange(8) * TICKS_PER_SAMPLE)


def test_uniform_data_is_untouched():
    data = make_step(25.0, n=512)
    data['tickStampImps'] = data['tickStampImps'].astype(np.int64)
    sig = {k: np.array(v, copy=True) for k, v in data.items()}
    out = iaT.impdData._gap_remove(sig)
    for key in data:
        assert np.array_equal(out[key], data[key]), key


def test_small_jitter_is_not_a_gap():
    tick = np.cumsum(np.r_[0, np.full(20, 1120), 1120 * 50, np.full(5, 1120)])  # 50 steps < GAP_FACTOR
    out = iaT.impdData._gap_remove(signal_with(tick))
    assert np.array_equal(out['tickStampImps'], tick)

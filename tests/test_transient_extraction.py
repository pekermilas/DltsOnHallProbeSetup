"""Qualitative Extract & Average's pulse search (liveDataTab._compute_legacy_transients)
for any pulse levels, and what it reports when it can't extract a transient."""
import json

import numpy as np
import pytest

import liveDataTab as ldT
from conftest import SAMPLE_DT_S, make_step


def pulse_train(n, fill_ms, rb_ms, fill_v, rb_v, seed=0):
    rng = np.random.default_rng(seed)
    fillN, rbN = int(fill_ms * 1e-3 / SAMPLE_DT_S), int(rb_ms * 1e-3 / SAMPLE_DT_S)
    k = np.arange(n) % (fillN + rbN)
    return np.where(k < fillN, fill_v, rb_v) + rng.normal(0, 1e-3, n), fillN, rbN


def test_gui_default_pulse_levels_are_found():
    """-0.5 V fill / -1.5 V reverse bias never crossed the old fixed -2.5 V threshold."""
    aux, fillN, rbN = pulse_train(20000, 3, 6, -0.5, -1.5)
    starts, msg = ldT._find_reverse_bias_starts(aux)
    assert msg is None
    # The last sample of each fill pulse, including the trailing partial cycle.
    assert np.array_equal(starts, np.arange(fillN - 1, 20000 - 1, fillN + rbN))


def test_short_fill_pulse_matches_old_fixed_threshold():
    """0 / -5 V with a 1 ms fill in 500 ms (0.2% of samples): same pulse starts as
    the fixed -2.5 V threshold the extractor used before."""
    aux = make_step(25.0, n=2**16)['AuxInput1']
    starts, msg = ldT._find_reverse_bias_starts(aux)
    assert msg is None
    old = np.where(np.diff((aux > -2.5).astype(int)) == -1)[0]
    assert np.array_equal(starts, old) and len(starts) >= 2


def test_constant_excitation_reports_no_pulses():
    aux = np.full(5000, -1.0) + np.random.default_rng(0).normal(0, 1e-3, 5000)
    starts, msg = ldT._find_reverse_bias_starts(aux)
    assert starts.size == 0 and 'no fill pulses found' in msg


def _write(tmp_path, name, aux, cap):
    path = tmp_path / name
    path.write_text(json.dumps({'AuxInput1': list(aux), 'ImpedanceIm': list(cap)}))
    return str(path)


def test_default_level_run_gives_a_transient(tmp_path):
    aux, fillN, rbN = pulse_train(20000, 3, 6, -0.5, -1.5)
    cap = np.full(aux.size, 1e-10)
    path = _write(tmp_path, 'p25p0.txt', aux, cap)

    transients, errors = ldT._compute_legacy_transients([25.0], 6.0, 5.4, {25.0: path}, SAMPLE_DT_S)
    assert errors == []
    assert len(transients[25.0]['avg_cap_pf']) == int(6e-3 / SAMPLE_DT_S)
    assert transients[25.0]['C_infinity'] == pytest.approx(100.0, rel=1e-6)


def test_skipped_temperatures_say_why(tmp_path):
    flat = _write(tmp_path, 'p25p0.txt', np.full(4000, -1.0), np.full(4000, 1e-10))
    aux, _, _ = pulse_train(4000, 3, 6, -0.5, -1.5)
    short = _write(tmp_path, 'p30p0.txt', aux, np.full(4000, 1e-10))

    transients, errors = ldT._compute_legacy_transients(
        [25.0, 30.0], 500.0, 450.0, {25.0: flat, 30.0: short}, SAMPLE_DT_S)
    assert transients == {}
    assert any(e.startswith('25.0°C: no fill pulses found') for e in errors)
    assert any(e.startswith('30.0°C:') and 'lower Reverse Bias' in e for e in errors)


@pytest.mark.parametrize('enable,disable,expected', [(0.5, 0.001, (1.0, 500.0)), (0.006, 0.003, (3.0, 6.0))])
def test_run_timing_from_run_params(tmp_path, enable, disable, expected):
    (tmp_path / 'runParams.txt').write_text(json.dumps({'State Enable Time': enable, 'State Disable Time': disable}))
    fp, rb = ldT._legacy_run_timing(str(tmp_path))
    assert (fp, rb) == pytest.approx(expected)


def test_run_timing_missing_is_none(tmp_path):
    assert ldT._legacy_run_timing(str(tmp_path)) is None


@pytest.mark.parametrize('peak,expected', [(150.0, (1.0, 'pF')), (4.5e3, (1e-3, 'nF')),
                                            (4.5e6, (1e-6, 'µF')), (2e9, (1e-9, 'mF'))])
def test_axis_units_keep_tick_labels_short(peak, expected):
    assert ldT._capacitance_axis_units([np.array([peak * 0.5, peak])]) == expected

"""Quick Analysis and Detailed Analysis share one pipeline (C_infinity, S(T),
peak finding with the edge guard, the Arrhenius fit and its exclusion rule, Nt),
so the same transients, windows, search range and peak method must give the
same Et, sigma and Nt in both tabs."""
import numpy as np
import pytest

import dataAnalysisTab as qaT
import detailedAnalysisTab as deT
from test_detailed_peaks import synthetic_run, params

RB_MS = 500.0


def as_quick_input(data):
    """Detailed-shape data {T_C: (t_ms, cap, C_inf)} as Quick Analysis' averaged
    transients {T_C: {'time_ms', 'avg_cap_pf', 'C_infinity'}}."""
    return {tc: {'time_ms': t, 'avg_cap_pf': c, 'C_infinity': ci} for tc, (t, c, ci) in data.items()}


def as_detailed_loaded(data):
    """What Detailed Analysis' loader hands its worker: C_infinity recomputed as
    the 40-90 % range mean."""
    return {tc: (t, c, deT._cinf_range_mean(t, c, RB_MS)) for tc, (t, c, _) in data.items()}


def run_both(data, windows, tpLo, tpHi, qaMethod, deMethod):
    records, temps = qaT._transient_records(as_quick_input(data), RB_MS)
    peaks = []
    for pk in qaT._window_peaks(records, temps, windows, tpLo, tpHi, qaMethod):
        if not pk['skipped']:
            peaks.append(dict(T_peak=pk['Tp'], T_peak_err=pk['Tp_err'], e_n=pk['e_n'], S_peak=pk['S_peak']))
    quick = qaT._quick_arrhenius(peaks, deT.DEFAULT_GAMMA, deT.DEFAULT_ND, (records, temps, RB_MS))

    loaded = as_detailed_loaded(data)
    out = deT._compute_detailed_analysis(loaded, sorted(loaded), params(
        stdWins=list(windows) + [(0, 0)], tpLo=tpLo, tpHi=tpHi, peakMethod=deMethod,
        gamma=deT.DEFAULT_GAMMA, nd=deT.DEFAULT_ND, rbMs=RB_MS))
    return quick, out['resStd'], out['Nt']


@pytest.mark.parametrize('tpLo', [290.0, 300.0])   # 300 K puts the slow windows' peaks on the edge
def test_quick_and_detailed_give_the_same_result(tpLo):
    quick, std, nt = run_both(synthetic_run(), deT.DEFAULT_STD_WINDOWS, tpLo, 400.0,
                              qaT.PEAK_METHOD_SPLINE, deT.PEAK_METHOD_SPLINE)
    assert quick is not None and std is not None
    for key in ('Et', 'Et_se', 'sigma', 'sigma_se', 'R2'):
        assert quick[key] == pytest.approx(std[key], rel=1e-9), key
    assert quick['N'] == std['N'] and quick['N_excluded'] == std['N_excluded']
    assert quick['Nt'] == pytest.approx(nt, rel=1e-12)
    assert quick['Et'] == pytest.approx(0.60, abs=0.03)


def test_quick_excludes_edge_peaks():
    quick, _, _ = run_both(synthetic_run(), deT.DEFAULT_STD_WINDOWS, 300.0, 400.0,
                           qaT.PEAK_METHOD_SPLINE, deT.PEAK_METHOD_SPLINE)
    assert quick['N_excluded'] >= 1
    assert np.all(quick['Tp_err_arr'][quick['fit_mask']] >= deT.MIN_TP_ERR_K)
    assert quick['Et_se'] < 0.05


def test_curve_fit_method_goes_through_the_edge_guard():
    """A curve-fit finder's peak on the range edge loses its error too."""
    T = np.arange(300.0, 330.0, 2.5)
    S = (T - 290.0) / 100.0
    pk = deT._peak_from_signal(T, S, np.full(T.size, 1e-3), 300.0, 330.0,
                               qaT._peak_method_for(qaT.PEAK_METHOD_GAUSSIAN))
    assert not pk['skipped'] and pk['Tp_err'] is None


def test_cinf_is_averaged_in_float64():
    """The extractors can return float32 capacitance; Quick Analysis converts to
    float64 first, so C_inf (and Nt) must not depend on the input dtype."""
    t, cap, _ = next(iter(synthetic_run().values()))
    cap32 = (cap * 1e4).astype(np.float32)   # ~5e6, like the real run's ImpedanceIm scale
    assert deT._cinf_range_mean(t, cap32, RB_MS) == deT._cinf_range_mean(t, cap32.astype(np.float64), RB_MS)


def test_defaults_match():
    assert [(float(a), float(b)) for a, b in qaT.DEFAULT_RATE_WINDOWS] == deT.DEFAULT_STD_WINDOWS
    assert float(qaT.DEFAULT_TPEAK_LO) == deT.DEFAULT_TPEAK_LO
    assert float(qaT.DEFAULT_TPEAK_HI) == deT.DEFAULT_TPEAK_HI
    assert float(qaT.DEFAULT_GAMMA) == deT.DEFAULT_GAMMA
    assert float(qaT.DEFAULT_ND) == deT.DEFAULT_ND
    assert qaT.K_BOLTZMANN == deT.KB_EV

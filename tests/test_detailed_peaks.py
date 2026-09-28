"""Detailed Analysis peak errors: a peak on the edge of the search range, or one
with a non-physical (near-zero) error, must not carry weight in the Arrhenius fit."""
import numpy as np
import pytest

import detailedAnalysisTab as deT

KB = 8.617333e-5
T_GRID = np.arange(290.0, 400.0, 2.5)


def synthetic_run(Et=0.60, sigma=1e-15, gamma=1.66e21, rb_ms=500.0, amp=10.0, noise=0.002, seed=0):
    """Averaged transients in the tab's data shape {T_C: (t_ms, cap_pF, C_inf)}
    for one trap, so S(T) has a clean peak whose position depends on the window."""
    rng = np.random.default_rng(seed)
    t_ms = np.arange(0, rb_ms, 0.0186667)
    data = {}
    for TK in T_GRID:
        en = gamma * sigma * TK ** 2 * np.exp(-Et / (KB * TK))
        cap = 500.0 - amp * np.exp(-en * t_ms * 1e-3) + rng.normal(0, noise, t_ms.size)
        data[round(TK - 273.15, 6)] = (t_ms, cap, 500.0)
    return data


def params(**over):
    p = dict(nWin=12, t1Min=0.5, t1Max=20.0, ratio=5.0, stdWins=[(1, 5), (2, 10), (5, 25), (10, 50), (20, 100)],
             gamma=1.66e21, nd=3.2e14, tpLo=290.0, tpHi=400.0, peakMethod=deT.PEAK_METHOD_SPLINE,
             signalMethod=deT.SIGNAL_METHOD_MEASURED, denoise=deT.DENOISE_NONE, rbMs=500.0, showStd=True,
             showSpectra=False, nSpectra=5, showTmap=False, showTau=False, showRwm=False)
    p.update(over)
    return p


@pytest.mark.parametrize('method', [deT.PEAK_METHOD_SPLINE, deT.PEAK_METHOD_PARABOLIC])
def test_edge_peak_has_no_error(method):
    T = np.arange(300.0, 330.0, 5.0)
    S = (T - 290.0) / 100.0              # still rising at the top of the range
    Tp, err = deT._find_peak(T, S, np.full(T.size, 1e-3), method)
    assert err is None and Tp >= T[-1] - 1e-6


def test_interior_peak_keeps_its_error():
    T = np.arange(300.0, 350.0, 2.5)
    S = np.exp(-((T - 324.0) / 8.0) ** 2) + np.random.default_rng(1).normal(0, 0.01, T.size)
    Tp, err = deT._find_peak(T, S, np.full(T.size, 0.01), deT.PEAK_METHOD_SPLINE)
    assert abs(Tp - 324.0) < 1.5 and err is not None and err >= deT.MIN_TP_ERR_K


def test_tiny_error_is_treated_as_no_error(monkeypatch):
    monkeypatch.setattr(deT, '_find_peak_spline', lambda T, S, E: (320.0, 1.1e-13, None, None))
    T = np.arange(300.0, 350.0, 5.0)
    assert deT._find_peak(T, np.zeros(T.size), None, deT.PEAK_METHOD_SPLINE) == (320.0, None)


@pytest.mark.parametrize('Tp,edge', [(300.0, True), (300.01, True), (300.2, False), (339.0, False), (345.0, True), (360.0, True)])
def test_peak_on_edge(Tp, edge):
    assert deT._peak_on_edge(np.arange(300.0, 350.0, 5.0), Tp) is edge


def test_edge_windows_do_not_dominate_the_fit():
    """Search range cut so the slow windows' peaks fall on its lower edge: those
    windows must be excluded, and Et must stay at the trap's 0.60 eV."""
    data = synthetic_run()
    temps = sorted(data)
    full = deT._compute_detailed_analysis(data, temps, params())['resMw']
    cut = deT._compute_detailed_analysis(data, temps, params(tpLo=330.0))['resMw']

    assert full['Et'] == pytest.approx(0.60, abs=0.02)
    assert cut['N_excluded'] >= 1
    assert all(err is np.nan or np.isnan(err) or err >= deT.MIN_TP_ERR_K for err in cut['Tp_err_arr'])
    assert cut['Et'] == pytest.approx(0.60, abs=0.03)
    assert cut['Et_se'] is not None and cut['Et_se'] < 0.05

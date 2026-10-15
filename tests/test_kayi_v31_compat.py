"""Compatibility with Dr. Kayi's DLTS Multiwindow Analysis v3.1
(DrKayisCorrectionsScript.txt): its own analysis functions, loaded from that
file, and this software's ports must give the same numbers on the same data.
Et / σ are compared with a tolerance (this software weights the peak and
Arrhenius fits by their errors, v3.1 does not); the Nt physics, the
fill-pulse information and the fill-scan analysis must agree exactly."""
import os

import matplotlib
import numpy as np
import pandas as pd
import pytest

import detailedAnalysisTab as deT
import dltsPhysics as dP

KB = 8.617333e-5
# v3.1 uses kB = 8.617333e-5 eV/K, this app the CODATA value (8.617333262e-5): λ, and so g and Nt,
# differ in the 9th digit.
RTOL = 1e-7
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'DrKayisCorrectionsScript.txt')


@pytest.fixture(scope='module')
def kayi():
    """v3.1's analysis helpers (everything above its GUI class), without its
    TkAgg backend switch; its rcParams changes are undone afterwards."""
    with open(SCRIPT, encoding='utf-8') as fh:
        src = fh.read().split('\nclass DLTSApp')[0].replace("matplotlib.use('TkAgg')", '')
    ns = {'__name__': 'kayi_v31'}
    with matplotlib.rc_context():
        exec(compile(src, SCRIPT, 'exec'), ns)
    return ns


def zi_like_run(t_fe=1.307, Et=0.60, sigma=1e-15, gamma=1.66e21, amp=10.0, noise=0.002, seed=0,
                T_K=np.arange(260.0, 400.0, 2.5)):
    """Averaged transients {T_C: (t_ms, cap_pF, C0)} on a ZI-like time axis that
    starts 1 ms before the trigger: the emission starts at t_fe, not at 0."""
    rng = np.random.default_rng(seed)
    t_ms = -1.0 + np.arange(0, 501.0, 0.0186667)
    data = {}
    for TK in T_K:
        en = gamma * sigma * TK ** 2 * np.exp(-Et / (KB * TK))
        cap = 500.0 - amp * np.exp(-en * np.clip(t_ms - t_fe, 0, None) * 1e-3) + rng.normal(0, noise, t_ms.size)
        data[round(TK - 273.15, 6)] = (t_ms, cap, 500.0)
    return data


def multi_windows(n=16, t1a=5.0, t1b=90.0, ratio=5.0):
    return [(float(t1), float(ratio * t1)) for t1 in np.logspace(np.log10(t1a), np.log10(t1b), n)]


#---------------------RATE WINDOWS-------------------------#
def test_boxcar_factor_matches_v31():
    # v3.1's docstring value: f = 0.947 for 5/490 ms (0.307 ms after the pulse end)
    assert dP.boxcar_factor(5.0, 490.0, 0.307) == pytest.approx(0.947, abs=5e-4)
    for t1, t2, fe in ((5.0, 25.0, 0.0), (10.0, 50.0, 1.307), (100.0, 490.0, 1.307)):
        r = (t2 - fe) / (t1 - fe)
        assert dP.boxcar_factor(t1, t2, fe) == pytest.approx(r ** (-1.0 / (r - 1.0)) * (1.0 - 1.0 / r), rel=1e-14)
        assert deT._boxcar_peak_factor(t1, t2, fe) == dP.boxcar_factor(t1, t2, fe)


def test_emission_rate_from_fill_end():
    tau1, tau2 = 5.0 - 1.307, 25.0 - 1.307
    assert deT._emission_rate(5.0, 25.0, 1.307) == pytest.approx(np.log(tau2 / tau1) / ((tau2 - tau1) * 1e-3))
    assert deT._emission_rate(5.0, 25.0) == pytest.approx(np.log(5.0) / 20e-3)
    assert deT._emission_rate(1.0, 5.0, 1.307) is None          # starts inside the fill pulse


@pytest.mark.parametrize('method,kayiMethod', [(deT.PEAK_METHOD_PVOIGT, 'Pseudo-Voigt'),
                                               (deT.PEAK_METHOD_GAUSSIAN, 'Gaussian')])
def test_et_and_sigma_match_v31_with_t_fe(kayi, method, kayiMethod):
    """Same data, windows, range, finder and t_FE: the same trap signature."""
    data = zi_like_run()
    temps = sorted(data)
    windows = multi_windows()
    ref = kayi['compute_arrhenius'](windows, temps, data, 1.66e21, 265.0, 395.0, t_fe_ms=1.307,
                                    peak_method=kayiMethod)
    prepared = deT._prepare_signal_data(data, temps, deT.SIGNAL_METHOD_SMOOTHED, deT.DENOISE_NONE)
    ours = deT._compute_arrhenius(windows, temps, prepared, 1.66e21, 265.0, 395.0, method, t_fe=1.307)
    assert ref['Et'] == pytest.approx(0.60, abs=0.01)
    assert ours['Et'] == pytest.approx(ref['Et'], abs=0.005)
    assert np.log10(ours['sigma']) == pytest.approx(np.log10(ref['sigma']), abs=0.1)
    assert ours['N'] + ours['N_excluded'] == ref['N']


def test_ignoring_t_fe_biases_et(kayi):
    """Why t_FE matters: the same ZI-like data analysed from t = 0."""
    data = zi_like_run()
    temps = sorted(data)
    prepared = deT._prepare_signal_data(data, temps, deT.SIGNAL_METHOD_SMOOTHED, deT.DENOISE_NONE)
    right = deT._compute_arrhenius(multi_windows(), temps, prepared, 1.66e21, 265.0, 395.0, deT.PEAK_METHOD_PVOIGT,
                                   t_fe=1.307)
    wrong = deT._compute_arrhenius(multi_windows(), temps, prepared, 1.66e21, 265.0, 395.0, deT.PEAK_METHOD_PVOIGT)
    assert abs(right['Et'] - 0.60) < abs(wrong['Et'] - 0.60)


def test_small_peak_skip_uses_the_in_range_max():
    """A strong peak outside the range must not suppress the weak trap's windows."""
    T = np.arange(250.0, 450.0, 2.0)
    weak = 0.02 * np.exp(-((T - 300.0) / 10.0) ** 2)
    strong = 1.0 * np.exp(-((T - 420.0) / 10.0) ** 2)
    S = weak + strong
    old = deT._peak_from_signal(T, S, None, 260.0, 350.0, deT.PEAK_METHOD_PARABOLIC)
    new = deT._peak_from_signal(T, S, None, 260.0, 350.0, deT.PEAK_METHOD_PARABOLIC,
                                ref_max=deT._in_range_max(T, [S], 260.0, 350.0))
    assert old['skipped'] and not new['skipped']
    assert new['Tp'] == pytest.approx(300.0, abs=0.5)


def test_profile_finder_reports_fitted_height_with_error():
    T = np.arange(280.0, 340.0, 2.0)
    S = 0.01 + 0.5 * np.exp(-4 * np.log(2) * ((T - 311.0) / 15.0) ** 2)
    S = S + np.random.default_rng(3).normal(0, 1e-3, T.size)
    pk = deT._peak_from_signal(T, S, np.full(T.size, 1e-3), 280.0, 340.0, deT.PEAK_METHOD_GAUSSIAN)
    assert pk['Tp'] == pytest.approx(311.0, abs=0.3)
    assert pk['S_peak'] == pytest.approx(0.51, abs=0.01)        # baseline included, as v3.1
    assert pk['S_peak_err'] is not None and pk['Tp_err'] is not None and not pk['fallback']


#---------------------Nt PHYSICS-------------------------#
def _geometry(T_C, C0, CF):
    return dict(on=True, v_fill=0.0, v_rev=-5.0, vbi=2.9, diam_mm=6.5, eps_r=9.7, wf_mode='cfill', wf_ratio=0.762,
                ls=False, nd_scale=True, t_ref=25.0, T=np.asarray(T_C, float), C0=np.asarray(C0, float),
                CF=np.asarray(CF, float))


@pytest.mark.parametrize('mode,ls,ndScale', [('cfill', False, True), ('cfill', True, True), ('ratio', False, False),
                                             ('vbi', False, True)])
def test_trap_concentration_matches_v31(kayi, mode, ls, ndScale):
    T_C = np.arange(-20.0, 120.0, 5.0)
    C0 = 480.0 + 0.8 * T_C                                         # baseline rises with T
    CF = np.where(T_C < 60.0, C0 / 0.73, np.nan)                   # C_fill only in part of the range
    detail = [(t1, t2, None, tp, sp) for (t1, t2), tp, sp in zip(multi_windows(6), np.linspace(20.0, 75.0, 6),
                                                                  np.linspace(0.010, 0.014, 6))]
    kayiGeom = _geometry(T_C, C0, CF)
    kayiGeom.update(wf_mode=mode, ls=ls, nd_scale=ndScale)
    kayi['GEOM'].clear(); kayi['GEOM'].update(kayiGeom)
    ref = kayi['trap_concentration'](dict(detail=detail, Et=0.63), 3.2e14, t_fe_ms=1.307)

    geom = dict(kayiGeom, T=T_C + 273.15, t_ref=298.15)
    peaks = [dict(t1=t1, t2=t2, T_peak=tp + 273.15, S_peak=sp, S_peak_err=None) for t1, t2, _, tp, sp in detail]
    ours = dP.trap_concentration(peaks, 3.2e14, 0.63, geom, t_fe=1.307)
    assert [r['nt'] for r in ours['rows']] == pytest.approx(list(ref['nt_arr']), rel=RTOL)
    assert [r['g'] for r in ours['rows']] == pytest.approx(list(ref['g_arr']), rel=RTOL)
    assert ours['Nt_median'] == pytest.approx(ref['Nt'], rel=RTOL)
    assert ours['Nt_sd'] == pytest.approx(ref['Nt_sd'], rel=RTOL)
    assert float(np.median([r['nt_raw'] for r in ours['rows']])) == pytest.approx(ref['Nt_raw'], rel=RTOL)
    assert ours['nd_med'] == pytest.approx(ref['nd_med'], rel=RTOL)
    assert ours['a_med'] == pytest.approx(ref['a_med'], rel=RTOL)
    for key in ('W_R', 'W_F', 'lam', 'g', 'C0', 'clipped', 'src'):
        assert ours['geom'][key] == pytest.approx(ref['geom'][key], rel=RTOL) if key not in ('clipped', 'src') \
            else ours['geom'][key] == ref['geom'][key]


def test_geometry_off_gives_the_detailed_nt():
    """Without N_D(T) and geometry, Trap Concentration's Nt is Detailed
    Analysis' uncorrected Nt (same windows, same weighting)."""
    peaks = [dict(t1=t1, t2=t2, T_peak=300.0 + i, S_peak=0.01 + 1e-4 * i, S_peak_err=2e-4)
             for i, (t1, t2) in enumerate(multi_windows(6))]
    geom = dict(dP.default_geometry(), on=False, nd_scale=False)
    tc = dP.trap_concentration(peaks, 3.2e14, 0.6, geom, t_fe=1.307)
    nt, ntErr = deT._trap_density_from_peaks(peaks, 3.2e14, 1.307)
    assert tc['Nt'] == pytest.approx(nt, rel=1e-12) and tc['Nt_err'] == pytest.approx(ntErr, rel=1e-12)
    assert tc['Nt_raw'] == pytest.approx(nt, rel=1e-12)


def test_geometry_arrays_plausibility_matches_v31(kayi):
    T_C = [0.0, 25.0, 50.0, 75.0]
    data = {t: (None, None, c) for t, c in zip(T_C, [100.0, 100.0, 100.0, 100.0])}
    fill = {0.0: dict(ok=True, c_fill=130.0), 25.0: dict(ok=True, c_fill=95.0), 50.0: dict(ok=False, c_fill=140.0),
            75.0: dict(ok=True, c_fill=600.0)}
    kayi['FILL_INFO'].clear(); kayi['FILL_INFO'].update(fill)
    _, refC0, refCF = kayi['geom_arrays'](data, T_C)
    _, C0, CF = dP.geometry_arrays({t + 273.15: c[2] for t, c in data.items()},
                                   {t + 273.15: d for t, d in fill.items()})
    assert np.array_equal(C0, refC0)
    assert np.array_equal(np.isnan(CF), np.isnan(refCF)) and np.allclose(CF[~np.isnan(CF)], refCF[~np.isnan(refCF)])


#---------------------FILL-PULSE INFORMATION-------------------------#
def kayi_record(t_start=0.2, width=1.107, v_fill=0.0, v_rev=-5.0, c0=100.0, c_fill=137.0, dC=-3.0, rec_ms=612.0,
                second=501.0, seed=0):
    """One raw record as v3.1 reads it: the fill pulse near the start, a second
    pulse at ~501 ms (C in pF, bias monitor in V)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, rec_ms, 0.0186667)
    v = np.full(t.size, v_rev) + rng.normal(0, 1e-3, t.size)
    v[(t >= t_start) & (t < t_start + width)] = v_fill
    v[(t >= second) & (t < second + width)] = v_fill
    tEnd = t_start + width
    c = np.where(t < tEnd, c_fill, c0 + dC * np.exp(-np.clip(t - tEnd, 0, None) / 40.0))
    c[(t >= t_start) & (t < tEnd)] = c_fill
    c[t < t_start] = c0
    c[(t >= second) & (t < second + width)] = c_fill
    return t, c + rng.normal(0, 0.01, t.size), v


def test_fill_record_info_matches_v31(kayi):
    t, c, v = kayi_record()
    ref = kayi['fill_record_info'](t, c, v)
    ours = dP.fill_record_info(t, c, v)
    for key in ('ok', 'v_rev', 'v_fill', 'c_fill', 'width_ms', 't_end', 'in_record'):
        assert ours[key] == pytest.approx(ref[key], rel=1e-12, nan_ok=True), key
    assert ours['pre_ok'] and ours['c_pre'] == pytest.approx(np.mean(c[:2]))
    assert ours['next_pulse_ms'] == pytest.approx(501.0 - ours['t_end'], abs=0.05)


def test_fill_record_info_finds_a_later_first_pulse():
    """A continuous record whose first pulse is past v3.1's 30 ms window."""
    t, c, v = kayi_record(t_start=120.0, second=622.0, rec_ms=900.0)
    info = dP.fill_record_info(t, c, v)
    assert info['ok'] and info['v_fill'] == pytest.approx(0.0, abs=0.01)
    assert info['c_fill'] == pytest.approx(137.0, abs=0.05)
    assert info['width_ms'] == pytest.approx(1.107, abs=0.03)
    assert info['pre_ok'] and info['c_pre'] == pytest.approx(100.0, abs=0.05)


def test_c0_estimate_cuts_the_tail_before_the_second_pulse():
    t = np.arange(0.0, 600.0, 0.02)
    cap = np.where(t < 500.0, 100.0, 137.0)               # a 2nd pulse at 500 ms inside the transient
    info = dict(pre_ok=False, c_pre=np.nan, next_pulse_ms=500.0)
    c0, src = dP.c0_estimate(t, cap, 600.0, 0.4, 0.9, info)
    assert c0 == pytest.approx(100.0) and src == 'tail'
    c0, src = dP.c0_estimate(t, cap - 1.0 * (t < 300), 600.0, 0.4, 0.9, dict(info, pre_ok=True, c_pre=99.5))
    assert c0 == pytest.approx(99.5) and src == 'pre-pulse'


def test_capacitance_mode():
    assert dP.capacitance_mode(np.full(10, 1e-10), 501e3) == 'direct'          # 100 pF stored in farads
    assert dP.capacitance_mode(np.full(10, 3.1e-4), 501e3) == 'susceptance'    # B = ωC for ~100 pF


#---------------------FILL-PULSE SCAN-------------------------#
def scan_rows():
    rows = []
    for bias, dC in ((-2.0, -2.0), (-1.0, -2.5), (0.0, -3.0), (0.5, -3.05), (1.0, -3.08), (1.5, -3.1), (2.0, -3.1),
                     (2.5, -2.6), (3.0, -2.0)):
        t, c, v = kayi_record(v_fill=bias, c_fill=100.0 / (0.73 - 0.04 * bias), dC=dC, rec_ms=520.0, second=505.0,
                              seed=int(10 * bias) + 30)
        rows.append(dict(name=f'FP1ms{bias}V', width_set=1.0, v_set=bias, t_ms=t, C_pF=c, V=v, reps=10))
    for width, dC in ((0.1, -2.6), (0.3, -2.9), (1.0, -3.0), (3.0, -3.04), (10.0, -3.05)):
        t, c, v = kayi_record(width=width, dC=dC, rec_ms=520.0, second=505.0, seed=int(10 * width))
        rows.append(dict(name=f'FP{width}ms0V', width_set=width, v_set=0.0, t_ms=t, C_pF=c, V=v, reps=10))
    return rows


def test_fill_scan_analysis_matches_v31(kayi):
    rows = scan_rows()
    ref = kayi['analyze_fill_scan'](rows, 3.2e14, T_C=25.0)
    ours = dP.analyze_fill_scan(rows, 3.2e14, T_K=298.15)
    assert ours['rec_bias'] == ref['rec_bias'] and ours['rec_width'] == ref['rec_width']
    assert ours['lam'] == pytest.approx(ref['lam'], rel=RTOL)
    for col in ('dC', 'g', 'Nt', 'WF'):
        pd.testing.assert_series_equal(ours['bias'][col], ref['bias'][col], check_exact=False, rtol=RTOL)
    pd.testing.assert_series_equal(ours['width']['frac'], ref['width']['frac'], check_exact=False, rtol=RTOL)
    assert 'Recommended fill bias' in dP.fill_scan_report(ours)


#---------------------LOADER-------------------------#
def test_loader_reads_fill_information(tmp_path, zi_device):
    """Step files (JSON) give fill-pulse information, t_FE = 0, and C in pF."""
    from conftest import write_run
    write_run(zi_device, str(tmp_path), [20.0, 30.0, 40.0], '.txt', n=2**15, rb_ms=200.0)
    data, temps, errors, info = deT._load_detailed_data_full(str(tmp_path), None, None, None, 190.0, 0.4, 0.9)
    assert temps == [20.0, 30.0, 40.0]
    assert info['tFe'] == 0.0 and info['cap_mode'] == 'direct' and info['formats'] == ['step files']
    assert set(info['fillByT']) == {t + 273.15 for t in temps}
    fs = info['fill']
    assert fs['v_fill'] == pytest.approx(0.0, abs=0.01) and fs['v_rev'] == pytest.approx(-5.0, abs=0.01)
    assert all(95.0 < rec[2] < 105.0 for rec in data.values())      # 100 pF baseline, in pF
    assert deT._load_detailed_data(str(tmp_path), None, None, None, 190.0, 0.4, 0.9)[1] == temps

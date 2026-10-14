"""Peak deconvolution (impedanceAnalysis_Tools' _deconvolve_peaks and
_smoothingSpline_multiPeakFinder, and Quick Analysis' region/trap pipeline on
top of them): overlapping peaks are separated, every peak carries an error,
peaks keep their listed order across windows, and two traps in one region give
two Arrhenius lines with their own activation energies."""
import numpy as np
import pytest

import impedanceAnalysis_Tools as iaT
import dataAnalysisTab as qaT
import detailedAnalysisTab as deT

KB = 8.617333e-5


def gaussian(x, h, c, s):
    return h * np.exp(-0.5 * ((x - c) / s) ** 2)


def two_peaks(noise=2e-4, seed=0, sign=1.0):
    """A heavy-left-tailed peak at 300 K overlapping a Gaussian at 335 K, on a
    5 K grid like the R11C4 run, with per-point errors."""
    rng = np.random.default_rng(seed)
    T = np.arange(250.0, 381.0, 5.0)
    S = iaT.mirroredLognormal(T, 0.03, 300.0, 40.0, 0.3) + gaussian(T, 0.012, 335.0, 10.0)
    err = np.full(T.size, noise)
    return T, sign * (S + rng.normal(0, noise, T.size)), err


def test_mirrored_lognormal_peaks_at_center_with_left_tail():
    x = np.linspace(200.0, 400.0, 4001)
    y = iaT.mirroredLognormal(x, height=2.0, center=300.0, width=40.0, shape=0.4)
    assert x[np.argmax(y)] == pytest.approx(300.0, abs=0.06)
    assert y.max() == pytest.approx(2.0, rel=1e-4)
    for d in (10.0, 20.0, 30.0):
        assert iaT.mirroredLognormal(300.0 - d, 2.0, 300.0, 40.0, 0.4) > iaT.mirroredLognormal(300.0 + d, 2.0, 300.0, 40.0, 0.4)
    # Zero beyond the reflection point on the right.
    assert iaT.mirroredLognormal(300.0 + 40.0, 2.0, 300.0, 40.0, 0.4) == 0.0


@pytest.mark.parametrize('sign', [1.0, -1.0])
def test_deconvolution_separates_overlapping_peaks(sign):
    T, S, err = two_peaks(sign=sign)
    res = iaT.impdData._deconvolve_peaks(T, S, ['mirroredLognormal', 'gaussian'], signalYErr=err)
    assert res['success'] and res['weighted']
    first, second = res['components']
    for comp, center, height in ((first, 300.0, 0.03), (second, 335.0, 0.012)):
        assert comp['isPeak'] and not comp['onEdge']
        assert comp['centerErr'] is not None and comp['heightErr'] is not None
        assert comp['center'] == pytest.approx(center, abs=max(4 * comp['centerErr'], 0.5))
        assert comp['height'] == pytest.approx(sign * height, rel=0.1)
    # Components add up to the total fit, in the signal's own sign.
    assert np.allclose(np.sum(res['componentCurves'], axis=0), res['yf'])
    assert res['redchi'] < 3.0


def test_like_peaks_keep_their_listed_order():
    T, S, err = two_peaks()
    res = iaT.impdData._deconvolve_peaks(T, S, ['gaussian', 'gaussian', 'gaussian'], signalYErr=err)
    centers = [c['center'] for c in res['components']]
    assert centers == sorted(centers)


def test_baseline_primitives_have_no_peak():
    T, S, err = two_peaks()
    res = iaT.impdData._deconvolve_peaks(T, S + 0.002, ['mirroredLognormal', 'gaussian', 'constant'],
                                         signalYErr=err)
    assert [c['isPeak'] for c in res['components']] == [True, True, False]
    assert res['components'][2]['center'] is None


def test_deconvolution_reports_too_few_points():
    T, S, err = two_peaks()
    res = iaT.impdData._deconvolve_peaks(T[:6], S[:6], ['voigt', 'voigt'], signalYErr=err[:6])
    assert not res['success'] and res['xf'] is None and 'free parameters' in res['message']


def test_unknown_primitive_is_rejected():
    T, S, err = two_peaks()
    with pytest.raises(ValueError):
        iaT.impdData._deconvolve_peaks(T, S, ['gaussian', 'beta'])


@pytest.mark.parametrize('sign', [1.0, -1.0])
def test_spline_multi_peak_finder_uses_the_prominence(sign):
    T, S, err = two_peaks(sign=sign)
    found = iaT.impdData._smoothingSpline_multiPeakFinder(T, S, minProminence=0.02, signalYErr=err)
    assert len(found['peaks']) == 2
    assert [p['center'] for p in found['peaks']] == pytest.approx([300.0, 335.0], abs=3.0)
    assert all(p['centerErr'] is not None and p['centerErr'] > 0 for p in found['peaks'])
    assert np.sign(found['peaks'][0]['height']) == sign
    # The 335 K peak only rises ~0.008 above the valley: a high threshold drops it.
    assert len(iaT.impdData._smoothingSpline_multiPeakFinder(T, S, minProminence=0.5, signalYErr=err)['peaks']) == 1


def test_single_peak_spline_finder_unchanged_by_refactor():
    """_smoothingSpline_peakFinder now shares _smoothing_spline_fit; its peak
    must still be the largest-|S| point of the same spline."""
    T, S, err = two_peaks()
    maxX, maxY, xf, yf, maxXErr, _ = iaT.impdData._smoothingSpline_peakFinder(T, S, signalYErr=err)
    found = iaT.impdData._smoothingSpline_multiPeakFinder(T, S, minProminence=0.02, signalYErr=err)
    assert maxX == pytest.approx(found['peaks'][0]['center'], abs=0.01)
    assert maxXErr is not None


def test_boxcar_peak_factor():
    # r = 5: 5^-0.25 - 5^-1.25
    assert deT._boxcar_peak_factor(20.0, 100.0) == pytest.approx(5 ** -0.25 - 5 ** -1.25)
    # It is exp(-e t1) - exp(-e t2) at the rate-window emission rate.
    t1, t2 = 5.0, 25.0
    e = deT._emission_rate(t1, t2) * 1e-3
    assert deT._boxcar_peak_factor(t1, t2) == pytest.approx(np.exp(-e * t1) - np.exp(-e * t2))


def test_trap_density_is_an_error_weighted_mean():
    nd = 1e15
    f = deT._boxcar_peak_factor(20.0, 100.0)
    peaks = [dict(S_peak=0.01 * f, S_peak_err=1e-4 * f, t1=20.0, t2=100.0),
             dict(S_peak=-0.01 * f, S_peak_err=1e-4 * f, t1=20.0, t2=100.0)]
    nt, ntErr = deT._trap_density_from_peaks(peaks, nd)
    assert nt == pytest.approx(2 * nd * 0.01)
    assert ntErr == pytest.approx(2 * nd * 1e-4 / np.sqrt(2))
    nt, ntErr = deT._trap_density_from_peaks([dict(p, S_peak_err=None) for p in peaks], nd)
    assert nt == pytest.approx(2 * nd * 0.01) and ntErr == pytest.approx(0.0, abs=1e-6 * nt)


def two_trap_run(traps=((0.55, 1e-15, 6.0), (0.70, 1e-15, 3.0)), gamma=1.66e21, rb_ms=500.0, seed=0):
    """Averaged transients {T_C: {'time_ms','avg_cap_pf','C_infinity'}} of two
    traps (Et, sigma, amplitude pF), so each rate window's S(T) has two
    overlapping peaks."""
    rng = np.random.default_rng(seed)
    t_ms = np.arange(0, rb_ms, 0.05)
    out = {}
    for TK in np.arange(250.0, 420.0, 2.5):
        cap = np.full(t_ms.size, 500.0)
        for Et, sigma, amp in traps:
            en = gamma * sigma * TK ** 2 * np.exp(-Et / (KB * TK))
            cap -= amp * np.exp(-en * t_ms * 1e-3)
        cap += rng.normal(0, 0.002, t_ms.size)
        out[round(TK - 273.15, 6)] = {'time_ms': t_ms, 'avg_cap_pf': cap, 'C_infinity': 500.0}
    return out


def test_two_traps_in_one_region_give_two_activation_energies():
    rb_ms = 500.0
    records, temps = qaT._transient_records(two_trap_run(rb_ms=rb_ms), rb_ms)
    T_K = np.array([tc + 273.15 for tc in temps])
    region = dict(tLo=250.0, tHi=420.0, primitives=['Gaussian', 'Gaussian'], prominence=0.02)
    byTrap = {}
    for t1, t2 in deT.DEFAULT_STD_WINDOWS:
        S, S_err = deT._rate_window_signal(temps, records, t1, t2)
        sig = dict(T_k=T_K, Signal=S, Signal_err=deT._valid_errors(S_err), t1=t1, t2=t2,
                   e_n=deT._emission_rate(t1, t2))
        res = deT._deconvolve_region(sig, region)
        assert res['ok'] and len(res['peaks']) == 2
        for k, pk in enumerate(res['peaks']):
            byTrap.setdefault(k, []).append((sig['e_n'], pk['T_peak'], pk['T_peak_err']))
    for k, Et in ((0, 0.55), (1, 0.70)):
        en, Tp, TpErr = zip(*byTrap[k])
        fit = deT._arrhenius_fit(en, Tp, TpErr, deT.DEFAULT_GAMMA)
        assert fit is not None and fit['Et_se'] is not None
        assert fit['Et'] == pytest.approx(Et, abs=0.04)


def detailed_params(**over):
    from test_detailed_peaks import params
    return params(**dict(dict(tpLo=250.0, tpHi=420.0), **over))


def detailed_input(quickShaped, rb_ms=500.0):
    """Quick-shaped transients as Detailed Analysis' loaded {T_C: (t_ms, cap, C_inf)}."""
    return {tc: (r['time_ms'], r['avg_cap_pf'], deT._cinf_range_mean(r['time_ms'], r['avg_cap_pf'], rb_ms))
            for tc, r in quickShaped.items()}


def test_detailed_analysis_fits_each_trap_of_a_region():
    """Detailed Analysis with a Quick-Analysis-style region (2 Gaussians) gives
    one Arrhenius fit per trap, for the multi and the standard windows."""
    data = detailed_input(two_trap_run())
    region = dict(tLo=250.0, tHi=420.0, primitives=['Gaussian', 'Gaussian'], prominence=0.02, source='Quick R1')
    out = deT._compute_detailed_analysis(data, sorted(data), detailed_params(regions=[region]))
    assert [t['peakId'] for t in out['traps']] == ['R1P1', 'R1P2']
    assert [t['peakId'] for t in out['trapsStd']] == ['R1P1', 'R1P2']
    for trap, Et in zip(out['traps'], (0.55, 0.70)):
        assert trap['Et'] == pytest.approx(Et, abs=0.04)
        assert trap['Et_se'] is not None and trap['Nt_err'] is not None
        assert trap['method'] == 'Gauss + Gauss'
    assert out['resMw'] is out['traps'][0]
    assert len(out['windowPeaks']) == detailed_params()['nWin']
    assert {pid for found in out['windowPeaks'] for pid, _ in found} == {'R1P1', 'R1P2'}


def test_detailed_default_region_is_the_old_single_peak_analysis():
    """A region without primitives uses the tab's own single-peak finder over
    it: the same result as the old Peak Search Range path (_compute_arrhenius)."""
    data = detailed_input(two_trap_run(traps=((0.60, 1e-15, 6.0),)))
    p = detailed_params(tpLo=290.0, tpHi=400.0)
    region = dict(tLo=290.0, tHi=400.0, primitives=[], prominence=0.02, source=None)
    out = deT._compute_detailed_analysis(data, sorted(data), dict(p, regions=[region]))
    prepared = deT._prepare_signal_data(data, sorted(data), p['signalMethod'], p['denoise'])
    t1Arr = np.logspace(np.log10(p['t1Min']), np.log10(p['t1Max']), p['nWin'])
    old = deT._compute_arrhenius([(t1, p['ratio'] * t1) for t1 in t1Arr], sorted(data), prepared, p['gamma'],
                                 290.0, 400.0, p['peakMethod'])
    assert [t['peakId'] for t in out['traps']] == ['R1P1']
    for key in ('Et', 'Et_se', 'sigma', 'R2', 'N', 'N_excluded'):
        assert out['resMw'][key] == pytest.approx(old[key], rel=1e-12), key


def test_detailed_regions_can_mix_methods():
    """One region deconvolved with primitives, another with the default finder."""
    data = detailed_input(two_trap_run())
    regions = [dict(tLo=250.0, tHi=340.0, primitives=[], prominence=0.02, source=None),
               dict(tLo=340.0, tHi=420.0, primitives=['Gaussian'], prominence=0.02, source='Quick R2')]
    out = deT._compute_detailed_analysis(data, sorted(data), detailed_params(regions=regions))
    assert [t['peakId'] for t in out['traps']] == ['R1P1', 'R2P1']
    assert out['traps'][0]['method'].startswith('single peak')


def test_peak_id_order_is_numeric():
    assert sorted(['R10P1', 'R2P1', 'R1P10', 'R1P2'], key=deT._peak_id_order) == ['R1P2', 'R1P10', 'R2P1', 'R10P1']


def test_region_problems():
    ok = dict(tLo=250.0, tHi=380.0, primitives=['Gaussian'], prominence=0.02)
    assert deT._region_problem(ok) is None
    assert deT._region_problem(dict(ok, tHi=200.0))
    assert deT._region_problem(dict(ok, primitives=[]))
    assert deT._region_problem(dict(ok, primitives=['Gaussian', qaT.PRIMITIVE_SPLINE]))
    assert deT._region_problem(dict(ok, primitives=['Constant Baseline']))
    assert deT._region_problem(dict(ok, primitives=[qaT.PRIMITIVE_SPLINE])) is None


def test_every_ui_primitive_maps_to_a_library_primitive():
    assert set(qaT.PRIMITIVE_KEYS.values()) == set(iaT.DECONV_PRIMITIVES)
    assert set(qaT.PRIMITIVE_SHORT) == set(qaT.PRIMITIVE_OPTIONS)

"""Detailed Analysis' v3.1 additions (peak-finder table, range stability,
checks, t_FE) and the Trap Concentration tab's calculation and report."""
import numpy as np
import pytest

import detailedAnalysisTab as deT
import dltsPhysics as dP
import trapConcentrationTab as tcT
from test_detailed_peaks import synthetic_run, params
from test_peak_deconvolution import two_trap_run, detailed_input, detailed_params


def test_method_table_and_checks():
    data = synthetic_run()
    out = deT._compute_detailed_analysis(data, sorted(data), params(methodTable=True, peakMethod=deT.PEAK_METHOD_PVOIGT))
    rows = out['methodTable']['R1P1']
    assert [m for m, _ in rows] == deT.PEAK_METHOD_OPTIONS
    for method, v in rows:
        assert v is not None, method
        assert v['Et'] == pytest.approx(0.60, abs=0.04), method
    # the selected method's row is the main result itself
    assert dict(rows)[deT.PEAK_METHOD_PVOIGT]['Et'] == out['resMw']['Et']
    notes = deT._detailed_checks(out, params(peakMethod=deT.PEAK_METHOD_PVOIGT), dict(second_pulse=60.0, f_osc=10e3))
    assert any('second fill pulse' in n for n in notes)
    assert any('lock-in' in n for n in notes)


def test_range_stability_of_a_primitive_region():
    data = detailed_input(two_trap_run(traps=((0.60, 1e-15, 6.0),)))
    region = dict(tLo=270.0, tHi=400.0, primitives=['Gaussian', 'Constant Baseline'], prominence=0.02, source=None)
    out = deT._compute_detailed_analysis(data, sorted(data), detailed_params(regions=[region], stability=True))
    st = out['stability']['R1P1']
    assert st is not None and st[2] >= 2
    assert st[1] - st[0] < deT.STABILITY_MAX_SPREAD_EV


def test_windows_inside_the_fill_pulse_are_left_out():
    data = synthetic_run()
    out = deT._compute_detailed_analysis(data, sorted(data), params(tFe=1.0))   # t1 min is 0.5 ms
    assert out['tFe'] == 1.0
    assert any('inside the fill pulse' in m for m in out['messages'])
    assert len(out['windowPeaks']) == params()['nWin']
    assert all(p['t1'] > 1.0 for p in out['resMw']['peaks'])


def detailed_source(out, nd=3.2e14, fill=None):
    data = synthetic_run()
    return dict(name=tcT.SOURCE_DETAILED, folder=None, tFe=out['tFe'], nd=nd,
                traps=[dict(peakId=t['peakId'], Et=t['Et'], Et_se=t['Et_se'], peaks=t['peaks']) for t in out['traps']],
                c0ByT={tc + 273.15: 500.0 * (1 + 0.001 * tc) for tc in data}, fillByT=fill or {}, fill=None,
                capMode='direct')


def test_trap_concentration_from_a_detailed_run():
    data = synthetic_run()
    out = deT._compute_detailed_analysis(data, sorted(data), params())
    source = detailed_source(out)
    # geometry and N_D(T) off: the Detailed Analysis Nt
    plain = dict(dP.default_geometry(), on=False, nd_scale=False)
    results, _ = tcT._compute_trap_concentration(source, 3.2e14, plain)
    (trap, tc), = results
    assert tc['Nt'] == pytest.approx(out['resMw']['Nt'], rel=1e-12)
    # on (C-V ratio, no C_fill): g < 1 raises Nt; N_D(T) follows C0(T)²
    results, geom = tcT._compute_trap_concentration(source, 3.2e14, dP.default_geometry())
    (trap, tc), = results
    assert tc['g_med'] < 1.0 and tc['Nt'] > out['resMw']['Nt']
    assert tc['geom']['src'].startswith('C-V ratio')
    for r in tc['rows']:
        assert r['nd_T'] == pytest.approx(3.2e14 * (np.interp(r['T_peak'], geom['T'], geom['C0'])
                                                    / np.interp(298.15, geom['T'], geom['C0'])) ** 2, rel=1e-12)
    text = tcT._trapconc_report(results, source, geom, 3.2e14)
    assert 'Nt (corrected)' in text and 'Checks' in text and 'R1P1' in text


def test_report_lists_the_fill_information():
    data = synthetic_run()
    out = deT._compute_detailed_analysis(data, sorted(data), params())
    source = detailed_source(out)
    source['fillByT'] = {T: dict(ok=True, v_rev=-5.0, v_fill=0.0, c_fill=c0 / 0.73, width_ms=1.0, note='')
                         for T, c0 in source['c0ByT'].items()}
    results, geom = tcT._compute_trap_concentration(source, 3.2e14, dP.default_geometry())
    (trap, tc), = results
    assert tc['geom']['src'] == 'measured C_fill'
    assert tc['geom']['W_F'] / tc['geom']['W_R'] == pytest.approx(0.73, rel=0.02)
    assert 'Fill pulse per record' in tcT._trapconc_report(results, source, geom, 3.2e14)

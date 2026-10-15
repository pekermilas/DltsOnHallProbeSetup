import os
import textwrap
import threading

import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import dltsConfig as dltsc
import dltsPhysics as dP
import detailedAnalysisTab as dA
import dataAnalysisTab as daT

# Trap Concentration: Nt with Dr. Kayi's v3.1 corrections (DrKayisCorrectionsScript.txt)
# -- N_D(T) = N_D (C0(T)/C0(T_ref))², the fill-pulse geometry factor g (W_R from
# C0(T), W_F from the measured C_fill, λ) and the optional large-signal term --
# from the traps of the last Detailed or Quick Analysis run. Those tabs find the
# peaks and fit Et / σ; this one only turns the peak heights into Nt, so changing
# a device input recalculates at once, without refitting. Also here: v3.1's
# fill-pulse scan analysis and its sample comparison. The physics is
# dltsPhysics (pure functions); the state is dltsc.trapconc_* globals, as in the
# other tabs. Temperatures are Kelvin, as in the other analysis tabs.

SOURCE_DETAILED = 'Detailed Analysis'
SOURCE_QUICK = 'Quick Analysis'
SOURCE_OPTIONS = [SOURCE_DETAILED, SOURCE_QUICK]

CTRL_BG = dA.CTRL_BG
TEXT_PRI, TEXT_SEC, TEXT_MUT = dA.TEXT_PRI, dA.TEXT_SEC, dA.TEXT_MUT
TRAP_COLORS = dA.TRAP_COLORS
SAMPLE_COLORS = ['#2a78d6', '#eb6834', '#2f9e6b', '#8a4fd6', '#c9a227', '#d6457a', '#3aa6b9', '#6b6b6b']
RECALC_DELAY_MS = 300     # debounce of the automatic recalculation while inputs are typed
SAMPLE_REDRAW_MS = 40     # debounce of the sample-comparison redraw while a slider is dragged


#---------------------SOURCES (PURE)-------------------------#
def _detailed_source():
    """(source, None) from the last Detailed Analysis run, or (None, reason).
    source = dict(name, folder, tFe, nd (the N_D that run used), traps
    [dict(peakId, Et, Et_se, peaks)], c0ByT {T (K): C0 (pF)}, fillByT
    {T (K): dP.fill_record_info}, fill (dP.fill_summary or None), capMode)."""
    traps = dltsc.detailed_lastTraps or []
    params = dltsc.detailed_lastParams
    if not traps or params is None or not dltsc.detailed_data:
        return None, 'Detailed Analysis has no result yet: Load Data and Run Analysis there first.'
    loadInfo = dltsc.detailed_loadInfo or {}
    return dict(name=SOURCE_DETAILED, folder=dltsc.detailed_folder, tFe=float(params.get('tFe', 0.0)),
                nd=float(params['nd']),
                traps=[dict(peakId=t['peakId'], Et=t['Et'], Et_se=t['Et_se'], peaks=t.get('peaks', [])) for t in traps],
                c0ByT={tc + 273.15: float(rec[2]) for tc, rec in dltsc.detailed_data.items()},
                fillByT=dict(loadInfo.get('fillByT') or {}), fill=loadInfo.get('fill'),
                capMode=loadInfo.get('cap_mode')), None

def _quick_source():
    """(source, None) from Quick Analysis' last Arrhenius solver run, or (None,
    reason); see _detailed_source. Quick Analysis keeps no bias monitor, so
    there is no C_fill (W_F falls back to the C-V ratio), and C0(T) is its
    data source's C∞ (same convention as Detailed Analysis' tail mean)."""
    traps = [t for t in (dltsc.arrhenius_trapResults or []) if t.get('peaks')]
    if not traps:
        return None, 'Quick Analysis has no Arrhenius result yet: run its Arrhenius solver first.'
    choice = dltsc.rateWindow_dataSourceVar.get() if dltsc.rateWindow_dataSourceVar is not None else daT.DATA_SOURCE_AUTO
    transients, label, _ = daT._get_processed_transients_for_source(choice)
    c0ByT = {}
    if transients:
        rbMs = daT._rb_ms_for_source(label, transients)
        c0ByT = {tc + 273.15: dA._cinf_range_mean(rec['time_ms'], rec['avg_cap_pf'], rbMs)
                 for tc, rec in transients.items()}
    return dict(name=SOURCE_QUICK + (f' ({label})' if label else ''), folder=None, tFe=float(traps[0].get('t_fe', 0.0)),
                nd=float(traps[0].get('nd', dA.DEFAULT_ND)),
                traps=[dict(peakId=t['peakId'], Et=t['Et'], Et_se=t['Et_se'], peaks=t['peaks']) for t in traps],
                c0ByT=c0ByT, fillByT={}, fill=None, capMode=None), None

def _compute_trap_concentration(source, nd, geom):
    """Nt of every trap of source (its fitted windows only) with the geometry
    settings geom (dP.default_geometry() shape; its T / C0 / CF arrays are
    filled here from the source's C0 and C_fill). Returns (results, geom):
    results [(trap, dP.trap_concentration result or None)]."""
    T, C0, CF = dP.geometry_arrays(source['c0ByT'], source['fillByT'])
    geom = dict(geom, T=T if T.size else None, C0=C0, CF=CF)
    results = []
    for trap in source['traps']:
        used = [p for p in trap['peaks'] if p.get('used', True)]
        results.append((trap, dP.trap_concentration(used, nd, trap['Et'], geom, source['tFe'])))
    return results, geom

def _wf_mode_label(mode):
    return next((label for label, key in dP.WF_MODES.items() if key == mode), mode)

def _trapconc_report(results, source, geom, nd):
    """Results text: settings, then per trap the corrected / uncorrected Nt,
    the geometry, the window table and the checks, then the fill-pulse
    information of every record."""
    L = ['=' * 66, '  Trap Concentration  —  Results', '=' * 66, '']
    L.append(f'  Source     : {source["name"]}')
    if source.get('folder'):
        L.append(f'  Folder     : {source["folder"]}')
    L.append(f'  t_FE       : {source["tFe"]:g} ms  (f(r), r = (t2 - t_FE)/(t1 - t_FE))')
    L.append(f'  N_D (C-V)  : {nd:.3e} cm-3' + (f',  N_D(T) = N_D (C0(T)/C0({geom["t_ref"]:g} K))²'
                                             if geom['nd_scale'] else ',  constant'))
    if geom['on']:
        L.append(f'  Geometry   : fill {geom["v_fill"]:g} V, reverse {geom["v_rev"]:g} V, Ø {geom["diam_mm"]:g} mm, '
                 f'ε_r {geom["eps_r"]:g}')
        L.append(f'               W_F from {_wf_mode_label(geom["wf_mode"])}'
                 + (f' (fall-back ratio {geom["wf_ratio"]:g})' if geom['wf_mode'] != dP.WF_MODE_VBI else
                    f' (V_bi {geom["vbi"]:g} V)'))
    else:
        L.append('  Geometry   : correction OFF (g = 1)')
    L.append('  Nt         : ' + ('N_D(T) a (2 - a) / g' if geom['ls'] else '2 N_D(T) a / g')
             + ',  a = S_pk / f(r), per window')
    for trap, tc in results:
        L += ['', '-' * 66, f'  Trap {trap["peakId"]}   Et = {dA._fmt_pm(trap["Et"], trap["Et_se"], ".4f", " +/- ")} eV']
        if tc is None:
            L.append('    no fitted windows')
            continue
        rows = tc['rows']
        L.append(f'    Nt (corrected)  = {dA._fmt_pm(tc["Nt"], tc["Nt_err"], ".3e", " +/- ")} cm-3  '
                 f'(weighted mean, {len(rows)} windows)')
        L.append(f'    Nt median       = {tc["Nt_median"]:.3e} cm-3  (± {tc["Nt_sd"]:.1e} window scatter, v3.1)')
        L.append(f'    Nt uncorrected  = {dA._fmt_pm(tc["Nt_raw"], tc["Nt_raw_err"], ".3e", " +/- ")} cm-3  '
                 f'(2 N_D(T) a, no g)')
        L.append(f'    Nt / N_D(T)     = {tc["frac"] * 100:.2f} %')
        L.append(f'    N_D(T) median   = {tc["nd_med"]:.3e} cm-3  (×{tc["nd_med"] / tc["nd"]:.3f} of N_D)')
        L.append(f'    a = S_pk/f, med = {tc["a_med"]:.4f};  f(r) median = {np.median([r["f"] for r in rows]):.4f}')
        gi = tc['geom']
        if gi:
            cf = f', C_fill = {gi["C_fill"]:.1f} pF' if np.isfinite(gi.get('C_fill', np.nan)) else ''
            L.append(f'    W_R = {gi["W_R"]:.2f} µm (C0 = {gi["C0"]:.1f} pF),  W_F = {gi["W_F"]:.2f} µm [{gi["src"]}{cf}]')
            L.append(f'    λ = {gi["lam"]:.2f} µm  ->  g = {gi["g"]:.3f} (median window; range '
                     f'{min(r["g"] for r in rows):.3f}-{max(r["g"] for r in rows):.3f})')
        L.append('')
        L.append(f'  {"t1(ms)":>7} {"t2(ms)":>7} {"Tp(K)":>7} {"Spk(1e-3)":>9} {"f(r)":>6} {"g":>6} '
                 f'{"N_D(T)":>9} {"Nt(cm-3)":>9} {"+/-":>8}')
        L.append('  ' + '-' * 76)
        for r in rows:
            err = f'{r["nt_err"]:8.1e}' if r['nt_err'] is not None else f'{"n/a":>8}'
            L.append(f'  {r["t1"]:7.2f} {r["t2"]:7.2f} {r["T_peak"]:7.2f} {r["S_peak"] * 1e3:9.4f} {r["f"]:6.4f} '
                     f'{r["g"]:6.3f} {r["nd_T"]:9.2e} {r["nt"]:9.2e} {err}')
        notes = dP.nt_checks(tc, geom, source.get('fill'), source.get('nd'))
        if notes:
            L.append('')
            L.append('  Checks')
            for note in notes:
                L.append(textwrap.fill(note, width=76, initial_indent='   - ', subsequent_indent='     '))
    fill = source.get('fillByT') or {}
    if fill:
        L += ['', '-' * 66, '  Fill pulse per record (AuxInput1)',
              f'  {"T(K)":>7} {"V_rev":>6} {"V_fill":>6} {"width":>6} {"C0(pF)":>8} {"C_fill":>8} {"C0/Cf":>6}  note']
        for T in sorted(fill):
            d = fill[T]
            c0 = source['c0ByT'].get(T, np.nan)
            cf = d.get('c_fill', np.nan)
            ratio = c0 / cf if np.isfinite(cf) and cf else np.nan
            L.append(f'  {T:7.2f} {d["v_rev"]:6.2f} {d["v_fill"]:6.2f} {d["width_ms"]:6.2f} {c0:8.2f} {cf:8.2f} '
                     f'{ratio:6.3f}  {d.get("note", "")}')
    return '\n'.join(L)


#---------------------Nt CALCULATION (GUI)-------------------------#
def _geometry_from_controls():
    """Geometry settings from the controls (raises TclError / ValueError on a bad entry)."""
    return dict(dP.default_geometry(), on=bool(dltsc.trapconc_geomOnVar.get()),
                v_fill=float(dltsc.trapconc_vFillVar.get()), v_rev=float(dltsc.trapconc_vRevVar.get()),
                vbi=float(dltsc.trapconc_vbiVar.get()), diam_mm=float(dltsc.trapconc_diamVar.get()),
                eps_r=float(dltsc.trapconc_epsRVar.get()),
                wf_mode=dP.WF_MODES.get(dltsc.trapconc_wfModeVar.get(), dP.WF_MODE_CFILL),
                wf_ratio=float(dltsc.trapconc_wfRatioVar.get()), ls=bool(dltsc.trapconc_lsVar.get()),
                nd_scale=bool(dltsc.trapconc_ndScaleVar.get()), t_ref=float(dltsc.trapconc_tRefVar.get()))

def _current_source():
    return _detailed_source() if dltsc.trapconc_sourceVar.get() == SOURCE_DETAILED else _quick_source()

def _set_status(text):
    if dltsc.trapconc_statusLabel is not None:
        dltsc.trapconc_statusLabel.config(text=text)

def _trapconc_calculate(log=True):
    """Recalculate Nt from the selected source with the current inputs, then
    redraw the panels and the results."""
    dltsc.trapconc_recalcJob = None
    source, reason = _current_source()
    if source is None:
        _set_status(reason)
        if log:
            dltsc.log_to_textbox(f"Trap concentration: {reason}")
        return
    try:
        geom = _geometry_from_controls()
        nd = float(dltsc.trapconc_ndVar.get())
        if nd <= 0:
            raise ValueError('N_D must be positive')
    except (tk.TclError, ValueError) as exc:
        _set_status(f'Check the inputs: {exc}')
        return
    try:
        results, geom = _compute_trap_concentration(source, nd, geom)
    except Exception as exc:
        _set_status(f'Calculation failed: {exc}')
        dltsc.log_to_textbox(f"Trap concentration: calculation failed: {exc}")
        return
    dltsc.trapconc_lastResults, dltsc.trapconc_lastSource, dltsc.trapconc_lastGeom = results, source, geom
    _trapconc_draw(results, source, geom)
    text = _trapconc_report(results, source, geom, nd)
    dltsc.trapconc_resultsText.configure(state='normal')
    dltsc.trapconc_resultsText.delete('1.0', 'end')
    dltsc.trapconc_resultsText.insert('end', text)
    dltsc.trapconc_resultsText.configure(state='disabled')
    summary = '   '.join(f'{trap["peakId"]}: Nt = {dA._fmt_pm(tc["Nt"], tc["Nt_err"], ".2e")} cm⁻³'
                           for trap, tc in results if tc is not None)
    _set_status(f'{source["name"]}:  {summary or "no fitted windows"}')
    if log:
        dltsc.log_to_textbox(f"Trap concentration ({source['name']}): {summary or 'no fitted windows'}")

def _trapconc_schedule_recalc(*_):
    """Debounced recalculation after an input changes (only once a result exists)."""
    if dltsc.trapconc_lastResults is None or dltsc.root is None:
        return
    if dltsc.trapconc_recalcJob is not None:
        try:
            dltsc.root.after_cancel(dltsc.trapconc_recalcJob)
        except Exception:
            pass
    dltsc.trapconc_recalcJob = dltsc.root.after(RECALC_DELAY_MS, lambda: _trapconc_calculate(log=False))

def _trapconc_read_biases(source=None, log=True):
    """Fill / reverse bias from the source's AuxInput1 records, when the fill
    bias is the same in all of them (v3.1 does this on load)."""
    if source is None:
        source, _ = _current_source()
    fs = (source or {}).get('fill')
    if not fs:
        if log:
            dltsc.log_to_textbox("Trap concentration: the source has no fill-pulse information (AuxInput1).")
        return
    if fs['v_fill_sd'] < 0.1:
        dltsc.trapconc_vFillVar.set(round(fs['v_fill'], 2))
        dltsc.trapconc_vRevVar.set(round(fs['v_rev'], 2))
        if log:
            dltsc.log_to_textbox(f"Trap concentration: fill {fs['v_fill']:+.2f} V / reverse {fs['v_rev']:+.2f} V "
                                 f"from AuxInput1 ({fs['n']} records).")
    elif log:
        dltsc.log_to_textbox(f"Trap concentration: the fill bias varies between records (sd {fs['v_fill_sd']:.2f} V); "
                             f"biases left as entered.")

def _trapconc_source_updated(which):
    """Called by Detailed / Quick Analysis after a run: recalculate when this
    tab follows that source."""
    selected = dltsc.trapconc_sourceVar.get() if dltsc.trapconc_sourceVar is not None else None
    if (which == 'detailed') != (selected == SOURCE_DETAILED):
        return
    source, _ = _current_source()
    if source is not None:
        _trapconc_read_biases(source, log=False)
    _trapconc_calculate(log=True)


#---------------------Nt PANELS-------------------------#
def _trapconc_draw(results, source, geom):
    """Four panels: C0 / C_fill vs T; W_R, W_F, λ at the peak temperatures; g
    and N_D(T)/N_D; Nt per window (corrected with errors, uncorrected open)
    with each trap's weighted mean."""
    fig = dltsc.trapconc_figure
    fig.clear()
    axC, axW, axG, axN = fig.subplots(2, 2).ravel()

    if geom.get('T') is not None:
        axC.plot(geom['T'], geom['C0'], 'o-', ms=3, color=TRAP_COLORS[0], label='C₀ (reverse bias)')
        if np.isfinite(geom['CF']).any():
            axC.plot(geom['T'], geom['CF'], 's-', ms=3, color=TRAP_COLORS[3], label='C_fill (end of fill pulse)')
        axC.legend(fontsize=7)
    axC.set_xlabel('T (K)'); axC.set_ylabel('C (pF)'); axC.set_title('Capacitance', fontsize=9)

    for i, (trap, tc) in enumerate(results):
        if tc is None:
            continue
        col = TRAP_COLORS[i % len(TRAP_COLORS)]
        Tp = np.array([r['T_peak'] for r in tc['rows']])
        infos = [r['info'] for r in tc['rows']]
        if all(info is not None for info in infos):
            axW.plot(Tp, [x['W_R'] for x in infos], 'o', color=col, label=f'{trap["peakId"]} W_R')
            axW.plot(Tp, [x['W_F'] for x in infos], 's', color=col, mfc='none', label=f'{trap["peakId"]} W_F')
            axW.plot(Tp, [x['lam'] for x in infos], '^', color=col, alpha=0.6, label=f'{trap["peakId"]} λ')
        axG.plot(Tp, [r['g'] for r in tc['rows']], 'o', color=col, label=f'{trap["peakId"]} g')
        axG.plot(Tp, [r['nd_T'] / tc['nd'] for r in tc['rows']], 'd', color=col, mfc='none',
                 label=f'{trap["peakId"]} N_D(T)/N_D')
        err = [r['nt_err'] if r['nt_err'] is not None else 0.0 for r in tc['rows']]
        axN.errorbar(Tp, [r['nt'] for r in tc['rows']], yerr=err, fmt='o', color=col, ms=4, capsize=2,
                     label=f'{trap["peakId"]} corrected')
        axN.plot(Tp, [r['nt_raw'] for r in tc['rows']], 'o', color=col, mfc='none', ms=4,
                 label=f'{trap["peakId"]} uncorrected')
        axN.axhline(tc['Nt'], color=col, lw=1)
        if tc['Nt_err'] is not None:
            axN.axhspan(tc['Nt'] - tc['Nt_err'], tc['Nt'] + tc['Nt_err'], color=col, alpha=0.12)
    if not geom['on']:
        axW.text(0.5, 0.5, 'Geometry correction off', transform=axW.transAxes, ha='center', color=TEXT_MUT)
    axW.set_xlabel('T_peak (K)'); axW.set_ylabel('width (µm)'); axW.set_title('Depletion widths', fontsize=9)
    axG.set_xlabel('T_peak (K)'); axG.set_ylabel('factor'); axG.set_title('Corrections', fontsize=9)
    axN.set_xlabel('T_peak (K)'); axN.set_ylabel('Nₜ (cm⁻³)'); axN.set_title('Nₜ per rate window', fontsize=9)
    for ax in (axW, axG, axN):
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=7)
    fig.suptitle(f'Trap concentration from {source["name"]}', fontsize=10)
    dltsc.trapconc_canvas.draw_idle()

def _trapconc_export_txt():
    txt = dltsc.trapconc_resultsText.get('1.0', 'end').strip() if dltsc.trapconc_resultsText is not None else ''
    if not txt:
        dltsc.log_to_textbox("Trap concentration: calculate first before exporting results.")
        return
    path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text file', '*.txt'), ('All files', '*.*')],
                                        initialfile='DLTS_TrapConcentration.txt')
    if path:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(txt)
        dltsc.log_to_textbox(f"Trap concentration: results exported to {path}")

def _save_figure(fig, initialfile, what):
    path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=dA._FIGURE_SAVE_FILETYPES,
                                        initialfile=initialfile)
    if not path:
        return None
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.svg', '.eps', '.pdf'):
            fig.savefig(path, bbox_inches='tight')
        else:
            fig.savefig(path, dpi=180, bbox_inches='tight', facecolor='white')
    except Exception as exc:
        dltsc.log_to_textbox(f"Trap concentration: failed to save the {what} figure: {exc}")
        return None
    dltsc.log_to_textbox(f"Trap concentration: {what} figure saved to {path}")
    return path


#---------------------FILL-PULSE SCAN-------------------------#
def _fs_add_folder():
    folder = filedialog.askdirectory(title='Fill-pulse scan folder (ZI csv export: bias or width scan)')
    if not folder:
        return
    dltsc.trapconc_fsFolders.append(folder)
    T = dP.scan_temperature_K(folder)
    if T is not None and len(dltsc.trapconc_fsFolders) == 1:
        dltsc.trapconc_fsTVar.set(round(T, 2))
    _fs_refresh_folders()

def _fs_clear_folders():
    dltsc.trapconc_fsFolders.clear()
    _fs_refresh_folders()

def _fs_refresh_folders():
    names = [os.path.basename(os.path.normpath(f)) for f in dltsc.trapconc_fsFolders]
    dltsc.trapconc_fsFolderLabel.config(text='\n'.join(names) if names else 'No scan folder added.')

def _fs_analyze():
    """Load and analyse the scan folders on a background thread, then show the
    panels and the report (uses N_D, diameter, ε_r and the large-signal option
    of the controls on the left)."""
    if not dltsc.trapconc_fsFolders:
        dltsc.log_to_textbox("Fill-pulse scan: add a bias- and/or width-scan folder first.")
        return
    try:
        args = dict(nd=float(dltsc.trapconc_ndVar.get()), diam_mm=float(dltsc.trapconc_diamVar.get()),
                    eps_r=float(dltsc.trapconc_epsRVar.get()), Et=float(dltsc.trapconc_fsEtVar.get()),
                    T_K=float(dltsc.trapconc_fsTVar.get()), t1=float(dltsc.trapconc_fsT1Var.get()),
                    t2=float(dltsc.trapconc_fsT2Var.get()), large_signal=bool(dltsc.trapconc_lsVar.get()))
    except (tk.TclError, ValueError) as exc:
        dltsc.log_to_textbox(f"Fill-pulse scan: check the inputs: {exc}")
        return
    folders = list(dltsc.trapconc_fsFolders)
    _set_status('Analysing fill-pulse scans...')

    def worker():
        res, error = None, None
        try:
            res = dP.merge_fill_scans([dP.analyze_fill_scan(dP.load_fill_scan(f), **args) for f in folders])
        except Exception as exc:
            error = str(exc)

        def apply():
            if error is not None:
                _set_status(f'Fill-pulse scan failed: {error}')
                dltsc.log_to_textbox(f"Fill-pulse scan: {error}")
                return
            dltsc.trapconc_fsResult = res
            _fs_draw(res)
            dltsc.trapconc_fsText.configure(state='normal')
            dltsc.trapconc_fsText.delete('1.0', 'end')
            dltsc.trapconc_fsText.insert('end', dP.fill_scan_report(res))
            dltsc.trapconc_fsText.configure(state='disabled')
            rec = [f'fill bias {res["rec_bias"]:+.2f} V' if res.get('rec_bias') is not None else '',
                   f'fill width {res["rec_width"]:g} ms' if res.get('rec_width') is not None else '']
            text = 'Fill-pulse scan: recommended ' + ', '.join(r for r in rec if r) if any(rec) else 'Fill-pulse scan done.'
            _set_status(text)
            dltsc.log_to_textbox(text)

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _fs_draw(res):
    fig = dltsc.trapconc_fsFigure
    fig.clear()
    axs = fig.subplots(2, 2).ravel()
    b, w = res['bias'], res['width']
    if b is not None:
        ok = b.flag == ''
        axs[0].errorbar(b.bias, b.dC, yerr=3 * b.err, fmt='o-', ms=3, color=TRAP_COLORS[0], capsize=1.5)
        axs[0].plot(b.bias[~ok], b.dC[~ok], 'rx')
        axs[0].axvline(res['rec_bias'], color='0.5', ls='--', lw=0.8)
        axs[0].set_xlabel('Fill bias (V)'); axs[0].set_ylabel('ΔC (pF)')
        axs[0].set_title(f'ΔC({res["t1"]:g}→{res["t2"]:g} ms); recommended {res["rec_bias"]:+.1f} V', fontsize=8)
        axs[2].plot(b.bias[ok], b.WF[ok], 's-', ms=3, color=TRAP_COLORS[0]); axs[2].set_xlabel('Fill bias (V)')
        axs[2].set_ylabel('W_F from C_fill (µm)', color=TRAP_COLORS[0])
        a2 = axs[2].twinx(); a2.plot(b.bias[ok], b.g[ok], 'o--', ms=3, color=TRAP_COLORS[3])
        a2.set_ylabel('g', color=TRAP_COLORS[3])
        axs[3].plot(b.bias[ok], b.Nt[ok] / 1e14, 'o-', ms=3, color=TRAP_COLORS[1]); axs[3].set_xlabel('Fill bias (V)')
        axs[3].set_ylabel('apparent Nₜ (10¹⁴ cm⁻³)'); axs[3].set_ylim(bottom=0)
    if w is not None:
        axs[1].semilogx(w.width, 100 * w.frac, 'o-', ms=3, color=TRAP_COLORS[3])
        axs[1].axhline(99, color='0.6', ls=':', lw=0.8); axs[1].axvline(res['rec_width'], color='0.5', ls='--', lw=0.8)
        axs[1].set_xlabel('Fill width (ms)'); axs[1].set_ylabel('ΔC, % of longest pulse')
        axs[1].set_title(f'recommended ≥ {res["rec_width"]:g} ms', fontsize=8)
    for ax in axs:
        ax.tick_params(labelsize=7); ax.xaxis.label.set_size(8); ax.yaxis.label.set_size(8)
    dltsc.trapconc_fsCanvas.draw_idle()

def _fs_save():
    if dltsc.trapconc_fsResult is None:
        dltsc.log_to_textbox("Fill-pulse scan: analyse a scan first.")
        return
    path = _save_figure(dltsc.trapconc_fsFigure, 'FillPulseScan.png', 'fill-pulse scan')
    if path:
        with open(os.path.splitext(path)[0] + '.txt', 'w', encoding='utf-8') as fh:
            fh.write(dP.fill_scan_report(dltsc.trapconc_fsResult))


#---------------------SAMPLE COMPARISON-------------------------#
def _sample_spectrum(smp, t1, t2):
    """(T (K), S, S_err) of one sample for the rate window (t1, t2)."""
    S, S_err = dA._rate_window_signal(smp['temps'], smp['records'], t1, t2)
    return np.array([tc + 273.15 for tc in smp['temps']]), S, S_err

def _register_sample(name, data, temps):
    names = {s['name'] for s in dltsc.trapconc_samples}
    base, i = name, 2
    while name in names:
        name = f'{base} ({i})'; i += 1
    col = SAMPLE_COLORS[len(dltsc.trapconc_samples) % len(SAMPLE_COLORS)]
    records = dA._prepare_signal_data(data, temps, dA.SIGNAL_METHOD_MEASURED, dA.DENOISE_NONE)
    dltsc.trapconc_samples.append(dict(name=name, data=data, temps=temps, records=records, color=col))
    dltsc.trapconc_sampleListbox.insert('end', f'{name}   [{temps[0] + 273.15:.0f}–{temps[-1] + 273.15:.0f} K]')
    dltsc.trapconc_sampleListbox.itemconfig('end', foreground=col)
    dltsc.trapconc_sampleNameVar.set('')
    _sample_replot()
    dltsc.log_to_textbox(f"Sample comparison: added \"{name}\" ({len(temps)} temperatures).")

def _sample_add_folder():
    """Load a sample folder with Detailed Analysis' loader and settings (grid,
    reverse bias, C0 window) in its worker process."""
    if dltsc.trapconc_spLoadingBusy:
        return
    base = filedialog.askdirectory(title='Select the data folder of the sample to add')
    if not base:
        return
    name = dltsc.trapconc_sampleNameVar.get().strip() or os.path.basename(os.path.normpath(base))
    try:
        args = (base, dltsc.detailed_gridOffVar.get(), dltsc.detailed_gridDtVar.get(),
                dltsc.detailed_chunkSizeVar.get(), dltsc.detailed_rbMsVar.get(), dltsc.detailed_cinfLoVar.get(),
                dltsc.detailed_cinfHiVar.get(), bool(dltsc.detailed_c0PrePulseVar.get()))
    except tk.TclError as exc:
        dltsc.log_to_textbox(f"Sample comparison: check Detailed Analysis' loader settings: {exc}")
        return
    dltsc.trapconc_spLoadingBusy = True
    _set_status(f'Loading sample "{name}"...')

    def worker():
        data, temps, error = {}, [], None
        try:
            data, temps, _ = dA._run_in_detailed_process(dA._load_detailed_data, *args)
            if not temps:
                error = 'no recognizable temperature data in that folder'
        except Exception as exc:
            error = str(exc)

        def apply():
            dltsc.trapconc_spLoadingBusy = False
            if error is not None:
                _set_status(f'Sample load failed: {error}')
                dltsc.log_to_textbox(f"Sample comparison: {name}: {error}")
                return
            _register_sample(name, data, temps)
            _set_status(f'Sample "{name}" added; {len(dltsc.trapconc_samples)} sample(s) plotted.')

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _sample_add_detailed():
    if not dltsc.detailed_data:
        dltsc.log_to_textbox("Sample comparison: load a dataset in Detailed Analysis first.")
        return
    folder = os.path.basename(os.path.normpath(dltsc.detailed_folder)) if dltsc.detailed_folder else ''
    name = dltsc.trapconc_sampleNameVar.get().strip() or folder or 'Detailed Analysis dataset'
    _register_sample(name, dltsc.detailed_data, dltsc.detailed_temps)

def _sample_remove():
    for i in sorted(dltsc.trapconc_sampleListbox.curselection(), reverse=True):
        dltsc.trapconc_sampleListbox.delete(i)
        del dltsc.trapconc_samples[i]
    _sample_replot()

def _sample_clear():
    dltsc.trapconc_sampleListbox.delete(0, 'end')
    dltsc.trapconc_samples.clear()
    _sample_replot()

def _sw_from_entry(*_):
    if dltsc.trapconc_swLock:
        return
    try:
        t1, t2 = float(dltsc.trapconc_swT1Var.get()), float(dltsc.trapconc_swT2Var.get())
    except (tk.TclError, ValueError):
        return
    dltsc.trapconc_swLock = True
    try:
        dltsc.trapconc_swS1Var.set(np.log10(max(t1, 0.1))); dltsc.trapconc_swS2Var.set(np.log10(max(t2, 0.1)))
    finally:
        dltsc.trapconc_swLock = False
    _sample_replot()

def _sw_from_scale(*_):
    if dltsc.trapconc_swLock:
        return
    dltsc.trapconc_swLock = True
    try:
        dltsc.trapconc_swT1Var.set(round(10 ** dltsc.trapconc_swS1Var.get(), 2))
        dltsc.trapconc_swT2Var.set(round(10 ** dltsc.trapconc_swS2Var.get(), 2))
    finally:
        dltsc.trapconc_swLock = False
    _sample_replot()

def _sample_replot(*_):
    """Debounced redraw so dragging a slider stays smooth."""
    if dltsc.root is None or dltsc.trapconc_spAx is None:
        return
    if dltsc.trapconc_spJob is not None:
        try:
            dltsc.root.after_cancel(dltsc.trapconc_spJob)
        except Exception:
            pass
    dltsc.trapconc_spJob = dltsc.root.after(SAMPLE_REDRAW_MS, _sample_draw)

def _sample_range():
    """Peak / fit range (K): the boxes, or Detailed Analysis' T min / T max when blank."""
    def num(var, fallback):
        try:
            return float(var.get())
        except (ValueError, tk.TclError):
            try:
                return float(fallback.get())
            except (ValueError, tk.TclError, AttributeError):
                return None
    return num(dltsc.trapconc_spTLoVar, dltsc.detailed_tpeakLoVar), num(dltsc.trapconc_spTHiVar, dltsc.detailed_tpeakHiVar)

def _sample_draw():
    dltsc.trapconc_spJob = None
    try:
        t1, t2 = float(dltsc.trapconc_swT1Var.get()), float(dltsc.trapconc_swT2Var.get())
    except (tk.TclError, ValueError):
        return
    ax = dltsc.trapconc_spAx
    ax.clear()
    if t2 <= t1 or t1 <= 0:
        dltsc.trapconc_swInfoLabel.config(text='t₂ must be larger than t₁')
        ax.text(0.5, 0.5, 't₂ must be larger than t₁', transform=ax.transAxes, ha='center', color=TEXT_MUT)
        dltsc.trapconc_spCanvas.draw_idle()
        return
    try:
        tFe = float(dltsc.detailed_tFeVar.get())
    except (tk.TclError, ValueError, AttributeError):
        tFe = 0.0
    en = dA._emission_rate(t1, t2, tFe) or dA._emission_rate(t1, t2)
    dltsc.trapconc_swInfoLabel.config(text=f'ratio t₂/t₁ = {t2 / t1:.2f}\neₙ = {en:.2f} s⁻¹  (τ = {1e3 / en:.2f} ms)'
                                           f'\nt_FE = {tFe:g} ms (Detailed Analysis)')
    norm = dltsc.trapconc_spNormVar.get()
    lo, hi = _sample_range()
    method = dltsc.detailed_peakMethodVar.get() if dltsc.detailed_peakMethodVar is not None else dA.PEAK_METHOD_DEFAULT
    lines = [f'  Rate window {t1:g}/{t2:g} ms   eₙ = {en:.2f} s⁻¹   peak finder: {method}',
             f'  {"Sample":<24} {"Tpeak(K)":>9} {"+/-":>6} {"Spk(1e-3)":>10}', '  ' + '-' * 52]
    csv = {}
    for smp in dltsc.trapconc_samples:
        T, S, S_err = _sample_spectrum(smp, t1, t2)
        pk = (dA._peak_from_signal(T, S, S_err, lo, hi, method, peak_min_frac=0.0)
              if lo is not None and hi is not None and ((T >= lo) & (T <= hi)).sum() >= 3 else dict(skipped=True))
        Sp = pk['S_peak'] if not pk['skipped'] else None
        scale = 1.0 / abs(Sp) if (norm and Sp) else 1e3
        col = smp['color']
        label = smp['name'] + (f'   Tₚ = {pk["Tp"]:.1f} K' if Sp is not None and dltsc.trapconc_spPeaksVar.get() else '')
        if dltsc.trapconc_spLineVar.get():
            ax.plot(T, S * scale, '-', color=col, lw=0.8, alpha=0.6, zorder=2)
        ax.plot(T, S * scale, 'o', ms=4.5, mfc=col, mec='white', mew=0.5, color=col, label=label, zorder=3)
        if Sp is not None and dltsc.trapconc_spFitVar.get() and pk['xFit'] is not None:
            ax.plot(pk['xFit'], np.asarray(pk['yFit']) * scale, color=col, lw=1.8, zorder=4)
        if Sp is not None and dltsc.trapconc_spPeaksVar.get():
            ax.plot([pk['Tp']], [Sp * scale], 'v', ms=8, mfc=col, mec=TEXT_PRI, mew=0.9, zorder=5)
        errTxt = f'{pk["Tp_err"]:6.2f}' if Sp is not None and pk['Tp_err'] is not None else f'{"-":>6}'
        lines.append(f'  {smp["name"][:24]:<24} ' + (f'{pk["Tp"]:9.2f} {errTxt} {Sp * 1e3:10.4f}' if Sp is not None
                                                      else f'{"-":>9} {"-":>6} {"-":>10}'))
        csv[smp['name']] = (T, S)
    dltsc.trapconc_spCsv = csv
    ax.axhline(0, color='0.75', lw=0.7)
    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('Normalised ΔC/C₀' if norm else 'ΔC/C₀ (×10⁻³)')
    ax.set_title(f'DLTS spectra, rate window {t1:g}/{t2:g} ms  (eₙ = {en:.1f} s⁻¹)', fontsize=10)
    if dltsc.trapconc_samples:
        ax.legend(fontsize=8, loc='upper left')
    else:
        ax.text(0.5, 0.5, 'Add a sample folder to plot its DLTS spectrum', transform=ax.transAxes, ha='center',
                color=TEXT_MUT)
    dltsc.trapconc_spCanvas.draw_idle()
    dltsc.trapconc_spText.configure(state='normal')
    dltsc.trapconc_spText.delete('1.0', 'end')
    dltsc.trapconc_spText.insert('end', '\n'.join(lines))
    dltsc.trapconc_spText.configure(state='disabled')

def _sample_export_csv():
    if not dltsc.trapconc_spCsv:
        dltsc.log_to_textbox("Sample comparison: add a sample first.")
        return
    path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')],
                                        initialfile='DLTS_samples_spectra.csv')
    if not path:
        return
    t1, t2 = dltsc.trapconc_swT1Var.get(), dltsc.trapconc_swT2Var.get()
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(f'# rate window t1={t1:g} ms, t2={t2:g} ms; dC/C0 (dimensionless)\n')
        for name, (T, S) in dltsc.trapconc_spCsv.items():
            fh.write(f'# sample: {name}\nT_K,dC_over_C0\n')
            for a, b in zip(T, S):
                fh.write(f'{a:g},{b:.6e}\n')
    dltsc.log_to_textbox(f"Sample comparison: spectra exported to {path}")


#---------------------TAB CONSTRUCTION-------------------------#
def _scrollable_column(parent, width):
    """A fixed-width, vertically scrolling control column; returns its inner frame."""
    outer = tk.Frame(parent, bg=CTRL_BG, width=width)
    outer.pack_propagate(False)
    canvas = tk.Canvas(outer, bg=CTRL_BG, highlightthickness=0, width=width - 17)
    vscroll = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)
    vscroll.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    inner = tk.Frame(canvas, bg=CTRL_BG, padx=10, pady=8)
    window = canvas.create_window((0, 0), window=inner, anchor='nw')
    inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
    canvas.bind('<Enter>', lambda e: canvas.bind_all(
        '<MouseWheel>', lambda ev: canvas.yview_scroll(int(-1 * (ev.delta / 120)), 'units')))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))
    return outer, inner

def _section(ctrl, title):
    tk.Frame(ctrl, bg='#1a3a5c', height=2).pack(fill='x', pady=(10, 2))
    tk.Label(ctrl, text=title.upper(), bg=CTRL_BG, fg='#1a3a5c', font=('Segoe UI', 8, 'bold')).pack(anchor='w')

def _row(ctrl, label, widget_factory, width=15):
    f = tk.Frame(ctrl, bg=CTRL_BG)
    f.pack(fill='x', pady=2)
    tk.Label(f, text=label, bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), width=width, anchor='w').pack(side='left')
    w = widget_factory(f)
    w.pack(side='left', fill='x', expand=True)
    return w

def _spinbox(parent, var, lo, hi, inc, fmt='%g'):
    return ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=inc, format=fmt, width=9,
                       font=('Segoe UI', 9))

def _hint(ctrl, text):
    tk.Label(ctrl, text=text, bg=CTRL_BG, fg=TEXT_MUT, font=('Segoe UI', 7, 'italic'), wraplength=250,
             justify='left').pack(anchor='w')

def _dark_text(parent, height=None):
    frame = tk.Frame(parent, bg=CTRL_BG)
    yscroll = ttk.Scrollbar(frame, orient='vertical')
    xscroll = ttk.Scrollbar(frame, orient='horizontal')
    text = tk.Text(frame, font=('Consolas', 9), bg='#1e1e2e', fg='#cdd6f4', insertbackground='white',
                   state='disabled', wrap='none', relief='flat', height=height or 10,
                   yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    yscroll.config(command=text.yview)
    xscroll.config(command=text.xview)
    xscroll.pack(side='bottom', fill='x')
    yscroll.pack(side='right', fill='y')
    text.pack(side='left', fill='both', expand=True)
    return frame, text

def _figure_panel(parent, figsize):
    fig = Figure(figsize=figsize, layout='constrained')
    canvas = FigureCanvasTkAgg(fig, master=parent)
    toolbar = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
    toolbar.update()
    toolbar.pack(side='bottom', fill='x')
    canvas.get_tk_widget().pack(fill='both', expand=True)
    return fig, canvas

def _build_nt_controls(ctrl):
    _section(ctrl, 'Source')
    dltsc.trapconc_sourceVar = tk.StringVar(value=SOURCE_DETAILED)
    _row(ctrl, 'Traps from', lambda p: ttk.Combobox(p, textvariable=dltsc.trapconc_sourceVar, values=SOURCE_OPTIONS,
                                                    state='readonly', font=('Segoe UI', 9)))
    _hint(ctrl, 'Et and the rate-window peaks of every trap of that tab\'s last run (its fitted windows). '
                'Nt follows each new run there and every input change here.')
    ttk.Button(ctrl, text='Calculate Nₜ', command=_trapconc_calculate).pack(fill='x', pady=(4, 0))

    _section(ctrl, 'Doping')
    dltsc.trapconc_ndVar = tk.DoubleVar(value=dA.DEFAULT_ND)
    _row(ctrl, 'N_D (cm⁻³)', lambda p: _spinbox(p, dltsc.trapconc_ndVar, 1e12, 1e18, 1e13, '%.2e'))
    dltsc.trapconc_ndScaleVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='N_D(T) = N_D·(C₀(T)/C₀(T_ref))²', variable=dltsc.trapconc_ndScaleVar).pack(anchor='w')
    dltsc.trapconc_tRefVar = tk.DoubleVar(value=dP.DEFAULT_T_REF_K)
    _row(ctrl, 'T_ref of C-V (K)', lambda p: _spinbox(p, dltsc.trapconc_tRefVar, 50, 1000, 5))
    _hint(ctrl, 'N_D should be the C-V profile averaged between W_F and W_R at the DLTS biases. Detailed Analysis '
                'keeps its own N_D for its uncorrected Nt.')

    _section(ctrl, 'Fill-pulse geometry')
    dltsc.trapconc_geomOnVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Fill-pulse geometry correction', variable=dltsc.trapconc_geomOnVar).pack(anchor='w')
    dltsc.trapconc_vFillVar = tk.DoubleVar(value=dP.DEFAULT_V_FILL)
    dltsc.trapconc_vRevVar = tk.DoubleVar(value=dP.DEFAULT_V_REV)
    _row(ctrl, 'Fill bias (V)', lambda p: _spinbox(p, dltsc.trapconc_vFillVar, -50, 10, 0.5))
    _row(ctrl, 'Reverse bias (V)', lambda p: _spinbox(p, dltsc.trapconc_vRevVar, -100, 0, 0.5))
    ttk.Button(ctrl, text='Read biases from AuxInput1', command=_trapconc_read_biases).pack(fill='x', pady=2)
    dltsc.trapconc_wfModeVar = tk.StringVar(value=next(iter(dP.WF_MODES)))
    _row(ctrl, 'W_F source', lambda p: ttk.Combobox(p, textvariable=dltsc.trapconc_wfModeVar, values=list(dP.WF_MODES),
                                                    state='readonly', font=('Segoe UI', 9)))
    dltsc.trapconc_wfRatioVar = tk.DoubleVar(value=dP.DEFAULT_WF_RATIO)
    _row(ctrl, 'W_F/W_R (C-V)', lambda p: _spinbox(p, dltsc.trapconc_wfRatioVar, 0.05, 1.0, 0.01, '%.3f'))
    dltsc.trapconc_vbiVar = tk.DoubleVar(value=dP.DEFAULT_VBI)
    _row(ctrl, 'V_bi (V)', lambda p: _spinbox(p, dltsc.trapconc_vbiVar, 0.5, 50, 0.1))
    dltsc.trapconc_diamVar = tk.DoubleVar(value=dP.DEFAULT_DIAM_MM)
    _row(ctrl, 'Diameter (mm)', lambda p: _spinbox(p, dltsc.trapconc_diamVar, 0.1, 50, 0.1))
    dltsc.trapconc_epsRVar = tk.DoubleVar(value=dP.DEFAULT_EPS_R)
    _row(ctrl, 'ε_r', lambda p: _spinbox(p, dltsc.trapconc_epsRVar, 5, 15, 0.1))
    dltsc.trapconc_lsVar = tk.BooleanVar(value=False)
    ttk.Checkbutton(ctrl, text='Large-signal term  Nₜ = N_D·a·(2-a)/g', variable=dltsc.trapconc_lsVar).pack(anchor='w')
    _hint(ctrl, 'g = [(W_R-λ)² - (W_F-λ)²] / W_R²: only traps between W_F-λ and W_R-λ are filled and emit.\n'
                'W_R = ε·A/C₀(T); λ = sqrt(2ε(E_F-Eₜ)/(q·N_D)) at each peak temperature.\n'
                'Measured C_fill: W_F = ε·A/C_fill(T), C_fill read at the end of the fill pulse in every record '
                '(needs AuxInput1); falls back to the C-V ratio.\n'
                'C-V ratio: W_F = (W_F/W_R)·W_R (0.762 for 0 V fill, 0.55 for +1.5 V, 25 °C).\n'
                'V_bi model: W_F = W_R·sqrt((V_bi+|V_fill|)/(V_bi+|V_rev|)), uniform doping.\n'
                'An estimate (±30 %): not reliable for strongly compensated / fully depleted layers.')

    _section(ctrl, '')
    ttk.Button(ctrl, text='Save Figure...', command=lambda: _save_figure(
        dltsc.trapconc_figure, 'DLTS_TrapConcentration.png', 'Nt')).pack(fill='x', pady=2)
    ttk.Button(ctrl, text='Export Results to TXT', command=_trapconc_export_txt).pack(fill='x', pady=2)

    for var in (dltsc.trapconc_sourceVar, dltsc.trapconc_ndVar, dltsc.trapconc_ndScaleVar, dltsc.trapconc_tRefVar,
                dltsc.trapconc_geomOnVar, dltsc.trapconc_vFillVar, dltsc.trapconc_vRevVar, dltsc.trapconc_wfModeVar,
                dltsc.trapconc_wfRatioVar, dltsc.trapconc_vbiVar, dltsc.trapconc_diamVar, dltsc.trapconc_epsRVar,
                dltsc.trapconc_lsVar):
        var.trace_add('write', _trapconc_schedule_recalc)

def _build_fill_scan_tab(parent):
    outer, ctrl = _scrollable_column(parent, 280)
    outer.pack(side='left', fill='y')
    right = tk.Frame(parent, bg=CTRL_BG)
    right.pack(side='left', fill='both', expand=True)

    _section(ctrl, 'Scan folders')
    _hint(ctrl, 'ZI csv exports of a fill-bias and/or a fill-width scan at one temperature (history names '
                'FP<width>ms<bias>V; needs the param1_avg, its header and the auxin0_avg files).')
    ttk.Button(ctrl, text='Add scan folder...', command=_fs_add_folder).pack(fill='x', pady=2)
    ttk.Button(ctrl, text='Clear folders', command=_fs_clear_folders).pack(fill='x', pady=2)
    dltsc.trapconc_fsFolderLabel = tk.Label(ctrl, text='No scan folder added.', bg=CTRL_BG, fg=TEXT_SEC,
                                            font=('Segoe UI', 8), justify='left', wraplength=250)
    dltsc.trapconc_fsFolderLabel.pack(anchor='w')

    _section(ctrl, 'Analysis')
    dltsc.trapconc_fsEtVar = tk.DoubleVar(value=0.63)
    _row(ctrl, 'Eₜ for λ (eV)', lambda p: _spinbox(p, dltsc.trapconc_fsEtVar, 0.05, 3.0, 0.01))
    _hint(ctrl, 'Z₁/₂ ≈ 0.63 eV at room temperature, EH₆/₇ ≈ 1.5 eV at 663 K.')
    dltsc.trapconc_fsTVar = tk.DoubleVar(value=298.15)
    _row(ctrl, 'Scan T (K)', lambda p: _spinbox(p, dltsc.trapconc_fsTVar, 50, 1000, 5))
    _hint(ctrl, 'Set from a "_<T>C" folder name when the first folder is added.')
    dltsc.trapconc_fsT1Var = tk.DoubleVar(value=5.0)
    dltsc.trapconc_fsT2Var = tk.DoubleVar(value=490.0)
    _row(ctrl, 't₁ after pulse (ms)', lambda p: _spinbox(p, dltsc.trapconc_fsT1Var, 0.5, 500, 1))
    _row(ctrl, 't₂ after pulse (ms)', lambda p: _spinbox(p, dltsc.trapconc_fsT2Var, 1, 2000, 10))
    _hint(ctrl, 'N_D, diameter, ε_r and the large-signal option come from the Nₜ controls.')
    ttk.Button(ctrl, text='Analyse scans', command=_fs_analyze).pack(fill='x', pady=(6, 2))
    ttk.Button(ctrl, text='Save report + figure...', command=_fs_save).pack(fill='x', pady=2)

    dltsc.trapconc_fsFigure, dltsc.trapconc_fsCanvas = _figure_panel(right, (7.2, 4.4))
    textFrame, dltsc.trapconc_fsText = _dark_text(right, height=14)
    textFrame.pack(side='bottom', fill='x', padx=4, pady=4, before=dltsc.trapconc_fsCanvas.get_tk_widget())

def _build_sample_tab(parent):
    outer, ctrl = _scrollable_column(parent, 280)
    outer.pack(side='left', fill='y')
    right = tk.Frame(parent, bg=CTRL_BG)
    right.pack(side='left', fill='both', expand=True)

    _section(ctrl, 'Samples')
    dltsc.trapconc_sampleNameVar = tk.StringVar(value='')
    _row(ctrl, 'Name (optional)', lambda p: ttk.Entry(p, textvariable=dltsc.trapconc_sampleNameVar))
    ttk.Button(ctrl, text='Add sample folder...', command=_sample_add_folder).pack(fill='x', pady=2)
    ttk.Button(ctrl, text='Add dataset loaded in Detailed Analysis', command=_sample_add_detailed).pack(fill='x', pady=2)
    _hint(ctrl, 'Folders load with Detailed Analysis\' loader settings (grid, reverse bias, C₀ window).')
    dltsc.trapconc_sampleListbox = tk.Listbox(ctrl, height=7, exportselection=False, font=('Segoe UI', 9),
                                              selectmode='extended')
    dltsc.trapconc_sampleListbox.pack(fill='x', pady=2)
    f = tk.Frame(ctrl, bg=CTRL_BG); f.pack(fill='x')
    ttk.Button(f, text='Remove selected', command=_sample_remove).pack(side='left', expand=True, fill='x')
    ttk.Button(f, text='Clear all', command=_sample_clear).pack(side='left', expand=True, fill='x')

    _section(ctrl, 'Single rate window (ms)')
    dltsc.trapconc_swT1Var = tk.DoubleVar(value=10.0)
    dltsc.trapconc_swT2Var = tk.DoubleVar(value=50.0)
    dltsc.trapconc_swS1Var = tk.DoubleVar(value=np.log10(10.0))
    dltsc.trapconc_swS2Var = tk.DoubleVar(value=np.log10(50.0))
    for label, var, svar in (('t₁', dltsc.trapconc_swT1Var, dltsc.trapconc_swS1Var),
                             ('t₂', dltsc.trapconc_swT2Var, dltsc.trapconc_swS2Var)):
        sb = _row(ctrl, label, lambda p, var=var: ttk.Spinbox(p, textvariable=var, from_=0.05, to=2000, increment=1,
                                                             width=8, format='%g', command=_sw_from_entry), width=4)
        sb.bind('<Return>', _sw_from_entry)
        sb.bind('<FocusOut>', _sw_from_entry)
        ttk.Scale(ctrl, from_=np.log10(0.1), to=np.log10(2000), variable=svar,
                  command=_sw_from_scale).pack(fill='x', pady=(0, 3))
    dltsc.trapconc_swInfoLabel = tk.Label(ctrl, text='', bg=CTRL_BG, fg=TEXT_SEC, font=('Consolas', 8), justify='left')
    dltsc.trapconc_swInfoLabel.pack(anchor='w')
    _hint(ctrl, 'Drag the sliders or type values: the plot updates live.')

    _section(ctrl, 'Display')
    dltsc.trapconc_spNormVar = tk.BooleanVar(value=False)
    dltsc.trapconc_spLineVar = tk.BooleanVar(value=True)
    dltsc.trapconc_spFitVar = tk.BooleanVar(value=False)
    dltsc.trapconc_spPeaksVar = tk.BooleanVar(value=True)
    for text, var in (('Normalise each spectrum to its peak', dltsc.trapconc_spNormVar),
                      ('Connect points with a line', dltsc.trapconc_spLineVar),
                      ('Overlay the peak fit (Detailed Analysis peak method)', dltsc.trapconc_spFitVar),
                      ('Mark the peak Tₚ', dltsc.trapconc_spPeaksVar)):
        ttk.Checkbutton(ctrl, text=text, variable=var, command=_sample_replot).pack(anchor='w')
    dltsc.trapconc_spTLoVar = tk.StringVar(value='')
    dltsc.trapconc_spTHiVar = tk.StringVar(value='')
    for label, var in (('Peak range min (K)', dltsc.trapconc_spTLoVar), ('Peak range max (K)', dltsc.trapconc_spTHiVar)):
        e = _row(ctrl, label, lambda p, var=var: ttk.Entry(p, textvariable=var, width=8))
        e.bind('<Return>', _sample_replot)
        e.bind('<FocusOut>', _sample_replot)
    _hint(ctrl, 'Blank = Detailed Analysis\' T min / T max, so the peaks are those of the same trap.')

    _section(ctrl, 'Export')
    ttk.Button(ctrl, text='Save Figure...', command=lambda: _save_figure(
        dltsc.trapconc_spFigure, 'DLTS_samples.png', 'sample comparison')).pack(fill='x', pady=2)
    ttk.Button(ctrl, text='Export spectra to CSV', command=_sample_export_csv).pack(fill='x', pady=2)

    dltsc.trapconc_spFigure, dltsc.trapconc_spCanvas = _figure_panel(right, (8, 5))
    dltsc.trapconc_spAx = dltsc.trapconc_spFigure.add_subplot(111)
    textFrame, dltsc.trapconc_spText = _dark_text(right, height=7)
    textFrame.pack(side='bottom', fill='x', padx=4, pady=4, before=dltsc.trapconc_spCanvas.get_tk_widget())
    _sample_replot()

def construct_trapConcentrationTab():
    tabControl = dltsc.tabControl
    tabControl.add(dltsc.trapConcentrationTab, text='Trap Concentration')
    tabControl.pack(expand=1, fill="both")

    # The app doesn't run dltsc.init(), so seed the state here.
    if dltsc.trapconc_fsFolders is None:
        dltsc.trapconc_fsFolders = list()
    if dltsc.trapconc_samples is None:
        dltsc.trapconc_samples = list()
    if dltsc.trapconc_swLock is None:
        dltsc.trapconc_swLock = False
    if dltsc.trapconc_spLoadingBusy is None:
        dltsc.trapconc_spLoadingBusy = False
    dltsc.trapconc_sourceUpdated = _trapconc_source_updated

    parent = dltsc.trapConcentrationTab
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Trap Concentration', font=('Segoe UI', 10, 'bold')).pack(side='left')
    ttk.Label(headerFrame, text='  (Nₜ with the N_D(T) and fill-pulse geometry corrections, fill-pulse scans, '
                                'sample comparison)', foreground=TEXT_SEC).pack(side='left')

    notebook = ttk.Notebook(parent)
    notebook.grid(row=1, column=0, sticky='nsew', padx=4, pady=(0, 4))

    # Nt: controls | panels | results, as in Detailed Analysis.
    ntTab = tk.Frame(notebook, bg=CTRL_BG)
    notebook.add(ntTab, text='  Nₜ  ')
    paned = ttk.PanedWindow(ntTab, orient='horizontal')
    paned.pack(fill='both', expand=True)
    outer, ctrl = _scrollable_column(paned, 295)
    paned.add(outer, weight=0)
    middle = tk.Frame(paned, bg=CTRL_BG)
    paned.add(middle, weight=1)
    dltsc.trapconc_statusLabel = ttk.Label(middle, text='Run Detailed or Quick Analysis, then Calculate Nₜ.')
    dltsc.trapconc_statusLabel.pack(side='bottom', fill='x', padx=6, pady=(0, 4))
    figFrame = tk.Frame(middle, bg=CTRL_BG)
    figFrame.pack(fill='both', expand=True)
    dltsc.trapconc_figure, dltsc.trapconc_canvas = _figure_panel(figFrame, (9, 7))
    resultsFrame = tk.LabelFrame(paned, text=' Results ', bg=CTRL_BG, fg=TEXT_SEC, font=('Consolas', 9))
    paned.add(resultsFrame, weight=0)
    textFrame, dltsc.trapconc_resultsText = _dark_text(resultsFrame)
    dltsc.trapconc_resultsText.configure(width=80)
    textFrame.pack(fill='both', expand=True, padx=4, pady=4)
    _build_nt_controls(ctrl)

    fsTab = tk.Frame(notebook, bg=CTRL_BG)
    notebook.add(fsTab, text='  Fill-pulse scan  ')
    _build_fill_scan_tab(fsTab)

    spTab = tk.Frame(notebook, bg=CTRL_BG)
    notebook.add(spTab, text='  Sample comparison  ')
    _build_sample_tab(spTab)

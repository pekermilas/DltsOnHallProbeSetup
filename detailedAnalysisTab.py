import os
import re
import threading

import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np
import pandas as pd
from scipy.stats import linregress
from scipy.interpolate import griddata

import matplotlib.pyplot as plt   # only for the plt.cm.* colormaps below -- never used to create a Figure (see _detailed_plot)
import matplotlib.ticker as mticker
import matplotlib.gridspec as mgridspec
from matplotlib.figure import Figure
from matplotlib.colors import Normalize, LogNorm
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.transforms import BboxTransformFrom

import dltsConfig as dltsc
import liveDataTab as ldT   # reuses its data-folder format detection/extraction -- see _load_detailed_data

# Ported from the standalone DLTS_APP.py ("DLTS Multiwindow Analysis" tool)
# into a tab of this app, following its conventions: module-level functions
# instead of a DLTSApp class, all state as dltsc.detailed_* globals instead of
# self.* instance attributes, heavy folder-scan/analysis work on a background
# thread (matching every other tab's loaders) instead of blocking the main
# thread, and dltsc.log_to_textbox() + status labels instead of messagebox
# popups (this app never uses modal dialogs for errors/status elsewhere).
# This tab keeps DLTS_APP.py's own data-folder convention (one subfolder per
# temperature, each holding a ZI imps_0_sample_param1_avg CSV) and its own
# multi-window Arrhenius pipeline -- a separate, self-contained analysis path
# from Qualitative Analysis / Automated Live Data / Quick Analysis, matching
# the original standalone app's design intent.

# ── Palette (from DLTS_APP.py) ──────────────────────────────────────────────
C0       = '#2a78d6'
C1       = '#eb6834'
SURFACE  = '#fcfcfb'
TEXT_PRI = '#0b0b0b'
TEXT_SEC = '#52514e'
TEXT_MUT = '#898781'
GRIDLINE = '#e1e0d9'
BASELINE = '#c3c2b7'
CTRL_BG  = '#f0f0f0'

# ── ZI grid defaults ─────────────────────────────────────────────────────────
DEFAULT_GRID_OFF   = -0.001
DEFAULT_GRID_DT    = 1.86667e-5
DEFAULT_CHUNK_SIZE = 32768
DEFAULT_RB_MS      = 500.0

# Matches both old-style "25C_001" and new-style "85C" / "n10C" temperature
# subfolder names.
_FOLDER_RE = re.compile(r'^(n?)(\d+)C(?:_\d+)?$', re.IGNORECASE)


#---------------------PURE ANALYSIS HELPERS (no GUI dependency)-------------------------#
def _folder_to_tempC(name):
    m = _FOLDER_RE.match(name)
    if not m:
        return None
    tc = float(m.group(2))
    return -tc if m.group(1).lower() == 'n' else tc

def _cap_at(t_ms, cap, tv_ms):
    return float(np.interp(tv_ms, t_ms, cap))

def _find_peak_parabolic(T_arr, S_arr, hw=2):
    ip = int(np.argmax(S_arr))
    lo, hi = max(ip - hw, 0), min(ip + hw + 1, len(T_arr))
    T_c, S_c = T_arr[lo:hi], S_arr[lo:hi]
    if len(T_c) < 3:
        return float(T_arr[ip])
    cf = np.polyfit(T_c, S_c, 2)
    if cf[0] < 0:
        Tp = -cf[1] / (2.0 * cf[0])
        lo_b = T_arr[max(ip - hw, 0)]
        hi_b = T_arr[min(ip + hw, len(T_arr) - 1)]
        if lo_b <= Tp <= hi_b:
            return float(Tp)
    return float(T_arr[ip])

def _load_detailed_data(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi):
    """Load every available temperature under base, auto-detecting which of
    this app's three data-folder formats it is (reusing liveDataTab.py's own
    detection/extraction, the same machinery Qualitative Analysis' folder
    scan uses -- see _scan_manual_directory_async there for the canonical
    three-way check this mirrors):
      1. a single combined ZI MFIA CSV export (one header CSV directly in
         base, temperatures told apart by chunk number within one data file);
      2. a subfolder-per-temperature ZI MFIA export (base holds one directory
         per temperature -- e.g. '0C'/'n10C'/'120C_000' -- each with its own
         single-chunk CSV): this tab's own original/native format, ported
         from DLTS_APP.py;
      3. legacy per-temperature files (flat JSON .txt or .csv, one file per
         temperature, e.g. 'n10p0.txt').
    Regardless of format, C_infinity is (re)computed here using this tab's
    OWN convention -- the mean capacitance over the [cinf_lo, cinf_hi]
    fraction of rb_ms (DLTS_APP.py's original range-averaged estimate) --
    rather than the single-nearest-sample convention liveDataTab.py's own
    extractors use for the rest of the app, so this tab's C_infinity
    estimation is unaffected by which format backed the raw transient.

    Pure computation (no Tk calls), safe to run on a background thread.
    Returns (data_dict, temps_list, errorMsgs) where data_dict[tc] =
    (t_ms, cap, c_inf), matching this tab's existing internal shape.
    """
    errorMsgs = []
    registry = {}
    ziParamsByFile = {}

    zi_headers = [f for f in os.listdir(base)
                 if re.search(r'imps_0_sample_param1_avg_header', f, re.IGNORECASE) and f.endswith('.csv')]
    if zi_headers:
        registry, ziInfo = ldT._compute_zi_dataset(base, zi_headers[0], errorMsgs)
        if ziInfo is not None:
            ziParamsByFile[ziInfo['dataFile']] = {
                'gridColOffset': ziInfo['gridColOffset'], 'gridColDelta': ziInfo['gridColDelta'],
                'chunkSize': ziInfo['chunkSize']}
    else:
        registry, ziParamsByFile = ldT._compute_zi_subfolder_dataset(base, errorMsgs)
        if not registry:
            registry = ldT._compute_legacy_dataset(base, errorMsgs)

    if not registry:
        return {}, [], errorMsgs

    allTemps = sorted(registry.keys())
    ziTemps = [t for t in allTemps if isinstance(registry[t], tuple) and registry[t][0] == 'zi']
    ziSubTemps = [t for t in allTemps if isinstance(registry[t], tuple) and registry[t][0] == 'zi_subfolder']
    legacyTemps = [t for t in allTemps if t not in ziTemps and t not in ziSubTemps]

    # cInfTargetMs only feeds ldT's own C_infinity estimate, which is
    # discarded and recomputed below using this tab's [cinf_lo, cinf_hi]
    # range-average convention instead.
    raw, extractionErrors = ldT._compute_mixed_transients(
        ziTemps, legacyTemps, 0.90 * rb_ms, registry, ziParamsByFile, rb_ms,
        samplingRateS=1.8666666666666665e-05, ziSubfolderTemps=ziSubTemps)
    errorMsgs.extend(extractionErrors)

    data = {}
    for tc, rec in raw.items():
        t_ms = rec['time_ms']
        cap = rec['avg_cap_pf']
        mi = (t_ms >= cinf_lo * rb_ms) & (t_ms <= cinf_hi * rb_ms)
        c_inf = float(np.nanmean(cap[mi])) if mi.any() else float(np.nanmean(cap))
        data[tc] = (t_ms, cap, c_inf)

    return data, sorted(data.keys()), errorMsgs

def _compute_arrhenius(windows, temps, data, gamma, t_peak_lo, t_peak_hi, peak_min_frac=0.05):
    T_K  = np.array([tc + 273.15 for tc in temps])
    mask = (T_K >= t_peak_lo) & (T_K <= t_peak_hi)
    T_m  = T_K[mask]

    en_list, Tp_list, Sp_list = [], [], []
    rows_detail = []

    for (t1, t2) in windows:
        S_full = np.array([
            (_cap_at(data[tc][0], data[tc][1], t2) - _cap_at(data[tc][0], data[tc][1], t1)) / data[tc][2]
            for tc in temps
        ])
        S_m = S_full[mask]
        if np.max(S_m) < abs(np.min(S_m)):
            S_m = -S_m
        peak_val = np.max(S_m)
        if peak_val <= peak_min_frac * np.max(np.abs(S_full)):
            continue
        Tp = _find_peak_parabolic(T_m, S_m)
        en = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
        en_list.append(en); Tp_list.append(Tp); Sp_list.append(peak_val)
        rows_detail.append((t1, t2, en, Tp - 273.15, peak_val))

    en_arr = np.array(en_list)
    Tp_arr = np.array(Tp_list)
    Sp_arr = np.array(Sp_list)
    if len(en_arr) < 2:
        return None

    x = 1000.0 / Tp_arr
    y = np.log(en_arr / Tp_arr**2)
    sl, ic, r, _, se = linregress(x, y)
    kB    = 8.617333e-5
    Et    = -sl * 1000.0 * kB
    Et_se = se  * 1000.0 * kB
    sigma = np.exp(ic) / gamma
    R2    = r**2
    return dict(en_arr=en_arr, Tp_arr=Tp_arr, Sp_arr=Sp_arr,
                Et=Et, Et_se=Et_se, sigma=sigma, R2=R2, N=len(en_arr),
                slope=sl, intercept=ic, x=x, y=y, detail=rows_detail)


#---------------------DATA LOADING-------------------------#
def _set_detailed_buttons_state(state):
    """Enable/disable Load/Run while a background worker is running. Run stays
    disabled on re-enable until data has actually been loaded at least once.
    """
    if dltsc.detailed_loadButton is not None:
        dltsc.detailed_loadButton.config(state=state)
    if dltsc.detailed_runButton is not None:
        if state == 'disabled':
            dltsc.detailed_runButton.config(state='disabled')
        else:
            dltsc.detailed_runButton.config(state='normal' if dltsc.detailed_data else 'disabled')

def _detailed_browse_folder():
    path = filedialog.askdirectory(title='Select DLTS Data Folder')
    if path:
        dltsc.detailed_baseVar.set(path)
        dltsc.log_to_textbox(f"Detailed analysis: selected {path} -- {ldT._describe_folder_contents(path)}")

def _detailed_load_data():
    """Scan the selected folder's temperature subfolders on a background
    thread, like every other folder loader in this app, so a large sweep
    never freezes the GUI.
    """
    if dltsc.detailed_loadingBusy or dltsc.detailedProcessingBusy:
        return
    base = dltsc.detailed_baseVar.get().strip()
    if not base or not os.path.isdir(base):
        dltsc.log_to_textbox("Detailed analysis: please select a valid data folder.")
        return

    dltsc.detailed_loadingBusy = True
    _set_detailed_buttons_state('disabled')
    if dltsc.detailed_statusLabel is not None:
        dltsc.detailed_statusLabel.config(text='Loading data...')

    gridOff = dltsc.detailed_gridOffVar.get()
    gridDt = dltsc.detailed_gridDtVar.get()
    chunkSize = dltsc.detailed_chunkSizeVar.get()
    rbMs = dltsc.detailed_rbMsVar.get()
    cinfLo = dltsc.detailed_cinfLoVar.get()
    cinfHi = dltsc.detailed_cinfHiVar.get()

    def worker():
        errorMsg = None
        data, temps, loadErrors = {}, [], []
        try:
            data, temps, loadErrors = _load_detailed_data(base, gridOff, gridDt, chunkSize, rbMs, cinfLo, cinfHi)
            if not temps:
                errorMsg = "No recognizable data found (checked ZI single-file, ZI subfolder-per-temperature, and legacy per-temperature formats)."
        except Exception as exc:
            errorMsg = str(exc)

        def apply():
            dltsc.detailed_loadingBusy = False
            if errorMsg is not None:
                _set_detailed_buttons_state('normal')
                dltsc.log_to_textbox(f"Detailed analysis: load failed: {errorMsg}")
                if dltsc.detailed_statusLabel is not None:
                    dltsc.detailed_statusLabel.config(text=f'Load failed: {errorMsg}')
                return

            dltsc.detailed_data = data
            dltsc.detailed_temps = temps
            _set_detailed_buttons_state('normal')
            n = len(temps)
            msg = f'{n} temperatures loaded: {temps[0]:.0f} °C to {temps[-1]:.0f} °C'
            if dltsc.detailed_loadInfoLabel is not None:
                dltsc.detailed_loadInfoLabel.config(text=msg, foreground=C0)
            if dltsc.detailed_statusLabel is not None:
                dltsc.detailed_statusLabel.config(text=msg)
            dltsc.log_to_textbox(f"Detailed analysis: {msg}")
            for err in loadErrors:
                dltsc.log_to_textbox(f"Detailed analysis: {err}")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()


#---------------------RUN ANALYSIS-------------------------#
def _detailed_run_analysis():
    if not dltsc.detailed_data:
        dltsc.log_to_textbox("Detailed analysis: load data first.")
        return
    if dltsc.detailed_loadingBusy or dltsc.detailedProcessingBusy:
        return

    dltsc.detailedProcessingBusy = True
    _set_detailed_buttons_state('disabled')
    if dltsc.detailed_statusLabel is not None:
        dltsc.detailed_statusLabel.config(text='Running analysis...')

    # Snapshot everything the worker needs so it never touches Tk widgets/variables.
    data = dltsc.detailed_data
    temps = dltsc.detailed_temps
    nWin = dltsc.detailed_nWinVar.get()
    t1Min = dltsc.detailed_t1MinVar.get()
    t1Max = dltsc.detailed_t1MaxVar.get()
    ratio = dltsc.detailed_ratioVar.get()
    stdWins = [(v1.get(), v2.get()) for v1, v2 in dltsc.detailed_stdEntries]
    gamma = dltsc.detailed_gammaVar.get()
    nd = dltsc.detailed_ndVar.get()
    tpLo = dltsc.detailed_tpeakLoVar.get()
    tpHi = dltsc.detailed_tpeakHiVar.get()
    rbMs = dltsc.detailed_rbMsVar.get()

    def worker():
        errorMsg = None
        resMw = resStd = None
        mw = []
        T_K = None
        Nt = None
        try:
            t1Arr = np.logspace(np.log10(t1Min), np.log10(t1Max), nWin)
            mw = [(float(t1), float(ratio * t1)) for t1 in t1Arr]

            resMw = _compute_arrhenius(mw, temps, data, gamma, tpLo, tpHi)
            resStd = _compute_arrhenius(stdWins, temps, data, gamma, tpLo, tpHi)

            if resMw is None:
                raise ValueError('Multi-window: no peaks found. Check t1 range and temperature bounds.')

            T_K = np.array([tc + 273.15 for tc in temps])
            S_ref = np.array([
                (_cap_at(data[tc][0], data[tc][1], rbMs) - _cap_at(data[tc][0], data[tc][1], 2.0)) / data[tc][2]
                for tc in temps
            ])
            Nt = 2.0 * float(np.nanmax(np.abs(S_ref))) * nd
        except Exception as exc:
            errorMsg = str(exc)

        def apply():
            dltsc.detailedProcessingBusy = False
            _set_detailed_buttons_state('normal')
            if errorMsg is not None:
                dltsc.log_to_textbox(f"Detailed analysis: {errorMsg}")
                if dltsc.detailed_statusLabel is not None:
                    dltsc.detailed_statusLabel.config(text=f'Error: {errorMsg}')
                return

            # Plotting itself must happen on the main thread (matplotlib/Tk
            # artists aren't thread-safe); only the number-crunching above ran
            # on the worker.
            _detailed_plot(resMw, resStd, mw, stdWins, T_K, Nt)
            _detailed_write_results(resMw, resStd, Nt)

            dltsc.detailed_lastResMw = resMw
            dltsc.detailed_lastResStd = resStd
            dltsc.detailed_lastNt = Nt

            statusMsg = (f'Done.  Et = {resMw["Et"]:.3f} ± {resMw["Et_se"]:.3f} eV  '
                        f'Nt = {Nt:.2e} cm⁻³')
            if dltsc.detailed_statusLabel is not None:
                dltsc.detailed_statusLabel.config(text=statusMsg)
            dltsc.log_to_textbox(f"Detailed analysis: {statusMsg}")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()


#---------------------PLOTTING-------------------------#
def _detailed_plot(res_mw, res_std, mw, std_wins, T_K, Nt):
    show_spectra = dltsc.detailed_showSpectraVar.get()
    show_tmap    = dltsc.detailed_showTmapVar.get()
    show_rwm     = dltsc.detailed_showRwmVar.get()
    n_spectra    = dltsc.detailed_nSpectraVar.get()
    data  = dltsc.detailed_data
    temps = dltsc.detailed_temps

    # Clear previous canvas
    for w in dltsc.detailed_figFrame.winfo_children():
        w.destroy()
    dltsc.detailed_figure = None

    dltsc.detailed_ax1 = dltsc.detailed_ax2 = dltsc.detailed_ax3 = dltsc.detailed_ax4 = None
    dltsc.detailed_leg1 = dltsc.detailed_leg2 = dltsc.detailed_legM = dltsc.detailed_legRW = None
    dltsc.detailed_annBox = None
    _pending_drags = []   # list of ('legend'|'annot', obj), applied AFTER canvas connects

    ax2 = ax3 = ax4 = None
    CL = dict(constrained_layout=True)

    # Figure() directly, never plt.figure()/plt.subplots(): those register the
    # figure with pyplot's global state, which (under the TkAgg backend this
    # app uses) gives it its own separate FigureManager/Tk window in addition
    # to the one explicitly embedded below via FigureCanvasTkAgg -- a second,
    # redundant popup showing the exact same plot. Figure() has no pyplot
    # registration, so only the embedded canvas exists, matching how every
    # other tab in this app builds its figures (see dataAnalysisTab.py,
    # liveDataTab.py).
    if show_spectra and show_tmap and show_rwm:
        fig = Figure(figsize=(14, 11.0), facecolor=SURFACE, **CL)
        gs  = mgridspec.GridSpec(2, 2, figure=fig, height_ratios=[1.0, 0.9], width_ratios=[1.0, 1.0])
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])
    elif show_spectra and show_tmap and not show_rwm:
        fig = Figure(figsize=(13, 10.5), facecolor=SURFACE, **CL)
        gs  = mgridspec.GridSpec(2, 2, figure=fig, height_ratios=[1.0, 0.85], width_ratios=[1.5, 1.0])
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[1, :])
    elif show_spectra and not show_tmap and show_rwm:
        fig = Figure(figsize=(13, 10.5), facecolor=SURFACE, **CL)
        gs  = mgridspec.GridSpec(2, 2, figure=fig, height_ratios=[1.0, 0.85], width_ratios=[1.5, 1.0])
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax4 = fig.add_subplot(gs[1, :])
    elif not show_spectra and show_tmap and show_rwm:
        fig = Figure(figsize=(14, 10.5), facecolor=SURFACE, **CL)
        gs  = mgridspec.GridSpec(2, 2, figure=fig, height_ratios=[1.0, 0.9])
        ax1 = fig.add_subplot(gs[0, :])
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])
    elif show_spectra and not show_tmap and not show_rwm:
        fig = Figure(figsize=(13, 5.4), facecolor=SURFACE, **CL)
        ax1, ax2 = fig.subplots(1, 2, gridspec_kw={'width_ratios': [1.5, 1]})
    elif not show_spectra and show_tmap and not show_rwm:
        fig = Figure(figsize=(10, 10.5), facecolor=SURFACE, **CL)
        gs  = mgridspec.GridSpec(2, 1, figure=fig, height_ratios=[1.0, 0.85])
        ax1 = fig.add_subplot(gs[0])
        ax3 = fig.add_subplot(gs[1])
    elif not show_spectra and not show_tmap and show_rwm:
        fig = Figure(figsize=(10, 10.5), facecolor=SURFACE, **CL)
        gs  = mgridspec.GridSpec(2, 1, figure=fig, height_ratios=[1.0, 0.85])
        ax1 = fig.add_subplot(gs[0])
        ax4 = fig.add_subplot(gs[1])
    else:   # Arrhenius only
        fig = Figure(figsize=(8, 5.4), facecolor=SURFACE, **CL)
        ax1 = fig.subplots()

    dltsc.detailed_figure = fig
    dltsc.detailed_ax1 = ax1; dltsc.detailed_ax2 = ax2
    dltsc.detailed_ax3 = ax3; dltsc.detailed_ax4 = ax4
    for ax in filter(None, [ax1, ax2, ax3]):
        ax.set_facecolor(SURFACE)

    # ── Arrhenius panel ───────────────────────────────────────────────────
    x_all = np.concatenate([res_mw['x'], res_std['x'] if res_std else res_mw['x']])
    x_lo  = x_all.min() * 0.97
    x_hi  = x_all.max() * 1.03
    x_line = np.linspace(x_lo, x_hi, 400)

    y_lm = res_mw['slope'] * x_line + res_mw['intercept']
    xmw  = res_mw['x']; n_mw = len(xmw); xb = xmw.mean()
    Sxx  = ((xmw - xb) ** 2).sum()
    ss   = np.sum((res_mw['y'] - (res_mw['slope'] * xmw + res_mw['intercept'])) ** 2)
    se_y = np.sqrt(ss / max(n_mw - 2, 1))
    half = 2.0 * se_y * np.sqrt(1 / n_mw + (x_line - xb) ** 2 / Sxx)
    ax1.fill_between(x_line, y_lm - half, y_lm + half, color=C0, alpha=0.13, zorder=1)
    ax1.plot(x_line, y_lm, color=C0, lw=2.0, zorder=3,
             label=(f'Multi ({res_mw["N"]} win)  Et={res_mw["Et"]:.3f}±{res_mw["Et_se"]:.3f} eV  '
                    f'R²={res_mw["R2"]:.4f}'))

    if res_std and dltsc.detailed_stdWinsVar.get():
        y_ls = res_std['slope'] * x_line + res_std['intercept']
        ax1.plot(x_line, y_ls, color=C1, lw=1.5, ls='--', zorder=3,
                 label=(f'Standard ({res_std["N"]} win)  Et={res_std["Et"]:.3f}±{res_std["Et_se"]:.3f} eV  '
                        f'R²={res_std["R2"]:.4f}'))
        ax1.scatter(res_std['x'], res_std['y'], color=C1, s=100, zorder=5, marker='D',
                    edgecolors=TEXT_PRI, lw=0.7, label='Standard windows')

    cmap_arr = plt.cm.plasma
    norm_arr = Normalize(np.log10(res_mw['en_arr'].min()), np.log10(res_mw['en_arr'].max()))
    sc = ax1.scatter(res_mw['x'], res_mw['y'], c=np.log10(res_mw['en_arr']),
                     cmap=cmap_arr, norm=norm_arr, s=55, zorder=4, edgecolors=C0, lw=0.5)
    cb = fig.colorbar(sc, ax=ax1, pad=0.01, fraction=0.025, aspect=28)
    cb.set_label('log₁₀ eₙ  (s⁻¹)', fontsize=8, color=TEXT_SEC)
    cb.ax.tick_params(labelsize=7.5, colors=TEXT_MUT)
    cb.outline.set_edgecolor(BASELINE)

    res_txt = (
        f'Multi-window  ({res_mw["N"]} pts)\n'
        f'Et = {res_mw["Et"]:.3f} ± {res_mw["Et_se"]:.3f} eV\n'
        f'σⁿ = {res_mw["sigma"]:.2e} cm²\n'
        f'Nt = {Nt:.2e} cm⁻³\n'
        f'R² = {res_mw["R2"]:.4f}'
    )
    ann_box = ax1.annotate(
        res_txt, xy=(0.42, 0.98), xycoords='axes fraction', xytext=(0.42, 0.98), textcoords='axes fraction',
        fontsize=8, va='top', ha='left', color=TEXT_PRI, fontfamily='monospace', annotation_clip=False,
        bbox=dict(boxstyle='round,pad=0.45', facecolor='#fffbe6', edgecolor=GRIDLINE, alpha=0.96))
    dltsc.detailed_annBox = ann_box
    _pending_drags.append(('annot', ann_box))

    ax1b = ax1.twiny()
    ax1b.set_xlim(ax1.get_xlim())
    K_ticks = np.arange(240, 370, 10)
    K_ok = K_ticks[(1000 / K_ticks >= x_lo) & (1000 / K_ticks <= x_hi)]
    if len(K_ok):
        ax1b.set_xticks(1000 / K_ok)
        ax1b.set_xticklabels([f'{k - 273:.0f}°C' for k in K_ok], fontsize=7.5)
    ax1b.tick_params(colors=TEXT_MUT, labelsize=7.5)
    ax1b.spines[['top', 'left', 'right']].set_color(BASELINE)

    ax1.set_xlabel('1000 / T  (K⁻¹)', fontsize=10, color=TEXT_PRI, labelpad=5)
    ax1.set_ylabel('ln(eₙ / T²)  (s⁻¹ K⁻²)', fontsize=10, color=TEXT_PRI, labelpad=5)
    ax1.set_title('Arrhenius Plot', fontsize=11, color=TEXT_PRI, fontweight='bold', pad=8)
    ax1.grid(which='major', color=GRIDLINE, lw=0.55)
    ax1.minorticks_off()
    ax1.spines[['top', 'right']].set_visible(False)
    ax1.spines[['left', 'bottom']].set_color(BASELINE)
    ax1.tick_params(colors=TEXT_MUT, labelsize=9)

    leg1 = ax1.legend(loc='upper right', fontsize=7.5, frameon=True, framealpha=0.92,
                      edgecolor=GRIDLINE, facecolor=SURFACE, labelcolor=TEXT_PRI, handlelength=2.0)
    dltsc.detailed_leg1 = leg1
    _pending_drags.append(('legend', leg1))

    # ── DLTS spectra panel ────────────────────────────────────────────────
    if ax2 is not None:
        idx_show = np.round(np.linspace(0, len(mw) - 1, min(n_spectra, len(mw)))).astype(int)
        cmap_w = plt.cm.cool
        norm_w = Normalize(0, len(mw) - 1)
        ax2.axhline(0, color=BASELINE, lw=0.7)

        for k in idx_show:
            t1, t2 = mw[k]
            S = np.array([
                (_cap_at(data[tc][0], data[tc][1], t2) - _cap_at(data[tc][0], data[tc][1], t1)) / data[tc][2] * 1e3
                for tc in temps
            ])
            en  = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
            col = cmap_w(norm_w(k))
            ax2.plot(T_K - 273.15, S, color=col, lw=1.4,
                     label=f't={t1:.0f}/{t2:.0f} ms  eₙ={en:.1f} s⁻¹')

        for Tp_v in res_mw['Tp_arr']:
            ax2.axvline(Tp_v - 273.15, color=TEXT_MUT, lw=0.4, ls=':', alpha=0.5)

        ax2.set_xlabel('Temperature  (°C)', fontsize=10, color=TEXT_PRI)
        ax2.set_ylabel('ΔC/C₀  (×10⁻³)', fontsize=10, color=TEXT_PRI)
        ax2.set_title('DLTS Spectra', fontsize=11, color=TEXT_PRI, fontweight='bold', pad=8)
        ax2.grid(which='major', color=GRIDLINE, lw=0.55)
        ax2.minorticks_off()
        ax2.spines[['top', 'right']].set_visible(False)
        ax2.spines[['left', 'bottom']].set_color(BASELINE)
        ax2.tick_params(colors=TEXT_MUT, labelsize=9)

        leg2 = ax2.legend(loc='upper left', fontsize=7, frameon=True, framealpha=0.90,
                          edgecolor=GRIDLINE, facecolor=SURFACE, labelcolor=TEXT_PRI)
        dltsc.detailed_leg2 = leg2
        _pending_drags.append(('legend', leg2))

    # ── 2D transient map ──────────────────────────────────────────────────
    if ax3 is not None:
        leg_m = _detailed_plot_transient_map(ax3, res_mw, T_K)
        if leg_m is not None:
            dltsc.detailed_legM = leg_m
            _pending_drags.append(('legend', leg_m))

    # ── Rate-Window Analysis map ───────────────────────────────────────────
    if ax4 is not None:
        leg_rw = _detailed_plot_rate_window_map(ax4, res_mw)
        if leg_rw is not None:
            dltsc.detailed_legRW = leg_rw
            _pending_drags.append(('legend', leg_rw))

    fig.suptitle('DLTS Multiwindow Analysis', fontsize=12, color=TEXT_PRI, fontweight='bold', y=1.001)

    # Embed in tkinter FIRST -- this connects fig.canvas, which draggable needs.
    dltsc.detailed_canvas = FigureCanvasTkAgg(fig, master=dltsc.detailed_figFrame)
    dltsc.detailed_canvas.draw()
    toolbar = NavigationToolbar2Tk(dltsc.detailed_canvas, dltsc.detailed_figFrame, pack_toolbar=False)
    toolbar.update()
    toolbar.pack(side='bottom', fill='x')
    dltsc.detailed_canvas.get_tk_widget().pack(fill='both', expand=True)

    # ── Drag installation ─────────────────────────────────────────────────
    # matplotlib 3.10 changed DraggableBase to use pick_event, which requires
    # legendPatch.contains() to use an up-to-date renderer transform. After
    # pack(fill='both'), tkinter resizes the canvas and the transform is
    # stale. Bypass the built-in draggable system entirely: wire
    # button_press/motion/release events directly so we re-fetch the artist
    # bbox at click time (see _detailed_install_drag()).
    _drag_snapshot = list(_pending_drags)

    def _apply_draggable():
        if dltsc.detailed_canvas is None:
            return
        dltsc.detailed_canvas.draw()
        canvas_ = dltsc.detailed_canvas
        fig_ = fig
        for kind, obj in _drag_snapshot:
            _detailed_install_drag(canvas_, fig_, obj, kind)

    dltsc.root.after(300, _apply_draggable)


#---------------------DRAGGABLE LEGENDS / ANNOTATIONS-------------------------#
def _detailed_install_drag(canvas, fig, artist, kind):
    """Wire button_press/motion/release drag to a Legend or Annotation.

    Bypasses matplotlib's pick_event-based DraggableBase so that dragging
    works even when the canvas has been resized after the initial draw().
    The legend's _loc tuple and the annotation's xyann are updated in the
    correct coordinate spaces so the artists persist at their new positions.

    kind : 'legend' | 'annot'
    """
    s = {'on': False, 'mx0': 0.0, 'my0': 0.0, 'ax': 0.0, 'ay': 0.0}   # saved anchor in display px

    def _on_press(evt):
        if evt.button != 1:
            return
        canvas.draw()   # refresh transforms before hit-testing
        try:
            hit, _ = artist.contains(evt)
        except Exception:
            return
        if not hit:
            return
        s['on']  = True
        s['mx0'] = evt.x
        s['my0'] = evt.y
        if kind == 'annot':
            s['ax'], s['ay'] = artist.get_transform().transform(artist.xyann)
        else:                                   # legend
            try:
                rend = fig._get_renderer()
                bb   = artist.get_window_extent(rend)
                s['ax'], s['ay'] = bb.x0, bb.y0
            except Exception:
                s['on'] = False

    def _on_motion(evt):
        if not s['on'] or evt.x is None or evt.y is None:
            return
        dx = evt.x - s['mx0']
        dy = evt.y - s['my0']
        try:
            if kind == 'annot':
                t = artist.get_transform()
                artist.xyann = t.inverted().transform((s['ax'] + dx, s['ay'] + dy))
            else:                               # legend
                new_x = s['ax'] + dx
                new_y = s['ay'] + dy
                bbox = artist.get_bbox_to_anchor()
                x_loc, y_loc = BboxTransformFrom(bbox).transform((new_x, new_y))
                artist._loc = (float(x_loc), float(y_loc))
        except Exception:
            return
        canvas.draw_idle()

    def _on_release(evt):
        s['on'] = False

    canvas.mpl_connect('button_press_event',   _on_press)
    canvas.mpl_connect('motion_notify_event',  _on_motion)
    canvas.mpl_connect('button_release_event', _on_release)


#---------------------2D TRANSIENT MAP-------------------------#
def _detailed_plot_transient_map(ax, res_mw, T_K):
    """Filled contour plot: ΔC/C0(t, T) on log-time y-axis.
    Returns the legend object (or None) so the caller can make it draggable."""
    rb_ms = dltsc.detailed_rbMsVar.get()
    temps = dltsc.detailed_temps
    data  = dltsc.detailed_data

    t_ms_ref = data[temps[0]][0]          # full axis in ms
    t_lo_ms  = max(2.0, t_ms_ref[1])      # skip pre-pulse / first point
    t_hi_ms  = rb_ms * 0.95

    mask_t    = (t_ms_ref >= t_lo_ms) & (t_ms_ref <= t_hi_ms)
    t_ms_full = t_ms_ref[mask_t]

    if len(t_ms_full) < 10:
        ax.text(0.5, 0.5, 'Not enough time points', transform=ax.transAxes, ha='center', fontsize=11, color=TEXT_MUT)
        return None

    n_t   = min(250, len(t_ms_full))
    idx_l = np.unique(np.round(np.logspace(0, np.log10(len(t_ms_full) - 1), n_t)).astype(int))
    idx_l = np.clip(idx_l, 0, len(t_ms_full) - 1)
    t_ms  = t_ms_full[idx_l]
    t_s   = t_ms * 1e-3                    # seconds

    Z = np.empty((len(t_ms), len(temps)))
    for j, tc in enumerate(temps):
        t_j, cap_j, cinf_j = data[tc]
        if abs(cinf_j) < 1e-30:
            Z[:, j] = 0.0
            continue
        cap_interp = np.interp(t_ms, t_j, cap_j)
        Z[:, j] = (cap_interp - cinf_j) / cinf_j

    Z_disp = Z * 1e5

    vlo = float(np.nanpercentile(Z_disp, 1))
    vhi = float(np.nanpercentile(Z_disp, 99))
    if vhi <= vlo:
        vlo, vhi = -1e-4, 1e-4
    n_lev  = 64
    levels = np.linspace(vlo, vhi, n_lev)

    Tm, tm = np.meshgrid(T_K, t_s)

    cf = ax.contourf(Tm, tm, Z_disp, levels=levels, cmap='jet', extend='both')
    ax.contour(Tm, tm, Z_disp, levels=levels[::6], colors='k', linewidths=0.25, alpha=0.35)

    ax.set_yscale('log')
    ax.set_xlabel('Temperature  (K)', fontsize=10, color=TEXT_PRI, labelpad=5)
    ax.set_ylabel('Time  (s)', fontsize=10, color=TEXT_PRI, labelpad=5)
    ax.set_title('ΔC/C₀  Transient Map', fontsize=11, color=TEXT_PRI, fontweight='bold', pad=8)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color(BASELINE)
    ax.tick_params(colors=TEXT_MUT, labelsize=9)

    cbar = dltsc.detailed_figure.colorbar(cf, ax=ax, pad=0.01, fraction=0.015, aspect=42)
    cbar.set_label('ΔC/C₀  (×10⁻⁵)', fontsize=9, color=TEXT_SEC)
    cbar.ax.tick_params(labelsize=8, colors=TEXT_MUT)
    cbar.outline.set_edgecolor(BASELINE)

    # ── τ(T) = 1/eₙ(T) overlay ───────────────────────────────────────────
    if dltsc.detailed_showTauVar.get() and res_mw is not None:
        kB    = 8.617333e-5
        gamma = dltsc.detailed_gammaVar.get()
        Et    = res_mw['Et']
        sigma = res_mw['sigma']

        T_line = np.linspace(T_K.min() - 20, T_K.max() + 20, 600)
        en_T   = gamma * sigma * T_line ** 2 * np.exp(-Et / (kB * T_line))
        tau_T  = 1.0 / en_T

        vis = (tau_T >= t_s.min() * 0.5) & (tau_T <= t_s.max() * 2.0)
        if vis.any():
            T_vis   = T_line[vis]
            tau_vis = np.clip(tau_T[vis], t_s.min(), t_s.max())
            ax.plot(T_vis, tau_vis, color='white', lw=2.2, ls='-', zorder=6,
                    label=f'Z₁₂  τ(T)  Et={Et:.3f} eV')

            Tp_all  = res_mw['Tp_arr']
            tau_all = 1.0 / res_mw['en_arr']

            vis_c    = ((tau_all >= t_s.min() * 0.5) & (tau_all <= t_s.max() * 2.0))
            Tp_plot  = Tp_all[vis_c]
            tau_plot = np.clip(tau_all[vis_c], t_s.min(), t_s.max())

            if len(Tp_plot):
                ax.scatter(Tp_plot, tau_plot, marker='o', s=70, facecolors='none', edgecolors='cyan',
                          lw=1.8, zorder=8, label='Rate-window peaks  (Tₚ, 1/eₙ)')

                mid = len(Tp_plot) // 2
                ax.annotate(
                    '  Z₁₂\n  defect',
                    xy=(Tp_plot[mid], tau_plot[mid]),
                    xytext=(Tp_plot[mid] + (T_K.max() - T_K.min()) * 0.07, tau_plot[mid]),
                    color='cyan', fontsize=9, fontweight='bold', va='center', zorder=9,
                    arrowprops=dict(arrowstyle='->', color='cyan', lw=1.2)
                )

            leg_m = ax.legend(loc='upper right', fontsize=8.5, frameon=True, framealpha=0.85,
                              edgecolor='#8fb4d8', facecolor='#1a3a5c', labelcolor='white')
            return leg_m

    return None


#---------------------RATE-WINDOW ANALYSIS MAP-------------------------#
def _detailed_plot_rate_window_map(ax, res_mw):
    """Plot Nt/Nd in (1/kT [eV^-1], T^2/en [K^2 s]) space. Color = 2|ΔC/C0|
    on a log scale. Black background. Overlays the Arrhenius line and a Z1/2 marker.
    """
    kB    = 8.617333e-5   # eV/K
    gamma = dltsc.detailed_gammaVar.get()
    nd    = dltsc.detailed_ndVar.get()
    temps = dltsc.detailed_temps
    data  = dltsc.detailed_data
    ratio = dltsc.detailed_ratioVar.get()

    t1_min = dltsc.detailed_t1MinVar.get()
    t1_max = dltsc.detailed_t1MaxVar.get()
    n_map  = 100
    t1_arr = np.logspace(np.log10(t1_min), np.log10(t1_max), n_map)

    T_K = np.array([tc + 273.15 for tc in temps])

    x_pts, y_pts, z_pts = [], [], []

    for t1 in t1_arr:
        t2 = ratio * t1
        en = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
        for j, tc in enumerate(temps):
            T = T_K[j]
            t_ms, cap, cinf = data[tc]
            if abs(cinf) < 1e-30:
                continue
            S = (np.interp(t2, t_ms, cap) - np.interp(t1, t_ms, cap)) / cinf
            nt_nd = 2.0 * abs(S)
            if nt_nd < 1e-8:
                continue
            x_pts.append(1.0 / (kB * T))          # eV^-1
            y_pts.append(T ** 2 / en)               # K^2 s
            z_pts.append(nt_nd)

    ax.set_facecolor('black')

    if len(x_pts) < 6:
        ax.text(0.5, 0.5, 'Insufficient data for Rate-Window map', transform=ax.transAxes, ha='center',
               color='white', fontsize=10)
        _detailed_style_rwm_axes(ax)
        return None

    x_pts = np.array(x_pts)
    y_pts = np.array(y_pts)
    z_pts = np.array(z_pts)

    z_lo = max(float(np.nanpercentile(z_pts, 2)), 1e-8)
    z_hi = max(float(np.nanpercentile(z_pts, 98)), z_lo * 10)

    xi = np.linspace(x_pts.min(), x_pts.max(), 220)
    log_y_min = np.log10(max(y_pts.min(), 1e-20))
    log_y_max = np.log10(y_pts.max())
    yi_log = np.linspace(log_y_min, log_y_max, 220)
    Xi, Yi_log = np.meshgrid(xi, yi_log)
    Yi = 10.0 ** Yi_log

    Zi = griddata((x_pts, np.log10(y_pts)), z_pts, (Xi, Yi_log), method='linear')
    Zi = np.ma.masked_invalid(Zi)
    Zi = np.ma.masked_less_equal(Zi, 0.0)

    pm = ax.pcolormesh(Xi, Yi, Zi, cmap='jet', norm=LogNorm(vmin=z_lo, vmax=z_hi), shading='auto', zorder=2)
    ax.set_yscale('log')

    cbar = dltsc.detailed_figure.colorbar(pm, ax=ax, pad=0.02, fraction=0.026, aspect=30)
    cbar.set_label('Nₜ / N_D', fontsize=10, labelpad=14)
    cbar.ax.yaxis.label.set_color('white')
    cbar.ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext())
    cbar.ax.tick_params(labelsize=8, colors='white', which='both', length=4, width=0.8)
    for lbl in cbar.ax.get_yticklabels():
        lbl.set_color('white')
    cbar.outline.set_edgecolor('#777777')
    cbar.outline.set_linewidth(0.8)

    if res_mw is not None:
        Et    = res_mw['Et']
        sigma = res_mw['sigma']

        x_line = np.linspace(x_pts.min() * 0.97, x_pts.max() * 1.03, 400)
        y_line = (1.0 / (gamma * sigma)) * np.exp(Et * x_line)
        vis    = (y_line >= Yi.min() * 0.2) & (y_line <= Yi.max() * 5.0)
        if vis.any():
            ax.plot(x_line[vis], y_line[vis], color='white', lw=1.8, ls='--', zorder=5,
                    label=f'Arrhenius  Eₜ={Et:.3f} eV')

        n_circles = 22
        x_circ = np.linspace(x_pts.min() * 0.98, x_pts.max() * 1.02, n_circles)
        y_circ = (1.0 / (gamma * sigma)) * np.exp(Et * x_circ)
        vis_c  = ((y_circ >= Yi.min() * 0.5) & (y_circ <= Yi.max() * 2.0))
        if vis_c.any():
            ax.scatter(x_circ[vis_c], y_circ[vis_c], s=55, facecolors='none', edgecolors='#00cfff',
                       lw=1.6, zorder=8, label='Z₁/₂ (fitted)')

    leg_rw = ax.legend(loc='upper left', fontsize=8.5, frameon=True, framealpha=0.85,
                       edgecolor='#8fb4d8', facecolor='#0d1b2a', labelcolor='white')

    _detailed_style_rwm_axes(ax)
    return leg_rw

def _detailed_style_rwm_axes(ax):
    """Apply black-background axis styling for the Rate-Window map."""
    ax.set_xlabel('1/kT  (eV⁻¹)', fontsize=10, labelpad=12)
    ax.set_ylabel('T²/eₙ  (K²s)', fontsize=10, labelpad=14)
    ax.set_title('Rate-Window Analysis Map', fontsize=11, color='white', fontweight='bold', pad=8)
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.tick_params(axis='both', which='both', colors='white', labelcolor='white',
                   labelsize=9, length=4, width=0.8)
    for spine in ax.spines.values():
        spine.set_color('#555555')
    ax.yaxis.set_minor_locator(mticker.NullLocator())
    ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext())


#---------------------LABEL / LEGEND EDITOR-------------------------#
def _detailed_open_label_editor():
    """Popup dialog to edit axis labels, titles, and legend text/font sizes.
    A Toplevel (not a modal messagebox) -- it is itself a genuine editing
    tool, not a status/error notification, so it stays as a dialog.
    """
    if dltsc.detailed_figure is None:
        dltsc.log_to_textbox("Detailed analysis: run the analysis first before editing labels.")
        return

    dlg = tk.Toplevel(dltsc.root)
    dlg.title('Edit Labels & Legends')
    dlg.configure(bg=CTRL_BG)
    dlg.minsize(460, 340)
    dlg.geometry('500x580')

    outer = tk.Frame(dlg, bg=CTRL_BG)
    outer.pack(fill='both', expand=True)
    cvs = tk.Canvas(outer, bg=CTRL_BG, highlightthickness=0)
    vsb = ttk.Scrollbar(outer, orient='vertical', command=cvs.yview)
    cvs.configure(yscrollcommand=vsb.set)
    vsb.pack(side='right', fill='y')
    cvs.pack(side='left', fill='both', expand=True)
    inner = tk.Frame(cvs, bg=CTRL_BG, padx=12, pady=8)
    cvs.create_window((0, 0), window=inner, anchor='nw')
    inner.bind('<Configure>', lambda e: cvs.configure(scrollregion=cvs.bbox('all')))

    def section(title):
        tk.Frame(inner, bg='#1a3a5c', height=2).pack(fill='x', pady=(10, 2))
        tk.Label(inner, text=title, bg=CTRL_BG, fg='#1a3a5c', font=('Segoe UI', 9, 'bold')).pack(anchor='w')

    # Collectors for Apply
    axis_updates = []   # (setter_fn, text_var, size_var)
    legend_sizes = []   # (legend_obj, size_var)
    legend_texts = []   # (text_obj, text_var)

    def axis_row(parent, label, current_text, current_size, setter_fn):
        f = tk.Frame(parent, bg=CTRL_BG)
        f.pack(fill='x', pady=2)
        tk.Label(f, text=label, bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), width=9, anchor='w').pack(side='left')
        tv = tk.StringVar(value=current_text)
        tk.Entry(f, textvariable=tv, font=('Segoe UI', 9), width=26, relief='solid').pack(side='left', padx=(4, 8))
        tk.Label(f, text='pt', bg=CTRL_BG, fg=TEXT_SEC, font=('Segoe UI', 8)).pack(side='right')
        sv = tk.IntVar(value=max(6, int(current_size)))
        ttk.Spinbox(f, textvariable=sv, from_=6, to=28, increment=1, width=4, font=('Segoe UI', 9)).pack(
            side='right', padx=(0, 4))
        axis_updates.append((setter_fn, tv, sv))

    panel_defs = [
        ('Arrhenius Panel',       dltsc.detailed_ax1),
        ('DLTS Spectra Panel',    dltsc.detailed_ax2),
        ('Transient Map Panel',   dltsc.detailed_ax3),
        ('Rate-Window Map Panel', dltsc.detailed_ax4),
    ]
    for pname, ax in panel_defs:
        if ax is None:
            continue
        section(pname)
        axis_row(inner, 'Title', ax.title.get_text(), ax.title.get_fontsize(), ax.set_title)
        axis_row(inner, 'X label', ax.xaxis.label.get_text(), ax.xaxis.label.get_fontsize() or 10, ax.set_xlabel)
        axis_row(inner, 'Y label', ax.yaxis.label.get_text(), ax.yaxis.label.get_fontsize() or 10, ax.set_ylabel)

    legend_defs = [
        ('Arrhenius Legend',     dltsc.detailed_ax1, dltsc.detailed_leg1),
        ('Spectra Legend',       dltsc.detailed_ax2, dltsc.detailed_leg2),
        ('Transient Map Legend', dltsc.detailed_ax3, dltsc.detailed_legM),
        ('Rate-Window Legend',   dltsc.detailed_ax4, dltsc.detailed_legRW),
    ]
    for lname, ax, leg in legend_defs:
        if ax is None or leg is None:
            continue
        texts = leg.get_texts()
        if not texts:
            continue
        section(lname)

        f_sz = tk.Frame(inner, bg=CTRL_BG)
        f_sz.pack(fill='x', pady=2)
        tk.Label(f_sz, text='Font size', bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), width=9,
                anchor='w').pack(side='left')
        tk.Label(f_sz, text='pt', bg=CTRL_BG, fg=TEXT_SEC, font=('Segoe UI', 8)).pack(side='right')
        fsv = tk.IntVar(value=max(6, int(texts[0].get_fontsize())))
        ttk.Spinbox(f_sz, textvariable=fsv, from_=6, to=18, increment=1, width=4, font=('Segoe UI', 9)).pack(
            side='right', padx=(0, 4))
        legend_sizes.append((leg, fsv))

        for i, txt_obj in enumerate(texts):
            fe = tk.Frame(inner, bg=CTRL_BG)
            fe.pack(fill='x', pady=1)
            tk.Label(fe, text=f'  Entry {i + 1}', bg=CTRL_BG, fg=TEXT_SEC, font=('Segoe UI', 8), width=9,
                    anchor='w').pack(side='left')
            ltv = tk.StringVar(value=txt_obj.get_text())
            tk.Entry(fe, textvariable=ltv, font=('Segoe UI', 9), width=32, relief='solid').pack(side='left', padx=4)
            legend_texts.append((txt_obj, ltv))

    def apply_all():
        for setter, tv, sv in axis_updates:
            setter(tv.get(), fontsize=sv.get())
        for leg, fsv in legend_sizes:
            for t in leg.get_texts():
                t.set_fontsize(fsv.get())
        for txt_obj, ltv in legend_texts:
            txt_obj.set_text(ltv.get())
        if dltsc.detailed_canvas:
            dltsc.detailed_canvas.draw_idle()

    btn_f = tk.Frame(dlg, bg=CTRL_BG)
    btn_f.pack(fill='x', padx=12, pady=8)
    ttk.Button(btn_f, text='Apply', command=apply_all).pack(side='left', padx=4)
    ttk.Button(btn_f, text='Apply & Close', command=lambda: [apply_all(), dlg.destroy()]).pack(side='left', padx=4)
    ttk.Button(btn_f, text='Close', command=dlg.destroy).pack(side='right', padx=4)


#---------------------RESULTS TEXT-------------------------#
def _detailed_write_results(res_mw, res_std, Nt):
    lines = []
    lines.append('=' * 60)
    lines.append('  DLTS Multiwindow Analysis  —  Results')
    lines.append('=' * 60)
    lines.append('')
    lines.append(f'  Multi-window  ({res_mw["N"]} windows)')
    lines.append(f'    Et   = {res_mw["Et"]:.4f} +/- {res_mw["Et_se"]:.4f} eV')
    lines.append(f'    sn   = {res_mw["sigma"]:.3e} cm2')
    lines.append(f'    R2   = {res_mw["R2"]:.5f}')
    lines.append(f'    Nt   ~ {Nt:.3e} cm-3')
    if res_std:
        lines.append('')
        lines.append(f'  Standard  ({res_std["N"]} windows)')
        lines.append(f'    Et   = {res_std["Et"]:.4f} +/- {res_std["Et_se"]:.4f} eV')
        lines.append(f'    sn   = {res_std["sigma"]:.3e} cm2')
        lines.append(f'    R2   = {res_std["R2"]:.5f}')
        if res_std['Et_se'] > 0:
            impr = res_std['Et_se'] / res_mw['Et_se']
            lines.append(f'    Et uncertainty improvement: {impr:.1f}x')
    lines.append('')
    lines.append('  Window detail  (multi):')
    lines.append(f'  {"t1(ms)":>8}  {"t2(ms)":>8}  {"en(s-1)":>10}  {"Tpeak(C)":>10}')
    lines.append('  ' + '-' * 44)
    for t1, t2, en, tp, sp in res_mw['detail']:
        lines.append(f'  {t1:8.1f}  {t2:8.1f}  {en:10.2f}  {tp:10.2f}')

    text = '\n'.join(lines)
    if dltsc.detailed_resultsText is not None:
        dltsc.detailed_resultsText.configure(state='normal')
        dltsc.detailed_resultsText.delete('1.0', 'end')
        dltsc.detailed_resultsText.insert('end', text)
        dltsc.detailed_resultsText.configure(state='disabled')


#---------------------FILE I/O (SAVE FIGURE / EXPORT TXT)-------------------------#
# Formats the installed backends actually support: PNG/PDF/SVG/EPS are native
# to matplotlib's Agg/PDF/SVG/PS backends; JPEG/TIFF/BMP go through Pillow
# (confirmed installed in this environment).
_FIGURE_SAVE_FILETYPES = [
    ('PNG image', '*.png'),
    ('PDF document', '*.pdf'),
    ('SVG vector image', '*.svg'),
    ('EPS vector image', '*.eps'),
    ('JPEG image', '*.jpg *.jpeg'),
    ('TIFF image', '*.tif *.tiff'),
    ('Bitmap image', '*.bmp'),
    ('All files', '*.*'),
]

def _detailed_save_figure():
    if dltsc.detailed_figure is None:
        dltsc.log_to_textbox("Detailed analysis: run the analysis first before saving a figure.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension='.png', filetypes=_FIGURE_SAVE_FILETYPES,
        initialfile='DLTS_MultiWindow.png')
    if not path:
        return
    try:
        # Vector formats (svg/eps/pdf) shouldn't be flattened to a fixed DPI
        # raster and don't need a forced facecolor override; raster formats
        # (png/jpg/tiff/bmp) get the figure's own SURFACE background baked in
        # (mirrors the previous PNG-only behavior) so they don't save transparent.
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.svg', '.eps', '.pdf'):
            dltsc.detailed_figure.savefig(path, bbox_inches='tight')
        else:
            dltsc.detailed_figure.savefig(path, dpi=180, bbox_inches='tight', facecolor=SURFACE)
    except Exception as exc:
        dltsc.log_to_textbox(f"Detailed analysis: failed to save figure as {ext or '(no extension)'}: {exc}")
        return
    if dltsc.detailed_statusLabel is not None:
        dltsc.detailed_statusLabel.config(text=f'Figure saved: {path}')
    dltsc.log_to_textbox(f"Detailed analysis: figure saved to {path}")

def _detailed_export_txt():
    if dltsc.detailed_resultsText is None:
        return
    txt = dltsc.detailed_resultsText.get('1.0', 'end').strip()
    if not txt:
        dltsc.log_to_textbox("Detailed analysis: run the analysis first before exporting results.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension='.txt', filetypes=[('Text file', '*.txt'), ('All files', '*.*')],
        initialfile='DLTS_Results.txt')
    if path:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(txt)
        if dltsc.detailed_statusLabel is not None:
            dltsc.detailed_statusLabel.config(text=f'Results exported: {path}')
        dltsc.log_to_textbox(f"Detailed analysis: results exported to {path}")


#---------------------TAB CONSTRUCTION-------------------------#
def construct_detailedAnalysisTab():
    tabControl = dltsc.tabControl

    tabControl.add(dltsc.detailedAnalysisTab, text='Detailed Analysis')
    tabControl.pack(expand=1, fill="both")

    parent = dltsc.detailedAnalysisTab
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Detailed Analysis', font=('Segoe UI', 10, 'bold')).pack(side='left')
    ttk.Label(headerFrame, text='  (DLTS Multiwindow Analysis — ZI MFIA temperature sweep)',
             foreground=TEXT_SEC).pack(side='left')

    # Main paned window: scrollable control column (left) + figure/results (right),
    # matching DLTS_APP.py's own layout.
    paned = ttk.PanedWindow(parent, orient='horizontal')
    paned.grid(row=1, column=0, sticky='nsew', padx=4, pady=(0, 4))

    ctrl_outer = tk.Frame(paned, bg=CTRL_BG, width=310)
    ctrl_outer.pack_propagate(False)
    paned.add(ctrl_outer, weight=0)

    canvas_ctrl = tk.Canvas(ctrl_outer, bg=CTRL_BG, highlightthickness=0, width=300)
    vscroll = ttk.Scrollbar(ctrl_outer, orient='vertical', command=canvas_ctrl.yview)
    canvas_ctrl.configure(yscrollcommand=vscroll.set)
    vscroll.pack(side='right', fill='y')
    canvas_ctrl.pack(side='left', fill='both', expand=True)

    ctrl = tk.Frame(canvas_ctrl, bg=CTRL_BG, padx=10, pady=8)
    canvas_ctrl.create_window((0, 0), window=ctrl, anchor='nw')
    ctrl.bind('<Configure>', lambda e: canvas_ctrl.configure(scrollregion=canvas_ctrl.bbox('all')))
    canvas_ctrl.bind('<Enter>', lambda e: canvas_ctrl.bind_all(
        '<MouseWheel>', lambda ev: canvas_ctrl.yview_scroll(int(-1 * (ev.delta / 120)), 'units')))
    canvas_ctrl.bind('<Leave>', lambda e: canvas_ctrl.unbind_all('<MouseWheel>'))

    right = tk.Frame(paned, bg=CTRL_BG)
    paned.add(right, weight=1)

    dltsc.detailed_figFrame = tk.Frame(right, bg=CTRL_BG)
    dltsc.detailed_figFrame.pack(fill='both', expand=True)

    results_frame = tk.LabelFrame(right, text=' Results ', bg=CTRL_BG, fg=TEXT_SEC, font=('Consolas', 9))
    results_frame.pack(fill='x', padx=6, pady=(0, 4))
    resultsInner = tk.Frame(results_frame, bg=CTRL_BG)
    resultsInner.pack(fill='both', expand=True, padx=4, pady=4)
    resultsScroll = ttk.Scrollbar(resultsInner, orient='vertical')
    dltsc.detailed_resultsText = tk.Text(
        resultsInner, height=8, font=('Consolas', 9),
        bg='#1e1e2e', fg='#cdd6f4', insertbackground='white',
        state='disabled', wrap='word', relief='flat',
        yscrollcommand=resultsScroll.set)
    resultsScroll.config(command=dltsc.detailed_resultsText.yview)
    dltsc.detailed_resultsText.pack(side='left', fill='both', expand=True)
    resultsScroll.pack(side='right', fill='y')

    dltsc.detailed_statusLabel = ttk.Label(right, text='Load a data folder to begin.')
    dltsc.detailed_statusLabel.pack(fill='x', padx=6, pady=(0, 4))

    # ── local UI-building helpers (construction-time only, mirrors DLTS_APP.py's
    # DLTSApp._section/_row/_spinbox, now closures over `ctrl` instead of methods) ──
    def section(title):
        tk.Frame(ctrl, bg='#1a3a5c', height=2).pack(fill='x', pady=(10, 2))
        tk.Label(ctrl, text=title.upper(), bg=CTRL_BG, fg='#1a3a5c', font=('Segoe UI', 8, 'bold')).pack(anchor='w')

    def row(label, widget_factory, **kw):
        f = tk.Frame(ctrl, bg=CTRL_BG)
        f.pack(fill='x', pady=2)
        tk.Label(f, text=label, bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), width=18, anchor='w').pack(side='left')
        w = widget_factory(f, **kw)
        w.pack(side='left', fill='x', expand=True)
        return w

    def spinbox(parent_, var, lo, hi, inc, fmt='%g', width=9):
        return ttk.Spinbox(parent_, textvariable=var, from_=lo, to=hi, increment=inc,
                           format=fmt, width=width, font=('Segoe UI', 9))

    # ── Data ──────────────────────────────────────────────────────────────
    section('Data')
    dltsc.detailed_baseVar = tk.StringVar(value='')
    tk.Label(ctrl, text='Data folder:', bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), anchor='w').pack(fill='x')
    f_path = tk.Frame(ctrl, bg=CTRL_BG)
    f_path.pack(fill='x', pady=2)
    tk.Entry(f_path, textvariable=dltsc.detailed_baseVar, font=('Segoe UI', 8), relief='solid',
             fg=TEXT_SEC).pack(side='left', fill='x', expand=True)
    ttk.Button(f_path, text='Browse', command=_detailed_browse_folder).pack(side='left', padx=(4, 0))

    dltsc.detailed_loadButton = ttk.Button(ctrl, text='Load Data', command=_detailed_load_data)
    dltsc.detailed_loadButton.pack(fill='x', pady=(4, 0))
    dltsc.detailed_loadInfoLabel = ttk.Label(ctrl, text='No data loaded.', foreground=TEXT_MUT)
    dltsc.detailed_loadInfoLabel.pack(fill='x')

    # ── ZI MFIA Grid ──────────────────────────────────────────────────────
    section('ZI MFIA Grid')
    dltsc.detailed_gridOffVar   = tk.DoubleVar(value=DEFAULT_GRID_OFF)
    dltsc.detailed_gridDtVar    = tk.DoubleVar(value=DEFAULT_GRID_DT)
    dltsc.detailed_chunkSizeVar = tk.IntVar(value=DEFAULT_CHUNK_SIZE)
    dltsc.detailed_rbMsVar      = tk.DoubleVar(value=DEFAULT_RB_MS)

    row('Grid offset (s)', lambda p, **k: spinbox(p, dltsc.detailed_gridOffVar, -0.01, 0, 0.0001, '%.6f'))
    row('Grid dt (s)', lambda p, **k: spinbox(p, dltsc.detailed_gridDtVar, 1e-6, 1e-3, 1e-6, '%.2e'))
    row('Chunk size', lambda p, **k: spinbox(p, dltsc.detailed_chunkSizeVar, 1024, 131072, 1024, '%d'))
    row('RB duration (ms)', lambda p, **k: spinbox(p, dltsc.detailed_rbMsVar, 10, 2000, 10))

    # ── C0 Estimation ─────────────────────────────────────────────────────
    section('C₀ Estimation Window')
    dltsc.detailed_cinfLoVar = tk.DoubleVar(value=0.40)
    dltsc.detailed_cinfHiVar = tk.DoubleVar(value=0.90)

    row('Start  (frac RB)', lambda p, **k: spinbox(p, dltsc.detailed_cinfLoVar, 0.1, 0.8, 0.05, '%.2f'))
    row('End    (frac RB)', lambda p, **k: spinbox(p, dltsc.detailed_cinfHiVar, 0.3, 0.99, 0.05, '%.2f'))

    # ── Physical constants ────────────────────────────────────────────────
    section('Physical Constants (4H-SiC)')
    dltsc.detailed_gammaVar = tk.DoubleVar(value=1.66e21)
    dltsc.detailed_ndVar    = tk.DoubleVar(value=3.2e14)

    row('γ (cm⁻²s⁻¹K⁻²)',
        lambda p, **k: spinbox(p, dltsc.detailed_gammaVar, 1e20, 1e22, 1e20, '%.2e'))
    row('Nᵈ (cm⁻³)', lambda p, **k: spinbox(p, dltsc.detailed_ndVar, 1e12, 1e17, 1e13, '%.2e'))

    # ── Peak search range ─────────────────────────────────────────────────
    section('Peak Search Range')
    dltsc.detailed_tpeakLoVar = tk.DoubleVar(value=250.0)
    dltsc.detailed_tpeakHiVar = tk.DoubleVar(value=400.0)

    row('T min (K)', lambda p, **k: spinbox(p, dltsc.detailed_tpeakLoVar, 100, 350, 5))
    row('T max (K)', lambda p, **k: spinbox(p, dltsc.detailed_tpeakHiVar, 200, 600, 5))

    # ── Multi-window parameters ───────────────────────────────────────────
    section('Multi-Window Parameters')
    dltsc.detailed_nWinVar  = tk.IntVar(value=16)
    dltsc.detailed_t1MinVar = tk.DoubleVar(value=5.0)
    dltsc.detailed_t1MaxVar = tk.DoubleVar(value=90.0)
    dltsc.detailed_ratioVar = tk.DoubleVar(value=5.0)

    row('N windows', lambda p, **k: spinbox(p, dltsc.detailed_nWinVar, 3, 60, 1, '%d'))
    row('t₁ min (ms)', lambda p, **k: spinbox(p, dltsc.detailed_t1MinVar, 1, 200, 1))
    row('t₁ max (ms)', lambda p, **k: spinbox(p, dltsc.detailed_t1MaxVar, 5, 450, 5))
    row('Ratio t₂/t₁', lambda p, **k: spinbox(p, dltsc.detailed_ratioVar, 2, 20, 0.5))

    # ── Standard 5 windows ────────────────────────────────────────────────
    section('Standard Windows (reference)')
    dltsc.detailed_stdWinsVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Show 5-window comparison', variable=dltsc.detailed_stdWinsVar).pack(anchor='w', pady=2)

    tk.Label(ctrl, text='t1 / t2  (ms):', bg=CTRL_BG, fg=TEXT_SEC, font=('Segoe UI', 8)).pack(anchor='w')
    dltsc.detailed_stdEntries = []
    for t1, t2 in [(5, 25), (10, 50), (20, 100), (50, 250), (100, 490)]:
        fr = tk.Frame(ctrl, bg=CTRL_BG)
        fr.pack(fill='x', pady=1)
        v1, v2 = tk.DoubleVar(value=t1), tk.DoubleVar(value=t2)
        ttk.Spinbox(fr, textvariable=v1, from_=1, to=490, increment=1, width=5, font=('Segoe UI', 9)).pack(side='left')
        tk.Label(fr, text=' / ', bg=CTRL_BG, font=('Segoe UI', 9)).pack(side='left')
        ttk.Spinbox(fr, textvariable=v2, from_=2, to=499, increment=1, width=5, font=('Segoe UI', 9)).pack(side='left')
        dltsc.detailed_stdEntries.append((v1, v2))

    # ── Display options ───────────────────────────────────────────────────
    section('Display')

    dltsc.detailed_showSpectraVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Show DLTS spectra panel', variable=dltsc.detailed_showSpectraVar).pack(anchor='w')
    dltsc.detailed_nSpectraVar = tk.IntVar(value=5)
    row('Spectra to plot', lambda p, **k: spinbox(p, dltsc.detailed_nSpectraVar, 2, 16, 1, '%d'))

    dltsc.detailed_showTmapVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Show 2D transient map', variable=dltsc.detailed_showTmapVar).pack(anchor='w', pady=(6, 0))

    dltsc.detailed_showTauVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='  Overlay τ(T) curve on map', variable=dltsc.detailed_showTauVar).pack(anchor='w')

    dltsc.detailed_showRwmVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Show Rate-Window Analysis map', variable=dltsc.detailed_showRwmVar).pack(
        anchor='w', pady=(6, 0))

    # ── Actions ───────────────────────────────────────────────────────────
    section('')
    btn_frame = tk.Frame(ctrl, bg=CTRL_BG)
    btn_frame.pack(fill='x', pady=6)

    dltsc.detailed_runButton = ttk.Button(btn_frame, text='Run Analysis', command=_detailed_run_analysis,
                                          state='disabled')
    dltsc.detailed_runButton.pack(fill='x', pady=2)
    ttk.Button(btn_frame, text='Edit Labels & Legends', command=_detailed_open_label_editor).pack(fill='x', pady=2)
    ttk.Button(btn_frame, text='Save Figure...', command=_detailed_save_figure).pack(fill='x', pady=2)
    ttk.Button(btn_frame, text='Export Results to TXT', command=_detailed_export_txt).pack(fill='x', pady=2)

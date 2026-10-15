import json
import os
import re
import textwrap
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np
import pandas as pd
from scipy.interpolate import griddata, CubicSpline
from lmfit.models import LinearModel, QuadraticModel

import matplotlib
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.patheffects as mpatheffects
from matplotlib.figure import Figure
from matplotlib.colors import Normalize, LogNorm
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.widgets import SpanSelector

import dltsConfig as dltsc
import dltsPhysics as dP   # fill-end emission rate, fill-pulse information, C0 (v3.1 corrections)
import liveDataTab as ldT   # reuses its data-folder format detection/extraction -- see _load_detailed_data
import impedanceAnalysis_Tools as iaT   # smoothing-spline peak finder shared with Quick Analysis

# Ported from the standalone DLTS_APP.py ("DLTS Multiwindow Analysis" tool)
# into a tab of this app, following its conventions: module-level functions
# instead of a DLTSApp class, all state as dltsc.detailed_* globals instead of
# self.* instance attributes, heavy folder-scan/analysis work off the main
# thread in this tab's own worker process (see _get_detailed_executor) instead
# of blocking the main thread, and dltsc.log_to_textbox() + status labels instead of messagebox
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
# One colour per trap (peak id) on the Arrhenius / spectra panels; the first is
# C0, the single-trap colour this tab always used.
TRAP_COLORS = (C0, '#1b9e77', '#9b59b6', C1, '#d4a017', '#e7298a', '#3f4f75')

# ── ZI grid defaults ─────────────────────────────────────────────────────────
DEFAULT_GRID_OFF   = -0.001
DEFAULT_GRID_DT    = 1.86667e-5
DEFAULT_CHUNK_SIZE = 32768
DEFAULT_RB_MS      = 500.0

# ── Analysis defaults shared with Quick Analysis (dataAnalysisTab), so both tabs
# give the same result for the same data and windows ─────────────────────────
KB_EV = 8.617333262145e-5          # Boltzmann constant, eV/K (CODATA 2018)
DEFAULT_CINF_LO = 0.40             # C_infinity = mean C over [lo, hi] x reverse bias
DEFAULT_CINF_HI = 0.90
DEFAULT_ND = 3.2e14                # background doping, cm^-3
DEFAULT_GAMMA = 1.66e21            # emission pre-factor, cm^-2 s^-1 K^-2 (4H-SiC)
PEAK_MIN_FRAC = 0.05               # skip a window whose peak is below this fraction of max|S|
DEFAULT_TPEAK_LO = 250.0           # peak-search range, K
DEFAULT_TPEAK_HI = 400.0
# Peak-search presets of Dr. Kayi's v3.1 (K); picking one fills T min / T max.
TRAP_PRESETS = {'Z1/Z2': (250.0, 430.0), 'EH6/EH7': (540.0, 730.0)}
TRAP_PRESET_CUSTOM = 'Custom range'
# Standard rate windows (t1, t2) in ms: this tab's "standard-window comparison"
# and Quick Analysis' default window sets.
DEFAULT_STD_WINDOWS = [(5.0, 25.0), (10.0, 50.0), (20.0, 100.0), (50.0, 250.0), (100.0, 490.0)]

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

# DLTS signal calculation options, mirroring Quick Analysis' "DLTS Signal
# Calculation" group (dataAnalysisTab.SIGNAL_METHOD_* / DENOISE_*). There they
# go through impdData.calculate_delC_normalized(), which needs per-repeat
# instrument data; this tab only has each temperature's averaged transient,
# so the same two read-off methods and the same four denoise filters (same
# settings as impdData.filter_emissions()) are applied to that curve directly.
SIGNAL_METHOD_MEASURED = 'Measured C (nearest sample)'
SIGNAL_METHOD_SMOOTHED = 'Smoothed C (spline-interpolated)'
SIGNAL_METHOD_OPTIONS = [SIGNAL_METHOD_MEASURED, SIGNAL_METHOD_SMOOTHED]

DENOISE_NONE = 'None (raw)'
DENOISE_OPTIONS = [DENOISE_NONE, 'pca', 'wavelet', 'sgolay', 'lowess']

def _denoise_transient(t_ms, cap, method):
    """Denoised copy of one averaged transient, via the same impdData filters
    and settings Quick Analysis' denoise option uses (impdData.filter_emissions)."""
    signal = {'x': t_ms, 'y': cap, 'ymean': cap}
    if method == 'pca':
        _, y, _ = iaT.impdData._pca_denoise(signal, index=-1, window_size=100)
    elif method == 'wavelet':
        _, y, _ = iaT.impdData._wavelet_denoise(signal, index=-1, wavelet='db4', level=4, mode='soft')
    elif method == 'sgolay':
        _, y, _ = iaT.impdData._savitzkyGolay_denoise(signal, index=-1, window_size=None, order=2)
    elif method == 'lowess':
        _, y, _ = iaT.impdData._lowess_denoise(signal, index=-1, fraction=None)
    else:
        return cap
    return np.asarray(y, dtype=float)[:len(cap)]

def _prepare_signal_data(data, temps, signal_method, denoise):
    """Per-temperature record every C(t) read-off in the worker goes through:
    tc -> (t_ms, cap_used, c_inf, cap_raw, spline). cap_used is the denoised
    transient (or the raw one for 'None (raw)'); spline is a CubicSpline
    through cap_used for Smoothed C (None for Measured C / nearest sample),
    built once here rather than per read-off. cap_raw is kept for the error
    estimate (see _cap_noise_at)."""
    out = {}
    for tc in temps:
        t_ms, cap, c_inf = data[tc]
        cap_used = _denoise_transient(t_ms, cap, denoise) if denoise != DENOISE_NONE else cap
        spline = CubicSpline(t_ms, cap_used) if signal_method == SIGNAL_METHOD_SMOOTHED else None
        out[tc] = (t_ms, cap_used, c_inf, cap, spline)
    return out

def _cap_at(rec, tv_ms):
    """C at time(s) tv_ms from a _prepare_signal_data record: the spline value
    (Smoothed C), or the nearest measured sample (Measured C). Scalar in,
    float out; array in, array out."""
    t_ms, cap, _, _, spline = rec
    if spline is not None:
        v = spline(tv_ms)
    else:
        i = np.clip(np.searchsorted(t_ms, tv_ms), 1, len(t_ms) - 1)
        i = np.where(np.abs(t_ms[i - 1] - tv_ms) <= np.abs(t_ms[i] - tv_ms), i - 1, i)
        v = cap[i]
    return float(v) if np.ndim(v) == 0 else v

def _cap_noise_at(t_ms, cap, tv_ms, hw=25):
    """1-sigma sample noise of cap around time tv_ms: the Rice (1984)
    second-difference estimator over the ±hw samples nearest tv_ms (the same
    robust estimator _smoothingSpline_peakFinder uses), which ignores the
    transient's own smooth decay so only the sample-to-sample scatter counts.
    Always evaluated on the RAW transient, even when a denoised one is used
    for the values -- the same choice Quick Analysis makes (its yerr is the
    raw cross-repeat spread regardless of denoising) -- since the residual
    scatter of an already-smoothed curve would badly understate the error
    and over-weight the peak and Arrhenius fits."""
    i = int(np.clip(np.searchsorted(t_ms, tv_ms), 0, len(t_ms) - 1))
    seg = cap[max(i - hw, 0):i + hw + 1]
    if len(seg) < 5:
        return np.nan
    d2 = seg[:-2] - 2.0 * seg[1:-1] + seg[2:]
    return float(np.sqrt(np.sum(d2 ** 2) / (6.0 * len(d2))))

def _rate_window_signal(temps, data, t1, t2):
    """Double-boxcar signal S(T) = (C(t2) - C(t1)) / C_inf for every
    temperature (data: _prepare_signal_data records), plus its per-point
    1-sigma error propagated from the raw sample noise at t1 and t2 (C_inf is
    a many-sample mean, so its error is negligible)."""
    S, S_err = [], []
    for tc in temps:
        rec = data[tc]
        t_ms, _, c_inf, cap_raw, _ = rec
        S.append((_cap_at(rec, t2) - _cap_at(rec, t1)) / c_inf)
        S_err.append(np.hypot(_cap_noise_at(t_ms, cap_raw, t1), _cap_noise_at(t_ms, cap_raw, t2)) / abs(c_inf))
    return np.array(S), np.array(S_err)

def _valid_errors(err):
    """err if every entry is a usable (finite, > 0) 1-sigma error, else None."""
    return err if err is not None and np.all(np.isfinite(err)) and np.all(err > 0) else None

PEAK_METHOD_PARABOLIC = 'Parabolic fit (lmfit)'
PEAK_METHOD_SPLINE = 'Smoothing Spline (bootstrap)'
# Dr. Kayi's v3.1 profile finders: one line shape plus a constant baseline,
# fitted (lmfit, weighted by the point errors) over the whole search range;
# Tp is the fitted centre. The 3-5 point parabola overestimates Et and σ for
# broad / asymmetric DLTS peaks, so v3.1 made Pseudo-Voigt its default.
PEAK_METHOD_GAUSSIAN = 'Gaussian + const (lmfit)'
PEAK_METHOD_LORENTZIAN = 'Lorentzian + const (lmfit)'
PEAK_METHOD_PVOIGT = 'Pseudo-Voigt + const (lmfit)'
PEAK_METHOD_VOIGT = 'Voigt + const (lmfit)'
PEAK_METHOD_PROFILES = {PEAK_METHOD_GAUSSIAN: 'gaussian', PEAK_METHOD_LORENTZIAN: 'lorentzian',
                        PEAK_METHOD_PVOIGT: 'pseudoVoigt', PEAK_METHOD_VOIGT: 'voigt'}
PEAK_METHOD_OPTIONS = [PEAK_METHOD_PARABOLIC, PEAK_METHOD_SPLINE, PEAK_METHOD_GAUSSIAN, PEAK_METHOD_LORENTZIAN,
                       PEAK_METHOD_PVOIGT, PEAK_METHOD_VOIGT]
PEAK_METHOD_DEFAULT = PEAK_METHOD_PVOIGT

# A peak within this fraction of a grid step of either end of the search range
# is on the edge: the signal still rises out of the range, so it isn't a real peak.
EDGE_PEAK_FRAC = 0.01
# Smallest Tp error (K) taken as real. A spline peak pinned to the range edge is
# the same grid point in every bootstrap sample, giving ~1e-13 K, and such a
# point would otherwise dominate the weighted Arrhenius fit.
MIN_TP_ERR_K = 1e-4

def _find_peak(T_arr, S_arr, S_err, method):
    """Peak temperature and its 1-sigma error, (Tp, Tp_err), by `method`.

    Tp_err is None -- so _compute_arrhenius leaves the window out of the
    weighted fit, like any peak without an error -- when the peak lies on the
    edge of the search range or its error is below MIN_TP_ERR_K."""
    return _find_peak_full(T_arr, S_arr, S_err, method)[:2]

def _find_peak_full(T_arr, S_arr, S_err, method):
    """(Tp, Tp_err, xFit, yFit, Sp, Sp_err): _find_peak plus the fitted curve
    for plotting (None, None when the method has none) and the fitted peak
    height with its error (None, None when the method gives none -- the grid
    maximum is used then). `method` is one of PEAK_METHOD_OPTIONS or a callable
    (T, S, S_err) -> (Tp, Tp_err, xFit, yFit[, Sp, Sp_err]) -- Quick Analysis
    passes its lmfit curve-fit finders that way."""
    if callable(method):
        found = method(T_arr, S_arr, S_err)
    elif method == PEAK_METHOD_SPLINE:
        found = _find_peak_spline(T_arr, S_arr, S_err)
    elif method in PEAK_METHOD_PROFILES:
        found = _find_peak_profile(T_arr, S_arr, S_err, PEAK_METHOD_PROFILES[method])
    else:
        found = (*_find_peak_parabolic(T_arr, S_arr, S_err), None, None)
    Tp, Tp_err, xFit, yFit, Sp, Sp_err = tuple(found) + (None,) * (6 - len(found))
    return Tp, _guard_peak_error(T_arr, Tp, Tp_err), xFit, yFit, Sp, Sp_err

def _find_peak_profile(T_arr, S_arr, S_err, primitive):
    """Peak of one line shape (an iaT.DECONV_PEAK_PRIMITIVES key) plus a
    constant baseline fitted over the whole search range -- v3.1's Gaussian /
    Lorentzian / Pseudo-Voigt / Voigt finders, through the same lmfit
    deconvolution Peak Regions use (iaT.impdData._deconvolve_peaks), so Tp and
    the height carry lmfit's covariance errors. The height is the fitted total
    curve at Tp (baseline included), as v3.1 takes it. As in v3.1, a failed fit
    or a centre on the range edge falls back to the 3-5 point parabola; the
    fallback returns no curve (xFit None), which is how callers count it.
    Returns (Tp, Tp_err, xFit, yFit, Sp, Sp_err)."""
    try:
        res = iaT.impdData._deconvolve_peaks(T_arr, S_arr, [primitive, 'constant'], signalYErr=_valid_errors(S_err))
        comp = res['components'][0] if res['xf'] is not None else None
    except Exception:
        comp = None
    if comp is None or comp['onEdge']:
        return (*_find_peak_parabolic(T_arr, S_arr, S_err), None, None, None, None)
    Tp = comp['center']
    return Tp, comp['centerErr'], res['xf'], res['yf'], float(np.interp(Tp, res['xf'], res['yf'])), comp['heightErr']

def _guard_peak_error(T_arr, Tp, Tp_err):
    """Tp_err, or None for a peak on the edge of the search range or an error
    below MIN_TP_ERR_K (see _find_peak)."""
    if _peak_on_edge(T_arr, Tp):
        return None
    if Tp_err is None or not (np.isfinite(Tp_err) and Tp_err >= MIN_TP_ERR_K):
        return None
    return float(Tp_err)

def _peak_on_edge(T_arr, Tp):
    """True if Tp is at (or outside) either end of the search-range grid T_arr."""
    T_arr = np.asarray(T_arr, dtype=float)
    if T_arr.size < 2:
        return True
    tol = EDGE_PEAK_FRAC * float(np.min(np.abs(np.diff(T_arr)))) if T_arr.size > 1 else 0.0
    return bool(Tp <= T_arr.min() + tol or Tp >= T_arr.max() - tol)

def _find_peak_spline(T_arr, S_arr, S_err):
    """Peak of a weighted smoothing cubic spline over the whole search range,
    via Quick Analysis' own iaT.impdData._smoothingSpline_peakFinder, whose
    Tp error is a parametric-bootstrap estimate (a spline has no parameter
    covariance). Returns (Tp, Tp_err, xFit, yFit, Sp, Sp_err), Sp the spline's
    peak height; falls back to the raw grid maximum (no error, no curve, no
    height) if it fails."""
    try:
        Tp, Sp, xFit, yFit, Tp_err, Sp_err = iaT.impdData._smoothingSpline_peakFinder(
            T_arr, S_arr, signalYErr=_valid_errors(S_err))
    except Exception:
        return float(T_arr[int(np.argmax(S_arr))]), None, None, None, None, None
    return float(Tp), Tp_err, xFit, yFit, float(Sp), Sp_err

def _find_peak_parabolic(T_arr, S_arr, S_err=None, hw=2):
    """Sub-grid peak temperature from a parabola fitted (lmfit QuadraticModel,
    weighted by 1/S_err when per-point errors are available) to the 2*hw+1
    points around the raw maximum. Returns (Tp, Tp_err), where Tp_err is the
    vertex's 1-sigma uncertainty propagated from the fit's a/b covariance, or
    None when it can't be estimated (no residual degrees of freedom, singular
    covariance, or a fallback to the raw grid maximum).
    """
    ip = int(np.argmax(S_arr))
    lo, hi = max(ip - hw, 0), min(ip + hw + 1, len(T_arr))
    T_c, S_c = T_arr[lo:hi], S_arr[lo:hi]
    T_ref = float(T_arr[ip])
    if len(T_c) < 3:
        return T_ref, None
    # Fit in x = T - T_ref: the same parabola/vertex as fitting in T directly
    # (what np.polyfit did before), but far better conditioned since T ~ 300 K
    # would otherwise make the T^2 term swamp a/b/c's covariance.
    x = T_c - T_ref
    fitKwargs = {}
    err_c = _valid_errors(S_err[lo:hi]) if S_err is not None else None
    if err_c is not None:
        fitKwargs['weights'] = 1.0 / err_c
    model = QuadraticModel()
    try:
        result = model.fit(S_c, model.guess(S_c, x=x), x=x, **fitKwargs)
    except Exception:
        return T_ref, None
    a = result.params['a'].value
    b = result.params['b'].value
    if a < 0:
        Tp = T_ref - b / (2.0 * a)
        lo_b = T_arr[max(ip - hw, 0)]
        hi_b = T_arr[min(ip + hw, len(T_arr) - 1)]
        if lo_b <= Tp <= hi_b:
            return float(Tp), _vertex_stderr(result, a, b)
    return T_ref, None

def _vertex_stderr(result, a, b):
    """1-sigma error on the parabola vertex -b/(2a), propagated from the fit's
    (a, b) covariance: J = d(vertex)/d(a, b) = (b/(2a^2), -1/(2a))."""
    if result.covar is None or result.nfree < 1:
        return None
    ia, ib = result.var_names.index('a'), result.var_names.index('b')
    cov = result.covar[np.ix_([ia, ib], [ia, ib])]
    J = np.array([b / (2.0 * a * a), -1.0 / (2.0 * a)])
    var = float(J @ cov @ J)
    return float(np.sqrt(var)) if np.isfinite(var) and var >= 0 else None

def _fmt_pm(val, err, fmt, sep=' ± '):
    """'val ± err' formatted with fmt (e.g. '.3f'), or just 'val' when err is None."""
    return f'{val:{fmt}}{sep}{err:{fmt}}' if err is not None else f'{val:{fmt}}'

def _load_detailed_data(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi, c0_pre_pulse=True):
    """(data, temps, errorMsgs) of _load_detailed_data_full."""
    return _load_detailed_data_full(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi, c0_pre_pulse)[:3]

def _load_detailed_data_full(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi, c0_pre_pulse=True):
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
      3. legacy per-temperature files (flat JSON .txt, .h5 or .csv, one file per
         temperature, e.g. 'n10p0.txt').
    Regardless of format, C_infinity is (re)computed here using this tab's
    OWN convention -- the mean capacitance over the [cinf_lo, cinf_hi]
    fraction of rb_ms (DLTS_APP.py's original range-averaged estimate) --
    rather than the single-nearest-sample convention liveDataTab.py's own
    extractors use for the rest of the app, so this tab's C_infinity
    estimation is unaffected by which format backed the raw transient.

    For the JSON / h5 step files (format 3), the raw records are read once
    more for Dr. Kayi's v3.1 corrections (dP): the capacitance is converted
    from susceptance (C = B/ω, f_osc from runParams.txt) when ImpedanceIm
    holds B rather than C, each record's fill-pulse information (V_fill,
    V_rev, width, C_fill) is read from its AuxInput1 bias monitor, and -- with
    c0_pre_pulse -- C_infinity is the lower of the tail mean and the pre-pulse
    equilibrium C, with the tail window cut before a second fill pulse
    (dP.c0_estimate). ZI exports have no bias monitor here, so they keep the
    tail mean.

    Pure computation (no Tk calls), safe to run on a background thread.
    Returns (data_dict, temps_list, errorMsgs, loadInfo) where data_dict[tc] =
    (t_ms, cap, c_inf), matching this tab's existing internal shape, and
    loadInfo = dict(formats, tFe (the fill-end time of this format: dP.T_FE_ZI_MS
    for ZI exports, 0 for step files cut at the fill end), f_osc, cap_mode,
    second_pulse (ms, or None), fill (dP.fill_summary or None), fillByT
    ({T (K): dP.fill_record_info}), c0Source ({tc: 'tail' / 'pre-pulse'})).
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

    loadInfo = dict(formats=[], tFe=dP.T_FE_ZI_MS, f_osc=None, cap_mode=None, second_pulse=None, fill=None,
                    fillByT={}, c0Source={})
    if not registry:
        return {}, [], errorMsgs, loadInfo

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

    loadInfo['formats'] = [name for name, temps in (('ZI', ziTemps), ('ZI subfolders', ziSubTemps),
                                                    ('step files', legacyTemps)) if temps]
    # Fill end of the transients' time axis: step files are cut at it, ZI
    # exports start 1 ms before the trigger (see dP.T_FE_ZI_MS).
    loadInfo['tFe'] = dP.T_FE_STEP_FILES_MS if not (ziTemps or ziSubTemps) else dP.T_FE_ZI_MS
    stepRecords = _read_step_records(base, legacyTemps, registry, errorMsgs, loadInfo)

    data = {}
    for tc, rec in raw.items():
        t_ms = np.asarray(rec['time_ms'], dtype=np.float64)
        cap = np.asarray(rec['avg_cap_pf'], dtype=np.float64)
        info = None
        if tc in stepRecords:
            scale, info = stepRecords[tc]
            cap = cap * scale
            if info is not None:
                loadInfo['fillByT'][tc + 273.15] = info
        if c0_pre_pulse and info is not None:
            cInf, source = dP.c0_estimate(t_ms, cap, rb_ms, cinf_lo, cinf_hi, info)
        else:
            cInf, source = _cinf_range_mean(t_ms, cap, rb_ms, cinf_lo, cinf_hi), 'tail'
        loadInfo['c0Source'][tc] = source
        data[tc] = (t_ms, cap, cInf)

    temps = sorted(data.keys())
    loadInfo['second_pulse'] = dP.detect_second_pulse(data, temps)
    loadInfo['fill'] = dP.fill_summary(loadInfo['fillByT'])
    return data, temps, errorMsgs, loadInfo

def _read_step_records(base, temps, registry, errorMsgs, loadInfo):
    """{tc: (scale, fillInfo)} for the JSON (.txt) / h5 step files among temps:
    scale converts the extractor's ImpedanceIm x 1e12 to pF (1, or 1/ω when the
    run stored the susceptance B -- decided once, from the first file, as
    v3.1 does), fillInfo is dP.fill_record_info of the raw record (None when
    it has no AuxInput1). Sets loadInfo f_osc / cap_mode."""
    out = {}
    fOsc = dP.read_osc_frequency(base)
    loadInfo['f_osc'] = fOsc
    capMode = None
    for tc in temps:
        path = registry.get(tc)
        if not isinstance(path, str) or os.path.splitext(path)[1].lower() not in ('.txt', '.h5'):
            continue
        try:
            if path.lower().endswith('.h5'):
                rec, _ = ldT._read_h5_step(path)
            else:
                with open(path, 'r') as fh:
                    rec = json.load(fh)
            imp = np.asarray(rec['ImpedanceIm'], dtype=np.float64)
            dtS = ldT._sample_interval_s(rec.get('timeStampImps'), 1.8666666666666665e-05)
            if capMode is None:
                capMode = dP.capacitance_mode(imp, fOsc or dP.DEFAULT_F_OSC_HZ)
                loadInfo['cap_mode'] = capMode
            scale = 1.0 if capMode == 'direct' else 1.0 / (2.0 * np.pi * (fOsc or dP.DEFAULT_F_OSC_HZ))
            info = None
            if 'AuxInput1' in rec:
                info = dP.fill_record_info(np.arange(imp.size) * dtS * 1e3, imp * 1e12 * scale,
                                           np.asarray(rec['AuxInput1'], dtype=np.float64))
            out[tc] = (scale, info)
        except Exception as exc:
            errorMsgs.append(f"{tc}°C: fill-pulse information not read: {exc}")
    return out

def _cinf_range_mean(t_ms, cap, rb_ms, cinf_lo=DEFAULT_CINF_LO, cinf_hi=DEFAULT_CINF_HI):
    """C_infinity of one averaged transient: the mean capacitance over
    [cinf_lo, cinf_hi] x rb_ms (all of it if that range holds no samples).
    Both analysis tabs use this, so they normalize the DLTS signal the same way.
    Averaged in float64: the extractors can return float32, whose mean would
    differ from the same data already converted to float64 in the 7th digit."""
    t_ms, cap = np.asarray(t_ms, dtype=np.float64), np.asarray(cap, dtype=np.float64)
    mi = (t_ms >= cinf_lo * rb_ms) & (t_ms <= cinf_hi * rb_ms)
    return float(np.nanmean(cap[mi])) if mi.any() else float(np.nanmean(cap))

def _fit_arrhenius_line(x, y, Tp, Tp_err):
    """Error-weighted lmfit LinearModel fit of y = ln(en/T²) vs x = 1000/T.

    Both x and y derive from the same peak temperature Tp, so each point's
    Tp error moves it along a line rather than purely vertically. That is
    handled by the effective-variance method: the residual r = y - (m·x + b)
    changes with T at dr/dT = dy/dT - m·dx/dT = -2/T + 1000·m/T², so each
    point's effective y error is |dr/dT|·σ_T. It depends on the slope, so the
    fit is iterated from an unweighted start until the slope settles.
    Returns (lmfit ModelResult, weighted?) -- unweighted only when the points
    carry no usable Tp errors (errors then come from the scatter alone).
    """
    model = LinearModel()
    result = model.fit(y, model.guess(y, x=x), x=x)
    if _valid_errors(Tp_err) is None:
        return result, False
    for _ in range(10):
        m = result.params['slope'].value
        sig_eff = np.abs(-2.0 / Tp + 1000.0 * m / Tp**2) * Tp_err
        result = model.fit(y, result.params, x=x, weights=1.0 / sig_eff)
        if abs(result.params['slope'].value - m) <= 1e-9 * max(abs(m), 1.0):
            break
    return result, True

def _emission_rate(t1, t2, t_fe=0.0):
    """Rate-window emission rate e_n (s^-1) for t1, t2 in ms, with the times
    measured from the fill end t_fe (ms) -- dP.emission_rate; None when the
    window starts inside or before the fill pulse."""
    return dP.emission_rate(t1, t2, t_fe)

def _in_range_max(T_K, signals, t_peak_lo, t_peak_hi):
    """Largest |S| inside [t_peak_lo, t_peak_hi] (K) over every window's S(T)
    -- the reference v3.1's small-peak skip uses (see _peak_from_signal)."""
    mask = (np.asarray(T_K) >= t_peak_lo) & (np.asarray(T_K) <= t_peak_hi)
    if not mask.any():
        return None
    return max((float(np.max(np.abs(np.asarray(S)[mask]))) for S in signals), default=None)

def _peak_from_signal(T_K, S_full, S_err_full, t_peak_lo, t_peak_hi, peak_method=PEAK_METHOD_SPLINE,
                      peak_min_frac=PEAK_MIN_FRAC, ref_max=None):
    """One rate window's peak from its S(T) curve -- the step both analysis tabs
    share. Inside [t_peak_lo, t_peak_hi] (K) the signal is flipped positive if
    the peak is negative; a window whose peak is at most peak_min_frac of
    ref_max is skipped. ref_max is the in-range max|S| over all windows
    (_in_range_max, v3.1: a stronger trap outside the range then can't
    suppress a weaker trap's windows), or, when None, max|S| of this window
    over all temperatures (the old rule). Returns a dict: skipped (bool), and
    unless skipped Tp, Tp_err (None if unusable, see _find_peak), S_peak (the
    fitted peak height when the method gives one, else the grid maximum; in
    the curve's own sign), S_peak_err (None without one), sign, xFit/yFit
    (fitted curve in the curve's own sign, or None), and fallback (a profile
    fit fell back to the parabola)."""
    T_K, S_full = np.asarray(T_K, dtype=float), np.asarray(S_full, dtype=float)
    S_err_full = None if S_err_full is None else np.asarray(S_err_full, dtype=float)
    mask = (T_K >= t_peak_lo) & (T_K <= t_peak_hi)
    if not mask.any():
        return dict(skipped=True)
    T_m, S_m = T_K[mask], S_full[mask]
    S_err_m = S_err_full[mask] if S_err_full is not None else None
    sign = -1.0 if np.max(S_m) < abs(np.min(S_m)) else 1.0
    S_m = sign * S_m
    peak_val = float(np.max(S_m))
    if peak_val <= peak_min_frac * (np.max(np.abs(S_full)) if ref_max is None else ref_max):
        return dict(skipped=True)
    Tp, Tp_err, xFit, yFit, Sp, Sp_err = _find_peak_full(T_m, S_m, S_err_m, peak_method)
    return dict(skipped=False, Tp=float(Tp), Tp_err=Tp_err, S_peak=sign * (peak_val if Sp is None else Sp),
                S_peak_err=Sp_err, sign=sign, xFit=xFit, yFit=None if yFit is None else sign * np.asarray(yFit),
                fallback=peak_method in PEAK_METHOD_PROFILES and xFit is None)

def _compute_arrhenius(windows, temps, data, gamma, t_peak_lo, t_peak_hi, peak_method=PEAK_METHOD_SPLINE,
                       peak_min_frac=PEAK_MIN_FRAC, t_fe=0.0):
    T_K  = np.array([tc + 273.15 for tc in temps])

    en_list, Tp_list, Tp_err_list, Sp_list = [], [], [], []
    rows_detail = []

    signals = [(t1, t2, *_rate_window_signal(temps, data, t1, t2)) for (t1, t2) in windows
               if _emission_rate(t1, t2, t_fe) is not None]
    ref_max = _in_range_max(T_K, [s[2] for s in signals], t_peak_lo, t_peak_hi)
    for (t1, t2, S_full, S_err_full) in signals:
        pk = _peak_from_signal(T_K, S_full, S_err_full, t_peak_lo, t_peak_hi, peak_method, peak_min_frac, ref_max)
        if pk['skipped']:
            continue
        en = _emission_rate(t1, t2, t_fe)
        Tp, Tp_err, peak_val = pk['Tp'], pk['Tp_err'], abs(pk['S_peak'])
        en_list.append(en); Tp_list.append(Tp); Sp_list.append(peak_val)
        Tp_err_list.append(np.nan if Tp_err is None else Tp_err)
        rows_detail.append((t1, t2, en, Tp, Tp_err, peak_val))

    res = _arrhenius_fit(en_list, Tp_list, Tp_err_list, gamma)
    if res is None:
        return None
    res.update(Sp_arr=np.array(Sp_list), peak_method=peak_method, detail=rows_detail)
    return res

def _arrhenius_fit(en_list, Tp_list, Tp_err_list, gamma):
    """Arrhenius fit of rate-window peaks -- shared by both analysis tabs.
    Tp_err entries are K, or NaN/None where the peak has no usable error.
    Returns a dict (Et, sigma, their errors, fit mask, ...) or None if fewer
    than 2 peaks can be fitted."""
    en_arr = np.array(en_list, dtype=float)
    Tp_arr = np.array(Tp_list, dtype=float)
    Tp_err_arr = np.array([np.nan if e is None else e for e in Tp_err_list], dtype=float)   # K, NaN = no error

    # Windows whose peak has no error estimate (the peak fell on the edge of
    # the search range, so only the raw grid maximum is known) can't be
    # weighted and aren't real sub-grid peak estimates, so they are left out
    # of the weighted fit (still plotted and listed, marked as excluded) --
    # unless too few points with errors remain, in which case every point is
    # fitted unweighted.
    fit_mask = np.isfinite(Tp_err_arr)
    if fit_mask.sum() < 3:
        fit_mask = np.ones(len(en_arr), dtype=bool)
    if fit_mask.sum() < 2:
        return None

    x = 1000.0 / Tp_arr
    y = np.log(en_arr / Tp_arr**2)
    linResult, weighted = _fit_arrhenius_line(x[fit_mask], y[fit_mask], Tp_arr[fit_mask], Tp_err_arr[fit_mask])
    sl, sl_se = linResult.params['slope'].value, linResult.params['slope'].stderr
    ic, ic_se = linResult.params['intercept'].value, linResult.params['intercept'].stderr
    covar = linResult.covar   # [slope, intercept] order, for the plot's confidence band
    # stderr is only meaningful with residual degrees of freedom, so a
    # 2-point line reports no error rather than a misleading ~0.
    if fit_mask.sum() < 3:
        sl_se = ic_se = covar = None
    kB       = KB_EV
    Et       = -sl * 1000.0 * kB
    Et_se    = sl_se * 1000.0 * kB if sl_se is not None else None
    sigma    = np.exp(ic) / gamma
    sigma_se = sigma * ic_se if ic_se is not None else None   # dσ = σ·d(intercept)
    R2       = float(linResult.rsquared)
    return dict(en_arr=en_arr, Tp_arr=Tp_arr, Tp_err_arr=Tp_err_arr,
                Et=Et, Et_se=Et_se, sigma=sigma, sigma_se=sigma_se, R2=R2,
                N=int(fit_mask.sum()), N_excluded=int((~fit_mask).sum()), fit_mask=fit_mask,
                weighted=weighted, redchi=float(linResult.redchi),
                slope=sl, slope_se=sl_se, intercept=ic, intercept_se=ic_se, covar=covar,
                x=x, y=y)

def _trap_density(data, temps, rb_ms, nd):
    """Trap density N_T = 2 * max over temperatures of |(C(rb_ms) - C(2 ms)) / C_inf|
    * Nd (cm^-3), from _prepare_signal_data records -- shared by both analysis tabs."""
    S_ref = np.array([(_cap_at(data[tc], rb_ms) - _cap_at(data[tc], 2.0)) / data[tc][2] for tc in temps])
    return 2.0 * float(np.nanmax(np.abs(S_ref))) * nd

#---------------------PEAK REGIONS (SHARED WITH QUICK ANALYSIS)-------------------------#
# Quick Analysis' Peak Deconvolution and this tab's Peak Regions split a rate
# window's S(T) into the same primitives, with impedanceAnalysis_Tools' shared
# finders, through the helpers below -- defined here (the module both tabs
# import) so this tab's worker process can run them too. A region is a dict
# {'tLo', 'tHi' (K), 'primitives': [PRIMITIVE_OPTIONS labels], 'prominence'}.

# Peak primitives: UI label -> impedanceAnalysis_Tools key
# (iaT.DECONV_PRIMITIVES), and the short name both tabs show.
# A Smoothing Spline region is not a sum of shapes: the spline is fitted alone
# and its peaks are those above the region's minimum prominence.
PRIMITIVE_SPLINE = 'Smoothing Spline (prominence peaks)'
PRIMITIVE_KEYS = {
    'Mirrored Lognormal (left tail)': 'mirroredLognormal',
    'Gaussian': 'gaussian',
    'Lorentzian': 'lorentzian',
    'Voigt': 'voigt',
    'Pseudo-Voigt': 'pseudoVoigt',
    'Constant Baseline': 'constant',
    'Linear Baseline': 'linear',
}
PRIMITIVE_OPTIONS = list(PRIMITIVE_KEYS) + [PRIMITIVE_SPLINE]
PRIMITIVE_SHORT = {
    'Mirrored Lognormal (left tail)': 'MirLogN', 'Gaussian': 'Gauss', 'Lorentzian': 'Lorentz',
    'Voigt': 'Voigt', 'Pseudo-Voigt': 'pVoigt', 'Constant Baseline': 'Const', 'Linear Baseline': 'Linear',
    PRIMITIVE_SPLINE: 'Spline',
}
# Smoothing Spline regions: a peak's prominence must be at least this fraction
# of the region's largest |S|. 0.02 still finds the R11C4 run's ~4 % shoulder
# next to its main 300 K peak.
DEFAULT_PROMINENCE = '0.02'

def _region_problem(region):
    """Why a region can't be deconvolved, or None if it can."""
    prims = region['primitives']
    if region['tHi'] <= region['tLo']:
        return 'its upper bound must exceed the lower bound'
    if not prims:
        return 'it has no primitives; add some'
    if PRIMITIVE_SPLINE in prims and len(prims) > 1:
        return 'Smoothing Spline must be its only primitive'
    if PRIMITIVE_SPLINE not in prims and not any(PRIMITIVE_KEYS[p] in iaT.DECONV_PEAK_PRIMITIVES for p in prims):
        return 'it needs at least one peak-shaped primitive (baselines alone give no peak)'
    return None

def _usable_tp_err(tpErr, onEdge):
    """A peak's T_peak error, or None -- leaving it out of the weighted
    Arrhenius fit, like _guard_peak_error -- when the peak is on its region's
    edge or has no usable error (below MIN_TP_ERR_K included)."""
    if onEdge or tpErr is None or not np.isfinite(tpErr) or tpErr < MIN_TP_ERR_K:
        return None
    return float(tpErr)

def _deconvolve_region(sig, region):
    """One rate window's S(T) -- sig = {'T_k', 'Signal', 'Signal_err'}, like a
    dltsc.rateWindow_signals entry -- deconvolved inside one region with
    non-empty primitives. Returns a dict: ok, message, x (the region's temperatures),
    residual (data - fit, divided by the point errors when residualNorm),
    residualNorm, xf/yf (total fit), componentCurves [(primitive label,
    curve on xf)], peaks [{T_peak, T_peak_err, S_peak, S_peak_err, primitive,
    onEdge}], redchi, rsquared."""
    T, S, S_err = sig['T_k'], sig['Signal'], sig['Signal_err']
    mask = (T >= region['tLo']) & (T <= region['tHi'])
    out = dict(ok=False, message='', x=T[mask], residual=None, residualNorm=False, xf=None, yf=None,
               componentCurves=[], peaks=[], redchi=None, rsquared=None)
    if mask.sum() < 5:
        out['message'] = f"only {int(mask.sum())} temperature(s) in {region['tLo']:g}–{region['tHi']:g} K"
        return out
    x, y = T[mask], S[mask]
    e = None if S_err is None else _valid_errors(S_err[mask])
    try:
        if region['primitives'] == [PRIMITIVE_SPLINE]:
            res = iaT.impdData._smoothingSpline_multiPeakFinder(x, y, minProminence=region['prominence'],
                                                                signalYErr=e)
            out.update(ok=True, xf=res['xf'], yf=res['yf'])
            residual = y - np.interp(x, res['xf'], res['yf'])
            for p in res['peaks']:
                out['peaks'].append(dict(T_peak=p['center'], T_peak_err=_usable_tp_err(p['centerErr'], False),
                                         S_peak=p['height'], S_peak_err=p['heightErr'],
                                         primitive=PRIMITIVE_SPLINE, onEdge=False))
        else:
            res = iaT.impdData._deconvolve_peaks(x, y, [PRIMITIVE_KEYS[p] for p in region['primitives']],
                                                 signalYErr=e)
            if res['xf'] is None:
                out['message'] = res['message']
                return out
            out.update(ok=True, xf=res['xf'], yf=res['yf'], redchi=res['redchi'], rsquared=res['rsquared'],
                       componentCurves=list(zip(region['primitives'], res['componentCurves'])),
                       message='' if res['success'] else f"fit did not converge ({res['message']})")
            residual = res['residual']
            for label, comp in zip(region['primitives'], res['components']):
                if comp['isPeak']:
                    out['peaks'].append(dict(T_peak=comp['center'],
                                             T_peak_err=_usable_tp_err(comp['centerErr'], comp['onEdge']),
                                             S_peak=comp['height'], S_peak_err=comp['heightErr'],
                                             primitive=label, onEdge=comp['onEdge']))
    except Exception as exc:
        out.update(ok=False, message=f'failed: {exc}', xf=None, yf=None, componentCurves=[], peaks=[])
        return out
    out['residualNorm'] = e is not None
    out['residual'] = residual / e if e is not None else residual
    return out

def _boxcar_peak_factor(t1, t2, t_fe=0.0):
    """S_peak / (ΔC/C∞) of an ideal exponential transient for a double boxcar
    (t1, t2): exp(-e t1) - exp(-e t2) at the rate-window emission rate e,
    = r^(-1/(r-1)) - r^(-r/(r-1)) = r^(-1/(r-1)) (1 - 1/r) with r = t2/t1, the
    times measured from the fill end t_fe (dP.boxcar_factor)."""
    return dP.boxcar_factor(t1, t2, t_fe)

def _trap_density_from_peaks(peaks, nd, t_fe=0.0):
    """Trap density Nt = 2 Nd ΔC/C∞ (small-signal, no fill-geometry or N_D(T)
    correction -- those are the Trap Concentration tab's), with ΔC/C∞ =
    |S_peak| / _boxcar_peak_factor for each peak (one per set), combined into
    an error-weighted mean when every peak has a height error (its error is the
    weighted-mean error, scaled up by sqrt(reduced chi-square) when the sets
    scatter more than their errors), else the plain mean and its standard
    error (dP.weighted_mean). Returns (Nt, Nt_err); Nt_err is None for a single
    peak without one."""
    values = [2.0 * nd * abs(p['S_peak']) / _boxcar_peak_factor(p['t1'], p['t2'], t_fe) for p in peaks]
    errs = [None if p['S_peak_err'] is None
            else 2.0 * nd * p['S_peak_err'] / _boxcar_peak_factor(p['t1'], p['t2'], t_fe) for p in peaks]
    return dP.weighted_mean(values, errs)

def _region_method_text(region, peak_method):
    """How a region's peaks are found: its primitives, or the single-peak
    peak_method when it has none."""
    if region['primitives']:
        text = ' + '.join(PRIMITIVE_SHORT[p] for p in region['primitives'])
        if region['primitives'] == [PRIMITIVE_SPLINE]:
            text += f" (prom. ≥ {region['prominence']:g})"
        return text
    return f'single peak, {peak_method}'

def _peak_id_order(peakId):
    """Sort key of a peak id 'R<r>P<k>': (r, k) as numbers, so R10 follows R9."""
    r, k = peakId[1:].split('P')
    return int(r), int(k)

def _window_region_peaks(T_K, S, S_err, region, peak_method, peak_min_frac=PEAK_MIN_FRAC, ref_max=None):
    """Peaks of one window's S(T) inside one region, low to high T: with the
    region's primitives (_deconvolve_region -- Quick Analysis' method) when it
    has any, else this tab's single-peak finder over the region
    (_peak_from_signal with peak_method and ref_max, i.e. the region acts as
    the old Peak Search Range). Returns (peaks, message): peaks as [{T_peak,
    T_peak_err, S_peak, S_peak_err, primitive, onEdge, fallback}], message ''
    unless something failed."""
    if region['primitives']:
        res = _deconvolve_region(dict(T_k=T_K, Signal=S, Signal_err=_valid_errors(S_err)), region)
        return [dict(p, fallback=False) for p in res['peaks']], res['message']
    pk = _peak_from_signal(T_K, S, S_err, region['tLo'], region['tHi'], peak_method, peak_min_frac, ref_max)
    if pk['skipped']:
        return [], ''
    return [dict(T_peak=pk['Tp'], T_peak_err=pk['Tp_err'], S_peak=pk['S_peak'], S_peak_err=pk['S_peak_err'],
                 primitive=peak_method, onEdge=pk['Tp_err'] is None, fallback=pk['fallback'])], ''

def _compute_trap_arrhenius(windows, temps, data, gamma, regions, peak_method=PEAK_METHOD_SPLINE, nd=DEFAULT_ND,
                            peak_min_frac=PEAK_MIN_FRAC, t_fe=0.0):
    """Every region's peaks in every window, grouped into traps by peak id
    R<r>P<k> (the k-th peak of region r from low T), each trap with its own
    _arrhenius_fit -- the multi-trap counterpart of _compute_arrhenius, which a
    single region without primitives reproduces exactly.

    Returns (traps, windowPeaks, messages). traps: one _arrhenius_fit result
    per trap with at least 2 fittable windows, in peak-id order, plus peakId,
    region (index), method (text), win_idx (window index of each point),
    Sp_arr (|S_peak|), detail (t1, t2, en, Tp (K), Tp_err, |S_peak| rows, as
    _compute_arrhenius), peak_method, Nt / Nt_err (_trap_density_from_peaks
    over the fitted windows), n_fallback (profile fits that fell back to the
    parabola), t_fe, and peaks (one dict per window: t1, t2, e_n, T_peak,
    T_peak_err, S_peak, S_peak_err, used -- what Trap Concentration needs).
    windowPeaks[w]: [(peakId, peak)] of window w. messages: fit problems worth
    logging.

    Emission rates are measured from the fill end t_fe (ms); a window that
    starts inside the fill pulse is left out. The small-peak skip of a region
    without primitives is relative to its in-range max over all windows (v3.1)."""
    T_K = np.array([tc + 273.15 for tc in temps])
    byTrap, windowPeaks, messages = dict(), [], []
    signals = [_rate_window_signal(temps, data, t1, t2) for (t1, t2) in windows]
    usable = [_emission_rate(t1, t2, t_fe) is not None for (t1, t2) in windows]
    if not all(usable):
        messages.append(f'{usable.count(False)} window(s) start inside the fill pulse (t1 <= t_FE = {t_fe:g} ms); '
                        f'left out.')
    refMax = [None if region['primitives'] else
              _in_range_max(T_K, [s[0] for s, ok in zip(signals, usable) if ok], region['tLo'], region['tHi'])
              for region in regions]
    for w, (t1, t2) in enumerate(windows):
        found = []
        if not usable[w]:
            windowPeaks.append(found)
            continue
        S, S_err = signals[w]
        en = _emission_rate(t1, t2, t_fe)
        for r, region in enumerate(regions):
            peaks, message = _window_region_peaks(T_K, S, S_err, region, peak_method, peak_min_frac, refMax[r])
            if message:
                messages.append(f'{t1:g}/{t2:g} ms, R{r + 1}: {message}')
            for k, pk in enumerate(peaks):
                peakId = f'R{r + 1}P{k + 1}'
                found.append((peakId, pk))
                byTrap.setdefault(peakId, []).append((w, t1, t2, en, pk))
        windowPeaks.append(found)

    traps = []
    for peakId in sorted(byTrap, key=_peak_id_order):
        entries = byTrap[peakId]
        res = _arrhenius_fit([e[3] for e in entries], [e[4]['T_peak'] for e in entries],
                             [e[4]['T_peak_err'] for e in entries], gamma)
        if res is None:
            messages.append(f'{peakId}: fewer than 2 windows can be fitted; no Arrhenius line.')
            continue
        peaks = [dict(t1=t1, t2=t2, e_n=en, T_peak=pk['T_peak'], T_peak_err=pk['T_peak_err'], S_peak=pk['S_peak'],
                      S_peak_err=pk['S_peak_err'], used=bool(fitted))
                 for (_, t1, t2, en, pk), fitted in zip(entries, res['fit_mask'])]
        nt, ntErr = _trap_density_from_peaks([p for p in peaks if p['used']], nd, t_fe)
        r = _peak_id_order(peakId)[0] - 1
        res.update(peakId=peakId, region=r, method=_region_method_text(regions[r], peak_method),
                   win_idx=np.array([e[0] for e in entries]),
                   Sp_arr=np.array([abs(e[4]['S_peak']) for e in entries]),
                   detail=[(t1, t2, en, pk['T_peak'], pk['T_peak_err'], abs(pk['S_peak']))
                           for _, t1, t2, en, pk in entries],
                   peak_method=_region_method_text(regions[r], peak_method), Nt=nt, Nt_err=ntErr,
                   n_fallback=sum(1 for e in entries if e[4].get('fallback')), t_fe=t_fe, peaks=peaks)
        traps.append(res)
    return traps, windowPeaks, messages

def _prepare_spectra(mw, temps, data, n_spectra, t_fe=0.0):
    """DLTS spectra for n_spectra of the multi-windows: list of (k, t1, t2, en, S*1e3),
    en from the fill end (from t = 0 for a window inside the fill pulse)."""
    idx_show = np.round(np.linspace(0, len(mw) - 1, min(n_spectra, len(mw)))).astype(int)
    spectra = []
    for k in idx_show:
        t1, t2 = mw[k]
        S = np.array([(_cap_at(data[tc], t2) - _cap_at(data[tc], t1)) / data[tc][2] * 1e3 for tc in temps])
        en = _emission_rate(t1, t2, t_fe) or _emission_rate(t1, t2)
        spectra.append((int(k), t1, t2, en, S))
    return spectra

def _prepare_transient_map(temps, data, rb_ms):
    """ΔC/C0(t, T) grid for the transient map on a log-spaced time axis.
    Returns dict(t_s, Z_disp, levels), or None if there are too few time points."""
    t_ms_ref = data[temps[0]][0]          # full axis in ms
    t_lo_ms  = max(2.0, t_ms_ref[1])      # skip pre-pulse / first point
    t_hi_ms  = rb_ms * 0.95

    mask_t    = (t_ms_ref >= t_lo_ms) & (t_ms_ref <= t_hi_ms)
    t_ms_full = t_ms_ref[mask_t]
    if len(t_ms_full) < 10:
        return None

    n_t   = min(250, len(t_ms_full))
    idx_l = np.unique(np.round(np.logspace(0, np.log10(len(t_ms_full) - 1), n_t)).astype(int))
    idx_l = np.clip(idx_l, 0, len(t_ms_full) - 1)
    t_ms  = t_ms_full[idx_l]
    t_s   = t_ms * 1e-3                    # seconds

    Z = np.empty((len(t_ms), len(temps)))
    for j, tc in enumerate(temps):
        cinf_j = data[tc][2]
        if abs(cinf_j) < 1e-30:
            Z[:, j] = 0.0
            continue
        Z[:, j] = (_cap_at(data[tc], t_ms) - cinf_j) / cinf_j

    Z_disp = Z * 1e5

    vlo = float(np.nanpercentile(Z_disp, 1))
    vhi = float(np.nanpercentile(Z_disp, 99))
    if vhi <= vlo:
        vlo, vhi = -1e-4, 1e-4
    levels = np.linspace(vlo, vhi, 64)
    return dict(t_s=t_s, Z_disp=Z_disp, levels=levels)

def _prepare_rate_window_map(temps, data, t1_min, t1_max, ratio, t_fe=0.0):
    """Nt/Nd sampled over (1/kT, T^2/en) and interpolated onto a 220x220 grid
    for the Rate-Window Analysis map (en from the fill end; windows inside the
    fill pulse left out). Returns dict(Xi, Yi, Zi, z_lo, z_hi, x_min, x_max),
    or None if there are too few points to interpolate."""
    kB     = KB_EV
    n_map  = 100
    t1_arr = np.logspace(np.log10(t1_min), np.log10(t1_max), n_map)
    T_K    = np.array([tc + 273.15 for tc in temps])

    x_pts, y_pts, z_pts = [], [], []
    for t1 in t1_arr:
        t2 = ratio * t1
        en = _emission_rate(t1, t2, t_fe)
        if en is None:
            continue
        for j, tc in enumerate(temps):
            T = T_K[j]
            cinf = data[tc][2]
            if abs(cinf) < 1e-30:
                continue
            S = (_cap_at(data[tc], t2) - _cap_at(data[tc], t1)) / cinf
            nt_nd = 2.0 * abs(S)
            if nt_nd < 1e-8:
                continue
            x_pts.append(1.0 / (kB * T))          # eV^-1
            y_pts.append(T ** 2 / en)               # K^2 s
            z_pts.append(nt_nd)

    if len(x_pts) < 6:
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
    return dict(Xi=Xi, Yi=Yi, Zi=Zi, z_lo=z_lo, z_hi=z_hi, x_min=float(x_pts.min()), x_max=float(x_pts.max()))

def _compute_detailed_analysis(data, temps, p):
    """Everything Run Analysis needs short of creating matplotlib artists:
    one Arrhenius fit per trap for both window sets, Nt, and the (optional)
    spectra / transient-map / rate-window-map arrays. p is the parameter
    snapshot taken by _detailed_run_analysis; p['regions'] (see the PEAK
    REGIONS section) are where peaks are found -- without it, one region
    [tpLo, tpHi] with this tab's single-peak finder, the old behaviour. Runs in
    this tab's worker process (see _get_detailed_executor), so it must stay a
    pure, picklable top-level function with no Tk/dltsc access. Raises
    ValueError on unusable input.

    resMw / resStd are the first trap's multi-window / standard results (the
    single trap of the old behaviour), kept for callers that read one trap.
    """
    # Denoise / read-off method applied once, up front, so every downstream
    # quantity (peaks, spectra, both maps, Nt) sees the same C(t).
    data = _prepare_signal_data(data, temps, p['signalMethod'], p['denoise'])

    regions = p.get('regions') or [dict(tLo=p['tpLo'], tHi=p['tpHi'], primitives=[],
                                        prominence=float(DEFAULT_PROMINENCE))]
    t1Arr = np.logspace(np.log10(p['t1Min']), np.log10(p['t1Max']), p['nWin'])
    mw = [(float(t1), float(p['ratio'] * t1)) for t1 in t1Arr]

    tFe = p.get('tFe', 0.0)
    trapsMw, windowPeaks, messages = _compute_trap_arrhenius(mw, temps, data, p['gamma'], regions,
                                                             p['peakMethod'], p['nd'], t_fe=tFe)
    # A standard window set to 0 / 0 (or any t2 <= t1) is unused, so the table can
    # also hold fewer than 5 windows -- e.g. Quick Analysis' four, for comparison.
    stdWins = [(float(a), float(b)) for a, b in p['stdWins'] if a > 0 and b > a]
    trapsStd = []
    if stdWins:
        trapsStd, _, stdMessages = _compute_trap_arrhenius(stdWins, temps, data, p['gamma'], regions,
                                                           p['peakMethod'], p['nd'], t_fe=tFe)
        messages += [f'standard {m}' for m in stdMessages]
    if not trapsMw:
        raise ValueError('Multi-window: no peaks found. Check the t1 range and the peak regions.')
    resMw = trapsMw[0]
    resStd = next((t for t in trapsStd if t['peakId'] == resMw['peakId']), None)

    T_K = np.array([tc + 273.15 for tc in temps])
    Nt = _trap_density(data, temps, p['rbMs'], p['nd'])

    return dict(
        resMw=resMw, resStd=resStd, traps=trapsMw, trapsStd=trapsStd, windowPeaks=windowPeaks,
        regions=regions, messages=messages, mw=mw, T_K=T_K, Nt=Nt, tFe=tFe,
        methodTable=(_peak_method_table(mw, temps, data, p, regions, trapsMw) if p.get('methodTable') else None),
        stability=(_region_stability(mw, temps, data, p, regions, trapsMw) if p.get('stability') else None),
        spectra=_prepare_spectra(mw, temps, data, p['nSpectra'], tFe) if p['showSpectra'] else None,
        tmap=_prepare_transient_map(temps, data, p['rbMs']) if p['showTmap'] else None,
        rwm=(_prepare_rate_window_map(temps, data, p['t1Min'], p['t1Max'], p['ratio'], tFe)
             if p['showRwm'] else None))

def _peak_method_table(mw, temps, data, p, regions, trapsMw):
    """v3.1's peak-finder sensitivity table: the multi-window analysis redone
    with every PEAK_METHOD_OPTIONS finder (same windows and regions). Only
    regions without primitives use the finder, so only their traps are listed.
    Returns {peakId: [(method, None or dict(Et, Et_se, sigma, R2, Nt, n_fallback))]},
    in PEAK_METHOD_OPTIONS order; empty if every region has primitives."""
    single = {t['peakId'] for t in trapsMw if not regions[t['region']]['primitives']}
    table = {pid: [] for pid in sorted(single, key=_peak_id_order)}
    if not table:
        return table
    for method in PEAK_METHOD_OPTIONS:
        try:
            traps = (trapsMw if method == p['peakMethod'] else
                     _compute_trap_arrhenius(mw, temps, data, p['gamma'], regions, method, p['nd'],
                                             t_fe=p.get('tFe', 0.0))[0])
        except Exception:
            traps = []
        byId = {t['peakId']: t for t in traps}
        for pid in table:
            t = byId.get(pid)
            table[pid].append((method, None if t is None else dict(
                Et=t['Et'], Et_se=t['Et_se'], sigma=t['sigma'], R2=t['R2'], Nt=t['Nt'], n_fallback=t['n_fallback'])))
    return table

STABILITY_DELTA_K = 20.0    # v3.1: limits moved by ±20 °C
STABILITY_MARGIN_K = 15.0   # a limit moves inward only if every peak stays this far inside it
STABILITY_MAX_SPREAD_EV = 0.05

def _region_stability(mw, temps, data, p, regions, trapsMw, delta=STABILITY_DELTA_K):
    """v3.1's range-stability scan of the deconvolution regions (those with
    primitives): each is refitted with its T limits moved by ±delta K. A
    limit is moved inward only if every fitted peak centre stays at least
    STABILITY_MARGIN_K inside it (otherwise the test would just cut the peak
    off); ranges whose Arrhenius line is poor (R² < 0.95, or < 8 windows) are
    ignored. Returns {peakId: (min Et, max Et, number of usable ranges)} -- a
    spread above STABILITY_MAX_SPREAD_EV means the split is not robust (merged
    peaks are model dependent)."""
    out = {}
    for r, region in enumerate(regions):
        if not region['primitives']:
            continue
        base = [t for t in trapsMw if t['region'] == r]
        t0s = [float(tp) for t in base for tp in t['Tp_arr']]
        tMin, tMax = (min(t0s), max(t0s)) if t0s else (region['tLo'], region['tHi'])
        lo, hi = region['tLo'], region['tHi']
        los = [lo - delta, lo] + ([lo + delta] if lo + delta <= tMin - STABILITY_MARGIN_K else [])
        his = [hi + delta, hi] + ([hi - delta] if hi - delta >= tMax + STABILITY_MARGIN_K else [])
        ets = {}
        for loK in los:
            for hiK in his:
                if (loK, hiK) == (lo, hi):
                    traps = [dict(t, peakId=f"R1P{_peak_id_order(t['peakId'])[1]}") for t in base]
                else:
                    try:
                        traps = _compute_trap_arrhenius(mw, temps, data, p['gamma'], [dict(region, tLo=loK, tHi=hiK)],
                                                        p['peakMethod'], p['nd'], t_fe=p.get('tFe', 0.0))[0]
                    except Exception:
                        continue
                for t in traps:
                    if t['R2'] >= 0.95 and t['N'] >= 8:
                        ets.setdefault(f"R{r + 1}P{_peak_id_order(t['peakId'])[1]}", []).append(t['Et'])
        for t in base:
            e = ets.get(t['peakId'])
            out[t['peakId']] = (min(e), max(e), len(e)) if e else None
    return out

def _detailed_checks(out, params, loadInfo):
    """v3.1's "Checks" on the Et / σ result, per trap, in plain language:
    line-shape sensitivity, parabola bias, overlap (R²), peaks at the region
    edge, emission-rate span, a second fill pulse inside the windows, lock-in
    settling at low test frequency, range stability. The Nt checks are the
    Trap Concentration tab's (dP.nt_checks)."""
    notes = []
    loadInfo = loadInfo or {}
    windows = list(out['mw'])
    for res in out['traps']:
        pid = res['peakId']
        rows = dict((m, v) for m, v in (out.get('methodTable') or {}).get(pid, []) if v)
        sym = [rows[m]['Et'] for m in (PEAK_METHOD_GAUSSIAN, PEAK_METHOD_PVOIGT, PEAK_METHOD_VOIGT) if m in rows]
        par = rows.get(PEAK_METHOD_PARABOLIC)
        if len(sym) >= 2 and (max(sym) - min(sym)) > 0.03:
            notes.append(f'{pid}: Gaussian / Pseudo-Voigt / Voigt disagree by {max(sym) - min(sym):.3f} eV: the '
                         f'result depends on the line shape, quote it as a range.')
        if par and sym and abs(par['Et'] - float(np.median(sym))) > 0.05:
            notes.append(f'{pid}: the parabolic peak top gives Eₜ = {par["Et"]:.3f} eV vs {float(np.median(sym)):.3f} eV '
                         f'from the fitted profiles. DLTS peaks are asymmetric; the parabola biases Eₜ and σₙ. '
                         f'Use a fitted profile.')
        if res['R2'] < 0.995:
            notes.append(f'{pid}: Arrhenius R² = {res["R2"]:.4f} (< 0.995): the peak is probably overlapped by a '
                         f'neighbouring trap. Deconvolve it (Peak Regions with primitives) and check its range '
                         f'stability before quoting Eₜ.')
        region = out['regions'][res['region']]
        nEdge = sum(1 for tp in res['Tp_arr'] if tp < region['tLo'] + 3 or tp > region['tHi'] - 3)
        if nEdge:
            notes.append(f'{pid}: {nEdge} window peak(s) lie within 3 K of the region limit: widen the region or '
                         f'the peak is cut off.')
        if res.get('n_fallback'):
            notes.append(f'{pid}: the {params["peakMethod"]} fit fell back to the parabola in {res["n_fallback"]} '
                         f'window(s).')
        en = res['en_arr']
        if len(en) and max(en) / min(en) < 30:
            notes.append(f'{pid}: emission rates span only {max(en) / min(en):.0f}x: Eₜ and σₙ are strongly '
                         f'correlated and the ± shown is statistical only.')
        st = (out.get('stability') or {}).get(pid)
        if st is not None and st[1] - st[0] > STABILITY_MAX_SPREAD_EV:
            notes.append(f'{pid}: NOT ROBUST -- Eₜ moves from {st[0]:.3f} to {st[1]:.3f} eV when the region limits '
                         f'move by ±{STABILITY_DELTA_K:g} K ({st[2]} usable ranges).')
    sp = loadInfo.get('second_pulse')
    if sp:
        late = [w for w in windows if w[1] > sp - 3.0]
        if late:
            notes.append(f'A second fill pulse sits at ~{sp:.0f} ms in the transients; {len(late)} window(s) have '
                         f't₂ within 3 ms of it or beyond. Keep t₂ below ~{sp - 5:.0f} ms.')
    fo = loadInfo.get('f_osc')
    if fo and fo <= 20e3 and windows:
        t1m = min(w[0] for w in windows) - out.get('tFe', 0.0)
        if t1m < 4.0:
            notes.append(f'Test frequency is {fo / 1e3:g} kHz: the lock-in needs about 3 ms to settle after the fill '
                         f'pulse (τ₁ = {t1m:.1f} ms here). Use t₁ ≥ 5 ms.')
    return notes


#---------------------WORKER PROCESS-------------------------#
def _get_detailed_executor():
    """Return this tab's own single-worker ProcessPoolExecutor, creating it on
    first use. Load and Run both do their number crunching there rather than
    on a plain background thread: a thread still shares the GIL with the Tk
    main thread, so pure-Python-heavy work (the per-file parsing inside
    ldT._compute_mixed_transients, per-window lmfit fits, the rate-window map
    sampling loop) would still make tab switches and redraws lag -- the same
    finding that moved Qualitative Analysis' extraction into a process (see
    ldT._process_raw_transients). A separate process has its own GIL, and
    being this tab's OWN executor (not ldT's shared one) means Detailed
    Analysis jobs never queue behind, or hold up, the other tabs' work.
    The caller's background thread only blocks on future.result().
    """
    if dltsc.detailed_executor is None:
        dltsc.detailed_executor = ProcessPoolExecutor(max_workers=1)
    return dltsc.detailed_executor

def _run_in_detailed_process(fn, *args):
    """Submit fn(*args) to the worker process and block (on a background
    thread only) for its result. If the worker process died, drop the broken
    executor so the next Load/Run starts a fresh one instead of failing forever."""
    try:
        return _get_detailed_executor().submit(fn, *args).result()
    except BrokenProcessPool:
        dltsc.detailed_executor = None
        raise


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
    """Scan the selected folder's temperature subfolders in this tab's worker
    process (waited on from a background thread), so a large sweep never
    freezes the GUI or slows the other tabs.
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
    c0PrePulse = bool(dltsc.detailed_c0PrePulseVar.get())

    def worker():
        errorMsg = None
        data, temps, loadErrors, loadInfo = {}, [], [], {}
        try:
            data, temps, loadErrors, loadInfo = _run_in_detailed_process(
                _load_detailed_data_full, base, gridOff, gridDt, chunkSize, rbMs, cinfLo, cinfHi, c0PrePulse)
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
            dltsc.detailed_loadInfo = loadInfo
            dltsc.detailed_folder = base
            _set_detailed_buttons_state('normal')
            # The fill end of this format's time axis (v3.1's t_FE): 0 for step
            # files (cut at the fill end), 1.307 ms for ZI exports.
            dltsc.detailed_tFeVar.set(loadInfo['tFe'])
            msg = _detailed_load_message(temps, loadInfo)
            if dltsc.detailed_loadInfoLabel is not None:
                dltsc.detailed_loadInfoLabel.config(text=msg, foreground=C0)
            if dltsc.detailed_statusLabel is not None:
                dltsc.detailed_statusLabel.config(text=msg)
            dltsc.log_to_textbox(f"Detailed analysis: {msg}")
            for err in loadErrors:
                dltsc.log_to_textbox(f"Detailed analysis: {err}")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _detailed_load_message(temps, loadInfo):
    """Load summary: temperatures, format, f_osc and capacitance mode, second
    fill pulse, the fill pulse read from AuxInput1, C0 source, and t_FE."""
    n = len(temps)
    msg = f'{n} temperatures loaded: {temps[0] + 273.15:.0f} K to {temps[-1] + 273.15:.0f} K'
    if loadInfo.get('formats'):
        msg += f' ({", ".join(loadInfo["formats"])})'
    if loadInfo.get('cap_mode'):
        fo = loadInfo.get('f_osc')
        msg += (f'  |  C from {"direct value" if loadInfo["cap_mode"] == "direct" else "B/ω"}'
                + (f', f_osc {fo / 1e3:g} kHz' if fo else f', f_osc not in runParams.txt '
                   f'(assumed {dP.DEFAULT_F_OSC_HZ / 1e3:g} kHz)'))
    if loadInfo.get('second_pulse'):
        msg += f'  |  2nd fill pulse at {loadInfo["second_pulse"]:.0f} ms'
    fs = loadInfo.get('fill')
    if fs:
        msg += (f'  |  fill {fs["v_fill"]:+.2f} V / reverse {fs["v_rev"]:+.2f} V'
                + (f' / {fs["width_ms"]:.2g} ms' if fs.get('width_ms') else '')
                + f' (from AuxInput1), C_fill in {fs["n_cfill"]}/{n} records')
    nPre = sum(1 for s in loadInfo.get('c0Source', {}).values() if s == 'pre-pulse')
    if nPre:
        msg += f'  |  C₀ from the pre-pulse level in {nPre}/{n} records'
    msg += f'  |  t_FE set to {loadInfo.get("tFe", 0.0):g} ms'
    return msg


#---------------------RUN ANALYSIS-------------------------#
def _detailed_run_analysis():
    if not dltsc.detailed_data:
        dltsc.log_to_textbox("Detailed analysis: load data first.")
        return
    if dltsc.detailed_loadingBusy or dltsc.detailedProcessingBusy:
        return
    regions = dltsc.detailed_regions or []
    problems = [f'R{r + 1}: {problem}' for r, region in enumerate(regions)
                if (problem := ('its upper bound must exceed the lower bound' if region['tHi'] <= region['tLo']
                                else region['primitives'] and _region_problem(region)))]
    if not regions:
        problems = ['add at least one peak region']
    if problems:
        message = 'Peak regions: ' + '; '.join(problems) + '.'
        dltsc.log_to_textbox(f"Detailed analysis: {message}")
        if dltsc.detailed_statusLabel is not None:
            dltsc.detailed_statusLabel.config(text=message)
        return

    dltsc.detailedProcessingBusy = True
    _set_detailed_buttons_state('disabled')
    if dltsc.detailed_statusLabel is not None:
        dltsc.detailed_statusLabel.config(text='Running analysis...')

    # Snapshot everything the worker (and the plot built from its result)
    # needs, so neither touches Tk variables later and the plot always
    # matches the parameters the analysis actually ran with.
    data = dltsc.detailed_data
    temps = dltsc.detailed_temps
    params = dict(
        nWin=dltsc.detailed_nWinVar.get(),
        t1Min=dltsc.detailed_t1MinVar.get(),
        t1Max=dltsc.detailed_t1MaxVar.get(),
        ratio=dltsc.detailed_ratioVar.get(),
        stdWins=[(v1.get(), v2.get()) for v1, v2 in dltsc.detailed_stdEntries],
        gamma=dltsc.detailed_gammaVar.get(),
        nd=dltsc.detailed_ndVar.get(),
        tpLo=dltsc.detailed_tpeakLoVar.get(),
        tpHi=dltsc.detailed_tpeakHiVar.get(),
        # Copies, so later edits to the regions can't change a running analysis.
        regions=[dict(region, primitives=list(region['primitives'])) for region in dltsc.detailed_regions],
        peakMethod=dltsc.detailed_peakMethodVar.get(),
        signalMethod=dltsc.detailed_signalMethodVar.get(),
        denoise=dltsc.detailed_denoiseVar.get(),
        rbMs=dltsc.detailed_rbMsVar.get(),
        tFe=dltsc.detailed_tFeVar.get(),
        methodTable=bool(dltsc.detailed_methodTableVar.get()),
        stability=bool(dltsc.detailed_stabilityVar.get()),
        # Every panel's data and every window's spectrum, whatever is shown
        # now: the Display options then change the plots without a re-run.
        showStd=True,
        showSpectra=True,
        nSpectra=dltsc.detailed_nWinVar.get(),
        showTmap=True,
        showTau=True,
        showRwm=True,
    )

    def worker():
        errorMsg = None
        out = None
        try:
            out = _run_in_detailed_process(_compute_detailed_analysis, data, temps, params)
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

            # Only artist creation + one draw happen here on the main thread
            # (matplotlib/Tk aren't thread-safe); every array the plot needs
            # was already computed in the worker process.
            _detailed_plot(out, params)
            _detailed_write_results(out, params)

            dltsc.detailed_lastResMw = out['resMw']
            dltsc.detailed_lastResStd = out['resStd']
            dltsc.detailed_lastNt = out['Nt']
            dltsc.detailed_lastTraps = out['traps']
            dltsc.detailed_lastTrapsStd = out['trapsStd']
            # Trap Concentration recalculates Nt from these traps when it follows this tab.
            if dltsc.trapconc_sourceUpdated is not None:
                dltsc.trapconc_sourceUpdated('detailed')

            messages = out['messages']
            for message in messages[:10]:
                dltsc.log_to_textbox(f"Detailed analysis: {message}")
            if len(messages) > 10:
                dltsc.log_to_textbox(f"Detailed analysis: ... and {len(messages) - 10} more fit message(s).")
            statusMsg = 'Done.  ' + '   '.join(
                f'{t["peakId"]}: Et = {_fmt_pm(t["Et"], t["Et_se"], ".3f")} eV' for t in out['traps'])
            if dltsc.detailed_statusLabel is not None:
                dltsc.detailed_statusLabel.config(text=statusMsg)
            dltsc.log_to_textbox(f"Detailed analysis: {statusMsg}")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()


#---------------------PEAK REGIONS (CONTROLS)-------------------------#
# The user picks where peaks are found: regions typed in, or dragged across the
# DLTS Spectra panel. A new region takes the primitives of the Quick Analysis
# Peak Deconvolution region overlapping it most (dltsc.deconv_regions) -- the
# method found to describe that part of the spectrum there -- or, with no
# overlapping Quick Analysis region, this tab's default single-peak finder
# (Peak method, Smoothing Spline by default). The Method box changes it.
METHOD_DEFAULT = 'Default (Peak method below)'

def _detailed_trap_color(trapIndex):
    return TRAP_COLORS[trapIndex % len(TRAP_COLORS)]

def _detailed_quick_methods():
    """[(label, quick region)] for every usable Quick Analysis region."""
    return [(f'Quick R{r + 1} ({region["tLo"]:g}–{region["tHi"]:g} K): {_region_method_text(region, "")}', region)
            for r, region in enumerate(dltsc.deconv_regions or []) if _region_problem(region) is None]

def _detailed_best_quick_method(tLo, tHi):
    """(label, quick region) of the Quick Analysis region overlapping
    [tLo, tHi] most, or None if none overlaps it."""
    best, bestOverlap = None, 0.0
    for label, region in _detailed_quick_methods():
        overlap = min(tHi, region['tHi']) - max(tLo, region['tLo'])
        if overlap > bestOverlap:
            best, bestOverlap = (label, region), overlap
    return best

def _detailed_set_region_method(region, method):
    """Give region the primitives of method ((label, quick region)), or the
    default single-peak finder when method is None."""
    if method is None:
        region.update(primitives=[], prominence=float(DEFAULT_PROMINENCE), source=None)
    else:
        label, quick = method
        region.update(primitives=list(quick['primitives']), prominence=quick['prominence'],
                      source=label.split(' (')[0])   # 'Quick R<n>'

def _detailed_region_text(r, region):
    method = _region_method_text(region, dltsc.detailed_peakMethodVar.get()) if region['primitives'] else 'default'
    source = f' [{region["source"]}]' if region.get('source') else ''
    return f'R{r + 1}: {region["tLo"]:g}–{region["tHi"]:g} K | {method}{source}'

def _detailed_selected_region():
    selection = dltsc.detailed_regionListbox.curselection() if dltsc.detailed_regionListbox is not None else ()
    return selection[0] if selection else None

def _detailed_refresh_regions(selectIndex=None):
    dltsc.detailed_regionListbox.delete(0, tk.END)
    for r, region in enumerate(dltsc.detailed_regions):
        dltsc.detailed_regionListbox.insert(tk.END, _detailed_region_text(r, region))
    if selectIndex is not None and dltsc.detailed_regions:
        selectIndex = min(selectIndex, len(dltsc.detailed_regions) - 1)
        dltsc.detailed_regionListbox.selection_set(selectIndex)
        # The region's own copy of its method (Quick Analysis may have changed since).
        region = dltsc.detailed_regions[selectIndex]
        dltsc.detailed_regionMethodVar.set(
            f'{region.get("source") or "Quick"}: {_region_method_text(region, "")}' if region['primitives']
            else METHOD_DEFAULT)

def _detailed_on_region_select():
    r = _detailed_selected_region()
    if r is None:
        return
    region = dltsc.detailed_regions[r]
    dltsc.detailed_tpeakLoVar.set(region['tLo'])
    dltsc.detailed_tpeakHiVar.set(region['tHi'])
    _detailed_refresh_regions(r)

def _detailed_region_bounds():
    """(tLo, tHi) from the T min / T max boxes, or None (reported) if invalid."""
    try:
        tLo, tHi = float(dltsc.detailed_tpeakLoVar.get()), float(dltsc.detailed_tpeakHiVar.get())
    except (tk.TclError, ValueError):
        dltsc.detailed_statusLabel.config(text='Peak regions: T min / T max must be numbers.')
        return None
    if tHi <= tLo:
        dltsc.detailed_statusLabel.config(text='Peak regions: T max must exceed T min.')
        return None
    return tLo, tHi

def _detailed_regions_changed(message):
    dltsc.detailed_statusLabel.config(text=f'{message}  Run Analysis to refit.')
    dltsc.log_to_textbox(f"Detailed analysis: {message}")

def _detailed_add_region():
    bounds = _detailed_region_bounds()
    if bounds is None:
        return
    region = dict(tLo=bounds[0], tHi=bounds[1])
    method = _detailed_best_quick_method(*bounds)
    _detailed_set_region_method(region, method)
    dltsc.detailed_regions.append(region)
    r = len(dltsc.detailed_regions) - 1
    _detailed_refresh_regions(r)
    if method is None:
        _detailed_regions_changed(f'R{r + 1} added ({bounds[0]:g}–{bounds[1]:g} K): no Quick Analysis region covers '
                                  f'it, so it uses the default {dltsc.detailed_peakMethodVar.get()}.')
    else:
        _detailed_regions_changed(f'R{r + 1} added ({bounds[0]:g}–{bounds[1]:g} K) with the method of {method[0]}.')

def _detailed_update_region():
    r = _detailed_selected_region()
    bounds = _detailed_region_bounds()
    if r is None or bounds is None:
        if r is None:
            dltsc.detailed_statusLabel.config(text='Peak regions: select a region to update.')
        return
    dltsc.detailed_regions[r].update(tLo=bounds[0], tHi=bounds[1])
    _detailed_refresh_regions(r)
    _detailed_regions_changed(f'R{r + 1} moved to {bounds[0]:g}–{bounds[1]:g} K.')

def _detailed_remove_region():
    r = _detailed_selected_region()
    if r is None:
        dltsc.detailed_statusLabel.config(text='Peak regions: select a region to remove.')
        return
    del dltsc.detailed_regions[r]
    _detailed_refresh_regions(r if dltsc.detailed_regions else None)
    _detailed_regions_changed(f'R{r + 1} removed (later regions renumbered).')

def _detailed_refresh_method_options():
    """Method box choices, rebuilt each time it opens so they follow Quick
    Analysis' current regions."""
    dltsc.detailed_regionMethodCombo.config(
        values=[METHOD_DEFAULT] + [label for label, _ in _detailed_quick_methods()])

def _detailed_apply_method():
    r = _detailed_selected_region()
    if r is None:
        dltsc.detailed_statusLabel.config(text='Peak regions: select a region, then choose its method.')
        return
    choice = dltsc.detailed_regionMethodVar.get()
    method = next(((label, quick) for label, quick in _detailed_quick_methods() if label == choice), None)
    _detailed_set_region_method(dltsc.detailed_regions[r], method)
    _detailed_refresh_regions(r)
    _detailed_regions_changed(f'R{r + 1} now uses ' + (method[0] if method else
                              f'the default {dltsc.detailed_peakMethodVar.get()}') + '.')

def _detailed_on_span_select(tLo, tHi):
    # The DLTS Spectra panel's x axis is temperature in K, like the regions.
    dltsc.detailed_tpeakLoVar.set(round(tLo, 1))
    dltsc.detailed_tpeakHiVar.set(round(tHi, 1))
    dltsc.detailed_statusLabel.config(text=f'Picked {tLo:.1f}–{tHi:.1f} K: click Add Region (or Update Region).')


#---------------------PLOTTING-------------------------#
# Four panels, each its own Figure, canvas and toolbar (pan / zoom / save):
# Arrhenius and DLTS Spectra on the top row, Transient Map and Rate-Window map
# on the bottom row. The two panels of a row share temperature: zooming or
# panning one sets the other to the same temperatures (1000/T <-> T on top,
# T <-> 1/kT below). Panels are drawn from the last run's result
# (dltsc.detailed_lastOut), so the Display options -- panels shown, 2D / 3D,
# which labels -- apply at once, without re-running the analysis. Labels: one
# set per panel at a time (its Labels choice), and legends sit outside the
# plot area, on the panel's right. Styling is matplotlib's default, as in
# Quick Analysis: black axes, labels and ticks at the default sizes.
PANEL_ARRHENIUS, PANEL_SPECTRA, PANEL_TMAP, PANEL_RWM = 'arr', 'spec', 'tmap', 'rwm'
PANEL_ROWS = ((PANEL_ARRHENIUS, PANEL_SPECTRA), (PANEL_TMAP, PANEL_RWM))

ARR_VIEW_2D = '2D'
ARR_VIEW_3D = '3D (peak height up)'
ARR_VIEW_OPTIONS = [ARR_VIEW_2D, ARR_VIEW_3D]
MAP_VIEW_2D = '2D colour map'
MAP_VIEW_3D = '3D isohypse surface'
MAP_VIEW_OPTIONS = [MAP_VIEW_2D, MAP_VIEW_3D]

LABELS_NONE = 'None'
LABELS_TRAP_IDS = 'Trap ids'
LABELS_LEGEND = 'Legend'
ARR_LABELS_RESULTS = 'Results (Et, σ, Nt)'
SPEC_LABELS_REGIONS = 'Region names'
ARR_LABEL_OPTIONS = [LABELS_TRAP_IDS, LABELS_LEGEND, ARR_LABELS_RESULTS, LABELS_NONE]
SPEC_LABEL_OPTIONS = [LABELS_TRAP_IDS, LABELS_LEGEND, SPEC_LABELS_REGIONS, LABELS_NONE]
MAP_LABEL_OPTIONS = [LABELS_TRAP_IDS, LABELS_LEGEND, LABELS_NONE]

# Trap curves on the jet maps get a white outline so every trap colour shows.
MAP_STROKE = [mpatheffects.withStroke(linewidth=3.5, foreground='white')]

def _reciprocal_1000(v):
    """1000/T <-> T (K): the Arrhenius x axis to temperature and back."""
    v = np.asarray(v, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return 1000.0 / v

def _reciprocal_kT(v):
    """T (K) <-> 1/kT (eV⁻¹): the Rate-Window map's x axis to temperature and back."""
    v = np.asarray(v, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return 1.0 / (KB_EV * v)

# Each panel's row partner and the map from its x axis to the partner's.
PANEL_LINKS = {PANEL_ARRHENIUS: (PANEL_SPECTRA, _reciprocal_1000), PANEL_SPECTRA: (PANEL_ARRHENIUS, _reciprocal_1000),
               PANEL_TMAP: (PANEL_RWM, _reciprocal_kT), PANEL_RWM: (PANEL_TMAP, _reciprocal_kT)}

def _detailed_display():
    """The Display options as they are now."""
    try:
        nSpectra = int(dltsc.detailed_nSpectraVar.get())
    except (tk.TclError, ValueError):
        nSpectra = 5
    return dict(showSpectra=dltsc.detailed_showSpectraVar.get(), showTmap=dltsc.detailed_showTmapVar.get(),
                showRwm=dltsc.detailed_showRwmVar.get(), showTau=dltsc.detailed_showTauVar.get(),
                showStd=dltsc.detailed_stdWinsVar.get(), nSpectra=max(1, nSpectra),
                arrView=dltsc.detailed_arrViewVar.get(), tmapView=dltsc.detailed_tmapViewVar.get(),
                rwmView=dltsc.detailed_rwmViewVar.get(), arrLabels=dltsc.detailed_arrLabelsVar.get(),
                specLabels=dltsc.detailed_specLabelsVar.get(), tmapLabels=dltsc.detailed_tmapLabelsVar.get(),
                rwmLabels=dltsc.detailed_rwmLabelsVar.get())

def _detailed_shown_panels(disp):
    """Rows of the panels to show, Arrhenius always."""
    shown = {PANEL_ARRHENIUS: True, PANEL_SPECTRA: disp['showSpectra'],
             PANEL_TMAP: disp['showTmap'], PANEL_RWM: disp['showRwm']}
    return [row for row in ([k for k in r if shown[k]] for r in PANEL_ROWS) if row]

def _detailed_side_legend(fig, handles, labels, **kw):
    """A legend outside the plot area, on the figure's right (None without entries)."""
    if not handles:
        return None
    return fig.legend(handles, labels, loc='outside right upper', fontsize=8, **kw)

def _detailed_draw_panel_on(fig, key, out, params, disp):
    """Draw panel `key` on a fresh Figure / SubFigure. Returns (ax, legend)."""
    if key == PANEL_ARRHENIUS:
        return _detailed_draw_arrhenius(fig, out, disp)
    if key == PANEL_SPECTRA:
        return _detailed_draw_spectra(fig, out, disp)
    if key == PANEL_TMAP:
        return _detailed_draw_transient_map(fig, out, params, disp)
    return _detailed_draw_rate_window_map(fig, out, params, disp)

def _detailed_plot(out, params):
    """Show the result `out` of _compute_detailed_analysis, run with the
    parameter snapshot `params`: kept as dltsc.detailed_lastOut / lastParams,
    then every shown panel built. Artist creation only -- no heavy math."""
    dltsc.detailed_lastOut, dltsc.detailed_lastParams = out, params
    _detailed_layout_panels()

def _detailed_layout_panels():
    """(Re)build the panel grid for the panels now shown: one row per panel
    row, a panel alone in its row spans it. Each panel gets its own Figure,
    canvas and toolbar."""
    if dltsc.detailed_lastOut is None or dltsc.detailed_figFrame is None:
        return
    frame = dltsc.detailed_figFrame
    for w in frame.winfo_children():
        w.destroy()
    for key in list(dltsc.detailed_figures):
        _detailed_forget_panel(key)
    for i in range(2):
        frame.grid_rowconfigure(i, weight=0, uniform='')
        frame.grid_columnconfigure(i, weight=1, uniform='col')

    rows = _detailed_shown_panels(_detailed_display())
    for r, row in enumerate(rows):
        frame.grid_rowconfigure(r, weight=1, uniform='row')
        for c, key in enumerate(row):
            holder = tk.Frame(frame, bg=CTRL_BG)
            holder.grid(row=r, column=c, columnspan=2 if len(row) == 1 else 1, sticky='nsew', padx=2, pady=2)
            # Figure() directly, never pyplot: pyplot would also open its own
            # window for it (see dataAnalysisTab.py, liveDataTab.py).
            fig = Figure(figsize=(6.0, 4.5), layout='constrained')
            canvas = FigureCanvasTkAgg(fig, master=holder)
            toolbar = NavigationToolbar2Tk(canvas, holder, pack_toolbar=False)
            toolbar.update()
            toolbar.pack(side='top', fill='x')
            # Tiny requested size: the canvas otherwise asks for the full
            # figsize in pixels, forcing an extra geometry pass and redraw.
            canvas.get_tk_widget().config(width=1, height=1)
            canvas.get_tk_widget().pack(fill='both', expand=True)
            dltsc.detailed_figures[key] = fig
            dltsc.detailed_canvases[key] = canvas
            _detailed_draw_panel(key, draw=False)
    # No explicit draw: packing resizes each (1x1-requested) canvas to its
    # cell, and that resize's draw_idle is the one real render.

def _detailed_forget_panel(key):
    """Drop a panel's figure, canvas and the references to its artists."""
    for store in (dltsc.detailed_figures, dltsc.detailed_canvases, dltsc.detailed_panelAxes,
                  dltsc.detailed_panelLegends, dltsc.detailed_linkCids):
        store.pop(key, None)
    if key == PANEL_SPECTRA:
        dltsc.detailed_spanSelector = None

def _detailed_draw_panel(key, draw=True):
    """(Re)draw one shown panel from the last result, with the Display
    options as they are now."""
    fig, canvas = dltsc.detailed_figures.get(key), dltsc.detailed_canvases.get(key)
    if fig is None or dltsc.detailed_lastOut is None:
        return
    fig.clear()
    ax, legend = _detailed_draw_panel_on(fig, key, dltsc.detailed_lastOut, dltsc.detailed_lastParams,
                                         _detailed_display())
    dltsc.detailed_panelAxes[key] = ax
    dltsc.detailed_panelLegends[key] = legend
    canvas.toolbar.update()   # a fresh view history: Home is this drawing's view

    if key == PANEL_SPECTRA:
        # Dragging across the spectra picks a peak region (see the Peak
        # Regions controls); legends are outside the axes, so never in the way.
        # The selector's hidden rectangle sits at x = 0, which would stretch
        # the autoscaled temperature axis down to 0 K: keep the data's range.
        xlim = ax.get_xlim()
        dltsc.detailed_spanSelector = SpanSelector(ax, _detailed_on_span_select, 'horizontal', useblit=True,
                                                   minspan=1.0, props=dict(facecolor=C0, alpha=0.2))
        ax.set_xlim(xlim)
    _detailed_link_panel(key)
    if draw:
        canvas.draw_idle()

def _detailed_redraw(*keys):
    """Redraw the given panels (those shown)."""
    for key in keys:
        if key in dltsc.detailed_figures:
            _detailed_draw_panel(key)


#---------------------LINKED TEMPERATURE AXES-------------------------#
def _detailed_link_panel(key):
    """Follow the panel's x-limit changes (zoom, pan, Home, Back) on its row
    partner -- connected after its first draw, once autoscaling has set its
    own limits, so only the user's changes are passed on."""
    canvas = dltsc.detailed_canvases[key]
    oldCid = dltsc.detailed_linkCids.pop(key, None)
    if oldCid is not None:
        canvas.mpl_disconnect(oldCid)

    def connect(evt):
        canvas.mpl_disconnect(dltsc.detailed_linkCids.pop(key, None))
        ax = dltsc.detailed_panelAxes.get(key)
        if ax is not None and ax.name != '3d':
            ax.callbacks.connect('xlim_changed', lambda a: _detailed_follow_xlim(key, a))

    dltsc.detailed_linkCids[key] = canvas.mpl_connect('draw_event', connect)

def _detailed_follow_xlim(key, ax):
    """Set the row partner of panel `key` to the temperatures `ax` now shows."""
    if dltsc.detailed_linkBusy:
        return
    partner, toPartner = PANEL_LINKS[key]
    other = dltsc.detailed_panelAxes.get(partner)
    if other is None or other.name == '3d' or partner not in dltsc.detailed_canvases:
        return
    lims = np.array(ax.get_xlim(), dtype=float)
    if not np.all(lims > 0):
        return
    lo, hi = np.sort(toPartner(lims))
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
        return
    dltsc.detailed_linkBusy = True
    try:
        other.set_xlim(lo, hi)
    finally:
        dltsc.detailed_linkBusy = False
    dltsc.detailed_canvases[partner].draw_idle()


#---------------------ARRHENIUS PANEL-------------------------#
def _detailed_arrhenius_errorbars(ax, res, color):
    """Error bars on the Arrhenius points from each window's peak-fit Tp
    error: x = 1000/T so dx = 1000·dT/T²; y = ln(en/T²) so dy = 2·dT/T.
    Only windows whose peak fit produced an error get a bar."""
    ok = np.isfinite(res['Tp_err_arr']) & res['fit_mask']
    if not ok.any():
        return
    Tp, dT = res['Tp_arr'][ok], res['Tp_err_arr'][ok]
    ax.errorbar(res['x'][ok], res['y'][ok], xerr=1000.0 * dT / Tp**2, yerr=2.0 * dT / Tp,
                fmt='none', ecolor=color, elinewidth=0.8, capsize=2, alpha=0.6, zorder=3.5)

def _detailed_fit_label(res, kind):
    return f'{res["peakId"]} {kind} ({res["N"]}): {_fmt_pm(res["Et"], res["Et_se"], ".3f")} eV'

def _detailed_results_legend(fig, out):
    """The fit results (Et, σ, Nt per trap, then the total Nt) as a text-only
    legend beside the plot."""
    entries = []
    for res in out['traps']:
        entries.append(f'{res["peakId"]}  ({res["N"]} pts, {"weighted" if res["weighted"] else "unweighted"})\n'
                       f'  Et = {_fmt_pm(res["Et"], res["Et_se"], ".3f")} eV\n'
                       f'  σₙ = {_fmt_pm(res["sigma"], res["sigma_se"], ".2e")} cm²\n'
                       f'  Nt = {_fmt_pm(res["Nt"], res["Nt_err"], ".2e")} cm⁻³\n'
                       f'  R² = {res["R2"]:.4f}' + (f'  χ²ᵣ = {res["redchi"]:.2f}' if res['weighted'] else ''))
    entries.append(f'Nt (all traps, transient)\n  = {out["Nt"]:.2e} cm⁻³')
    return _detailed_side_legend(fig, [mpatches.Patch(visible=False)] * len(entries), entries,
                                 handlelength=0, handletextpad=0, prop=dict(family='monospace', size=8))

def _detailed_draw_arrhenius(fig, out, disp):
    """Arrhenius panel: per trap, the multi-window line with its 2σ band and
    points (coloured by eₙ, edged in the trap's colour), and the standard-window
    line and diamonds when shown. No frame: left and bottom axes only, with
    the temperature (K) along the top."""
    traps = out['traps']
    stdById = {t['peakId']: t for t in out['trapsStd']} if disp['showStd'] else dict()
    if disp['arrView'] == ARR_VIEW_3D:
        return _detailed_draw_arrhenius_3d(fig, out, traps, stdById, disp)

    ax = fig.add_subplot()
    x_all = np.concatenate([t['x'] for t in traps] + [t['x'] for t in stdById.values()])
    x_line = np.linspace(x_all.min() * 0.97, x_all.max() * 1.03, 400)
    en_all = np.log10(np.concatenate([t['en_arr'] for t in traps]))
    norm_en = Normalize(en_all.min(), en_all.max())
    sc = None
    excludedLabel = 'Excluded (no Tp error)'
    stdLabel = 'Standard windows'
    for i, res in enumerate(traps):
        col = _detailed_trap_color(i)
        # 2-sigma confidence band of the (weighted) fit line, straight from its
        # slope/intercept covariance: var(y) = var_m·x² + var_b + 2·x·cov_mb.
        y_lm = res['slope'] * x_line + res['intercept']
        cv = res['covar']
        if cv is not None:
            half = 2.0 * np.sqrt(np.maximum(cv[0, 0] * x_line**2 + cv[1, 1] + 2.0 * cv[0, 1] * x_line, 0.0))
            ax.fill_between(x_line, y_lm - half, y_lm + half, color=col, alpha=0.13, zorder=1)
        ax.plot(x_line, y_lm, color=col, lw=2.0, zorder=3, label=_detailed_fit_label(res, 'multi'))
        _detailed_arrhenius_errorbars(ax, res, col)
        fm = res['fit_mask']
        sc = ax.scatter(res['x'][fm], res['y'][fm], c=np.log10(res['en_arr'][fm]), cmap='plasma', norm=norm_en,
                        s=55, zorder=4, edgecolors=col, lw=1.0)
        if (~fm).any():
            ax.scatter(res['x'][~fm], res['y'][~fm], marker='x', s=45, color='k', lw=1.2, zorder=4,
                       label=excludedLabel)
            excludedLabel = '_nolegend_'

        res_std = stdById.get(res['peakId'])
        if res_std is not None:
            ax.plot(x_line, res_std['slope'] * x_line + res_std['intercept'], color=col, lw=1.5, ls='--',
                    zorder=3, label=_detailed_fit_label(res_std, 'standard'))
            _detailed_arrhenius_errorbars(ax, res_std, col)
            ax.scatter(res_std['x'], res_std['y'], color=col, s=100, zorder=5, marker='D', edgecolors='k',
                       lw=0.7, label=stdLabel)
            stdLabel = '_nolegend_'

        if disp['arrLabels'] == LABELS_TRAP_IDS:
            # At the line's high-temperature (left) end.
            x0 = res['x'].min()
            ax.annotate(res['peakId'], (x0, res['slope'] * x0 + res['intercept']), textcoords='offset points',
                        xytext=(-6, 6), ha='right', fontweight='bold', color=col, zorder=6)

    cb = fig.colorbar(sc, ax=ax, pad=0.01, fraction=0.04)
    cb.set_label('log₁₀ eₙ (s⁻¹)')

    # Temperature along the top, from 1000/T: tick labels only, so no frame.
    top = ax.secondary_xaxis('top', functions=(_reciprocal_1000, _reciprocal_1000))
    top.xaxis.set_major_locator(mticker.MaxNLocator(5))
    top.tick_params(length=0)
    for spine in top.spines.values():
        spine.set_visible(False)
    top.set_xlabel('T (K)')
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_xlabel('1000 / T (K⁻¹)')
    ax.set_ylabel('ln(eₙ / T²) (s⁻¹ K⁻²)')
    ax.set_title('Arrhenius Plot')
    ax.grid(True, linestyle=':')

    legend = None
    if disp['arrLabels'] == LABELS_LEGEND:
        legend = _detailed_side_legend(fig, *ax.get_legend_handles_labels())
    elif disp['arrLabels'] == ARR_LABELS_RESULTS:
        legend = _detailed_results_legend(fig, out)
    return ax, legend

def _detailed_draw_arrhenius_3d(fig, out, traps, stdById, disp):
    """3D Arrhenius: the 2D plot on the floor (each trap's fit line), every
    window's point raised to its peak height |ΔC/C₀| on a stem, so a trap's
    points should sit at about one height (one trap density)."""
    ax = fig.add_subplot(projection='3d')
    stdLabel = 'Standard windows'
    for i, res in enumerate(traps):
        col = _detailed_trap_color(i)
        sets = [(res, 'o', 30, 'multi', '-')]
        if res['peakId'] in stdById:
            sets.append((stdById[res['peakId']], 'D', 45, 'standard', '--'))
        for r, marker, size, kind, ls in sets:
            x, y, z = r['x'], r['y'], r['Sp_arr'] * 1e3
            x_line = np.linspace(x.min() * 0.99, x.max() * 1.01, 100)
            ax.plot(x_line, r['slope'] * x_line + r['intercept'], zs=0, zdir='z', color=col, lw=2.0 if
                    kind == 'multi' else 1.5, ls=ls, label=_detailed_fit_label(r, kind))
            for xi, yi, zi in zip(x, y, z):
                ax.plot([xi, xi], [yi, yi], [0, zi], color=col, lw=0.7, alpha=0.6)
            fm = r['fit_mask']
            ax.scatter(x[fm], y[fm], z[fm], marker=marker, s=size, color=col, edgecolors='k', lw=0.5,
                       depthshade=False, label=stdLabel if kind == 'standard' else '_nolegend_')
            if kind == 'standard':
                stdLabel = '_nolegend_'
            if (~fm).any():
                ax.scatter(x[~fm], y[~fm], z[~fm], marker='x', s=size, color='k', depthshade=False)
        if disp['arrLabels'] == LABELS_TRAP_IDS:
            k = int(np.argmax(res['Sp_arr']))
            ax.text(res['x'][k], res['y'][k], res['Sp_arr'][k] * 1e3, f'  {res["peakId"]}', color=col,
                    fontweight='bold')
    ax.set_zlim(bottom=0)
    ax.set_xlabel('1000 / T (K⁻¹)')
    ax.set_ylabel('ln(eₙ / T²)')
    ax.set_zlabel('Peak |ΔC/C₀| (×10⁻³)')
    ax.set_title('Arrhenius Plot')

    legend = None
    if disp['arrLabels'] == LABELS_LEGEND:
        legend = _detailed_side_legend(fig, *ax.get_legend_handles_labels())
    elif disp['arrLabels'] == ARR_LABELS_RESULTS:
        legend = _detailed_results_legend(fig, out)
    return ax, legend


#---------------------DLTS SPECTRA PANEL-------------------------#
def _detailed_shown_spectra(spectra, nSpectra):
    """nSpectra of the computed spectra, spread evenly over the windows."""
    if not spectra:
        return []
    picks = np.unique(np.round(np.linspace(0, len(spectra) - 1, min(nSpectra, len(spectra)))).astype(int))
    return [spectra[j] for j in picks]

def _detailed_draw_spectra(fig, out, disp):
    """DLTS Spectra panel: the peak regions shaded, the shown windows' S(T),
    each trap's multi-window Tp as dotted lines and the shown spectra's peaks
    as ▼ in the trap's colour."""
    ax = fig.add_subplot()
    T_K, traps = out['T_K'], out['traps']
    spectra = out['spectra'] or []
    shown = _detailed_shown_spectra(spectra, disp['nSpectra'])
    labels = disp['specLabels']
    ax.axhline(0, color='k', lw=0.6)

    for r, region in enumerate(out['regions']):
        ax.axvspan(region['tLo'], region['tHi'], color='0.85', alpha=0.5, lw=0, zorder=0)
        if labels == SPEC_LABELS_REGIONS:
            ax.text(region['tLo'], 0.99, f' R{r + 1}', transform=ax.get_xaxis_transform(), va='top', ha='left')

    cmap_w = matplotlib.colormaps['cool']
    norm_w = Normalize(0, max(len(out['mw']) - 1, 1))
    for k, t1, t2, en, S in shown:
        ax.plot(T_K, S, color=cmap_w(norm_w(k)), lw=1.4, label=f'{t1:.3g}/{t2:.3g} ms (eₙ = {en:.3g} s⁻¹)')

    trapIndex = {t['peakId']: i for i, t in enumerate(traps)}
    for i, res in enumerate(traps):
        for Tp_v in res['Tp_arr']:
            ax.axvline(Tp_v, color=_detailed_trap_color(i), lw=0.5, ls=':', alpha=0.6)
    tallest = dict()
    for k, t1, t2, en, S in shown:
        for pid, pk in out['windowPeaks'][k]:
            i = trapIndex.get(pid)
            col = _detailed_trap_color(i) if i is not None else '0.5'
            xy = (pk['T_peak'], pk['S_peak'] * 1e3)
            ax.plot(*xy, marker='v', ls='none', color=col, mec='k', mew=0.6, ms=7, zorder=5)
            if pid not in tallest or abs(xy[1]) > abs(tallest[pid][1]):
                tallest[pid] = xy
    if labels == LABELS_TRAP_IDS:
        for pid, xy in tallest.items():
            ax.annotate(pid, xy, textcoords='offset points', xytext=(0, 9), ha='center', fontweight='bold',
                        zorder=6)
    if tallest:
        ax.plot([], [], marker='v', ls='none', color='0.5', mec='k', ms=7, label='Peaks (trap colour)')

    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('ΔC/C₀ (×10⁻³)')
    ax.set_title('DLTS Spectra')
    ax.grid(True, linestyle=':')
    legend = None
    if labels == LABELS_LEGEND:
        legend = _detailed_side_legend(fig, *ax.get_legend_handles_labels())
    return ax, legend


#---------------------TRANSIENT MAP PANEL-------------------------#
def _detailed_tau_curves(traps, T_K, t_s, gamma):
    """Per trap: (index, res, T, τ(T) on the map's time range, Tp, 1/eₙ of
    its rate-window peaks on the map's time range); traps whose τ(T) misses
    the map are left out."""
    T_line = np.linspace(T_K.min() - 20, T_K.max() + 20, 600)
    curves = []
    for i, res in enumerate(traps):
        tau_T = 1.0 / (gamma * res['sigma'] * T_line ** 2 * np.exp(-res['Et'] / (KB_EV * T_line)))
        vis = (tau_T >= t_s.min() * 0.5) & (tau_T <= t_s.max() * 2.0)
        if not vis.any():
            continue
        tau_all = 1.0 / res['en_arr']
        vis_c = (tau_all >= t_s.min() * 0.5) & (tau_all <= t_s.max() * 2.0)
        curves.append((i, res, T_line[vis], np.clip(tau_T[vis], t_s.min(), t_s.max()),
                       res['Tp_arr'][vis_c], np.clip(tau_all[vis_c], t_s.min(), t_s.max())))
    return curves

def _detailed_draw_transient_map(fig, out, params, disp):
    """ΔC/C₀(t, T) from _prepare_transient_map: a filled contour map on a log
    time axis (2D), or a surface with its isohypses (3D, same colours), with
    each trap's τ(T) and rate-window peaks overlaid in its colour."""
    tmap, T_K, traps = out['tmap'], out['T_K'], out['traps']
    is3d = disp['tmapView'] == MAP_VIEW_3D
    ax = fig.add_subplot(projection='3d' if is3d else None)
    ax.set_title('ΔC/C₀ Transient Map')
    if tmap is None:
        (ax.text2D if is3d else ax.text)(0.5, 0.5, 'Not enough time points', transform=ax.transAxes, ha='center')
        return ax, None

    t_s, Z_disp, levels = tmap['t_s'], tmap['Z_disp'], tmap['levels']
    norm = Normalize(levels[0], levels[-1])
    curves = _detailed_tau_curves(traps, T_K, t_s, params['gamma']) if disp['showTau'] else []
    labels = disp['tmapLabels']

    if is3d:
        Tm, logT = np.meshgrid(T_K, np.log10(t_s))
        Zc = np.clip(Z_disp, levels[0], levels[-1])
        mappable = _detailed_isohypse_surface(ax, Tm, logT, Zc, norm, levels)
        for i, res, T_line, tau, Tp, tauP in curves:
            col = _detailed_trap_color(i)
            ax.plot(T_line, np.log10(tau), zs=levels[0], zdir='z', color=col, lw=2.2,
                    label=f'{res["peakId"]} τ(T), Et = {res["Et"]:.3f} eV')
            ax.scatter(Tp, np.log10(tauP), levels[0], marker='o', s=40, facecolors='none', edgecolors=col, lw=1.5,
                       depthshade=False)
            if labels == LABELS_TRAP_IDS and len(Tp):
                ax.text(Tp[len(Tp) // 2], np.log10(tauP[len(Tp) // 2]), levels[0], f'  {res["peakId"]}', color=col,
                        fontweight='bold')
        ax.set_ylabel('log₁₀ t (s)')
        ax.set_zlabel('ΔC/C₀ (×10⁻⁵)', labelpad=12)
    else:
        Tm, tm = np.meshgrid(T_K, t_s)
        mappable = ax.contourf(Tm, tm, Z_disp, levels=levels, cmap='jet', extend='both')
        ax.contour(Tm, tm, Z_disp, levels=levels[::6], colors='k', linewidths=0.25, alpha=0.35)
        ax.set_yscale('log')
        for i, res, T_line, tau, Tp, tauP in curves:
            col = _detailed_trap_color(i)
            ax.plot(T_line, tau, color=col, lw=2.2, zorder=6, path_effects=MAP_STROKE,
                    label=f'{res["peakId"]} τ(T), Et = {res["Et"]:.3f} eV')
            if len(Tp):
                ax.scatter(Tp, tauP, marker='o', s=70, facecolors='none', edgecolors=col, lw=1.8, zorder=8,
                           path_effects=MAP_STROKE, label=f'{res["peakId"]} peaks (Tₚ, 1/eₙ)')
                if labels == LABELS_TRAP_IDS:
                    # Above the top of the trap's column of peaks, or below its
                    # bottom for every other trap, so neighbouring traps' ids
                    # don't collide.
                    above = i % 2 == 0
                    j = int(np.argmax(tauP) if above else np.argmin(tauP))
                    ax.annotate(res['peakId'], (Tp[j], tauP[j]), textcoords='offset points',
                                xytext=(0, 10 if above else -10), ha='center', va='bottom' if above else 'top',
                                color=col, fontweight='bold', zorder=9, path_effects=MAP_STROKE)
        ax.set_ylabel('Time (s)')
    ax.set_xlabel('Temperature (K)')

    cbar = fig.colorbar(mappable, ax=ax, pad=0.02 if not is3d else 0.08, fraction=0.04, shrink=0.8 if is3d else 1.0)
    cbar.locator = mticker.MaxNLocator(7)   # not one tick per contour level
    cbar.update_ticks()
    cbar.set_label('ΔC/C₀ (×10⁻⁵)')
    legend = None
    if labels == LABELS_LEGEND:
        legend = _detailed_side_legend(fig, *ax.get_legend_handles_labels())
    return ax, legend

def _detailed_isohypse_surface(ax, X, Y, Z, norm, levels, cmap='jet'):
    """A 3D surface in the 2D map's colours, with isohypses (contour lines)
    on it and projected onto the floor. Returns a mappable for the colorbar."""
    step = max(1, int(np.ceil(max(Z.shape) / 90)))   # at most ~90 x 90 facets
    ax.plot_surface(X, Y, Z, cmap=cmap, norm=norm, rstride=step, cstride=step, linewidth=0, antialiased=False,
                    alpha=0.95)
    lines = levels[::6]
    ax.contour(X, Y, Z, levels=lines, colors='k', linewidths=0.4, alpha=0.6)
    ax.contour(X, Y, Z, levels=lines, cmap=cmap, norm=norm, zdir='z', offset=levels[0], linewidths=0.8)
    ax.set_zlim(levels[0], levels[-1])
    return matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)


#---------------------RATE-WINDOW ANALYSIS MAP PANEL-------------------------#
def _detailed_draw_rate_window_map(fig, out, params, disp):
    """Nt/Nd = 2|ΔC/C₀| in (1/kT, T²/eₙ) space, from _prepare_rate_window_map,
    in log colours on a black background (2D) or as a log surface with its
    isohypses (3D, same colours), with each trap's Arrhenius line (and circles
    along it) in its colour."""
    rwm, traps, gamma = out['rwm'], out['traps'], params['gamma']
    is3d = disp['rwmView'] == MAP_VIEW_3D
    labels = disp['rwmLabels']
    ax = fig.add_subplot(projection='3d' if is3d else None)
    ax.set_title('Rate-Window Analysis Map')
    ax.set_xlabel('1/kT (eV⁻¹)')
    if rwm is None:
        message = 'Insufficient data for Rate-Window map'
        (ax.text2D if is3d else ax.text)(0.5, 0.5, message, transform=ax.transAxes, ha='center')
        return ax, None

    Xi, Yi, Zi = rwm['Xi'], rwm['Yi'], rwm['Zi']
    z_lo, z_hi = rwm['z_lo'], rwm['z_hi']
    x_min, x_max = rwm['x_min'], rwm['x_max']
    logNorm = LogNorm(vmin=z_lo, vmax=z_hi)

    if is3d:
        logLevels = np.linspace(np.log10(z_lo), np.log10(z_hi), 64)
        logZ = np.log10(np.clip(Zi.filled(np.nan), z_lo, z_hi))
        _detailed_isohypse_surface(ax, Xi, np.log10(Yi), logZ, Normalize(logLevels[0], logLevels[-1]), logLevels)
        mappable = matplotlib.cm.ScalarMappable(norm=logNorm, cmap='jet')
        ax.set_ylabel('log₁₀ T²/eₙ (K² s)')
        ax.set_zlabel('log₁₀ Nₜ/N_D')
    else:
        ax.set_facecolor('black')
        mappable = ax.pcolormesh(Xi, Yi, Zi, cmap='jet', norm=logNorm, shading='auto', zorder=2)
        ax.set_yscale('log')
        ax.yaxis.set_minor_locator(mticker.NullLocator())
        ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext())
        ax.set_ylabel('T²/eₙ (K² s)')

    for i, res in enumerate(traps or []):
        col = _detailed_trap_color(i)
        x_line = np.linspace(x_min * 0.97, x_max * 1.03, 400)
        y_line = (1.0 / (gamma * res['sigma'])) * np.exp(res['Et'] * x_line)
        vis = (y_line >= Yi.min() * 0.2) & (y_line <= Yi.max() * 5.0)
        x_circ = np.linspace(x_min * 0.98, x_max * 1.02, 22)
        y_circ = (1.0 / (gamma * res['sigma'])) * np.exp(res['Et'] * x_circ)
        vis_c = (y_circ >= Yi.min() * 0.5) & (y_circ <= Yi.max() * 2.0)
        lineLabel = f'{res["peakId"]} Arrhenius, Et = {res["Et"]:.3f} eV'
        if is3d:
            # On the floor, under the surface.
            if vis.any():
                ax.plot(x_line[vis], np.log10(y_line[vis]), zs=np.log10(z_lo), zdir='z', color=col, lw=1.8, ls='--',
                        label=lineLabel)
            if labels == LABELS_TRAP_IDS and vis_c.any():
                j = np.flatnonzero(vis_c)[vis_c.sum() // 2]
                ax.text(x_circ[j], np.log10(y_circ[j]), np.log10(z_lo), f'  {res["peakId"]}', color=col,
                        fontweight='bold')
            continue
        if vis.any():
            ax.plot(x_line[vis], y_line[vis], color=col, lw=1.8, ls='--', zorder=5, path_effects=MAP_STROKE,
                    label=lineLabel)
        if vis_c.any():
            ax.scatter(x_circ[vis_c], y_circ[vis_c], s=55, facecolors='none', edgecolors=col, lw=1.6, zorder=8,
                       path_effects=MAP_STROKE, label=f'{res["peakId"]} (fitted)')
            if labels == LABELS_TRAP_IDS:
                j = np.flatnonzero(vis_c)[vis_c.sum() // 2]
                ax.annotate(f'{res["peakId"]}', (x_circ[j], y_circ[j]), textcoords='offset points', xytext=(8, -12),
                            color=col, fontweight='bold', zorder=9, path_effects=MAP_STROKE)

    cbar = fig.colorbar(mappable, ax=ax, pad=0.02 if not is3d else 0.08, fraction=0.04, shrink=0.8 if is3d else 1.0)
    cbar.set_label('Nₜ / N_D')
    cbar.ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext())
    legend = None
    if labels == LABELS_LEGEND:
        legend = _detailed_side_legend(fig, *ax.get_legend_handles_labels())
    return ax, legend


#---------------------DISPLAY OPTIONS-------------------------#
# Every Display option redraws what it changes from the last result, at once.
def _detailed_on_display_change(*keys):
    """keys: the panels to redraw; none = which panels are shown changed."""
    if dltsc.detailed_lastOut is None:
        return
    if keys:
        _detailed_redraw(*keys)
    else:
        _detailed_layout_panels()


#---------------------LABEL / LEGEND EDITOR-------------------------#
def _detailed_open_label_editor():
    """Popup dialog to edit axis labels, titles, and legend text/font sizes.
    A Toplevel (not a modal messagebox) -- it is itself a genuine editing
    tool, not a status/error notification, so it stays as a dialog. Edits
    last until the panel is redrawn (a Display change or a new run).
    """
    if not dltsc.detailed_figures:
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

    panelNames = [(PANEL_ARRHENIUS, 'Arrhenius'), (PANEL_SPECTRA, 'DLTS Spectra'),
                  (PANEL_TMAP, 'Transient Map'), (PANEL_RWM, 'Rate-Window Map')]
    panel_defs = [(f'{name} Panel', dltsc.detailed_panelAxes.get(key)) for key, name in panelNames]
    for pname, ax in panel_defs:
        if ax is None:
            continue
        section(pname)
        axis_row(inner, 'Title', ax.title.get_text(), ax.title.get_fontsize(), ax.set_title)
        axis_row(inner, 'X label', ax.xaxis.label.get_text(), ax.xaxis.label.get_fontsize() or 10, ax.set_xlabel)
        axis_row(inner, 'Y label', ax.yaxis.label.get_text(), ax.yaxis.label.get_fontsize() or 10, ax.set_ylabel)

    legend_defs = [(f'{name} Legend', dltsc.detailed_panelAxes.get(key), dltsc.detailed_panelLegends.get(key))
                   for key, name in panelNames]
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
        for canvas in dltsc.detailed_canvases.values():
            canvas.draw_idle()

    btn_f = tk.Frame(dlg, bg=CTRL_BG)
    btn_f.pack(fill='x', padx=12, pady=8)
    ttk.Button(btn_f, text='Apply', command=apply_all).pack(side='left', padx=4)
    ttk.Button(btn_f, text='Apply & Close', command=lambda: [apply_all(), dlg.destroy()]).pack(side='left', padx=4)
    ttk.Button(btn_f, text='Close', command=dlg.destroy).pack(side='right', padx=4)


#---------------------RESULTS TEXT-------------------------#
def _detailed_write_results(out, params):
    """Results column: run settings, the peak regions, then one block per trap
    (multi-window and standard fits, Nt, window detail), then the total Nt."""
    traps, Nt = out['traps'], out['Nt']
    stdById = {t['peakId']: t for t in out['trapsStd']}
    lines = []
    lines.append('=' * 55)
    lines.append('  DLTS Multiwindow Analysis  —  Results')
    lines.append('=' * 55)
    lines.append('')
    # All +/- values are 1-sigma standard errors: Tpeak from the per-window
    # peak fit (parabola covariance, or spline bootstrap), weighted by each
    # point's sample-noise error; Et/sn from the Arrhenius line fit weighted
    # by those Tpeak errors (effective variance). Omitted where a fit had no
    # residual degrees of freedom.
    def fit_block(res):
        lines_ = [f'    fit  : {"weighted by Tpeak errors" if res["weighted"] else "UNWEIGHTED (no Tpeak errors)"}'
                  + (f', {res["N_excluded"]} window(s) excluded' if res['N_excluded'] else ''),
                  f'    Et   = {_fmt_pm(res["Et"], res["Et_se"], ".4f", " +/- ")} eV',
                  f'    sn   = {_fmt_pm(res["sigma"], res["sigma_se"], ".3e", " +/- ")} cm2',
                  f'    slope     = {_fmt_pm(res["slope"], res["slope_se"], ".4f", " +/- ")} K',
                  f'    intercept = {_fmt_pm(res["intercept"], res["intercept_se"], ".4f", " +/- ")}',
                  f'    R2   = {res["R2"]:.5f}']
        if res['weighted']:
            lines_.append(f'    red. chi2 = {res["redchi"]:.3f}')
        return lines_

    lines.append(f'  Signal     : {params["signalMethod"]}')
    lines.append(f'  Denoise    : {params["denoise"]}')
    lines.append(f'  t_FE       : {out.get("tFe", 0.0):g} ms  (e_n, f(r) from the fill end)')
    lines.append('  Peak regions:')
    for r, region in enumerate(out['regions']):
        source = f'  (from {region["source"]})' if region.get('source') else ''
        lines.append(f'    R{r + 1}: {region["tLo"]:g}-{region["tHi"]:g} K, '
                     f'{_region_method_text(region, params["peakMethod"])}{source}')

    for res_mw in traps:
        res_std = stdById.get(res_mw['peakId'])
        lines.append('')
        lines.append('-' * 55)
        lines.append(f'  Trap {res_mw["peakId"]}  ({res_mw["method"]})')
        lines.append(f'  Multi-window  ({res_mw["N"]} windows)')
        if res_mw.get('n_fallback'):
            lines.append(f'    ({res_mw["n_fallback"]} window(s) fell back to the parabola)')
        lines.extend(fit_block(res_mw))
        lines.append(f'    Nt   = {_fmt_pm(res_mw["Nt"], res_mw["Nt_err"], ".3e", " +/- ")} cm-3'
                     '  (2 Nd S/f(r), uncorrected;')
        lines.append('           N_D(T) and fill geometry: Trap Concentration tab)')
        st = (out.get('stability') or {}).get(res_mw['peakId'], 'n/a')
        if st != 'n/a':
            lines.append('    range stability: ' + ('no usable ranges' if st is None else
                         f'Et {st[0]:.3f}-{st[1]:.3f} eV over {st[2]} ranges'
                         + ('  NOT ROBUST' if st[1] - st[0] > STABILITY_MAX_SPREAD_EV else '  robust')))
        if res_std:
            lines.append(f'  Standard  ({res_std["N"]} windows)')
            lines.extend(fit_block(res_std))
            if res_std['Et_se'] and res_mw['Et_se']:
                impr = res_std['Et_se'] / res_mw['Et_se']
                lines.append(f'    Et uncertainty improvement: {impr:.1f}x')
        lines.append('')
        lines.append('  Window detail  (multi):')
        lines.append(f'  {"t1(ms)":>8}  {"t2(ms)":>8}  {"en(s-1)":>10}  {"Tpeak(K)":>10}  {"+/-(K)":>7}')
        lines.append('  ' + '-' * 53)
        for (t1, t2, en, tp, tp_err, sp), used in zip(res_mw['detail'], res_mw['fit_mask']):
            err_txt = f'{tp_err:7.2f}' if tp_err is not None else f'{"n/a":>7}'
            lines.append(f'  {t1:8.1f}  {t2:8.1f}  {en:10.2f}  {tp:10.2f}  {err_txt}' + ('' if used else '  excl.'))

    lines.append('')
    lines.append('-' * 55)
    lines.append(f'  Nt (all traps, transient amplitude) ~ {Nt:.3e} cm-3')

    for pid, rows in (out.get('methodTable') or {}).items():
        lines.append('')
        lines.append(f'  Peak-finder sensitivity, {pid}  (same windows and regions)')
        lines.append(f'  {"Finder":<16}{"Et (eV)":>15}{"σ (cm²)":>10}{"R²":>8}{"Nt (cm⁻³)":>10}')
        lines.append('  ' + '-' * 59)
        for method, v in rows:
            name = method.replace(' + const (lmfit)', '').replace(' (lmfit)', '').replace(' (bootstrap)', '')
            mark = ' <' if method == params['peakMethod'] else ''
            if v is None:
                lines.append(f'  {name:<16}  (no result)')
            else:
                etTxt = _fmt_pm(v['Et'], v['Et_se'], '.3f', '±')
                lines.append(f'  {name:<16}{etTxt:>15}{v["sigma"]:10.2e}{v["R2"]:8.4f}{v["Nt"]:10.2e}{mark}')

    notes = _detailed_checks(out, params, dltsc.detailed_loadInfo)
    if notes:
        lines.append('')
        lines.append('-' * 55)
        lines.append('  Checks')
        for note in notes:
            # The results column doesn't wrap (tables stay aligned), so wrap the notes here.
            lines.append(textwrap.fill(note, width=55, initial_indent='   - ', subsequent_indent='     '))

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

def _detailed_combined_figure(out, params, disp):
    """Every shown panel, laid out as on screen, in one Figure (for Save
    Figure; each panel's own toolbar saves that panel alone)."""
    rows = _detailed_shown_panels(disp)
    fig = Figure(figsize=(14, 5.5 * len(rows)), layout='constrained')
    grid = fig.add_gridspec(len(rows), 2)
    for r, row in enumerate(rows):
        for c, key in enumerate(row):
            sub = fig.add_subfigure(grid[r, :] if len(row) == 1 else grid[r, c])
            _detailed_draw_panel_on(sub, key, out, params, disp)
    return fig

def _detailed_save_figure():
    if dltsc.detailed_lastOut is None:
        dltsc.log_to_textbox("Detailed analysis: run the analysis first before saving a figure.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension='.png', filetypes=_FIGURE_SAVE_FILETYPES,
        initialfile='DLTS_MultiWindow.png')
    if not path:
        return
    try:
        fig = _detailed_combined_figure(dltsc.detailed_lastOut, dltsc.detailed_lastParams, _detailed_display())
        # Vector formats (svg/eps/pdf) shouldn't be flattened to a fixed DPI
        # raster; raster formats (png/jpg/tiff/bmp) get a white background
        # baked in so they don't save transparent.
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.svg', '.eps', '.pdf'):
            fig.savefig(path, bbox_inches='tight')
        else:
            fig.savefig(path, dpi=180, bbox_inches='tight', facecolor='white')
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

    # The app doesn't run dltsc.init(), so seed the panel stores here.
    for name in ('detailed_figures', 'detailed_canvases', 'detailed_panelAxes', 'detailed_panelLegends',
                 'detailed_linkCids'):
        if getattr(dltsc, name) is None:
            setattr(dltsc, name, dict())
    if dltsc.detailed_linkBusy is None:
        dltsc.detailed_linkBusy = False

    parent = dltsc.detailedAnalysisTab
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Detailed Analysis', font=('Segoe UI', 10, 'bold')).pack(side='left')
    ttk.Label(headerFrame, text='  (DLTS Multiwindow Analysis — ZI MFIA temperature sweep)',
             foreground=TEXT_SEC).pack(side='left')

    # Main paned window: narrow scrollable control column (left), figure
    # (middle, gets all extra width), results text (right) -- results beside
    # rather than under the figure so the figure keeps the full tab height,
    # which is what lets its panels stay close to square.
    paned = ttk.PanedWindow(parent, orient='horizontal')
    paned.grid(row=1, column=0, sticky='nsew', padx=4, pady=(0, 4))

    ctrl_outer = tk.Frame(paned, bg=CTRL_BG, width=295)
    ctrl_outer.pack_propagate(False)
    paned.add(ctrl_outer, weight=0)

    canvas_ctrl = tk.Canvas(ctrl_outer, bg=CTRL_BG, highlightthickness=0, width=278)
    vscroll = ttk.Scrollbar(ctrl_outer, orient='vertical', command=canvas_ctrl.yview)
    canvas_ctrl.configure(yscrollcommand=vscroll.set)
    vscroll.pack(side='right', fill='y')
    canvas_ctrl.pack(side='left', fill='both', expand=True)

    ctrl = tk.Frame(canvas_ctrl, bg=CTRL_BG, padx=10, pady=8)
    ctrl_window = canvas_ctrl.create_window((0, 0), window=ctrl, anchor='nw')
    ctrl.bind('<Configure>', lambda e: canvas_ctrl.configure(scrollregion=canvas_ctrl.bbox('all')))
    # Stretch the controls to the column's full width (entries/spinboxes fill
    # the extra room) instead of staying at their natural, narrower width.
    canvas_ctrl.bind('<Configure>', lambda e: canvas_ctrl.itemconfigure(ctrl_window, width=e.width))
    canvas_ctrl.bind('<Enter>', lambda e: canvas_ctrl.bind_all(
        '<MouseWheel>', lambda ev: canvas_ctrl.yview_scroll(int(-1 * (ev.delta / 120)), 'units')))
    canvas_ctrl.bind('<Leave>', lambda e: canvas_ctrl.unbind_all('<MouseWheel>'))

    middle = tk.Frame(paned, bg=CTRL_BG)
    paned.add(middle, weight=1)

    dltsc.detailed_statusLabel = ttk.Label(middle, text='Load a data folder to begin.')
    dltsc.detailed_statusLabel.pack(side='bottom', fill='x', padx=6, pady=(0, 4))

    dltsc.detailed_figFrame = tk.Frame(middle, bg=CTRL_BG)
    dltsc.detailed_figFrame.pack(fill='both', expand=True)

    # Results column: sized for the window-detail table (only the trailing
    # 'excl.' marker of an excluded row needs the horizontal scroll), no
    # wrapping so table columns stay aligned.
    results_frame = tk.LabelFrame(paned, text=' Results ', bg=CTRL_BG, fg=TEXT_SEC, font=('Consolas', 9))
    paned.add(results_frame, weight=0)
    resultsInner = tk.Frame(results_frame, bg=CTRL_BG)
    resultsInner.pack(fill='both', expand=True, padx=4, pady=4)
    resultsScroll = ttk.Scrollbar(resultsInner, orient='vertical')
    resultsXScroll = ttk.Scrollbar(resultsInner, orient='horizontal')
    dltsc.detailed_resultsText = tk.Text(
        resultsInner, width=57, font=('Consolas', 9),
        bg='#1e1e2e', fg='#cdd6f4', insertbackground='white',
        state='disabled', wrap='none', relief='flat',
        yscrollcommand=resultsScroll.set, xscrollcommand=resultsXScroll.set)
    resultsScroll.config(command=dltsc.detailed_resultsText.yview)
    resultsXScroll.config(command=dltsc.detailed_resultsText.xview)
    resultsXScroll.pack(side='bottom', fill='x')
    resultsScroll.pack(side='right', fill='y')
    dltsc.detailed_resultsText.pack(side='left', fill='both', expand=True)

    # ── local UI-building helpers (construction-time only, mirrors DLTS_APP.py's
    # DLTSApp._section/_row/_spinbox, now closures over `ctrl` instead of methods) ──
    def section(title):
        tk.Frame(ctrl, bg='#1a3a5c', height=2).pack(fill='x', pady=(10, 2))
        tk.Label(ctrl, text=title.upper(), bg=CTRL_BG, fg='#1a3a5c', font=('Segoe UI', 8, 'bold')).pack(anchor='w')

    def row(label, widget_factory, **kw):
        f = tk.Frame(ctrl, bg=CTRL_BG)
        f.pack(fill='x', pady=2)
        tk.Label(f, text=label, bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), width=15, anchor='w').pack(side='left')
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
    dltsc.detailed_loadInfoLabel = ttk.Label(ctrl, text='No data loaded.', foreground=TEXT_MUT, wraplength=250)
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
    dltsc.detailed_cinfLoVar = tk.DoubleVar(value=DEFAULT_CINF_LO)
    dltsc.detailed_cinfHiVar = tk.DoubleVar(value=DEFAULT_CINF_HI)

    row('Start  (frac RB)', lambda p, **k: spinbox(p, dltsc.detailed_cinfLoVar, 0.1, 0.8, 0.05, '%.2f'))
    row('End    (frac RB)', lambda p, **k: spinbox(p, dltsc.detailed_cinfHiVar, 0.3, 0.99, 0.05, '%.2f'))
    dltsc.detailed_c0PrePulseVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Pre-pulse C₀ when lower (step files)', variable=dltsc.detailed_c0PrePulseVar).pack(
        anchor='w')
    tk.Label(ctrl, text='  v3.1: C₀ = min(pre-pulse level, tail mean), the tail cut before a 2nd fill pulse '
                        '(needs AuxInput1). Applies on Load.',
             bg=CTRL_BG, fg=TEXT_MUT, font=('Segoe UI', 7, 'italic'), wraplength=250, justify='left').pack(anchor='w')

    # ── Physical constants ────────────────────────────────────────────────
    section('Physical Constants (4H-SiC)')
    dltsc.detailed_gammaVar = tk.DoubleVar(value=DEFAULT_GAMMA)
    dltsc.detailed_ndVar    = tk.DoubleVar(value=DEFAULT_ND)

    row('γ (cm⁻²s⁻¹K⁻²)',
        lambda p, **k: spinbox(p, dltsc.detailed_gammaVar, 1e20, 1e22, 1e20, '%.2e'))
    row('Nᵈ (cm⁻³)', lambda p, **k: spinbox(p, dltsc.detailed_ndVar, 1e12, 1e17, 1e13, '%.2e'))

    # ── DLTS signal calculation (same options as Quick Analysis) ──────────
    section('DLTS Signal Calculation')
    dltsc.detailed_signalMethodVar = tk.StringVar(value=SIGNAL_METHOD_MEASURED)
    tk.Label(ctrl, text='Method:', bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), anchor='w').pack(fill='x')
    ttk.Combobox(ctrl, textvariable=dltsc.detailed_signalMethodVar, values=SIGNAL_METHOD_OPTIONS,
                 state='readonly', font=('Segoe UI', 9)).pack(fill='x', pady=2)
    dltsc.detailed_denoiseVar = tk.StringVar(value=DENOISE_NONE)
    tk.Label(ctrl, text='Denoise:', bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), anchor='w').pack(fill='x')
    ttk.Combobox(ctrl, textvariable=dltsc.detailed_denoiseVar, values=DENOISE_OPTIONS,
                 state='readonly', font=('Segoe UI', 9)).pack(fill='x', pady=2)

    # ── Peak regions (see the PEAK REGIONS (CONTROLS) section) ───────────
    section('Peak Regions')
    if not dltsc.detailed_regions:
        # Default: the old Peak Search Range with the default single-peak finder.
        dltsc.detailed_regions = [dict(tLo=DEFAULT_TPEAK_LO, tHi=DEFAULT_TPEAK_HI, primitives=[],
                                       prominence=float(DEFAULT_PROMINENCE), source=None)]
    tk.Label(ctrl, text='Drag across the DLTS Spectra panel (after a run) or type T min / max, then Add '
                        'Region. A new region uses the primitives of the Quick Analysis region overlapping '
                        'it most, else the default peak method below.',
             bg=CTRL_BG, fg=TEXT_SEC, font=('Segoe UI', 8), wraplength=250, justify='left').pack(anchor='w')
    dltsc.detailed_regionListbox = tk.Listbox(ctrl, height=4, exportselection=False, font=('Segoe UI', 8))
    dltsc.detailed_regionListbox.pack(fill='x', pady=2)
    dltsc.detailed_regionListbox.bind('<<ListboxSelect>>', lambda e: _detailed_on_region_select())
    dltsc.detailed_tpeakLoVar = tk.DoubleVar(value=DEFAULT_TPEAK_LO)
    dltsc.detailed_tpeakHiVar = tk.DoubleVar(value=DEFAULT_TPEAK_HI)

    dltsc.detailed_trapPresetVar = tk.StringVar(value=TRAP_PRESET_CUSTOM)

    def on_preset(_e=None):
        if dltsc.detailed_trapPresetVar.get() in TRAP_PRESETS:
            lo, hi = TRAP_PRESETS[dltsc.detailed_trapPresetVar.get()]
            dltsc.detailed_tpeakLoVar.set(lo)
            dltsc.detailed_tpeakHiVar.set(hi)
            dltsc.detailed_statusLabel.config(text=f'{dltsc.detailed_trapPresetVar.get()}: {lo:g}–{hi:g} K. '
                                                   f'Click Add Region (or Update).')
    presetCombo = row('Trap preset', lambda p, **k: ttk.Combobox(
        p, textvariable=dltsc.detailed_trapPresetVar, values=list(TRAP_PRESETS) + [TRAP_PRESET_CUSTOM],
        state='readonly', font=('Segoe UI', 9)))
    presetCombo.bind('<<ComboboxSelected>>', on_preset)
    row('T min (K)', lambda p, **k: spinbox(p, dltsc.detailed_tpeakLoVar, 50, 1000, 5))
    row('T max (K)', lambda p, **k: spinbox(p, dltsc.detailed_tpeakHiVar, 50, 1000, 5))
    f_regionButtons = tk.Frame(ctrl, bg=CTRL_BG)
    f_regionButtons.pack(fill='x', pady=2)
    for text, command in (('Add Region', _detailed_add_region), ('Update', _detailed_update_region),
                          ('Remove', _detailed_remove_region)):
        ttk.Button(f_regionButtons, text=text, command=command).pack(side='left', fill='x', expand=True, padx=1)
    tk.Label(ctrl, text='Method of the selected region:', bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9),
             anchor='w').pack(fill='x')
    dltsc.detailed_regionMethodVar = tk.StringVar(value=METHOD_DEFAULT)
    dltsc.detailed_regionMethodCombo = ttk.Combobox(
        ctrl, textvariable=dltsc.detailed_regionMethodVar, state='readonly', font=('Segoe UI', 8),
        postcommand=_detailed_refresh_method_options)
    dltsc.detailed_regionMethodCombo.pack(fill='x', pady=2)
    dltsc.detailed_regionMethodCombo.bind('<<ComboboxSelected>>', lambda e: _detailed_apply_method())

    # Every method gives each window's Tpeak a 1-sigma error (parabola
    # covariance / spline bootstrap / profile-fit covariance), which then
    # weights the Arrhenius fit. Checked against synthetic sweeps with a known
    # Et over repeated noise realizations, the spline's Et errors matched the
    # actual scatter (pull RMS ~0.9), while the 5-point parabola's (only 2
    # residual degrees of freedom per window) underestimated it ~2.5x (pull
    # RMS ~2.8). The default is Pseudo-Voigt + constant, Dr. Kayi's v3.1
    # default, so both programs give the same Et for the same data and
    # settings; the peak-finder table in the results compares all of them.
    # It is the method for regions without Quick Analysis primitives: one peak
    # per region and window.
    dltsc.detailed_peakMethodVar = tk.StringVar(value=PEAK_METHOD_DEFAULT)
    tk.Label(ctrl, text='Default peak method (one peak per region):', bg=CTRL_BG, fg=TEXT_PRI,
             font=('Segoe UI', 9), anchor='w').pack(fill='x')
    peakMethodCombo = ttk.Combobox(ctrl, textvariable=dltsc.detailed_peakMethodVar, values=PEAK_METHOD_OPTIONS,
                                   state='readonly', font=('Segoe UI', 9))
    peakMethodCombo.pack(fill='x', pady=2)
    peakMethodCombo.bind('<<ComboboxSelected>>', lambda e: _detailed_refresh_regions(_detailed_selected_region()))
    _detailed_refresh_regions(0)
    dltsc.detailed_methodTableVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Compare all peak methods (results table)',
                    variable=dltsc.detailed_methodTableVar).pack(anchor='w')
    dltsc.detailed_stabilityVar = tk.BooleanVar(value=False)
    ttk.Checkbutton(ctrl, text=f'Range-stability check of primitive regions (±{STABILITY_DELTA_K:g} K, slow)',
                    variable=dltsc.detailed_stabilityVar).pack(anchor='w')

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
    # v3.1's fill-end time: e_n = ln(τ2/τ1)/(τ2-τ1) and f(r) with τ = t - t_FE.
    dltsc.detailed_tFeVar = tk.DoubleVar(value=dP.T_FE_STEP_FILES_MS)
    row('Fill-end t_FE (ms)', lambda p, **k: spinbox(p, dltsc.detailed_tFeVar, 0.0, 20.0, 0.1, '%.3f'))
    tk.Label(ctrl, text=f'  Set on Load: 0 for step files (cut at the fill end), {dP.T_FE_ZI_MS:g} ms for '
                        f'ZI exports (v3.1\'s MFIA estimate).',
             bg=CTRL_BG, fg=TEXT_MUT, font=('Segoe UI', 7, 'italic'), wraplength=250, justify='left').pack(anchor='w')

    # ── Standard 5 windows ────────────────────────────────────────────────
    section('Standard Windows (reference)')
    dltsc.detailed_stdWinsVar = tk.BooleanVar(value=True)
    ttk.Checkbutton(ctrl, text='Show standard-window comparison (0 / 0 = unused)', variable=dltsc.detailed_stdWinsVar).pack(anchor='w', pady=2)

    tk.Label(ctrl, text='t1 / t2  (ms):', bg=CTRL_BG, fg=TEXT_SEC, font=('Segoe UI', 8)).pack(anchor='w')
    dltsc.detailed_stdEntries = []
    # Same defaults as Quick Analysis' window sets, so the Standard result here
    # and Quick Analysis' Arrhenius result match on the same data.
    for t1, t2 in DEFAULT_STD_WINDOWS:
        fr = tk.Frame(ctrl, bg=CTRL_BG)
        fr.pack(fill='x', pady=1)
        v1, v2 = tk.DoubleVar(value=t1), tk.DoubleVar(value=t2)
        # 0 / 0 leaves a row unused (see _compute_detailed_analysis).
        ttk.Spinbox(fr, textvariable=v1, from_=0, to=490, increment=1, width=5, font=('Segoe UI', 9)).pack(side='left')
        tk.Label(fr, text=' / ', bg=CTRL_BG, font=('Segoe UI', 9)).pack(side='left')
        ttk.Spinbox(fr, textvariable=v2, from_=0, to=499, increment=1, width=5, font=('Segoe UI', 9)).pack(side='left')
        dltsc.detailed_stdEntries.append((v1, v2))

    # ── Display options ───────────────────────────────────────────────────
    # Applied at once to the last run's plots (see DISPLAY OPTIONS); each
    # panel's Labels box picks the one set of labels it shows.
    section('Display')

    def combo_row(label, var, options):
        f = tk.Frame(ctrl, bg=CTRL_BG)
        f.pack(fill='x', pady=1)
        tk.Label(f, text=label, bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9), width=9, anchor='w').pack(side='left')
        ttk.Combobox(f, textvariable=var, values=options, state='readonly', font=('Segoe UI', 9)).pack(
            side='left', fill='x', expand=True)

    def panel_heading(text, var=None):
        if var is None:
            tk.Label(ctrl, text=text, bg=CTRL_BG, fg=TEXT_PRI, font=('Segoe UI', 9, 'bold'), anchor='w').pack(
                fill='x', pady=(6, 0))
        else:
            ttk.Checkbutton(ctrl, text=text, variable=var).pack(anchor='w', pady=(6, 0))

    dltsc.detailed_arrViewVar = tk.StringVar(value=ARR_VIEW_2D)
    dltsc.detailed_arrLabelsVar = tk.StringVar(value=LABELS_TRAP_IDS)
    panel_heading('Arrhenius plot')
    combo_row('View', dltsc.detailed_arrViewVar, ARR_VIEW_OPTIONS)
    combo_row('Labels', dltsc.detailed_arrLabelsVar, ARR_LABEL_OPTIONS)

    dltsc.detailed_showSpectraVar = tk.BooleanVar(value=True)
    dltsc.detailed_nSpectraVar = tk.IntVar(value=5)
    dltsc.detailed_specLabelsVar = tk.StringVar(value=LABELS_TRAP_IDS)
    panel_heading('Show DLTS spectra panel', dltsc.detailed_showSpectraVar)
    row('Spectra to plot', lambda p, **k: spinbox(p, dltsc.detailed_nSpectraVar, 2, 60, 1, '%d'))
    combo_row('Labels', dltsc.detailed_specLabelsVar, SPEC_LABEL_OPTIONS)

    dltsc.detailed_showTmapVar = tk.BooleanVar(value=True)
    dltsc.detailed_showTauVar = tk.BooleanVar(value=True)
    dltsc.detailed_tmapViewVar = tk.StringVar(value=MAP_VIEW_2D)
    dltsc.detailed_tmapLabelsVar = tk.StringVar(value=LABELS_TRAP_IDS)
    panel_heading('Show transient map', dltsc.detailed_showTmapVar)
    ttk.Checkbutton(ctrl, text='  Overlay τ(T) curve on map', variable=dltsc.detailed_showTauVar).pack(anchor='w')
    combo_row('View', dltsc.detailed_tmapViewVar, MAP_VIEW_OPTIONS)
    combo_row('Labels', dltsc.detailed_tmapLabelsVar, MAP_LABEL_OPTIONS)

    dltsc.detailed_showRwmVar = tk.BooleanVar(value=True)
    dltsc.detailed_rwmViewVar = tk.StringVar(value=MAP_VIEW_2D)
    dltsc.detailed_rwmLabelsVar = tk.StringVar(value=LABELS_TRAP_IDS)
    panel_heading('Show Rate-Window Analysis map', dltsc.detailed_showRwmVar)
    combo_row('View', dltsc.detailed_rwmViewVar, MAP_VIEW_OPTIONS)
    combo_row('Labels', dltsc.detailed_rwmLabelsVar, MAP_LABEL_OPTIONS)

    for var, keys in ((dltsc.detailed_showSpectraVar, ()), (dltsc.detailed_showTmapVar, ()),
                      (dltsc.detailed_showRwmVar, ()),
                      (dltsc.detailed_stdWinsVar, (PANEL_ARRHENIUS,)), (dltsc.detailed_arrViewVar, (PANEL_ARRHENIUS,)),
                      (dltsc.detailed_arrLabelsVar, (PANEL_ARRHENIUS,)), (dltsc.detailed_nSpectraVar, (PANEL_SPECTRA,)),
                      (dltsc.detailed_specLabelsVar, (PANEL_SPECTRA,)), (dltsc.detailed_showTauVar, (PANEL_TMAP,)),
                      (dltsc.detailed_tmapViewVar, (PANEL_TMAP,)), (dltsc.detailed_tmapLabelsVar, (PANEL_TMAP,)),
                      (dltsc.detailed_rwmViewVar, (PANEL_RWM,)), (dltsc.detailed_rwmLabelsVar, (PANEL_RWM,))):
        var.trace_add('write', lambda *_, keys=keys: _detailed_on_display_change(*keys))

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

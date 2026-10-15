import tkinter as tk
import threading
import os

from tkinter import ttk
from tkinter import filedialog

import numpy as np
import matplotlib
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import dltsConfig as dltsc
import impedanceAnalysis_Tools as iaT
import detailedAnalysisTab as dA   # shares its raw-transient noise estimate and Arrhenius line fit
import liveDataTab as ldT          # shares its folder scan and transient extraction

# Physical constants and material defaults come from Detailed Analysis, so both
# tabs use the same values.
K_BOLTZMANN = dA.KB_EV   # eV / K
# Default emission pre-factor gamma (cm^-2 s^-1 K^-2) for sigma = exp(intercept)/gamma.
# Was fixed at DrKayisScript.py's silicon value (3.256e21); now a user input,
# defaulting to the SiC value Detailed Analysis also uses.
DEFAULT_GAMMA = f'{dA.DEFAULT_GAMMA:g}'
DEFAULT_ND = f'{dA.DEFAULT_ND:g}'   # background doping Nd (cm^-3)

# Default peak-search temperature bounds (K), matching Detailed Analysis'
# own defaults. Blank = no bound on that side.
DEFAULT_TPEAK_LO = f'{dA.DEFAULT_TPEAK_LO:.1f}'
DEFAULT_TPEAK_HI = f'{dA.DEFAULT_TPEAK_HI:.1f}'

# Requested height (px) of the scrollable controls area under BOTH plots.
# Shared so the two side-by-side frames request identical heights and, with
# identical row weights, split the tab height identically -- otherwise each
# frame's controls request their own natural height and the plots end up
# at different sizes.
QUICK_CONTROLS_HEIGHT = 260

# The same five windows as Detailed Analysis' standard windows (5/25 ... 100/490 ms),
# so this tab's result matches that tab's Standard result by default.
DEFAULT_RATE_WINDOWS = [(f'{t1:.1f}', f'{t2:.1f}') for t1, t2 in dA.DEFAULT_STD_WINDOWS]

# Data Source options for Rate Window Analysis. Selection is optional -- 'Auto'
# (the default) resolves to whichever source actually has data, so the frame
# works with no configuration as long as ANY of them has been populated.
# 'Loaded Folder' is this tab's own Offline Data column (a saved folder,
# extracted here); 'Qualitative Analysis' is the Live Tools tab's frame, which
# only follows the running experiment.
DATA_SOURCE_AUTO = 'Auto (first available)'
DATA_SOURCE_LOADED = 'Loaded Folder (Offline Data)'
DATA_SOURCE_QUALITATIVE = 'Live Run (Qualitative Analysis)'
DATA_SOURCE_LIVE = 'Automated/Live Data — Live'
DATA_SOURCE_OFFLINE = 'Automated/Live Data — Offline'
DATA_SOURCE_OPTIONS = [DATA_SOURCE_AUTO, DATA_SOURCE_LOADED, DATA_SOURCE_QUALITATIVE,
                       DATA_SOURCE_LIVE, DATA_SOURCE_OFFLINE]
# Sources holding already-averaged transients only (no impdData instance).
_AVERAGED_ONLY_SOURCES = (DATA_SOURCE_LOADED, DATA_SOURCE_QUALITATIVE)

# DLTS signal calculation method: how C(t1)/C(t2)/C_infinity are read off each
# temperature's transient to build the DLTS-signal-vs-temperature curve.
#
# 'DrKayisScript.py Method' and 'Measured C' used to be two separate options
# here, but they computed the same thing -- ΔC/C∞ from the nearest MEASURED
# (unsmoothed) sample at t1/t2 -- and only differed in which data structure
# backed that lookup: DrKayisScript.py Method read off the ensemble-averaged
# transient from whichever Data Source was selected (works for all three:
# Qualitative Analysis, Live, Offline), while the old Measured C always went
# through impedanceAnalysis_Tools.impdData.calculate_delC_normalized()
# (needs a real impdData instance -- Live/Offline only -- but adds cross-
# repeat error-bar propagation and the denoise option). They're now merged
# into one 'Measured C' option that keeps BOTH capabilities: it uses
# calculate_delC_normalized() when the resolved Data Source has a live
# impdData instance (Live/Offline), and falls back to the plain nearest-
# sample lookup (no error bars -- there's no per-repeat data to propagate
# from) when it doesn't (Qualitative Analysis). See _calculate_rate_windows().
# Smoothed C works the same way: impdData's spline over the raw per-repeat
# samples when the source has a live instance (Live/Offline), else a cubic
# spline through the averaged transient (Detailed Analysis' Smoothed C).
SIGNAL_METHOD_MEASURED = 'Measured C (nearest sample)'
SIGNAL_METHOD_SMOOTHED = 'Smoothed C (spline-interpolated)'
SIGNAL_METHOD_OPTIONS = [SIGNAL_METHOD_MEASURED, SIGNAL_METHOD_SMOOTHED]

# Denoise choice for the Measured C / Smoothed C signal methods, for every
# Data Source. Backed by a live impdData instance (Live/Offline): 'None (raw)'
# uses calculate_delC_normalized()'s raw (yRaw) emission, any other choice its
# denoised (yFiltered) emission via that method. Averaged-only sources (Loaded
# Folder, Qualitative Analysis): each averaged transient is denoised with the
# same filter and settings (dA._denoise_transient, via _transient_records()).
DENOISE_NONE = 'None (raw)'
DENOISE_OPTIONS = [DENOISE_NONE, 'pca', 'wavelet', 'sgolay', 'lowess']


def _resolve_impd_for_source(source):
    """Resolve a Data Source selection to a live impdData instance, for the
    Measured C / Smoothed C signal methods. Returns (impd, resolvedLabel), or
    (None, None) if that source has no impdData instance behind it (always
    true for Loaded Folder and Qualitative Analysis).
    """
    if source == DATA_SOURCE_LIVE:
        return (dltsc.livePlot_liveImpdData, DATA_SOURCE_LIVE) if dltsc.livePlot_liveImpdData is not None else (None, None)
    if source == DATA_SOURCE_OFFLINE:
        return (dltsc.livePlot_offlineImpdData, DATA_SOURCE_OFFLINE) if dltsc.livePlot_offlineImpdData is not None else (None, None)
    if source in _AVERAGED_ONLY_SOURCES:
        return None, None
    # Auto: Live then Offline -- Loaded Folder / Qualitative Analysis never have an instance.
    if dltsc.livePlot_liveImpdData is not None:
        return dltsc.livePlot_liveImpdData, DATA_SOURCE_LIVE
    if dltsc.livePlot_offlineImpdData is not None:
        return dltsc.livePlot_offlineImpdData, DATA_SOURCE_OFFLINE
    return None, None


# Single-peak finding for each rate-window's DLTS-signal-vs-temperature curve.
# No longer offered in the UI -- Peak Deconvolution replaced it -- but kept, with
# _window_peaks()/_quick_arrhenius() below, as the single-peak path the
# Quick-vs-Detailed tests and the hardware benchmark compare against.
# Deviating from DrKayisScript.py's own inline scipy pseudo-Voigt curve_fit:
# this reuses impedanceAnalysis_Tools.impdData's shared peak finders instead,
# with the smoothing spline (non-parametric; its peak error is bootstrap-
# estimated rather than from a fitted-parameter covariance matrix) as the
# default, and a choice of lmfit-based curve-fit shapes -- which report
# parameter standard errors directly -- as user-selectable alternatives.
PEAK_METHOD_SPLINE = 'Smoothing Spline'
PEAK_METHOD_PSEUDOVOIGT = 'Curve Fit (Pseudo-Voigt)'
PEAK_METHOD_GAUSSIAN = 'Curve Fit (Gaussian)'
PEAK_METHOD_LORENTZIAN = 'Curve Fit (Lorentzian)'
PEAK_METHOD_VOIGT = 'Curve Fit (Voigt)'
PEAK_METHOD_OPTIONS = [PEAK_METHOD_SPLINE, PEAK_METHOD_PSEUDOVOIGT, PEAK_METHOD_GAUSSIAN,
                       PEAK_METHOD_LORENTZIAN, PEAK_METHOD_VOIGT]
# Maps each curve-fit option above to the curveType impdData._curveFit_peakFinder() expects.
PEAK_METHOD_CURVETYPE = {
    PEAK_METHOD_PSEUDOVOIGT: 'pseudoVoigt',
    PEAK_METHOD_GAUSSIAN: 'gaussian',
    PEAK_METHOD_LORENTZIAN: 'lorenzian',
    PEAK_METHOD_VOIGT: 'voigt',
}



# Peak Deconvolution primitives and the default spline prominence live in
# detailedAnalysisTab (shared with its Peak Regions); same names here.
PRIMITIVE_SPLINE = dA.PRIMITIVE_SPLINE
PRIMITIVE_KEYS = dA.PRIMITIVE_KEYS
PRIMITIVE_OPTIONS = dA.PRIMITIVE_OPTIONS
PRIMITIVE_SHORT = dA.PRIMITIVE_SHORT
DEFAULT_PROMINENCE = dA.DEFAULT_PROMINENCE

#---------------------RATE WINDOW ANALYSIS (TOP FRAME)-------------------------#
# Ported from DrKayisScript.py's "2. Rate Window Analysis" tab (PyQt6) into tkinter.
#
# DrKayisScript.py's Tab 2 read directly off Tab 1's self.processed_transients.
# This app already has that exact data source (dltsc.manual_processedTransients,
# populated by Qualitative Analysis' "Extract & Average Transients" in the Live
# Tools tab), but ALSO has two more transient sources that never fed it: a Run
# DLTS session in progress (dltsc.livePlot_live*) and a previously loaded run
# (dltsc.livePlot_offline*), both in the Automated/Live Data frame. The Data
# Source selector below lets Rate Window Analysis pull from any of the three.
def _processed_transients_from_automated(mode):
    """Adapt the Automated/Live Data frame's ('live' or 'offline') already
    ensemble-averaged All-Emissions-Aligned snapshot into the same
    {'time_ms', 'avg_cap_pf', 'C_infinity'}-per-temperature shape Rate Window
    Analysis expects from Qualitative Analysis' processed_transients -- 'All
    Emissions Aligned' is the multi-repeat average for that temperature
    (dataEmissions[T]['ymean'] = np.mean(y, axis=1) across every reverse-bias
    cycle recorded), the same averaging Extract & Average Transients performs,
    unlike 'Emission 0' which is a single, unaveraged pulse. Keys come back in
    Celsius (matching manual_processedTransients) even though
    dltsc.livePlot_* temperatures are Kelvin.
    """
    allEmissionsData = (dltsc.livePlot_liveAllEmissionsData if mode == 'live'
                        else dltsc.livePlot_offlineAllEmissionsData) or {}
    result = {}
    for tempK, sig in allEmissionsData.items():
        x = np.asarray(sig.get('x', []))
        yMean = np.asarray(sig.get('ymean', []))
        if x.size == 0 or yMean.size == 0 or x.size != yMean.size:
            continue

        timeMs = x * 1000.0  # 'x' is pulse-relative time in seconds
        avgCurve = yMean.astype(np.float64)
        # Same Farads -> pF auto-detection _process_raw_transients() uses: raw
        # ImpedanceIm from the impedance analyzer is in Farads (~1e-12), while
        # a manually-extracted transient (Qualitative Analysis) is already pF.
        if np.nanmax(np.abs(avgCurve)) < 1e-3:
            avgCurve = avgCurve * 1e12

        # No separate reverse-bias duration is tracked per Automated/Live Data
        # dataset, so C_infinity is referenced at 90% of this transient's own
        # elapsed time -- the same fraction _process_raw_transients() applies
        # to the (tracked) reverse-bias duration, here applied to the curve's
        # own span instead.
        cInfTargetMs = 0.90 * timeMs[-1]
        cInfIdx = int(np.argmin(np.abs(timeMs - cInfTargetMs)))
        cInfinity = avgCurve[cInfIdx]

        # impdData keys are exact kelvin (298.15 for 25 C); round away the float
        # residue so the Celsius keys read 25.0, not 25.000000000000057.
        tempC = round(tempK - 273.15, 6)
        result[tempC] = {'time_ms': timeMs, 'avg_cap_pf': avgCurve, 'C_infinity': cInfinity}

    return result

def _get_processed_transients_for_source(source):
    """Resolve a Data Source selection to (processedTransients, resolvedLabel,
    errorReason). processedTransients is None (with errorReason set) if that
    source currently has nothing to offer.
    """
    if source == DATA_SOURCE_LOADED:
        data = dltsc.quickData_processedTransients or {}
        if not data:
            return None, None, ("Offline Data has no extracted transients yet: select a folder, "
                                "then click Extract & Average Transients.")
        return data, DATA_SOURCE_LOADED, None

    if source == DATA_SOURCE_QUALITATIVE:
        data = dltsc.manual_processedTransients or {}
        if not data:
            return None, None, "Qualitative Analysis (live run) has no extracted transients yet."
        return data, DATA_SOURCE_QUALITATIVE, None

    if source == DATA_SOURCE_LIVE:
        data = _processed_transients_from_automated('live')
        if not data:
            return None, None, "Automated/Live Data has no Live data yet."
        return data, DATA_SOURCE_LIVE, None

    if source == DATA_SOURCE_OFFLINE:
        data = _processed_transients_from_automated('offline')
        if not data:
            return None, None, "Automated/Live Data has no Offline data loaded."
        return data, DATA_SOURCE_OFFLINE, None

    # Auto: a folder loaded in this tab first (the user asked for it here),
    # then the live run's Qualitative Analysis, then whichever of Live/Offline
    # currently has data.
    if dltsc.quickData_processedTransients:
        return dltsc.quickData_processedTransients, DATA_SOURCE_LOADED, None
    if dltsc.manual_processedTransients:
        return dltsc.manual_processedTransients, DATA_SOURCE_QUALITATIVE, None
    liveData = _processed_transients_from_automated('live')
    if liveData:
        return liveData, DATA_SOURCE_LIVE, None
    offlineData = _processed_transients_from_automated('offline')
    if offlineData:
        return offlineData, DATA_SOURCE_OFFLINE, None
    return None, None, (
        "No data available yet. Load and extract a folder in Offline Data, run DLTS, "
        "or load an offline run in Automated/Live Data first.")

#---------------------SHARED WITH DETAILED ANALYSIS-------------------------#
# The signal read-off, C_infinity, peak finding (with its edge-peak guard and
# small-peak skip), Arrhenius fit (with its exclusion rule) and Nt below all go
# through detailedAnalysisTab's own functions, so the two tabs give the same
# Et, sigma and Nt for the same transients, windows, search range and peak method.
def _rb_ms_for_source(label, processedTransients):
    """Reverse-bias duration (ms) C_infinity and Nt are referenced to: the 'Reverse
    Bias (ms)' field of the source's own extraction (Offline Data or Qualitative
    Analysis), else (or if it is not a positive number) the longest transient's span."""
    paramVars = {DATA_SOURCE_LOADED: dltsc.quickData_paramVars,
                 DATA_SOURCE_QUALITATIVE: dltsc.manual_paramVars}.get(label) or {}
    if 'rb_ms' in paramVars:
        try:
            rb = float(paramVars['rb_ms'].get())
            if rb > 0:
                return rb
        except (ValueError, AttributeError):
            pass
    return max(float(np.asarray(rec['time_ms'])[-1]) for rec in processedTransients.values())

def _transient_records(processedTransients, rb_ms, denoise=DENOISE_NONE, smoothed=False):
    """Averaged transients {T_C: {'time_ms', 'avg_cap_pf', ...}} as Detailed
    Analysis' prepared records (Measured C, or Smoothed C -- a cubic spline
    through each transient -- if smoothed; optionally denoised per transient
    with dA._denoise_transient -- its per-point errors still come from the raw
    transient), with C_infinity recomputed by its convention
    (dA._cinf_range_mean). Returns (records, temps)."""
    temps = sorted(processedTransients)
    data = {}
    for tc in temps:
        t_ms = np.asarray(processedTransients[tc]['time_ms'], dtype=np.float64)
        cap = np.asarray(processedTransients[tc]['avg_cap_pf'], dtype=np.float64)
        data[tc] = (t_ms, cap, dA._cinf_range_mean(t_ms, cap, rb_ms))
    signalMethod = dA.SIGNAL_METHOD_SMOOTHED if smoothed else dA.SIGNAL_METHOD_MEASURED
    return dA._prepare_signal_data(data, temps, signalMethod, denoise), temps

def _curve_fit_peak_method(curveType):
    """Peak method for dA._peak_from_signal: impdData's lmfit curve-fit finder
    of the given shape, returning (Tp, Tp_err, xFit, yFit); falls back to the
    raw grid maximum (no error, no curve) if the fit fails."""
    def find(T, S, S_err):
        try:
            result = iaT.impdData._curveFit_peakFinder(T, S, curveType=curveType,
                                                       signalYErr=dA._valid_errors(S_err))
            if isinstance(result, int):
                raise ValueError('peak finder reported no data')
            tPeak, _, xFit, yFit, tPeakErr, _ = result
            return float(tPeak), tPeakErr, xFit, yFit
        except Exception:
            return float(T[int(np.argmax(S))]), None, None, None
    return find

def _peak_method_for(peakMethod):
    """This tab's Peak-Finding Method choice as a dA._peak_from_signal method.
    The smoothing spline is the same finder Detailed Analysis' 'Smoothing
    Spline (bootstrap)' uses."""
    curveType = PEAK_METHOD_CURVETYPE.get(peakMethod)
    return dA.PEAK_METHOD_SPLINE if curveType is None else _curve_fit_peak_method(curveType)

def _window_peaks(records, temps, windows, tpLo, tpHi, peakMethod):
    """Rate-window peaks from averaged-transient records (see _transient_records),
    one dict per (t1, t2) window: t1, t2, e_n, T_k, Signal, Signal_err, plus
    dA._peak_from_signal's result (skipped, Tp, Tp_err, S_peak, xFit, yFit)."""
    T_K = np.array([tc + 273.15 for tc in temps])
    method = _peak_method_for(peakMethod)
    signals = [dA._rate_window_signal(temps, records, t1, t2) for t1, t2 in windows]
    # Small-peak skip relative to the in-range max over all windows, as Detailed Analysis does.
    refMax = dA._in_range_max(T_K, [S for S, _ in signals], tpLo, tpHi)
    out = []
    for (t1, t2), (S, S_err) in zip(windows, signals):
        pk = dA._peak_from_signal(T_K, S, S_err, tpLo, tpHi, method, ref_max=refMax)
        pk.update(t1=t1, t2=t2, e_n=dA._emission_rate(t1, t2), T_k=T_K, Signal=S, Signal_err=S_err)
        out.append(pk)
    return out

def _quick_arrhenius(peaks, gamma, nd, transients=None):
    """Arrhenius fit of the (non-skipped) peaks -- {'T_peak', 'T_peak_err',
    'e_n', 'S_peak'} dicts -- via dA._arrhenius_fit, plus 'Nt' (cm^-3). Nt is
    dA._trap_density on transients = (records, temps, rb_ms) when given (the
    Detailed Analysis definition), else 2 * max|S_peak| * nd. None if fewer
    than 2 peaks can be fitted."""
    res = dA._arrhenius_fit([p['e_n'] for p in peaks], [p['T_peak'] for p in peaks],
                            [p['T_peak_err'] for p in peaks], gamma)
    if res is None:
        return None
    if transients is not None:
        records, temps, rbMs = transients
        res['Nt'] = dA._trap_density(records, temps, rbMs, nd)
    else:
        res['Nt'] = 2.0 * max(abs(p['S_peak']) for p in peaks) * nd
    return res

def _calculate_rate_windows():
    signalMethod = (dltsc.rateWindow_signalMethodVar.get() if dltsc.rateWindow_signalMethodVar is not None
                    else SIGNAL_METHOD_MEASURED)
    source = dltsc.rateWindow_dataSourceVar.get() if dltsc.rateWindow_dataSourceVar is not None else DATA_SOURCE_AUTO

    processedTransients = None
    impd = None
    temperaturesC = None
    nTemps = 0

    if signalMethod == SIGNAL_METHOD_MEASURED:
        # Resolve which Data Source to use, then whether it has a live
        # impdData instance behind it (Live/Offline only -- routes through
        # calculate_delC_normalized(), with error bars/denoise) or not
        # (Qualitative Analysis, or Live/Offline with only an averaged
        # snapshot and no live instance -- the plain nearest-sample lookup on
        # the ensemble-averaged transient is used instead, with no error
        # bars). Resolved via instance-availability directly, not through
        # _get_processed_transients_for_source() first, since an impd-backed
        # source doesn't need (and may not have) an averaged-snapshot cache.
        if source != DATA_SOURCE_AUTO:
            resolvedLabel = source
        else:
            # Auto: Loaded Folder, then the live run's Qualitative Analysis
            # (matches _get_processed_transients_for_source()'s own Auto
            # priority), then whichever of Live/Offline has something to offer.
            if dltsc.quickData_processedTransients:
                resolvedLabel = DATA_SOURCE_LOADED
            elif dltsc.manual_processedTransients:
                resolvedLabel = DATA_SOURCE_QUALITATIVE
            elif dltsc.livePlot_liveImpdData is not None or dltsc.livePlot_liveAllEmissionsData:
                resolvedLabel = DATA_SOURCE_LIVE
            elif dltsc.livePlot_offlineImpdData is not None or dltsc.livePlot_offlineAllEmissionsData:
                resolvedLabel = DATA_SOURCE_OFFLINE
            else:
                resolvedLabel = DATA_SOURCE_AUTO  # nothing available anywhere

        impd, _ = _resolve_impd_for_source(resolvedLabel)
        if impd is not None:
            busy = (dltsc.livePlot_liveIngestBusy if resolvedLabel == DATA_SOURCE_LIVE
                   else dltsc.livePlot_offlineIngestBusy)
            if busy:
                errorReason = f"{resolvedLabel} is still loading/ingesting; try again once it finishes."
                dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
                if dltsc.rateWindow_statusLabel is not None:
                    dltsc.rateWindow_statusLabel.config(text=errorReason)
                return
            nTemps = len(impd.dataTemps or [])
        else:
            processedTransients, resolvedLabel, errorReason = _get_processed_transients_for_source(resolvedLabel)
            if not processedTransients:
                dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
                if dltsc.rateWindow_statusLabel is not None:
                    dltsc.rateWindow_statusLabel.config(text=errorReason)
                return
            temperaturesC = sorted(processedTransients.keys())
            nTemps = len(temperaturesC)
    else:
        # Smoothed C: impdData's per-repeat spline (Live/Offline instance) when
        # the source has one; otherwise (Loaded Folder, Qualitative Analysis,
        # or a Live/Offline averaged snapshot only) a cubic spline through the
        # averaged transient -- Detailed Analysis' Smoothed C.
        impd, resolvedLabel = _resolve_impd_for_source(source)
        if impd is not None:
            busy = (dltsc.livePlot_liveIngestBusy if resolvedLabel == DATA_SOURCE_LIVE
                   else dltsc.livePlot_offlineIngestBusy)
            if busy:
                errorReason = f"{resolvedLabel} is still loading/ingesting; try again once it finishes."
                dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
                if dltsc.rateWindow_statusLabel is not None:
                    dltsc.rateWindow_statusLabel.config(text=errorReason)
                return
            nTemps = len(impd.dataTemps or [])
        else:
            processedTransients, resolvedLabel, errorReason = _get_processed_transients_for_source(source)
            if not processedTransients:
                dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
                if dltsc.rateWindow_statusLabel is not None:
                    dltsc.rateWindow_statusLabel.config(text=errorReason)
                return
            temperaturesC = sorted(processedTransients.keys())
            nTemps = len(temperaturesC)

    denoiseChoice = dltsc.rateWindow_denoiseVar.get() if dltsc.rateWindow_denoiseVar is not None else DENOISE_NONE

    windows = []
    for i, (t1Var, t2Var) in enumerate(dltsc.rateWindow_windowVars):
        try:
            t1 = float(t1Var.get())
            t2 = float(t2Var.get())
        except ValueError:
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1} has a non-numeric t1/t2.")
            return
        if t1 <= 0 or t2 <= t1:
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1}: need 0 < t1 < t2.")
            return
        windows.append((t1, t2))

    useRecords = impd is None
    if useRecords:
        # Loaded Folder / Qualitative Analysis (or a Live/Offline averaged
        # snapshot with no impdData instance): the averaged transients go
        # through Detailed Analysis' own pipeline -- optional per-transient
        # denoise, C(t1)/C(t2) from the nearest sample (Measured C) or a cubic
        # spline (Smoothed C), C_infinity as the mean over 40-90 % of the
        # reverse bias, and per-point errors from the raw transient's own
        # sample noise (dA._rate_window_signal) -- so this tab and Detailed
        # Analysis give the same S(T) for the same data, method and denoise.
        rbMs = _rb_ms_for_source(resolvedLabel, processedTransients)
        records, recTemps = _transient_records(processedTransients, rbMs, denoiseChoice,
                                               smoothed=(signalMethod == SIGNAL_METHOD_SMOOTHED))
        recT_K = np.array([tc + 273.15 for tc in recTemps])

    # Peaks are no longer searched here: Peak Deconvolution (the middle frame)
    # splits each set's S(T) into the primitives of its regions, below.
    signals = dict()
    for i, (t1, t2) in enumerate(windows):
        if useRecords:
            S, S_err = dA._rate_window_signal(recTemps, records, t1, t2)
            x, y, yErr = recT_K, S, S_err
        else:
            # Measured C or Smoothed C backed by a live impdData instance
            # (Live/Offline). emissionIndex=-1: the ensemble
            # average across every reverse-bias repeat, the same averaging the
            # Qualitative-Analysis-backed branch above (and Extract & Average
            # Transients) performs -- and the only index with a meaningful
            # cross-repeat yerr to propagate (see calculate_delC_normalized()'s
            # docstring).
            try:
                delC, delCErr = impd.calculate_delC_normalized(
                    t1=t1 / 1000.0, t2=t2 / 1000.0, emissionIndex=-1,
                    denoiseEmission=(denoiseChoice != DENOISE_NONE),
                    denoiseMethod=(denoiseChoice if denoiseChoice != DENOISE_NONE else 'pca'),
                    smoothCapacitance=(signalMethod == SIGNAL_METHOD_SMOOTHED), plot=False)
            except Exception as exc:
                dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1} calculation failed: {exc}")
                return

            x = delC[:, 0]
            y = delC[:, 3]
            yErr = delCErr[:, 1]

            # Store the denoised (and raw) emission snapshot this call used,
            # so it's inspectable/reusable rather than only living transiently
            # inside impd.dataEmissions.
            dltsc.rateWindow_denoisedEmissions = {T: dict(rec) for T, rec in impd.dataEmissions.items()}

        order = np.argsort(np.asarray(x, dtype=float))
        x, y = np.asarray(x, dtype=float)[order], np.asarray(y, dtype=float)[order]
        yErr = None if yErr is None else np.asarray(yErr, dtype=float)[order]
        signals[i] = {'T_k': x, 'Signal': y, 'Signal_err': dA._valid_errors(yErr),
                      't1': t1, 't2': t2, 'e_n': dA._emission_rate(t1, t2)}

    dltsc.rateWindow_signals = signals
    statusText = f"Using: {resolvedLabel} / {signalMethod} ({nTemps} temperature(s))."
    if dltsc.rateWindow_statusLabel is not None:
        dltsc.rateWindow_statusLabel.config(text=statusText)
    dltsc.log_to_textbox(
        f"Rate window analysis: computed {len(signals)} window set(s) "
        f"from {resolvedLabel} using {signalMethod} ({nTemps} temperature(s)).")
    if dltsc.deconv_displaySetCombo is not None:
        dltsc.deconv_displaySetCombo.config(values=[f'Set {i + 1}' for i in sorted(signals)])
        if dltsc.deconv_displaySetVar.get() not in dltsc.deconv_displaySetCombo.cget('values'):
            dltsc.deconv_displaySetVar.set('Set 1')
    _run_deconvolution()

def _selected_peak_rows():
    # Row ids selected in the Extracted Peaks table; empty = none selected.
    if dltsc.rateWindow_peakTable is None:
        return set()
    return set(dltsc.rateWindow_peakTable.selection())

def _redraw_rate_window_plot():
    # Draws the last Compute's spectra from dltsc.rateWindow_signals, with each
    # region's total deconvolution fit (dashed) and the extracted peaks (x),
    # limited to the sets that have a row selected in the Extracted Peaks table
    # (no selection = every set; then only the selected rows' peaks are
    # marked). Each set keeps a fixed colour (data and its fits share it) so
    # hiding some sets doesn't recolour the rest. The Arrhenius solver fits
    # the same selection.
    if not dltsc.rateWindow_signals:
        return
    selected = _selected_peak_rows()
    rowInfo = dltsc.rateWindow_rowInfo or {}
    selectedSets = {rowInfo[iid][0] for iid in selected if iid in rowInfo}
    visible = [i for i in sorted(dltsc.rateWindow_signals.keys()) if not selected or i in selectedSets]

    dltsc.rateWindow_ax.clear()
    for i in visible:
        sig = dltsc.rateWindow_signals[i]
        color = f'C{i % 10}'
        if sig['Signal_err'] is not None:
            dltsc.rateWindow_ax.errorbar(sig['T_k'], sig['Signal'], yerr=sig['Signal_err'], fmt='o',
                                         color=color, capsize=3, markersize=4, label=f'RW {i + 1}')
        else:
            dltsc.rateWindow_ax.plot(sig['T_k'], sig['Signal'], 'o', color=color, markersize=4, label=f'RW {i + 1}')
        for res in (dltsc.deconv_results or {}).get(i, []):
            if res.get('xf') is not None:
                dltsc.rateWindow_ax.plot(res['xf'], res['yf'], '--', color=color, alpha=0.7)

    for iid, peak in (dltsc.rateWindow_extractedPeaks or {}).items():
        if peak['set'] not in visible or (selected and iid not in selected):
            continue
        if peak['T_peak_err'] is not None:
            dltsc.rateWindow_ax.errorbar(peak['T_peak'], peak['S_peak'], xerr=peak['T_peak_err'], fmt='kx',
                                         markersize=9, capsize=4)
        else:
            dltsc.rateWindow_ax.plot(peak['T_peak'], peak['S_peak'], 'x', color='gray', markersize=9)

    for region in dltsc.deconv_regions or []:
        for bound in (region['tLo'], region['tHi']):
            dltsc.rateWindow_ax.axvline(bound, color='gray', linestyle=':', linewidth=1.0)
    dltsc.rateWindow_ax.set_xlabel('Temperature (K)')
    dltsc.rateWindow_ax.set_ylabel('DLTS Signal (ΔC / C∞)')
    dltsc.rateWindow_ax.set_title('Multi-Window DLTS Signal Spectrum')
    dltsc.rateWindow_ax.grid(True, linestyle=':')
    handles, labels = dltsc.rateWindow_ax.get_legend_handles_labels()
    if labels:
        dltsc.rateWindow_ax.legend()
    dltsc.rateWindow_figure.tight_layout(pad=2.0)
    dltsc.rateWindow_canvas.draw()

def _show_all_rate_windows():
    # Clearing the selection fires <<TreeviewSelect>>, which redraws every window.
    dltsc.rateWindow_peakTable.selection_set(())

def _build_rateWindowFrame(parent):
    # dltsConfig.init() (which would normally seed these as dicts) is not called by
    # DLTSGUI_MainWindow.py, so seed them here to be safe regardless of that wiring.
    if dltsc.rateWindow_signals is None:
        dltsc.rateWindow_signals = dict()
    if dltsc.rateWindow_extractedPeaks is None:
        dltsc.rateWindow_extractedPeaks = dict()
    if dltsc.rateWindow_rowInfo is None:
        dltsc.rateWindow_rowInfo = dict()

    # Plot on top, parameter/control fields below it -- the frames sit side by
    # side now (see construct_dataAnalysisTab()), so a left-sidebar-of-controls
    # layout would squeeze the plot into a narrow half-width column; stacking
    # instead lets the plot use the pane's full width, with controls laid out
    # horizontally underneath using that same width. Both rows get a share of
    # weight (not a weight=0 fixed-height bottom row) so the controls section
    # actually grows on a taller/maximized window instead of staying pinned to
    # one small size and forcing a scroll regardless of how much room there is.
    # The Arrhenius frame beside this one uses the same weights and controls
    # height (QUICK_CONTROLS_HEIGHT) so the two plots come out equally tall.
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=3)
    parent.grid_rowconfigure(2, weight=2)
    parent.grid_columnconfigure(0, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Rate Window Analysis', font=('Segoe UI', 10, 'bold')).pack(side='left')

    # --- Plot area (embedded, no popup window) ---
    plotHolder = tk.Frame(parent)
    plotHolder.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
    plotHolder.grid_rowconfigure(1, weight=1)
    plotHolder.grid_columnconfigure(0, weight=1)

    dltsc.rateWindow_figure = Figure(figsize=(6, 5), dpi=100)
    dltsc.rateWindow_ax = dltsc.rateWindow_figure.add_subplot(1, 1, 1)
    dltsc.rateWindow_ax.set_title('Multi-Window DLTS Signal Spectrum (Pseudo-Voigt Refinement)')
    dltsc.rateWindow_ax.set_xlabel('Temperature (K)')
    dltsc.rateWindow_ax.set_ylabel('DLTS Signal (ΔC / C∞)')
    dltsc.rateWindow_figure.tight_layout(pad=2.0)

    dltsc.rateWindow_canvas = FigureCanvasTkAgg(dltsc.rateWindow_figure, master=plotHolder)
    toolbar = NavigationToolbar2Tk(dltsc.rateWindow_canvas, plotHolder, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.rateWindow_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')
    dltsc.rateWindow_canvas.draw()

    # --- Controls, below the plot. Wrapped in a scrollable canvas (like
    # Qualitative Analysis' control column) so every field stays reachable --
    # scrolling if needed -- no matter how short the window gets. ---
    bottomContainer = tk.Frame(parent)
    bottomContainer.grid(row=2, column=0, sticky='nsew', padx=4, pady=(0, 4))

    bottomCanvas = tk.Canvas(bottomContainer, highlightthickness=0, height=QUICK_CONTROLS_HEIGHT)
    bottomScroll = ttk.Scrollbar(bottomContainer, orient='vertical', command=bottomCanvas.yview)
    bottomCanvas.configure(yscrollcommand=bottomScroll.set)
    bottomCanvas.pack(side='left', fill='both', expand=True)
    bottomScroll.pack(side='right', fill='y')

    bottomPanel = tk.Frame(bottomCanvas)
    bottomPanelWindow = bottomCanvas.create_window((0, 0), window=bottomPanel, anchor='nw')
    bottomPanel.bind('<Configure>', lambda e: bottomCanvas.configure(scrollregion=bottomCanvas.bbox('all')))
    bottomCanvas.bind('<Configure>', lambda e: bottomCanvas.itemconfigure(bottomPanelWindow, width=e.width))

    def _on_mousewheel(event):
        bottomCanvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    bottomCanvas.bind('<Enter>', lambda e: bottomCanvas.bind_all('<MouseWheel>', _on_mousewheel))
    bottomCanvas.bind('<Leave>', lambda e: bottomCanvas.unbind_all('<MouseWheel>'))

    # Data Source / DLTS Signal Calculation side by side. Peak finding moved to
    # the Peak Deconvolution frame.
    topRow = tk.Frame(bottomPanel)
    topRow.pack(fill='x', pady=(0, 4))

    # --- Data Source (optional -- 'Auto' resolves to whichever source has data) ---
    srcGroup = tk.LabelFrame(topRow, text='Data Source')
    srcGroup.pack(side='left', fill='both', expand=True, padx=(0, 2))
    dltsc.rateWindow_dataSourceVar = tk.StringVar(value=DATA_SOURCE_AUTO)
    ttk.Combobox(srcGroup, textvariable=dltsc.rateWindow_dataSourceVar, values=DATA_SOURCE_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=(4, 2))
    dltsc.rateWindow_statusLabel = ttk.Label(srcGroup, text='No data source resolved yet.',
                                             wraplength=220, justify='left')
    dltsc.rateWindow_statusLabel.pack(fill='x', padx=4, pady=(0, 4))

    # --- DLTS Signal Calculation (method + denoise) ---
    sigGroup = tk.LabelFrame(topRow, text='DLTS Signal Calculation')
    sigGroup.pack(side='left', fill='both', expand=True, padx=2)
    ttk.Label(sigGroup, text='Method:').pack(anchor='w', padx=4, pady=(4, 0))
    dltsc.rateWindow_signalMethodVar = tk.StringVar(value=SIGNAL_METHOD_MEASURED)
    ttk.Combobox(sigGroup, textvariable=dltsc.rateWindow_signalMethodVar, values=SIGNAL_METHOD_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=(0, 4))
    ttk.Label(sigGroup, text='Denoise (any Data Source):').pack(
        anchor='w', padx=4, pady=(0, 0))
    dltsc.rateWindow_denoiseVar = tk.StringVar(value=DENOISE_NONE)
    ttk.Combobox(sigGroup, textvariable=dltsc.rateWindow_denoiseVar, values=DENOISE_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=(0, 4))

    # --- Configure Rate Windows (Double Boxcar) ---
    # 2 sets per row (not one set per row) -- halves this group's height, which
    # matters now that it competes with the plot for vertical space above it
    # rather than sharing a fixed-width sidebar with nothing else fighting for room.
    rwGroup = tk.LabelFrame(bottomPanel, text='Configure Rate Windows (Double Boxcar)')
    rwGroup.pack(fill='x', pady=(0, 4))
    dltsc.rateWindow_windowVars = []
    setsPerRow = 2
    rowFrame = None
    for i, (t1Default, t2Default) in enumerate(DEFAULT_RATE_WINDOWS):
        t1Var = tk.StringVar(value=t1Default)
        t2Var = tk.StringVar(value=t2Default)
        dltsc.rateWindow_windowVars.append((t1Var, t2Var))

        if i % setsPerRow == 0:
            rowFrame = tk.Frame(rwGroup)
            rowFrame.pack(fill='x', padx=4, pady=2)
        setFrame = tk.Frame(rowFrame)
        setFrame.pack(side='left', padx=(0, 16))
        ttk.Label(setFrame, text=f'Set {i + 1}:').pack(side='left')
        ttk.Label(setFrame, text='t1 (ms):').pack(side='left', padx=(8, 2))
        ttk.Entry(setFrame, textvariable=t1Var, width=8).pack(side='left')
        ttk.Label(setFrame, text='t2 (ms):').pack(side='left', padx=(8, 2))
        ttk.Entry(setFrame, textvariable=t2Var, width=8).pack(side='left')

    # --- Execution Action ---
    calcBtn = tk.Button(bottomPanel, text='Compute Boxcar Spectrums', font=('Segoe UI', 9, 'bold'),
                        bg='#bbdefb', command=_calculate_rate_windows)
    calcBtn.pack(fill='x', pady=(0, 4))

    # --- Peak results table ---
    tableGroup = tk.LabelFrame(bottomPanel, text='Extracted Peaks')
    tableGroup.pack(fill='both', expand=True)
    # One row per deconvolved peak per set (row id 'w<set>r<region>p<peak>'),
    # or one 'no peak' / 'fit failed' row per set and region
    # (dltsc.rateWindow_rowInfo maps every row id to its set).
    columns = ('window', 'peak', 'en', 'tpeak', 'speak', 'fit')
    dltsc.rateWindow_peakTable = ttk.Treeview(tableGroup, columns=columns, show='headings', height=6)
    dltsc.rateWindow_peakTable.heading('window', text='Window')
    dltsc.rateWindow_peakTable.heading('peak', text='Peak')
    dltsc.rateWindow_peakTable.heading('en', text='e_n (s⁻¹)')
    dltsc.rateWindow_peakTable.heading('tpeak', text='T_peak (K)')
    dltsc.rateWindow_peakTable.heading('speak', text='Height ΔC/C∞')
    # Filled in by the Arrhenius solver: used / excluded (see dA._arrhenius_fit).
    dltsc.rateWindow_peakTable.heading('fit', text='Arrhenius fit')
    for col, width in zip(columns, (50, 110, 70, 110, 120, 110)):
        dltsc.rateWindow_peakTable.column(col, width=width, minwidth=40, anchor='center')
    tableScroll = ttk.Scrollbar(tableGroup, orient='horizontal', command=dltsc.rateWindow_peakTable.xview)
    dltsc.rateWindow_peakTable.configure(xscrollcommand=tableScroll.set)
    dltsc.rateWindow_peakTable.pack(fill='both', expand=True, padx=4, pady=(4, 0))
    tableScroll.pack(fill='x', padx=4)
    # Selecting rows (Ctrl/Shift-click for several) limits the spectrum plot and
    # the Arrhenius solver to those peaks, stars them on the Arrhenius plot and
    # shows the first one's set in Peak Deconvolution; no selection uses them all.
    dltsc.rateWindow_peakTable.bind('<<TreeviewSelect>>', lambda e: _on_peak_table_select())
    tableHint = tk.Frame(tableGroup)
    tableHint.pack(fill='x', padx=4, pady=(0, 4))
    ttk.Label(tableHint, text='Select rows (Ctrl/Shift-click for several) to use only those peaks '
                              'in the plot and the Arrhenius fit.',
              wraplength=300, justify='left').pack(side='left')
    ttk.Button(tableHint, text='Show All', command=_show_all_rate_windows).pack(side='right')


#---------------------PEAK DECONVOLUTION (MIDDLE FRAME)-------------------------#
# Replaces Rate Window Analysis' single-peak Peak-Finding Method. The user picks
# temperature regions (typed, or dragged on this frame's plot) and the primitives
# to split each one into; every rate-window set's S(T) is then deconvolved region
# by region with impedanceAnalysis_Tools' shared finders (impdData._deconvolve_peaks,
# or impdData._smoothingSpline_multiPeakFinder for a Smoothing Spline region), and
# each fitted peak becomes one Extracted Peaks row. A peak's id R<region>P<peak>
# -- its place in its region, low to high temperature -- is what ties it across
# sets into one trap for the Arrhenius solver.
def _region_text(r, region):
    prims = ' + '.join(PRIMITIVE_SHORT[p] for p in region['primitives']) or '(no primitives)'
    if region['primitives'] == [PRIMITIVE_SPLINE]:
        prims += f" (prom. ≥ {region['prominence']:g})"
    return f"R{r + 1}: {region['tLo']:g}–{region['tHi']:g} K | {prims}"

def _run_deconvolution():
    """Deconvolve every computed set in every region and refill the Extracted
    Peaks table (dltsc.rateWindow_extractedPeaks / rateWindow_rowInfo), then
    redraw. Arrhenius results from before stay on screen but lose their
    selection stars, since the row ids now name the new peaks."""
    if not dltsc.rateWindow_signals:
        dltsc.log_to_textbox("Peak deconvolution: click Compute Boxcar Spectrums first.")
        return
    regions = dltsc.deconv_regions or []
    problems = [f'R{r + 1}: {p}' for r, region in enumerate(regions) if (p := dA._region_problem(region))]
    if not regions:
        problems = ['add at least one region']
    if problems:
        message = "Peak deconvolution: " + '; '.join(problems) + '.'
        dltsc.log_to_textbox(message)
        if dltsc.deconv_statusLabel is not None:
            dltsc.deconv_statusLabel.config(text=message)
        return

    results, peaks, rowInfo = dict(), dict(), dict()
    for row in dltsc.rateWindow_peakTable.get_children():
        dltsc.rateWindow_peakTable.delete(row)
    for i in sorted(dltsc.rateWindow_signals):
        sig = dltsc.rateWindow_signals[i]
        results[i] = []
        for r, region in enumerate(regions):
            res = dA._deconvolve_region(sig, region)
            results[i].append(res)
            if res['message']:
                dltsc.log_to_textbox(f"Peak deconvolution: Set {i + 1}, R{r + 1}: {res['message']}")
            if not res['peaks']:
                iid = f'w{i}r{r}'
                rowInfo[iid] = (i, None)
                dltsc.rateWindow_peakTable.insert('', 'end', iid=iid, values=(
                    f'Set {i + 1}', f'R{r + 1}', f"{sig['e_n']:.2f}", '—', '—',
                    'no peak' if res['ok'] else 'fit failed'))
                continue
            for k, pk in enumerate(res['peaks']):
                iid = f'w{i}r{r}p{k}'
                peakId = f'R{r + 1}P{k + 1}'
                peaks[iid] = dict(pk, set=i, region=r, peakId=peakId,
                                  e_n=sig['e_n'], t1=sig['t1'], t2=sig['t2'])
                rowInfo[iid] = (i, peakId)
                tPeakText = dA._fmt_pm(pk['T_peak'], pk['T_peak_err'], '.2f')
                heightText = dA._fmt_pm(pk['S_peak'], pk['S_peak_err'], '.5f')
                status = '—' if pk['T_peak_err'] is not None else (
                    'no Tp error (edge)' if pk['onEdge'] else 'no Tp error')
                dltsc.rateWindow_peakTable.insert('', 'end', iid=iid, values=(
                    f'Set {i + 1}', f"{peakId} {PRIMITIVE_SHORT[pk['primitive']]}", f"{sig['e_n']:.2f}",
                    tPeakText, heightText, status))

    # A spline region's P<k> is its k-th peak from low T, so it only names the
    # same trap in every set if every set found the same number of peaks there.
    for r, region in enumerate(regions):
        if region['primitives'] == [PRIMITIVE_SPLINE]:
            counts = [len(results[i][r]['peaks']) for i in sorted(results)]
            if len(set(counts)) > 1:
                dltsc.log_to_textbox(
                    f"Peak deconvolution: R{r + 1} spline found {counts} peak(s) in the sets; its P<n> may "
                    f"not be the same trap in every set -- adjust the prominence or the region.")

    dltsc.deconv_results = results
    dltsc.rateWindow_extractedPeaks = peaks
    dltsc.rateWindow_rowInfo = rowInfo
    dltsc.arrhenius_windowPoints = dict()
    _redraw_rate_window_plot()
    _redraw_deconv_plot()
    _update_arrhenius_highlight()
    message = (f"Deconvolved {len(results)} set(s) in {len(regions)} region(s): "
               f"{len(peaks)} peak(s) extracted.")
    if dltsc.deconv_statusLabel is not None:
        dltsc.deconv_statusLabel.config(text=message)
    dltsc.log_to_textbox(f"Peak deconvolution: {message}")

def _display_set_index():
    try:
        return int(dltsc.deconv_displaySetVar.get().split()[-1]) - 1
    except (AttributeError, ValueError, IndexError):
        return 0

def _selected_region_index():
    if dltsc.deconv_regionListbox is None:
        return None
    selection = dltsc.deconv_regionListbox.curselection()
    return selection[0] if selection else None

def _redraw_deconv_plot():
    """The displayed set's S(T) around the regions, each region's total fit
    (black), its primitives (dashed, filled) and peaks (▼ with T_peak error),
    and the residuals below (divided by the point errors when the set has
    them). The selected region is shaded gold."""
    if dltsc.deconv_ax is None:
        return
    ax, residAx = dltsc.deconv_ax, dltsc.deconv_residAx
    ax.clear()
    residAx.clear()
    regions = dltsc.deconv_regions or []
    selectedRegion = _selected_region_index()
    for r, region in enumerate(regions):
        isSelected = r == selectedRegion
        ax.axvspan(region['tLo'], region['tHi'], color='gold' if isSelected else 'lightgray',
                   alpha=0.3 if isSelected else 0.25, linewidth=0)
        ax.text(region['tLo'], 0.98, f' R{r + 1}', transform=ax.get_xaxis_transform(), va='top', fontsize=8)

    i = _display_set_index()
    sig = (dltsc.rateWindow_signals or {}).get(i)
    title = 'Peak Deconvolution'
    infoLines = []
    residualNorm = False
    if sig is not None:
        title = f"Peak Deconvolution — Set {i + 1} (e_n = {sig['e_n']:.2f} s⁻¹)"
        T, S, S_err = sig['T_k'], sig['Signal'], sig['Signal_err']
        view = np.ones(T.size, dtype=bool)
        if regions:
            lo, hi = min(rg['tLo'] for rg in regions), max(rg['tHi'] for rg in regions)
            pad = 0.08 * (hi - lo)
            view = (T >= lo - pad) & (T <= hi + pad)
            ax.set_xlim(lo - pad, hi + pad)
        color = f'C{i % 10}'
        if S_err is not None:
            ax.errorbar(T[view], S[view], yerr=S_err[view], fmt='o', color=color, markersize=4, capsize=2,
                        label=f'RW {i + 1} data')
        else:
            ax.plot(T[view], S[view], 'o', color=color, markersize=4, label=f'RW {i + 1} data')

        totalLabel = 'Total fit'
        for r, res in enumerate((dltsc.deconv_results or {}).get(i, [])):
            if res['xf'] is None:
                infoLines.append(f"R{r + 1}: {res['message'] or 'no fit'}")
                continue
            ax.plot(res['xf'], res['yf'], 'k-', linewidth=1.5, label=totalLabel)
            totalLabel = '_nolegend_'
            for label, curve in res['componentCurves']:
                line, = ax.plot(res['xf'], curve, '--', linewidth=1.0, label=f'R{r + 1} {PRIMITIVE_SHORT[label]}')
                ax.fill_between(res['xf'], curve, color=line.get_color(), alpha=0.12, linewidth=0)
            residAx.plot(res['x'], res['residual'], 'o', color=color, markersize=3)
            residualNorm = residualNorm or res['residualNorm']
            if res['redchi'] is not None:
                infoLines.append(f"R{r + 1}: χ²ᵣ = {res['redchi']:.3g}, R² = {res['rsquared']:.4f}, "
                                 f"{len(res['peaks'])} peak(s)" + (f" — {res['message']}" if res['message'] else ''))
            else:
                infoLines.append(f"R{r + 1}: spline, {len(res['peaks'])} peak(s) above the prominence")

        for peak in (dltsc.rateWindow_extractedPeaks or {}).values():
            if peak['set'] != i:
                continue
            ax.errorbar(peak['T_peak'], peak['S_peak'], xerr=peak['T_peak_err'], fmt='v',
                        color='black' if peak['T_peak_err'] is not None else 'gray', markersize=7, capsize=3)
            ax.annotate(peak['peakId'], (peak['T_peak'], peak['S_peak']), textcoords='offset points',
                        xytext=(0, 8), ha='center', fontsize=8)

    residAx.axhline(0.0, color='gray', linewidth=0.8)
    residAx.set_ylabel('resid. / σ' if residualNorm else 'residual')
    residAx.set_xlabel('Temperature (K)')
    residAx.grid(True, linestyle=':')
    ax.set_ylabel('DLTS Signal (ΔC / C∞)')
    ax.set_title(title, fontsize=10)
    ax.grid(True, linestyle=':')
    ax.tick_params(labelbottom=False)
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend(fontsize=7)
    if dltsc.deconv_fitInfoLabel is not None:
        dltsc.deconv_fitInfoLabel.config(text='\n'.join(infoLines) if infoLines else 'No fit for this set yet.')

    # ax.clear() drops the selector's own artists, so it is rebuilt each redraw.
    if dltsc.deconv_spanSelector is not None:
        dltsc.deconv_spanSelector.disconnect_events()
    dltsc.deconv_spanSelector = SpanSelector(ax, _on_span_select, 'horizontal', useblit=True, minspan=1.0,
                                             props=dict(facecolor='tab:blue', alpha=0.2))
    dltsc.deconv_figure.tight_layout(pad=1.5)
    dltsc.deconv_canvas.draw()

def _on_span_select(tLo, tHi):
    dltsc.deconv_tLoVar.set(f'{tLo:.1f}')
    dltsc.deconv_tHiVar.set(f'{tHi:.1f}')
    dltsc.deconv_statusLabel.config(text=f'Picked {tLo:.1f}–{tHi:.1f} K: click Add Region, or Update '
                                         f'Region to move the selected one.')

def _regions_changed(message):
    """After any region/primitive edit: refresh the lists, redraw the region
    shading and bounds (the fits stay until the next Deconvolve All Sets)."""
    _refresh_region_widgets(_selected_region_index())
    _redraw_deconv_plot()
    _redraw_rate_window_plot()
    dltsc.deconv_statusLabel.config(text=f'{message} Click Deconvolve All Sets to refit.')

def _refresh_region_widgets(selectIndex=None, primitiveIndex=None):
    regions = dltsc.deconv_regions
    dltsc.deconv_regionListbox.delete(0, tk.END)
    for r, region in enumerate(regions):
        dltsc.deconv_regionListbox.insert(tk.END, _region_text(r, region))
    dltsc.deconv_primitiveListbox.delete(0, tk.END)
    if selectIndex is None or not regions:
        return
    selectIndex = min(selectIndex, len(regions) - 1)
    dltsc.deconv_regionListbox.selection_set(selectIndex)
    for prim in regions[selectIndex]['primitives']:
        dltsc.deconv_primitiveListbox.insert(tk.END, prim)
    if primitiveIndex is not None and regions[selectIndex]['primitives']:
        dltsc.deconv_primitiveListbox.selection_set(min(primitiveIndex, len(regions[selectIndex]['primitives']) - 1))

def _on_region_select():
    r = _selected_region_index()
    if r is None:
        return
    region = dltsc.deconv_regions[r]
    dltsc.deconv_tLoVar.set(f"{region['tLo']:g}")
    dltsc.deconv_tHiVar.set(f"{region['tHi']:g}")
    dltsc.deconv_prominenceVar.set(f"{region['prominence']:g}")
    _refresh_region_widgets(r)
    _redraw_deconv_plot()

def _read_region_entries():
    """(tLo, tHi, prominence) from the region entries, or None (logged) if invalid."""
    try:
        tLo = float(dltsc.deconv_tLoVar.get())
        tHi = float(dltsc.deconv_tHiVar.get())
        prominence = float(dltsc.deconv_prominenceVar.get())
    except ValueError:
        dltsc.deconv_statusLabel.config(text='Region bounds and prominence must be numbers.')
        return None
    if tHi <= tLo:
        dltsc.deconv_statusLabel.config(text='The region upper bound must exceed the lower bound.')
        return None
    if not 0.0 < prominence < 1.0:
        dltsc.deconv_statusLabel.config(text='Min prominence is a fraction of the region maximum: 0 < p < 1.')
        return None
    return tLo, tHi, prominence

def _add_region():
    values = _read_region_entries()
    if values is None:
        return
    tLo, tHi, prominence = values
    dltsc.deconv_regions.append(dict(tLo=tLo, tHi=tHi, primitives=[], prominence=prominence))
    _refresh_region_widgets(len(dltsc.deconv_regions) - 1)
    _regions_changed(f'R{len(dltsc.deconv_regions)} added: add its primitives.')

def _update_region():
    r = _selected_region_index()
    values = _read_region_entries()
    if r is None or values is None:
        if r is None:
            dltsc.deconv_statusLabel.config(text='Select a region to update.')
        return
    region = dltsc.deconv_regions[r]
    region['tLo'], region['tHi'], region['prominence'] = values
    _regions_changed(f'R{r + 1} updated.')

def _remove_region():
    r = _selected_region_index()
    if r is None:
        dltsc.deconv_statusLabel.config(text='Select a region to remove.')
        return
    del dltsc.deconv_regions[r]
    _refresh_region_widgets(r if dltsc.deconv_regions else None)
    _regions_changed(f'R{r + 1} removed (later regions renumbered).')

def _add_primitive():
    r = _selected_region_index()
    if r is None:
        dltsc.deconv_statusLabel.config(text='Select (or add) a region first.')
        return
    choice = dltsc.deconv_primitiveVar.get()
    prims = dltsc.deconv_regions[r]['primitives']
    if prims and (choice == PRIMITIVE_SPLINE or PRIMITIVE_SPLINE in prims):
        dltsc.deconv_statusLabel.config(
            text='Smoothing Spline must be a region\'s only primitive: remove the others first, or add a new region.')
        return
    prims.append(choice)
    _refresh_region_widgets(r, len(prims) - 1)
    _regions_changed(f'{choice} added to R{r + 1}.')

def _remove_primitive():
    r = _selected_region_index()
    selection = dltsc.deconv_primitiveListbox.curselection()
    if r is None or not selection:
        dltsc.deconv_statusLabel.config(text='Select a primitive to remove.')
        return
    removed = dltsc.deconv_regions[r]['primitives'].pop(selection[0])
    _refresh_region_widgets(r, selection[0])
    _regions_changed(f'{removed} removed from R{r + 1}.')

def _move_primitive(step):
    r = _selected_region_index()
    selection = dltsc.deconv_primitiveListbox.curselection()
    if r is None or not selection:
        return
    prims = dltsc.deconv_regions[r]['primitives']
    k, j = selection[0], selection[0] + step
    if not 0 <= j < len(prims):
        return
    prims[k], prims[j] = prims[j], prims[k]
    _refresh_region_widgets(r, j)
    _regions_changed(f'R{r + 1} reordered.')

def _build_deconvolutionFrame(parent):
    # Same plot-on-top / scrollable-controls-below layout, row weights and
    # controls height as the frames on either side, so all three plots come
    # out equally tall.
    if not dltsc.deconv_regions:
        # Default: the old single-peak default (smoothing spline over the
        # default Tp search range), now finding every peak in it.
        dltsc.deconv_regions = [dict(tLo=float(DEFAULT_TPEAK_LO), tHi=float(DEFAULT_TPEAK_HI),
                                     primitives=[PRIMITIVE_SPLINE], prominence=float(DEFAULT_PROMINENCE))]
    if dltsc.deconv_results is None:
        dltsc.deconv_results = dict()

    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=3)
    parent.grid_rowconfigure(2, weight=2)
    parent.grid_columnconfigure(0, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Peak Deconvolution', font=('Segoe UI', 10, 'bold')).pack(side='left')

    # --- Plot area: fit on top, residuals below ---
    plotHolder = tk.Frame(parent)
    plotHolder.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
    plotHolder.grid_rowconfigure(1, weight=1)
    plotHolder.grid_columnconfigure(0, weight=1)

    dltsc.deconv_figure = Figure(figsize=(6, 5), dpi=100)
    grid = dltsc.deconv_figure.add_gridspec(2, 1, height_ratios=[3, 1])
    dltsc.deconv_ax = dltsc.deconv_figure.add_subplot(grid[0])
    dltsc.deconv_residAx = dltsc.deconv_figure.add_subplot(grid[1], sharex=dltsc.deconv_ax)

    dltsc.deconv_canvas = FigureCanvasTkAgg(dltsc.deconv_figure, master=plotHolder)
    toolbar = NavigationToolbar2Tk(dltsc.deconv_canvas, plotHolder, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.deconv_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')

    # --- Controls, below the plot, scrollable like the other frames ---
    bottomContainer = tk.Frame(parent)
    bottomContainer.grid(row=2, column=0, sticky='nsew', padx=4, pady=(0, 4))

    bottomCanvas = tk.Canvas(bottomContainer, highlightthickness=0, height=QUICK_CONTROLS_HEIGHT)
    bottomScroll = ttk.Scrollbar(bottomContainer, orient='vertical', command=bottomCanvas.yview)
    bottomCanvas.configure(yscrollcommand=bottomScroll.set)
    bottomCanvas.pack(side='left', fill='both', expand=True)
    bottomScroll.pack(side='right', fill='y')

    bottomPanel = tk.Frame(bottomCanvas)
    bottomPanelWindow = bottomCanvas.create_window((0, 0), window=bottomPanel, anchor='nw')
    bottomPanel.bind('<Configure>', lambda e: bottomCanvas.configure(scrollregion=bottomCanvas.bbox('all')))
    bottomCanvas.bind('<Configure>', lambda e: bottomCanvas.itemconfigure(bottomPanelWindow, width=e.width))

    def _on_mousewheel(event):
        bottomCanvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    bottomCanvas.bind('<Enter>', lambda e: bottomCanvas.bind_all('<MouseWheel>', _on_mousewheel))
    bottomCanvas.bind('<Leave>', lambda e: bottomCanvas.unbind_all('<MouseWheel>'))

    # --- Display set + Execution Action ---
    topRow = tk.Frame(bottomPanel)
    topRow.pack(fill='x', pady=(0, 4))
    ttk.Label(topRow, text='Show:').pack(side='left', padx=(0, 2))
    dltsc.deconv_displaySetVar = tk.StringVar(value='Set 1')
    dltsc.deconv_displaySetCombo = ttk.Combobox(
        topRow, textvariable=dltsc.deconv_displaySetVar, state='readonly', width=7,
        values=[f'Set {i + 1}' for i in range(len(DEFAULT_RATE_WINDOWS))])
    dltsc.deconv_displaySetCombo.pack(side='left')
    dltsc.deconv_displaySetCombo.bind('<<ComboboxSelected>>', lambda e: _redraw_deconv_plot())
    tk.Button(topRow, text='Deconvolve All Sets', font=('Segoe UI', 9, 'bold'), bg='#c8e6c9',
              command=_run_deconvolution).pack(side='left', fill='x', expand=True, padx=(8, 0))

    dltsc.deconv_fitInfoLabel = ttk.Label(bottomPanel, text='No fit for this set yet.', justify='left',
                                          wraplength=420)
    dltsc.deconv_fitInfoLabel.pack(fill='x', pady=(0, 4))

    # --- Regions ---
    regionGroup = tk.LabelFrame(bottomPanel, text='Regions (drag on the plot to pick a range)')
    regionGroup.pack(fill='x', pady=(0, 4))
    dltsc.deconv_regionListbox = tk.Listbox(regionGroup, height=4, exportselection=False)
    dltsc.deconv_regionListbox.pack(fill='x', padx=4, pady=(4, 2))
    dltsc.deconv_regionListbox.bind('<<ListboxSelect>>', lambda e: _on_region_select())
    entryRow = tk.Frame(regionGroup)
    entryRow.pack(fill='x', padx=4, pady=2)
    dltsc.deconv_tLoVar = tk.StringVar(value=f"{dltsc.deconv_regions[0]['tLo']:g}")
    dltsc.deconv_tHiVar = tk.StringVar(value=f"{dltsc.deconv_regions[0]['tHi']:g}")
    dltsc.deconv_prominenceVar = tk.StringVar(value=DEFAULT_PROMINENCE)
    ttk.Label(entryRow, text='T (K):').pack(side='left')
    ttk.Entry(entryRow, textvariable=dltsc.deconv_tLoVar, width=7).pack(side='left', padx=(2, 0))
    ttk.Label(entryRow, text='to').pack(side='left', padx=2)
    ttk.Entry(entryRow, textvariable=dltsc.deconv_tHiVar, width=7).pack(side='left')
    ttk.Label(entryRow, text='Spline min prominence:').pack(side='left', padx=(10, 2))
    ttk.Entry(entryRow, textvariable=dltsc.deconv_prominenceVar, width=6).pack(side='left')
    regionButtons = tk.Frame(regionGroup)
    regionButtons.pack(fill='x', padx=4, pady=(2, 4))
    for text, command in (('Add Region', _add_region), ('Update Region', _update_region),
                          ('Remove Region', _remove_region)):
        ttk.Button(regionButtons, text=text, command=command).pack(side='left', fill='x', expand=True, padx=1)
    ttk.Label(regionGroup, text='Spline min prominence: fraction of the region\'s largest |S| a peak must '
                                'rise above its surroundings (Smoothing Spline regions only).',
              foreground='gray', wraplength=420, justify='left').pack(anchor='w', padx=4, pady=(0, 4))

    # --- Primitives of the selected region ---
    primGroup = tk.LabelFrame(bottomPanel, text='Primitives of the selected region (list peaks low → high T)')
    primGroup.pack(fill='x', pady=(0, 4))
    dltsc.deconv_primitiveListbox = tk.Listbox(primGroup, height=4, exportselection=False)
    dltsc.deconv_primitiveListbox.pack(fill='x', padx=4, pady=(4, 2))
    primRow = tk.Frame(primGroup)
    primRow.pack(fill='x', padx=4, pady=(2, 4))
    dltsc.deconv_primitiveVar = tk.StringVar(value=PRIMITIVE_OPTIONS[0])
    ttk.Combobox(primRow, textvariable=dltsc.deconv_primitiveVar, values=PRIMITIVE_OPTIONS,
                 state='readonly', width=30).pack(side='left', fill='x', expand=True)
    for text, command in (('Add', _add_primitive), ('Remove', _remove_primitive),
                          ('▲', lambda: _move_primitive(-1)), ('▼', lambda: _move_primitive(1))):
        ttk.Button(primRow, text=text, width=7 if len(text) > 1 else 3,
                   command=command).pack(side='left', padx=1)

    dltsc.deconv_statusLabel = ttk.Label(bottomPanel, text='Compute Boxcar Spectrums, then adjust the regions.',
                                         wraplength=420, justify='left')
    dltsc.deconv_statusLabel.pack(fill='x', pady=(0, 4))

    _refresh_region_widgets(0)
    _redraw_deconv_plot()


#---------------------ARRHENIUS DEFECT MAPPING (RIGHT FRAME)-------------------------#
# Ported from DrKayisScript.py's "3. Arrhenius Defect Mapping" tab (PyQt6) into tkinter.
# Consumes dltsc.rateWindow_extractedPeaks, populated by _run_deconvolution() above:
# every peak id (R<region>P<peak>) found in several sets is one trap, with its own
# Arrhenius line.
ARRHENIUS_TRAP_MARKERS = ('s', 'o', '^', 'D', 'v', 'P', 'h')

def _trap_style(trapIndex):
    """(colour, marker) of the trapIndex-th trap on the Arrhenius plot. The
    'Dark2' colours stay distinct from the C0..C9 set colours the spectra and
    the selection stars use."""
    color = matplotlib.colormaps['Dark2'](trapIndex % 8)
    return color, ARRHENIUS_TRAP_MARKERS[trapIndex % len(ARRHENIUS_TRAP_MARKERS)]

def _update_arrhenius_highlight():
    # Marks the peaks selected in the Extracted Peaks table on the Arrhenius
    # plot with a star in their set's spectrum colour (C<i>), so a selection
    # can be followed from the table and the spectrum to this plot. Only points
    # from the last solver run (dltsc.arrhenius_windowPoints) can be marked;
    # no selection = no markers.
    if dltsc.arrhenius_ax is None:
        return
    for artist in dltsc.arrhenius_highlightArtists or []:
        artist.remove()
    dltsc.arrhenius_highlightArtists = []

    selected = _selected_peak_rows()
    points = dltsc.arrhenius_windowPoints or {}
    rowInfo = dltsc.rateWindow_rowInfo or {}
    label = 'Selected peak(s)'
    for iid in sorted(selected & points.keys()):
        x, y = points[iid]
        i = rowInfo[iid][0] if iid in rowInfo else 0
        artist, = dltsc.arrhenius_ax.plot(x, y, '*', color=f'C{i % 10}', markeredgecolor='k',
                                          markersize=16, zorder=5, label=label)
        dltsc.arrhenius_highlightArtists.append(artist)
        label = '_nolegend_'

    handles, labels = dltsc.arrhenius_ax.get_legend_handles_labels()
    if labels:
        dltsc.arrhenius_ax.legend(fontsize=8)
    dltsc.arrhenius_figure.tight_layout(pad=2.0)
    dltsc.arrhenius_canvas.draw()

def _on_peak_table_select():
    _redraw_rate_window_plot()
    _update_arrhenius_highlight()
    # Show the first selected row's set in Peak Deconvolution.
    rowInfo = dltsc.rateWindow_rowInfo or {}
    selection = [iid for iid in dltsc.rateWindow_peakTable.selection() if iid in rowInfo]
    if selection and dltsc.deconv_displaySetVar is not None:
        dltsc.deconv_displaySetVar.set(f'Set {rowInfo[selection[0]][0] + 1}')
        _redraw_deconv_plot()

def _run_arrhenius_solver():
    allPeaks = dltsc.rateWindow_extractedPeaks or {}
    if not allPeaks:
        dltsc.log_to_textbox(
            "Arrhenius solver: no extracted peaks yet -- Compute Boxcar Spectrums (and Deconvolve) first.")
        return

    # Only the peaks selected in the Extracted Peaks table (no selection =
    # every peak), the same ones the spectrum plot marks; grouped by peak id,
    # one trap per id.
    selected = _selected_peak_rows()
    traps = dict()
    for iid in sorted(allPeaks, key=lambda k: (allPeaks[k]['peakId'], allPeaks[k]['set'])):
        if not selected or iid in selected:
            traps.setdefault(allPeaks[iid]['peakId'], []).append(iid)
    if not any(len(iids) >= 2 for iids in traps.values()):
        dltsc.log_to_textbox(
            "Arrhenius solver: need one peak (R<n>P<n>) in at least 2 selected sets of the Extracted Peaks "
            "table (or clear the selection to use all of them).")
        return

    try:
        nBackgroundDoping = float(dltsc.arrhenius_ndVar.get().strip())
        if nBackgroundDoping <= 0:
            raise ValueError()
    except ValueError:
        dltsc.log_to_textbox("Arrhenius solver: Background Doping (Nd) must be a valid positive number.")
        return

    try:
        gamma = float(dltsc.arrhenius_gammaVar.get().strip())
        if gamma <= 0:
            raise ValueError()
    except ValueError:
        dltsc.log_to_textbox("Arrhenius solver: Emission pre-factor γ must be a valid positive number.")
        return

    fitStatus = {iid: 'not selected' for iid in allPeaks}
    dltsc.arrhenius_ax.clear()
    dltsc.arrhenius_windowPoints = dict()
    dltsc.arrhenius_trapResults = []
    for row in dltsc.arrhenius_trapTable.get_children():
        dltsc.arrhenius_trapTable.delete(row)

    for trapIndex, (peakId, iids) in enumerate(sorted(traps.items())):
        peaks = [allPeaks[iid] for iid in iids]
        # The fit itself is Detailed Analysis' dA._arrhenius_fit: an effective-
        # variance lmfit line weighted by each peak's T_peak error (x and y
        # both derive from T_peak, so a T_peak error moves a point along a
        # line). Peaks with no T_peak error -- on the edge of their region, or
        # no error estimate -- are left out of it, unless fewer than 3 have
        # errors, in which case every peak is fitted unweighted.
        try:
            res = dA._arrhenius_fit([p['e_n'] for p in peaks], [p['T_peak'] for p in peaks],
                                    [p['T_peak_err'] for p in peaks], gamma) if len(peaks) >= 2 else None
        except Exception as exc:
            dltsc.log_to_textbox(f"Arrhenius solver: {peakId}: linear fit failed: {exc}")
            res = None
        if res is None:
            for iid in iids:
                fitStatus[iid] = 'too few sets'
            dltsc.log_to_textbox(f"Arrhenius solver: {peakId}: fewer than 2 sets can be fitted; skipped.")
            continue

        fitMask = res['fit_mask']
        for iid, used in zip(iids, fitMask):
            fitStatus[iid] = 'used' if used else 'excluded (no Tp error)'
        nt, ntErr = dA._trap_density_from_peaks([p for p, used in zip(peaks, fitMask) if used], nBackgroundDoping)
        # The window peaks go along for the Trap Concentration tab's corrected Nt
        # (this tab's transients start at the fill end: t_FE = 0).
        res.update(peakId=peakId, Nt=nt, Nt_err=ntErr, t_fe=0.0, nd=nBackgroundDoping, peaks=[
            dict(t1=p['t1'], t2=p['t2'], e_n=p['e_n'], T_peak=p['T_peak'], T_peak_err=p['T_peak_err'],
                 S_peak=p['S_peak'], S_peak_err=p['S_peak_err'], used=bool(used)) for p, used in zip(peaks, fitMask)])
        dltsc.arrhenius_trapResults.append(res)

        # T_peak error on this plot's axes: x = 1000/T so dx = 1000*dT/T^2;
        # y = ln(e_n/T^2) = ln(e_n) - 2*ln(T) so dy = 2*dT/T.
        xInvT, yLnEnT2 = res['x'], res['y']
        tPeaks, tPeakErrs = res['Tp_arr'], res['Tp_err_arr']
        haveErr = np.isfinite(tPeakErrs)
        color, marker = _trap_style(trapIndex)
        energyText = dA._fmt_pm(res['Et'], res['Et_se'], '.3f')
        if (fitMask & haveErr).any():
            sel = fitMask & haveErr
            dltsc.arrhenius_ax.errorbar(xInvT[sel], yLnEnT2[sel],
                                        xerr=1000.0 * tPeakErrs[sel] / tPeaks[sel] ** 2,
                                        yerr=2.0 * tPeakErrs[sel] / tPeaks[sel],
                                        fmt=marker, color=color, markersize=7, capsize=4)
        if (fitMask & ~haveErr).any():
            sel = fitMask & ~haveErr
            dltsc.arrhenius_ax.plot(xInvT[sel], yLnEnT2[sel], marker, color=color, markersize=7,
                                    markerfacecolor='none')
        if (~fitMask).any():
            dltsc.arrhenius_ax.plot(xInvT[~fitMask], yLnEnT2[~fitMask], 'x', color='gray', markersize=9)
        xFitLine = np.linspace(min(xInvT) * 0.98, max(xInvT) * 1.02, 50)
        dltsc.arrhenius_ax.plot(xFitLine, res['slope'] * xFitLine + res['intercept'], '-', color=color,
                                label=f'{peakId}: Et = {energyText} eV')
        for k, iid in enumerate(iids):
            dltsc.arrhenius_windowPoints[iid] = (xInvT[k], yLnEnT2[k])

        captureText = dA._fmt_pm(res['sigma'], res['sigma_se'], '.2e')
        densityText = dA._fmt_pm(nt, ntErr, '.2e')
        dltsc.arrhenius_trapTable.insert('', 'end', iid=peakId, values=(
            peakId, energyText, captureText, densityText, f"{res['N']}" + (
                f" (+{res['N_excluded']} excl.)" if res['N_excluded'] else '')))
        dltsc.log_to_textbox(
            f"Arrhenius solver {peakId} ({'T_peak-error weighted' if res['weighted'] else 'unweighted'}, "
            f"{res['N']} sets" + (f", {res['N_excluded']} excluded" if res['N_excluded'] else '') + "): "
            f"Et={energyText} eV, sigma={captureText} cm² (γ={gamma:.3g}), Nt={densityText} cm⁻³.")

    for iid, status in fitStatus.items():
        if dltsc.rateWindow_peakTable is not None and dltsc.rateWindow_peakTable.exists(iid):
            dltsc.rateWindow_peakTable.set(iid, 'fit', status)

    dltsc.arrhenius_ax.set_xlabel('Reciprocal Temperature (1000 / T) (K⁻¹)')
    dltsc.arrhenius_ax.set_ylabel('ln(e_n / T²)')
    dltsc.arrhenius_ax.set_title('Arrhenius Plot Representation for Trap Signature Extraction')
    dltsc.arrhenius_ax.grid(True, linestyle=':')
    # ax.clear() above already removed the old highlight markers.
    dltsc.arrhenius_highlightArtists = []
    _update_arrhenius_highlight()
    # Trap Concentration recalculates Nt from these traps when it follows this tab.
    if dltsc.trapconc_sourceUpdated is not None:
        dltsc.trapconc_sourceUpdated('quick')

def _build_arrheniusFrame(parent):
    # Plot on top, parameter/control fields below it -- see _build_rateWindowFrame()
    # for why (the frames now sit side by side rather than top/bottom). Row
    # weights and the controls' requested height (QUICK_CONTROLS_HEIGHT) must
    # match _build_rateWindowFrame()'s exactly so both plots get equal heights.
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=3)
    parent.grid_rowconfigure(2, weight=2)
    parent.grid_columnconfigure(0, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Arrhenius Defect Mapping', font=('Segoe UI', 10, 'bold')).pack(side='left')

    # --- Plot area (embedded, no popup window) ---
    plotHolder = tk.Frame(parent)
    plotHolder.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
    plotHolder.grid_rowconfigure(1, weight=1)
    plotHolder.grid_columnconfigure(0, weight=1)

    dltsc.arrhenius_figure = Figure(figsize=(6, 5), dpi=100)
    dltsc.arrhenius_ax = dltsc.arrhenius_figure.add_subplot(1, 1, 1)
    dltsc.arrhenius_ax.set_title('Arrhenius Plot Representation for Trap Signature Extraction')
    dltsc.arrhenius_ax.set_xlabel('Reciprocal Temperature (1000 / T) (K⁻¹)')
    dltsc.arrhenius_ax.set_ylabel('ln(e_n / T²)')
    dltsc.arrhenius_figure.tight_layout(pad=2.0)

    dltsc.arrhenius_canvas = FigureCanvasTkAgg(dltsc.arrhenius_figure, master=plotHolder)
    toolbar = NavigationToolbar2Tk(dltsc.arrhenius_canvas, plotHolder, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.arrhenius_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')
    dltsc.arrhenius_canvas.draw()

    # --- Controls, below the plot. Wrapped in a scrollable canvas (like
    # Qualitative Analysis' control column) so every field stays reachable --
    # scrolling if needed -- no matter how short the window gets. ---
    bottomContainer = tk.Frame(parent)
    bottomContainer.grid(row=2, column=0, sticky='nsew', padx=4, pady=(0, 4))

    bottomCanvas = tk.Canvas(bottomContainer, highlightthickness=0, height=QUICK_CONTROLS_HEIGHT)
    bottomScroll = ttk.Scrollbar(bottomContainer, orient='vertical', command=bottomCanvas.yview)
    bottomCanvas.configure(yscrollcommand=bottomScroll.set)
    bottomCanvas.pack(side='left', fill='both', expand=True)
    bottomScroll.pack(side='right', fill='y')

    bottomPanel = tk.Frame(bottomCanvas)
    bottomPanelWindow = bottomCanvas.create_window((0, 0), window=bottomPanel, anchor='nw')
    bottomPanel.bind('<Configure>', lambda e: bottomCanvas.configure(scrollregion=bottomCanvas.bbox('all')))
    bottomCanvas.bind('<Configure>', lambda e: bottomCanvas.itemconfigure(bottomPanelWindow, width=e.width))

    def _on_mousewheel(event):
        bottomCanvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    bottomCanvas.bind('<Enter>', lambda e: bottomCanvas.bind_all('<MouseWheel>', _on_mousewheel))
    bottomCanvas.bind('<Leave>', lambda e: bottomCanvas.unbind_all('<MouseWheel>'))

    # Material Parameters / Execution Action side by side, the trap table below.
    topRow = tk.Frame(bottomPanel)
    topRow.pack(fill='x')

    # --- Material Parameters ---
    matGroup = tk.LabelFrame(topRow, text='Material Parameters')
    matGroup.pack(side='left', fill='both', expand=True, padx=(0, 2))
    dltsc.arrhenius_ndVar = tk.StringVar(value=DEFAULT_ND)
    ttk.Label(matGroup, text='Background Doping Nd (cm⁻³):').grid(
        row=0, column=0, sticky='w', padx=4, pady=2)
    ttk.Entry(matGroup, textvariable=dltsc.arrhenius_ndVar, width=12).grid(
        row=0, column=1, sticky='ew', padx=4, pady=2)
    dltsc.arrhenius_gammaVar = tk.StringVar(value=DEFAULT_GAMMA)
    ttk.Label(matGroup, text='Pre-factor γ (cm⁻² s⁻¹ K⁻²):').grid(
        row=1, column=0, sticky='w', padx=4, pady=2)
    ttk.Entry(matGroup, textvariable=dltsc.arrhenius_gammaVar, width=12).grid(
        row=1, column=1, sticky='ew', padx=4, pady=2)
    ttk.Label(matGroup, text='(SiC ≈ 1.66e21, Si ≈ 3.256e21)', foreground='gray').grid(
        row=2, column=0, columnspan=2, sticky='w', padx=4, pady=(0, 2))
    matGroup.grid_columnconfigure(1, weight=1)

    # --- Execution Action ---
    execGroup = tk.Frame(topRow)
    execGroup.pack(side='left', fill='both', expand=True, padx=(2, 0))
    solveBtn = tk.Button(execGroup, text='Execute Arrhenius Signature Solver', font=('Segoe UI', 9, 'bold'),
                         bg='#ffe082', wraplength=160, command=_run_arrhenius_solver)
    solveBtn.pack(fill='both', expand=True, padx=4, pady=4)

    # --- Extracted Microscopic Trap Signatures ---
    # One row per trap (peak id R<region>P<peak>), below the controls at full
    # width -- each value carries its ± error, which a narrow column would clip.
    outGroup = tk.LabelFrame(bottomPanel, text='Extracted Microscopic Trap Signatures')
    outGroup.pack(fill='both', expand=True, pady=(4, 0))
    columns = ('trap', 'et', 'sigma', 'nt', 'n')
    dltsc.arrhenius_trapTable = ttk.Treeview(outGroup, columns=columns, show='headings', height=4)
    for col, text, width in zip(columns, ('Trap', 'Et (eV)', 'σ (cm²)', 'Nt (cm⁻³)', 'Sets'),
                                (50, 100, 140, 140, 70)):
        dltsc.arrhenius_trapTable.heading(col, text=text)
        dltsc.arrhenius_trapTable.column(col, width=width, minwidth=40, anchor='center')
    trapScroll = ttk.Scrollbar(outGroup, orient='horizontal', command=dltsc.arrhenius_trapTable.xview)
    dltsc.arrhenius_trapTable.configure(xscrollcommand=trapScroll.set)
    dltsc.arrhenius_trapTable.pack(fill='both', expand=True, padx=4, pady=(4, 0))
    trapScroll.pack(fill='x', padx=4)
    ttk.Label(outGroup, text='Nt = 2·Nd·ΔC/C∞, ΔC/C∞ = peak height / boxcar factor, '
                             'averaged over the sets used.', foreground='gray',
              wraplength=420, justify='left').pack(anchor='w', padx=4, pady=(0, 4))


#---------------------OFFLINE DATA (SAVED FOLDER LOADER, LEFT COLUMN)-------------------------#
# Moved here from the Live Tools tab's Qualitative Analysis frame, which now only
# follows the running experiment. Loads a saved folder (ZI single-file, ZI
# subfolder-per-temperature, or legacy per-temperature files; several folders can
# be combined with Append), extracts & averages the checked temperatures, and
# feeds the result to Rate Window Analysis as the 'Loaded Folder' Data Source.
# The scan and extraction themselves are liveDataTab's (ldT._scan_folder,
# ldT._extract_transients_async).
def _set_quick_buttons_state(state):
    """Enable/disable the Offline Data buttons while a worker is running."""
    for button in (dltsc.quickData_selectFolderButton, dltsc.quickData_appendFolderButton,
                   dltsc.quickData_extractButton):
        if button is not None:
            button.config(state=state)

def _quick_busy():
    return bool(dltsc.quickData_loadingBusy or dltsc.quickData_processingBusy)

def _browse_quick_folder(isAppend=False):
    """Select Source Folder (isAppend=False) or Append Source Folder: add
    another folder's temperatures to the current dataset instead of replacing
    it, so a run that was split into pieces or taken across different
    dates/sessions can still be analyzed together."""
    if _quick_busy():
        return
    if isAppend and not dltsc.quickData_datasetRegistry:
        isAppend = False   # nothing loaded yet: append is just a first load
    dir_path = filedialog.askdirectory(
        title="Select DLTS Source Folder to Append" if isAppend else "Select DLTS Source Folder",
        # No cwd fallback: that is the software's own folder, and a folder
        # picked there risks writing into the source tree. Like Detailed
        # Analysis' Load Data, open at the OS default until a folder is chosen.
        **({'initialdir': dltsc.quickData_dataDirectory} if dltsc.quickData_dataDirectory else {}))
    if dir_path:
        dltsc.log_to_textbox(f"Offline Data: selected {dir_path} -- {ldT._describe_folder_contents(dir_path)}")
        _scan_quick_folder_async(dir_path, isAppend)

def _scan_quick_folder_async(dir_path, isAppend):
    """Index dir_path's temperatures on a background thread (ldT._scan_folder),
    then merge (isAppend) them into the Offline Data set or replace it, on the
    main thread. A new or changed set clears the previous extraction."""
    dltsc.quickData_loadingBusy = True
    _set_quick_buttons_state('disabled')
    dltsc.quickData_statusLabel.config(
        text=f"{'Appending' if isAppend else 'Loading'} {os.path.basename(dir_path)}...")

    def worker():
        scan = ldT._scan_folder(dir_path)

        def apply():
            dltsc.quickData_loadingBusy = False
            _set_quick_buttons_state('normal')
            registry = scan['registry']
            if isAppend:
                skipped = sorted(t for t in registry if t in dltsc.quickData_datasetRegistry)
                dltsc.quickData_datasetRegistry.update(
                    {t: v for t, v in registry.items() if t not in dltsc.quickData_datasetRegistry})
                dltsc.quickData_sourceFolders.append(dir_path)
                if skipped:
                    dltsc.log_to_textbox(
                        f"Offline Data: skipped {len(skipped)} temperature(s) already present "
                        f"from a previous source (kept the first-loaded copy): {skipped}")
                dltsc.quickData_folderLabel.config(
                    text=f"Source: {len(dltsc.quickData_sourceFolders)} folder(s) combined "
                         f"(latest: {os.path.basename(dir_path)})")
            else:
                dltsc.quickData_datasetRegistry = dict(registry)
                dltsc.quickData_sourceFolders = [dir_path]
                dltsc.quickData_dataDirectory = dir_path
                dltsc.quickData_ziParamsByFile = {}
                dltsc.quickData_folderLabel.config(text=f"Source: {os.path.basename(dir_path)}")
                if scan['fpMs'] is not None:
                    dltsc.quickData_paramVars['fp_ms'].set(f"{scan['fpMs']:g}")
                if scan['rbMs'] is not None:
                    dltsc.quickData_paramVars['rb_ms'].set(f"{scan['rbMs']:g}")
                    dltsc.log_to_textbox(f"Offline Data: Reverse Bias set to {scan['rbMs']:g} ms from the folder.")
            dltsc.quickData_ziParamsByFile.update(scan['ziParamsByFile'])
            dltsc.quickData_processedTransients = {}

            dltsc.quickData_tempListbox.delete(0, tk.END)
            for temp in sorted(dltsc.quickData_datasetRegistry):
                dltsc.quickData_tempListbox.insert(tk.END, f"{temp} °C")
            dltsc.quickData_tempListbox.select_set(0, tk.END)

            for msg in scan['errors']:
                dltsc.log_to_textbox(f"Offline Data: {msg}")
            dltsc.quickData_statusLabel.config(
                text=f"[{ldT._registry_format_label(dltsc.quickData_datasetRegistry)}] "
                     f"{len(dltsc.quickData_datasetRegistry)} temperature step(s) from "
                     f"{len(dltsc.quickData_sourceFolders)} source(s). Click Extract & Average.")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _extract_quick_transients():
    """Extract & average the checked Offline Data temperatures (off the main
    thread); the result is Rate Window Analysis' 'Loaded Folder' source."""
    if not dltsc.quickData_datasetRegistry or _quick_busy():
        return
    sortedTemps = sorted(dltsc.quickData_datasetRegistry)
    selectedTemps = [sortedTemps[i] for i in dltsc.quickData_tempListbox.curselection()]
    if not selectedTemps:
        dltsc.log_to_textbox("Offline Data: select at least one temperature.")
        return
    try:
        rbMs = float(dltsc.quickData_paramVars['rb_ms'].get())
        if rbMs <= 0:
            raise ValueError()
    except ValueError:
        dltsc.log_to_textbox("Offline Data: Reverse Bias (ms) must be a positive number.")
        return

    dltsc.quickData_processingBusy = True
    _set_quick_buttons_state('disabled')
    dltsc.quickData_statusLabel.config(text=f"Processing {len(selectedTemps)} temperature(s)...")

    def apply(processedTransients, executionErrors):
        dltsc.quickData_processingBusy = False
        _set_quick_buttons_state('normal')
        dltsc.quickData_processedTransients = processedTransients
        for err in executionErrors:
            dltsc.log_to_textbox(f"Offline Data: {err}")
        dltsc.quickData_statusLabel.config(
            text=f"{len(processedTransients)} of {len(selectedTemps)} temperature(s) extracted"
                 + ("; see log for the rest." if executionErrors else ". Ready for Compute Boxcar Spectrums."))
        dltsc.log_to_textbox(f"Offline Data: extracted {len(processedTransients)} averaged transient(s) "
                             f"(Data Source '{DATA_SOURCE_LOADED}').")

    ldT._extract_transients_async(dltsc.quickData_datasetRegistry, selectedTemps, rbMs,
                                  dltsc.quickData_ziParamsByFile, apply)

def _build_offlineDataFrame(parent):
    """Offline Data column (left side of the tab): Directory Loader Config,
    Available Temperatures Filter, Timing Boundaries and Execution Action.
    Scrollable, like the Live Tools tab's left columns, so every control stays
    reachable on a short window."""
    if dltsc.quickData_datasetRegistry is None:
        dltsc.quickData_datasetRegistry = dict()
    if dltsc.quickData_ziParamsByFile is None:
        dltsc.quickData_ziParamsByFile = dict()
    if dltsc.quickData_sourceFolders is None:
        dltsc.quickData_sourceFolders = list()
    if dltsc.quickData_processedTransients is None:
        dltsc.quickData_processedTransients = dict()
    dltsc.quickData_loadingBusy = False
    dltsc.quickData_processingBusy = False

    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)
    ttk.Label(parent, text='Offline Data', font=('Segoe UI', 10, 'bold')).grid(
        row=0, column=0, sticky='w', padx=4, pady=4)

    container = tk.Frame(parent)
    container.grid(row=1, column=0, sticky='nsew', padx=4, pady=(0, 4))
    canvas = tk.Canvas(container, width=230, highlightthickness=0)
    scroll = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    panel = tk.Frame(canvas)
    panelWindow = canvas.create_window((0, 0), window=panel, anchor='nw')
    panel.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(panelWindow, width=e.width))

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _on_mousewheel))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

    # --- Directory Loader Config ---
    ioGroup = tk.LabelFrame(panel, text='Directory Loader Config')
    ioGroup.pack(fill='x', pady=(0, 4))
    dltsc.quickData_selectFolderButton = ttk.Button(ioGroup, text='Select Source Folder',
                                                    command=lambda: _browse_quick_folder(isAppend=False))
    dltsc.quickData_selectFolderButton.pack(fill='x', padx=4, pady=(4, 2))
    dltsc.quickData_appendFolderButton = ttk.Button(ioGroup, text='Append Source Folder',
                                                    command=lambda: _browse_quick_folder(isAppend=True))
    dltsc.quickData_appendFolderButton.pack(fill='x', padx=4, pady=(0, 2))
    dltsc.quickData_folderLabel = ttk.Label(ioGroup, text='Source: (none selected)', wraplength=220, justify='left')
    dltsc.quickData_folderLabel.pack(fill='x', padx=4, pady=(0, 4))

    # --- Available Temperatures Filter ---
    tempGroup = tk.LabelFrame(panel, text='Available Temperatures Filter')
    tempGroup.pack(fill='x', pady=(0, 4))
    listFrame = tk.Frame(tempGroup)
    listFrame.pack(fill='both', expand=True, padx=4, pady=(4, 2))
    listScroll = ttk.Scrollbar(listFrame, orient='vertical')
    dltsc.quickData_tempListbox = tk.Listbox(listFrame, selectmode=tk.MULTIPLE, exportselection=False,
                                             height=8, yscrollcommand=listScroll.set)
    listScroll.config(command=dltsc.quickData_tempListbox.yview)
    dltsc.quickData_tempListbox.pack(side='left', fill='both', expand=True)
    listScroll.pack(side='right', fill='y')
    utilFrame = tk.Frame(tempGroup)
    utilFrame.pack(fill='x', padx=4, pady=(0, 4))
    ttk.Button(utilFrame, text='Select All', command=lambda: dltsc.quickData_tempListbox.select_set(0, tk.END)).pack(
        side='left', fill='x', expand=True, padx=(0, 2))
    ttk.Button(utilFrame, text='Clear All', command=lambda: dltsc.quickData_tempListbox.select_clear(0, tk.END)).pack(
        side='left', fill='x', expand=True, padx=(2, 0))

    # --- Timing Boundaries (set from the folder when it says them) ---
    paramGroup = tk.LabelFrame(panel, text='Timing Boundaries')
    paramGroup.pack(fill='x', pady=(0, 4))
    dltsc.quickData_paramVars = {'fp_ms': tk.StringVar(value='1.0'), 'rb_ms': tk.StringVar(value='500.0')}
    for row, (key, label) in enumerate((('fp_ms', 'Filling Duration (ms):'), ('rb_ms', 'Reverse Bias (ms):'))):
        ttk.Label(paramGroup, text=label).grid(row=row, column=0, sticky='w', padx=4, pady=1)
        ttk.Entry(paramGroup, textvariable=dltsc.quickData_paramVars[key], width=10).grid(
            row=row, column=1, sticky='ew', padx=4, pady=1)
    paramGroup.grid_columnconfigure(1, weight=1)

    # --- Execution Action ---
    execGroup = tk.LabelFrame(panel, text='Execution Action')
    execGroup.pack(fill='x')
    dltsc.quickData_extractButton = tk.Button(execGroup, text='Extract & Average Transients',
                                              font=('Segoe UI', 9, 'bold'), bg='#e8f5e9',
                                              command=_extract_quick_transients)
    dltsc.quickData_extractButton.pack(fill='x', padx=4, pady=(4, 2))
    dltsc.quickData_statusLabel = ttk.Label(execGroup, text='Status: Idle', wraplength=220, justify='left')
    dltsc.quickData_statusLabel.pack(fill='x', padx=4, pady=(0, 4))


#---------------------TAB CONSTRUCTION-------------------------#
def construct_dataAnalysisTab():
    tabControl = dltsc.tabControl

    tabControl.add(dltsc.dataAnalysisTab, text='Quick Analysis')
    tabControl.pack(expand=1, fill="both")

    dltsc.dataAnalysisTab.grid_rowconfigure(0, weight=1)
    dltsc.dataAnalysisTab.grid_columnconfigure(0, weight=0)
    dltsc.dataAnalysisTab.grid_columnconfigure(1, weight=1)

    # Offline Data column (saved-folder loader) on the left, fixed width.
    offlineFrame = tk.Frame(dltsc.dataAnalysisTab, highlightbackground="gray",
                            highlightthickness=1, highlightcolor='gray')
    offlineFrame.grid(row=0, column=0, padx=(10, 0), pady=10, sticky='ns')
    _build_offlineDataFrame(offlineFrame)

    # Rate Window Analysis (left), Peak Deconvolution (middle) and Arrhenius
    # Defect Mapping (right), side by side in a resizable pane -- in the order
    # the analysis flows: spectra -> peaks -> trap signatures.
    analysisPanes = tk.PanedWindow(dltsc.dataAnalysisTab, orient=tk.HORIZONTAL, sashrelief='raised', sashwidth=6)
    analysisPanes.grid(row=0, column=1, padx=10, pady=10, sticky='nsew')

    rateWindowFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                               highlightthickness=1, highlightcolor='gray')
    deconvolutionFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                                  highlightthickness=1, highlightcolor='gray')
    arrheniusFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray')
    analysisPanes.add(rateWindowFrame, width=480, stretch='always')
    analysisPanes.add(deconvolutionFrame, width=480, stretch='always')
    analysisPanes.add(arrheniusFrame, width=480, stretch='always')

    _build_rateWindowFrame(rateWindowFrame)
    _build_arrheniusFrame(arrheniusFrame)
    # Last: its first redraw also redraws the other two frames' plots.
    _build_deconvolutionFrame(deconvolutionFrame)

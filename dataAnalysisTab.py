import tkinter as tk

from tkinter import ttk

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import dltsConfig as dltsc
import impedanceAnalysis_Tools as iaT
import detailedAnalysisTab as dA   # shares its raw-transient noise estimate and Arrhenius line fit

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
# works with no configuration as long as ANY of the three has been populated.
DATA_SOURCE_AUTO = 'Auto (first available)'
DATA_SOURCE_QUALITATIVE = 'Qualitative Analysis'
DATA_SOURCE_LIVE = 'Automated/Live Data — Live'
DATA_SOURCE_OFFLINE = 'Automated/Live Data — Offline'
DATA_SOURCE_OPTIONS = [DATA_SOURCE_AUTO, DATA_SOURCE_QUALITATIVE, DATA_SOURCE_LIVE, DATA_SOURCE_OFFLINE]

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
# Smoothed C is unaffected: it still always requires Live/Offline, since
# cubic-spline interpolation needs impdData's raw per-repeat samples.
SIGNAL_METHOD_MEASURED = 'Measured C (nearest sample)'
SIGNAL_METHOD_SMOOTHED = 'Smoothed C (impdData, spline-interpolated)'
SIGNAL_METHOD_OPTIONS = [SIGNAL_METHOD_MEASURED, SIGNAL_METHOD_SMOOTHED]

# Denoise choice for the Measured C / Smoothed C signal methods, applied only
# when Measured C is backed by a live impdData instance (Live/Offline) --
# Qualitative Analysis-backed Measured C has no per-repeat data to denoise.
# 'None (raw)' uses calculate_delC_normalized()'s raw (yRaw) emission; any
# other choice uses its denoised (yFiltered) emission via that method.
DENOISE_NONE = 'None (raw)'
DENOISE_OPTIONS = [DENOISE_NONE, 'pca', 'wavelet', 'sgolay', 'lowess']


def _resolve_impd_for_source(source):
    """Resolve a Data Source selection to a live impdData instance, for the
    Measured C / Smoothed C signal methods. Returns (impd, resolvedLabel), or
    (None, None) if that source has no impdData instance behind it (always
    true for Qualitative Analysis).
    """
    if source == DATA_SOURCE_LIVE:
        return (dltsc.livePlot_liveImpdData, DATA_SOURCE_LIVE) if dltsc.livePlot_liveImpdData is not None else (None, None)
    if source == DATA_SOURCE_OFFLINE:
        return (dltsc.livePlot_offlineImpdData, DATA_SOURCE_OFFLINE) if dltsc.livePlot_offlineImpdData is not None else (None, None)
    if source == DATA_SOURCE_QUALITATIVE:
        return None, None
    # Auto: Live then Offline -- Qualitative Analysis never has an instance.
    if dltsc.livePlot_liveImpdData is not None:
        return dltsc.livePlot_liveImpdData, DATA_SOURCE_LIVE
    if dltsc.livePlot_offlineImpdData is not None:
        return dltsc.livePlot_offlineImpdData, DATA_SOURCE_OFFLINE
    return None, None


# Peak-finding method for each rate-window's DLTS-signal-vs-temperature curve.
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
    if source == DATA_SOURCE_QUALITATIVE:
        data = dltsc.manual_processedTransients or {}
        if not data:
            return None, None, "Qualitative Analysis has no extracted transients yet."
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

    # Auto: Qualitative Analysis first (the original, unconfigured behavior),
    # then whichever of Live/Offline currently has data.
    if dltsc.manual_processedTransients:
        return dltsc.manual_processedTransients, DATA_SOURCE_QUALITATIVE, None
    liveData = _processed_transients_from_automated('live')
    if liveData:
        return liveData, DATA_SOURCE_LIVE, None
    offlineData = _processed_transients_from_automated('offline')
    if offlineData:
        return offlineData, DATA_SOURCE_OFFLINE, None
    return None, None, (
        "No data available yet from Qualitative Analysis or Automated/Live Data (Live/Offline). "
        "Extract transients, run DLTS, or load an offline run first.")

#---------------------SHARED WITH DETAILED ANALYSIS-------------------------#
# The signal read-off, C_infinity, peak finding (with its edge-peak guard and
# small-peak skip), Arrhenius fit (with its exclusion rule) and Nt below all go
# through detailedAnalysisTab's own functions, so the two tabs give the same
# Et, sigma and Nt for the same transients, windows, search range and peak method.
def _rb_ms_for_source(label, processedTransients):
    """Reverse-bias duration (ms) C_infinity and Nt are referenced to: Qualitative
    Analysis' own 'Reverse Bias (ms)' field for that source, else (or if it is not
    a positive number) the longest transient's span."""
    if label == DATA_SOURCE_QUALITATIVE and 'rb_ms' in (dltsc.manual_paramVars or {}):
        try:
            rb = float(dltsc.manual_paramVars['rb_ms'].get())
            if rb > 0:
                return rb
        except (ValueError, AttributeError):
            pass
    return max(float(np.asarray(rec['time_ms'])[-1]) for rec in processedTransients.values())

def _transient_records(processedTransients, rb_ms):
    """Averaged transients {T_C: {'time_ms', 'avg_cap_pf', ...}} as Detailed
    Analysis' prepared records (Measured C, no denoise), with C_infinity
    recomputed by its convention (dA._cinf_range_mean). Returns (records, temps)."""
    temps = sorted(processedTransients)
    data = {}
    for tc in temps:
        t_ms = np.asarray(processedTransients[tc]['time_ms'], dtype=np.float64)
        cap = np.asarray(processedTransients[tc]['avg_cap_pf'], dtype=np.float64)
        data[tc] = (t_ms, cap, dA._cinf_range_mean(t_ms, cap, rb_ms))
    return dA._prepare_signal_data(data, temps, dA.SIGNAL_METHOD_MEASURED, dA.DENOISE_NONE), temps

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
    out = []
    for t1, t2 in windows:
        S, S_err = dA._rate_window_signal(temps, records, t1, t2)
        pk = dA._peak_from_signal(T_K, S, S_err, tpLo, tpHi, method)
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
        if source in (DATA_SOURCE_QUALITATIVE, DATA_SOURCE_LIVE, DATA_SOURCE_OFFLINE):
            resolvedLabel = source
        else:
            # Auto: Qualitative Analysis first (matches
            # _get_processed_transients_for_source()'s own Auto priority),
            # then whichever of Live/Offline has something to offer.
            if dltsc.manual_processedTransients:
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
        impd, resolvedLabel = _resolve_impd_for_source(source)
        if impd is None:
            errorReason = ("Smoothed C needs Automated/Live Data (Live or Offline) as the "
                           "Data Source -- it reads per-repeat instrument data that Qualitative Analysis, "
                           "which only stores an already-averaged transient, doesn't have.")
            dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
            if dltsc.rateWindow_statusLabel is not None:
                dltsc.rateWindow_statusLabel.config(text=errorReason)
            return
        busy = (dltsc.livePlot_liveIngestBusy if resolvedLabel == DATA_SOURCE_LIVE
               else dltsc.livePlot_offlineIngestBusy)
        if busy:
            errorReason = f"{resolvedLabel} is still loading/ingesting; try again once it finishes."
            dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
            if dltsc.rateWindow_statusLabel is not None:
                dltsc.rateWindow_statusLabel.config(text=errorReason)
            return
        nTemps = len(impd.dataTemps or [])

    denoiseChoice = dltsc.rateWindow_denoiseVar.get() if dltsc.rateWindow_denoiseVar is not None else DENOISE_NONE
    peakMethod = dltsc.rateWindow_peakMethodVar.get() if dltsc.rateWindow_peakMethodVar is not None else PEAK_METHOD_SPLINE

    # Peak-search temperature range (K). Features outside it (other traps,
    # the sweep's edges) otherwise pull the spline/curve fit away from the
    # peak of interest. Blank = unbounded on that side.
    try:
        tpLoText = dltsc.rateWindow_tpLoVar.get().strip() if dltsc.rateWindow_tpLoVar is not None else ''
        tpHiText = dltsc.rateWindow_tpHiVar.get().strip() if dltsc.rateWindow_tpHiVar is not None else ''
        tpLo = float(tpLoText) if tpLoText else -np.inf
        tpHi = float(tpHiText) if tpHiText else np.inf
    except ValueError:
        dltsc.log_to_textbox("Rate window analysis: Tp search range bounds must be numeric (or blank).")
        return
    if tpHi <= tpLo:
        dltsc.log_to_textbox("Rate window analysis: Tp search range upper bound must exceed the lower bound.")
        return

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

    dltsc.rateWindow_ax.clear()
    dltsc.rateWindow_signals = dict()
    dltsc.rateWindow_extractedPeaks = dict()
    for row in dltsc.rateWindow_peakTable.get_children():
        dltsc.rateWindow_peakTable.delete(row)

    useRecords = signalMethod == SIGNAL_METHOD_MEASURED and impd is None
    if useRecords:
        # Qualitative Analysis (or a Live/Offline averaged snapshot with no
        # impdData instance): the averaged transients go through Detailed
        # Analysis' own pipeline -- nearest measured sample at t1/t2, C_infinity
        # as the mean over 40-90 % of the reverse bias, and per-point errors
        # from the transient's own sample noise (dA._rate_window_signal) -- so
        # this tab and Detailed Analysis give the same S(T) for the same data.
        rbMs = _rb_ms_for_source(resolvedLabel, processedTransients)
        records, recTemps = _transient_records(processedTransients, rbMs)
        dltsc.rateWindow_transients = (records, recTemps, rbMs)
        windowResults = _window_peaks(records, recTemps, windows, tpLo, tpHi, peakMethod)
    else:
        # Nt still uses the averaged snapshot (Detailed Analysis' definition)
        # when this source has one.
        mode = 'live' if resolvedLabel == DATA_SOURCE_LIVE else 'offline'
        snapshot = _processed_transients_from_automated(mode)
        if snapshot:
            rbMs = _rb_ms_for_source(resolvedLabel, snapshot)
            dltsc.rateWindow_transients = (*_transient_records(snapshot, rbMs), rbMs)
        else:
            dltsc.rateWindow_transients = None
        windowResults = [None] * len(windows)

    for i, (t1, t2) in enumerate(windows):
        if useRecords:
            res = windowResults[i]
            x, y, yErr = res['T_k'], res['Signal'], res['Signal_err']
        else:
            # Measured C backed by a live impdData instance (Live/Offline), or
            # Smoothed C (always Live/Offline). emissionIndex=-1: the ensemble
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

        # Peak finding only sees the points inside the Tp search range; the
        # full curve is still stored and plotted. dA._peak_from_signal flips a
        # negative peak, skips a window whose peak is below 5 % of max|S|, and
        # drops the Tp error of a peak on the edge of the range (such a window
        # is then left out of the weighted Arrhenius fit, as in Detailed Analysis).
        if ((x >= tpLo) & (x <= tpHi)).sum() < 4:
            dltsc.log_to_textbox(
                f"Rate window analysis: Window Set {i + 1}: fewer than 4 temperatures inside the "
                f"Tp search range; the peak is the raw maximum. Widen the range.")
        pk = windowResults[i] if useRecords else dA._peak_from_signal(x, y, yErr, tpLo, tpHi,
                                                                     _peak_method_for(peakMethod))
        eN = dA._emission_rate(t1, t2)
        yErrPlot = dA._valid_errors(yErr)
        dltsc.rateWindow_signals[i] = {'T_k': x, 'Signal': y, 'Signal_err': yErrPlot}

        if yErrPlot is not None:
            dltsc.rateWindow_ax.errorbar(x, y, yerr=yErrPlot, fmt='o', capsize=3, label=f'RW {i + 1}')
        else:
            dltsc.rateWindow_ax.plot(x, y, 'o', label=f'RW {i + 1}')

        if pk['skipped']:
            dltsc.rateWindow_peakTable.insert('', 'end', iid=f'w{i}', values=(
                f'Set {i + 1}', f'{eN:.2f}', '—', '—', 'skipped (no peak)'))
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1}: no peak in the search range "
                                 f"(below {dA.PEAK_MIN_FRAC:.0%} of max|S|); skipped.")
            continue

        tPeak, tPeakErr, sPeak = pk['Tp'], pk['Tp_err'], pk['S_peak']
        if pk['xFit'] is not None:
            dltsc.rateWindow_ax.plot(pk['xFit'], pk['yFit'], '--', alpha=0.5, label=f'Fit {i + 1}')
        dltsc.rateWindow_extractedPeaks[i] = {
            'T_peak': tPeak, 'S_peak': sPeak, 'e_n': eN, 'T_peak_err': tPeakErr, 't1': t1, 't2': t2,
        }

        tPeakText = f'{tPeak:.2f}' + (f' ± {tPeakErr:.2f}' if tPeakErr is not None else '')
        dltsc.rateWindow_peakTable.insert('', 'end', iid=f'w{i}', values=(
            f'Set {i + 1}', f'{eN:.2f}', tPeakText, f'{sPeak:.5f}',
            '—' if tPeakErr is not None else 'no Tp error (edge)'))

        if tPeakErr is not None:
            dltsc.rateWindow_ax.errorbar(tPeak, sPeak, xerr=tPeakErr, fmt='kx', markersize=10, capsize=4)
        else:
            dltsc.rateWindow_ax.plot(tPeak, sPeak, 'x', color='gray', markersize=10)

    for bound in (tpLo, tpHi):
        if np.isfinite(bound):
            dltsc.rateWindow_ax.axvline(bound, color='gray', linestyle=':', linewidth=1.0)
    dltsc.rateWindow_ax.set_xlabel('Temperature (K)')
    dltsc.rateWindow_ax.set_ylabel('DLTS Signal (ΔC / C∞)')
    dltsc.rateWindow_ax.set_title(f'Multi-Window DLTS Signal Spectrum ({peakMethod})')
    dltsc.rateWindow_ax.grid(True, linestyle=':')
    handles, labels = dltsc.rateWindow_ax.get_legend_handles_labels()
    if labels:
        dltsc.rateWindow_ax.legend()
    dltsc.rateWindow_figure.tight_layout(pad=2.0)
    dltsc.rateWindow_canvas.draw()

    statusText = f"Using: {resolvedLabel} / {signalMethod} ({nTemps} temperature(s))."
    if dltsc.rateWindow_statusLabel is not None:
        dltsc.rateWindow_statusLabel.config(text=statusText)
    dltsc.log_to_textbox(
        f"Rate window analysis: computed {len(dltsc.rateWindow_extractedPeaks)} window set(s) "
        f"from {resolvedLabel} using {signalMethod} ({nTemps} temperature(s)).")

def _build_rateWindowFrame(parent):
    # dltsConfig.init() (which would normally seed these as dicts) is not called by
    # DLTSGUI_MainWindow.py, so seed them here to be safe regardless of that wiring.
    if dltsc.rateWindow_signals is None:
        dltsc.rateWindow_signals = dict()
    if dltsc.rateWindow_extractedPeaks is None:
        dltsc.rateWindow_extractedPeaks = dict()

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

    # Data Source / DLTS Signal Calculation / Peak-Finding Method side by side --
    # the full pane width now easily fits all three across in one row.
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
    ttk.Label(sigGroup, text='Denoise (Live/Offline-backed Measured C, or Smoothed C, only):').pack(
        anchor='w', padx=4, pady=(0, 0))
    dltsc.rateWindow_denoiseVar = tk.StringVar(value=DENOISE_NONE)
    ttk.Combobox(sigGroup, textvariable=dltsc.rateWindow_denoiseVar, values=DENOISE_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=(0, 4))

    # --- Peak-Finding Method ---
    methodGroup = tk.LabelFrame(topRow, text='Peak-Finding Method')
    methodGroup.pack(side='left', fill='both', expand=True, padx=(2, 0))
    dltsc.rateWindow_peakMethodVar = tk.StringVar(value=PEAK_METHOD_SPLINE)
    ttk.Combobox(methodGroup, textvariable=dltsc.rateWindow_peakMethodVar, values=PEAK_METHOD_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=4)
    ttk.Label(methodGroup, text='Tp search range (K, blank = no bound):').pack(anchor='w', padx=4, pady=(0, 0))
    rangeFrame = tk.Frame(methodGroup)
    rangeFrame.pack(fill='x', padx=4, pady=(0, 4))
    dltsc.rateWindow_tpLoVar = tk.StringVar(value=DEFAULT_TPEAK_LO)
    dltsc.rateWindow_tpHiVar = tk.StringVar(value=DEFAULT_TPEAK_HI)
    ttk.Entry(rangeFrame, textvariable=dltsc.rateWindow_tpLoVar, width=8).pack(side='left')
    ttk.Label(rangeFrame, text=' to ').pack(side='left')
    ttk.Entry(rangeFrame, textvariable=dltsc.rateWindow_tpHiVar, width=8).pack(side='left')

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
    columns = ('window', 'en', 'tpeak', 'speak', 'fit')
    dltsc.rateWindow_peakTable = ttk.Treeview(tableGroup, columns=columns, show='headings', height=4)
    dltsc.rateWindow_peakTable.heading('window', text='Window')
    dltsc.rateWindow_peakTable.heading('en', text='Emission e_n (s⁻¹)')
    dltsc.rateWindow_peakTable.heading('tpeak', text='T_peak (K)')
    dltsc.rateWindow_peakTable.heading('speak', text='Max Extrema ΔC/C∞')
    # Filled in by the Arrhenius solver: used / excluded (see dA._arrhenius_fit).
    dltsc.rateWindow_peakTable.heading('fit', text='Arrhenius fit')
    for col, width in zip(columns, (55, 110, 90, 110, 110)):
        dltsc.rateWindow_peakTable.column(col, width=width, anchor='center')
    dltsc.rateWindow_peakTable.pack(fill='both', expand=True, padx=4, pady=4)


#---------------------ARRHENIUS DEFECT MAPPING (BOTTOM FRAME)-------------------------#
# Ported from DrKayisScript.py's "3. Arrhenius Defect Mapping" tab (PyQt6) into tkinter.
# Consumes dltsc.rateWindow_extractedPeaks, populated by _calculate_rate_windows() above.
def _run_arrhenius_solver():
    if len(dltsc.rateWindow_extractedPeaks or {}) < 2:
        dltsc.log_to_textbox(
            "Arrhenius solver: need at least 2 complete rate window sets from Rate Window Analysis first.")
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

    # The fit itself is Detailed Analysis' dA._arrhenius_fit: an effective-
    # variance lmfit line weighted by each window's T_peak error (x and y both
    # derive from T_peak, so a T_peak error moves a point along a line). Windows
    # with no T_peak error -- a peak on the edge of the search range -- are left
    # out of it, unless fewer than 3 windows have errors, in which case every
    # window is fitted unweighted.
    peakKeys = sorted(dltsc.rateWindow_extractedPeaks.keys())
    peaks = [dltsc.rateWindow_extractedPeaks[i] for i in peakKeys]
    try:
        res = _quick_arrhenius(peaks, gamma, nBackgroundDoping, dltsc.rateWindow_transients)
    except Exception as exc:
        dltsc.log_to_textbox(f"Arrhenius solver: linear fit failed: {exc}")
        return
    if res is None:
        dltsc.log_to_textbox("Arrhenius solver: fewer than 2 windows can be fitted.")
        return

    slope, intercept = res['slope'], res['intercept']
    fitMask = res['fit_mask']
    energyText = dA._fmt_pm(res['Et'], res['Et_se'], '.3f') + " eV"
    captureText = dA._fmt_pm(res['sigma'], res['sigma_se'], '.2e') + " cm²"
    densityText = f"{res['Nt']:.2e} cm⁻³"
    dltsc.arrhenius_energyLabel.config(text=energyText)
    dltsc.arrhenius_captureLabel.config(text=captureText)
    dltsc.arrhenius_densityLabel.config(text=densityText)

    for i, used in zip(peakKeys, fitMask):
        if dltsc.rateWindow_peakTable is not None and dltsc.rateWindow_peakTable.exists(f'w{i}'):
            dltsc.rateWindow_peakTable.set(f'w{i}', 'fit', 'used' if used else 'excluded (edge peak)')

    # T_peak error on this plot's axes: x = 1000/T so dx = 1000*dT/T^2;
    # y = ln(e_n/T^2) = ln(e_n) - 2*ln(T) so dy = 2*dT/T.
    xInvT, yLnEnT2 = res['x'], res['y']
    tPeaks, tPeakErrs = res['Tp_arr'], res['Tp_err_arr']
    haveErr = np.isfinite(tPeakErrs)

    dltsc.arrhenius_ax.clear()
    for sel, label in ((fitMask & haveErr, 'Experimental Extrema Points'),
                       (fitMask & ~haveErr, 'Experimental Extrema Points (no T_peak error)')):
        if not sel.any():
            continue
        if haveErr[sel].all():
            dltsc.arrhenius_ax.errorbar(xInvT[sel], yLnEnT2[sel],
                                        xerr=1000.0 * tPeakErrs[sel] / tPeaks[sel] ** 2,
                                        yerr=2.0 * tPeakErrs[sel] / tPeaks[sel],
                                        fmt='rs', markersize=8, capsize=4, label=label)
        else:
            dltsc.arrhenius_ax.plot(xInvT[sel], yLnEnT2[sel], 'rs', markersize=8, label=label)
    if (~fitMask).any():
        dltsc.arrhenius_ax.plot(xInvT[~fitMask], yLnEnT2[~fitMask], 'x', color='gray', markersize=9,
                                label='Excluded (peak on search-range edge)')
    xFitLine = np.linspace(min(xInvT) * 0.95, max(xInvT) * 1.05, 50)
    dltsc.arrhenius_ax.plot(xFitLine, slope * xFitLine + intercept, 'b-', label='Linear Fit Reference')
    dltsc.arrhenius_ax.set_xlabel('Reciprocal Temperature (1000 / T) (K⁻¹)')
    dltsc.arrhenius_ax.set_ylabel('ln(e_n / T²)')
    dltsc.arrhenius_ax.set_title('Arrhenius Plot Representation for Trap Signature Extraction')
    dltsc.arrhenius_ax.grid(True, linestyle=':')
    handles, labels = dltsc.arrhenius_ax.get_legend_handles_labels()
    if labels:
        dltsc.arrhenius_ax.legend()
    dltsc.arrhenius_figure.tight_layout(pad=2.0)
    dltsc.arrhenius_canvas.draw()

    excludedText = f", {res['N_excluded']} excluded" if res['N_excluded'] else ''
    dltsc.log_to_textbox(
        f"Arrhenius solver ({'T_peak-error weighted' if res['weighted'] else 'unweighted'}, "
        f"{res['N']} windows{excludedText}): "
        f"Et={energyText}, sigma={captureText} (γ={gamma:.3g}), Nt={densityText}.")

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

    # Material Parameters / Execution Action / Output side by side -- the full
    # pane width now easily fits all three across in one row.
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
    execGroup.pack(side='left', fill='both', expand=True, padx=2)
    solveBtn = tk.Button(execGroup, text='Execute Arrhenius Signature Solver', font=('Segoe UI', 9, 'bold'),
                         bg='#ffe082', wraplength=160, command=_run_arrhenius_solver)
    solveBtn.pack(fill='both', expand=True, padx=4, pady=4)

    # --- Extracted Microscopic Trap Signatures ---
    # Description above its value (not side by side) -- this group's value
    # text ("0.288 ± 0.010 eV") needs the full group width to avoid clipping,
    # which a narrow second grid column (squeezed by the 3-groups-across
    # layout) can't reliably give it.
    outGroup = tk.LabelFrame(topRow, text='Extracted Microscopic Trap Signatures')
    outGroup.pack(side='left', fill='both', expand=True, padx=(2, 0))
    ttk.Label(outGroup, text='Defect Activation Energy Et (eV):').pack(anchor='w', padx=4, pady=(4, 0))
    dltsc.arrhenius_energyLabel = ttk.Label(outGroup, text='Waiting...', font=('Segoe UI', 9, 'bold'))
    dltsc.arrhenius_energyLabel.pack(anchor='w', padx=4, pady=(0, 4))
    ttk.Label(outGroup, text='Apparent Capture Cross-Sec σ (cm²):').pack(anchor='w', padx=4, pady=(0, 0))
    dltsc.arrhenius_captureLabel = ttk.Label(outGroup, text='Waiting...', font=('Segoe UI', 9, 'bold'))
    dltsc.arrhenius_captureLabel.pack(anchor='w', padx=4, pady=(0, 4))
    ttk.Label(outGroup, text='Calculated Trap Density Nt (cm⁻³):').pack(anchor='w', padx=4, pady=(0, 0))
    dltsc.arrhenius_densityLabel = ttk.Label(outGroup, text='Waiting...', font=('Segoe UI', 9, 'bold'))
    dltsc.arrhenius_densityLabel.pack(anchor='w', padx=4, pady=(0, 4))


#---------------------TAB CONSTRUCTION-------------------------#
def construct_dataAnalysisTab():
    tabControl = dltsc.tabControl

    tabControl.add(dltsc.dataAnalysisTab, text='Quick Analysis')
    tabControl.pack(expand=1, fill="both")

    dltsc.dataAnalysisTab.grid_rowconfigure(0, weight=1)
    dltsc.dataAnalysisTab.grid_columnconfigure(0, weight=1)

    # Rate Window Analysis (left) and Arrhenius Defect Mapping (right), side by
    # side in a resizable pane.
    analysisPanes = tk.PanedWindow(dltsc.dataAnalysisTab, orient=tk.HORIZONTAL, sashrelief='raised', sashwidth=6)
    analysisPanes.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')

    rateWindowFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                               highlightthickness=1, highlightcolor='gray')
    arrheniusFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray')
    analysisPanes.add(rateWindowFrame, width=700, stretch='always')
    analysisPanes.add(arrheniusFrame, width=700, stretch='always')

    _build_rateWindowFrame(rateWindowFrame)
    _build_arrheniusFrame(arrheniusFrame)

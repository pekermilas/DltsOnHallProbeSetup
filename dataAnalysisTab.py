import tkinter as tk

from tkinter import ttk

import numpy as np
from lmfit.models import LinearModel
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import dltsConfig as dltsc
import impedanceAnalysis_Tools as iaT

# Physical constants for defect property conversions, ported from DrKayisScript.py.
K_BOLTZMANN = 8.617333262145e-5   # eV / K
C_CONSTANT_SI = 3.256e21          # Pre-factor mapping T^2 emission tracking for Si

DEFAULT_RATE_WINDOWS = [
    ('10.0', '50.0'),
    ('20.0', '100.0'),
    ('50.0', '250.0'),
    ('100.0', '490.0'),
]

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
# DrKayisScript.py Method matches this app's existing inline calculation
# (nearest measured sample on the ensemble-averaged transient from whichever
# Data Source is selected above); Measured C / Smoothed C instead delegate to
# impedanceAnalysis_Tools.impdData.calculate_delC_normalized() -- which needs
# a real impdData instance (clustering, per-repeat data), so those two are
# only available when Data Source resolves to Automated/Live Data (Live or
# Offline), not Qualitative Analysis (which only stores an already-averaged
# transient with no instance behind it).
SIGNAL_METHOD_DRKAYIS = 'DrKayisScript.py Method (nearest sample, ensemble avg)'
SIGNAL_METHOD_MEASURED = 'Measured C (impdData, nearest sample)'
SIGNAL_METHOD_SMOOTHED = 'Smoothed C (impdData, spline-interpolated)'
SIGNAL_METHOD_OPTIONS = [SIGNAL_METHOD_DRKAYIS, SIGNAL_METHOD_MEASURED, SIGNAL_METHOD_SMOOTHED]

# Denoise choice for the Measured C / Smoothed C signal methods (ignored by
# DrKayisScript.py Method, which has no per-repeat data to denoise). 'None
# (raw)' uses calculate_delC_normalized()'s raw (yRaw) emission; any other
# choice uses its denoised (yFiltered) emission via that method.
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

        tempC = tempK - 273.15
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

def _calculate_rate_windows():
    signalMethod = (dltsc.rateWindow_signalMethodVar.get() if dltsc.rateWindow_signalMethodVar is not None
                    else SIGNAL_METHOD_DRKAYIS)
    source = dltsc.rateWindow_dataSourceVar.get() if dltsc.rateWindow_dataSourceVar is not None else DATA_SOURCE_AUTO

    processedTransients = None
    impd = None
    temperaturesC = None
    nTemps = 0

    if signalMethod == SIGNAL_METHOD_DRKAYIS:
        processedTransients, resolvedLabel, errorReason = _get_processed_transients_for_source(source)
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
            errorReason = ("Measured C / Smoothed C need Automated/Live Data (Live or Offline) as the "
                           "Data Source -- they read per-repeat instrument data that Qualitative Analysis, "
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

    dltsc.rateWindow_ax.clear()
    dltsc.rateWindow_signals = dict()
    dltsc.rateWindow_extractedPeaks = dict()
    for row in dltsc.rateWindow_peakTable.get_children():
        dltsc.rateWindow_peakTable.delete(row)

    for i, (t1Var, t2Var) in enumerate(dltsc.rateWindow_windowVars):
        try:
            t1 = float(t1Var.get())
            t2 = float(t2Var.get())
        except ValueError:
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1} has a non-numeric t1/t2.")
            return

        if t2 <= t1:
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1}: t2 must be larger than t1.")
            return

        eN = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
        yErr = None

        if signalMethod == SIGNAL_METHOD_DRKAYIS:
            dltsProfile = []
            validTempsK = []
            for tC in temperaturesC:
                data = processedTransients[tC]
                tAxis = data['time_ms']
                cAxis = data['avg_cap_pf']
                cInf = data['C_infinity']

                idx1 = np.argmin(np.abs(tAxis - t1))
                idx2 = np.argmin(np.abs(tAxis - t2))

                signal = (cAxis[idx2] - cAxis[idx1]) / cInf
                dltsProfile.append(signal)
                validTempsK.append(tC + 273.15)

            y = np.array(dltsProfile, dtype=np.float64)
            x = np.array(validTempsK, dtype=np.float64)
        else:
            # emissionIndex=-1: the ensemble average across every reverse-bias
            # repeat, the same averaging DrKayisScript.py Method (and Extract
            # & Average Transients) performs -- and the only index with a
            # meaningful cross-repeat yerr to propagate (see
            # calculate_delC_normalized()'s docstring).
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
            if not (np.all(np.isfinite(yErr)) and np.all(yErr > 0)):
                yErr = None

            # Store the denoised (and raw) emission snapshot this call used,
            # so it's inspectable/reusable rather than only living transiently
            # inside impd.dataEmissions.
            dltsc.rateWindow_denoisedEmissions = {T: dict(rec) for T, rec in impd.dataEmissions.items()}

        maxIdx = int(np.argmax(np.abs(y)))

        try:
            curveType = PEAK_METHOD_CURVETYPE.get(peakMethod)
            if curveType is not None:
                result = iaT.impdData._curveFit_peakFinder(x, y, curveType=curveType, signalYErr=yErr)
            else:
                result = iaT.impdData._smoothingSpline_peakFinder(x, y, signalYErr=yErr)
            if result == -1:
                raise ValueError("peak finder reported no data")
            tPeak, sPeak, xFit, yFit, tPeakErr, sPeakErr = result
            dltsc.rateWindow_ax.plot(xFit, yFit, '--', alpha=0.5, label=f'Fit {i + 1}')
        except Exception as exc:
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1} fit failed ({exc}); using raw extremum.")
            tPeak, sPeak = x[maxIdx], y[maxIdx]
            tPeakErr = sPeakErr = None

        dltsc.rateWindow_signals[i] = {'T_k': x, 'Signal': y, 'Signal_err': yErr}
        dltsc.rateWindow_extractedPeaks[i] = {
            'T_peak': tPeak, 'S_peak': sPeak, 'e_n': eN,
            'T_peak_err': tPeakErr, 'S_peak_err': sPeakErr,
        }

        tPeakText = f'{tPeak:.2f}' + (f' ± {tPeakErr:.2f}' if tPeakErr is not None else '')
        sPeakText = f'{sPeak:.5f}' + (f' ± {sPeakErr:.5f}' if sPeakErr is not None else '')
        dltsc.rateWindow_peakTable.insert('', 'end', values=(
            f'Set {i + 1}', f'{eN:.2f}', tPeakText, sPeakText))

        if yErr is not None:
            dltsc.rateWindow_ax.errorbar(x, y, yerr=yErr, fmt='o', capsize=3, label=f'RW {i + 1}')
        else:
            dltsc.rateWindow_ax.plot(x, y, 'o', label=f'RW {i + 1}')
        if tPeakErr is not None or sPeakErr is not None:
            dltsc.rateWindow_ax.errorbar(tPeak, sPeak, xerr=tPeakErr, yerr=sPeakErr,
                                         fmt='kx', markersize=10, capsize=4)
        else:
            dltsc.rateWindow_ax.plot(tPeak, sPeak, 'kx', markersize=10)

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

    bottomCanvas = tk.Canvas(bottomContainer, highlightthickness=0)
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
    dltsc.rateWindow_signalMethodVar = tk.StringVar(value=SIGNAL_METHOD_DRKAYIS)
    ttk.Combobox(sigGroup, textvariable=dltsc.rateWindow_signalMethodVar, values=SIGNAL_METHOD_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=(0, 4))
    ttk.Label(sigGroup, text='Denoise (Measured C / Smoothed C only):').pack(anchor='w', padx=4, pady=(0, 0))
    dltsc.rateWindow_denoiseVar = tk.StringVar(value=DENOISE_NONE)
    ttk.Combobox(sigGroup, textvariable=dltsc.rateWindow_denoiseVar, values=DENOISE_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=(0, 4))

    # --- Peak-Finding Method ---
    methodGroup = tk.LabelFrame(topRow, text='Peak-Finding Method')
    methodGroup.pack(side='left', fill='both', expand=True, padx=(2, 0))
    dltsc.rateWindow_peakMethodVar = tk.StringVar(value=PEAK_METHOD_SPLINE)
    ttk.Combobox(methodGroup, textvariable=dltsc.rateWindow_peakMethodVar, values=PEAK_METHOD_OPTIONS,
                state='readonly', width=24).pack(fill='x', padx=4, pady=4)

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
    columns = ('window', 'en', 'tpeak', 'speak')
    dltsc.rateWindow_peakTable = ttk.Treeview(tableGroup, columns=columns, show='headings', height=4)
    dltsc.rateWindow_peakTable.heading('window', text='Window')
    dltsc.rateWindow_peakTable.heading('en', text='Emission e_n (s⁻¹)')
    dltsc.rateWindow_peakTable.heading('tpeak', text='T_peak (K)')
    dltsc.rateWindow_peakTable.heading('speak', text='Max Extrema ΔC/C∞')
    for col, width in zip(columns, (55, 120, 80, 120)):
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

    # Propagate each rate window's T_peak uncertainty -- from lmfit's fitted-
    # parameter covariance for a curve-fit peak method, or from
    # _smoothingSpline_peakFinder()'s bootstrap estimate for the smoothing
    # spline -- into this plot's axes: x = 1000/T so dx = 1000*dT/T^2;
    # y = ln(e_n/T^2) = ln(e_n) - 2*ln(T) so dy = 2*dT/T.
    xInvT, xInvTErr = [], []
    yLnEnT2, yLnEnT2Err = [], []
    signalsMax, signalsMaxErr = [], []
    for i in sorted(dltsc.rateWindow_extractedPeaks.keys()):
        peak = dltsc.rateWindow_extractedPeaks[i]
        tK = peak['T_peak']
        eN = peak['e_n']
        tKErr = peak.get('T_peak_err')

        xInvT.append(1000.0 / tK)
        yLnEnT2.append(np.log(eN / (tK ** 2)))
        xInvTErr.append(1000.0 * tKErr / (tK ** 2) if tKErr is not None else None)
        yLnEnT2Err.append(2.0 * tKErr / tK if tKErr is not None else None)
        signalsMax.append(abs(peak['S_peak']))
        signalsMaxErr.append(peak.get('S_peak_err'))

    xInvT = np.array(xInvT, dtype=np.float64)
    yLnEnT2 = np.array(yLnEnT2, dtype=np.float64)
    haveXErr = all(e is not None for e in xInvTErr)
    haveYErr = all(e is not None for e in yLnEnT2Err)
    xInvTErrArr = np.array(xInvTErr, dtype=np.float64) if haveXErr else None
    yLnEnT2ErrArr = np.array(yLnEnT2Err, dtype=np.float64) if haveYErr else None

    # Deviating from DrKayisScript.py's scipy curve_fit: lmfit's LinearModel is
    # used here (and for the rate-window curve-fit peak method above), which
    # also reports standard errors on slope/intercept from the fit's
    # covariance -- available even when the individual points carry no error
    # of their own (e.g. the smoothing-spline peak method).
    linModel = LinearModel()
    linParams = linModel.guess(yLnEnT2, x=xInvT)
    fitKwargs = {}
    if haveYErr and np.all(yLnEnT2ErrArr > 0) and np.all(np.isfinite(yLnEnT2ErrArr)):
        fitKwargs['weights'] = 1.0 / yLnEnT2ErrArr
    try:
        linResult = linModel.fit(yLnEnT2, linParams, x=xInvT, **fitKwargs)
    except Exception as exc:
        dltsc.log_to_textbox(f"Arrhenius solver: linear fitting matrix criteria failed: {exc}")
        return

    slope, slopeErr = linResult.params['slope'].value, linResult.params['slope'].stderr
    intercept, interceptErr = linResult.params['intercept'].value, linResult.params['intercept'].stderr

    activationEnergyEv = -slope * 1000.0 * K_BOLTZMANN
    activationEnergyErrEv = 1000.0 * K_BOLTZMANN * slopeErr if slopeErr is not None else None

    apparentSigmaCm2 = np.exp(intercept) / C_CONSTANT_SI
    apparentSigmaErrCm2 = apparentSigmaCm2 * interceptErr if interceptErr is not None else None

    maxIdx = int(np.argmax(signalsMax))
    maxSignalAmplitude = signalsMax[maxIdx]
    maxSignalAmplitudeErr = signalsMaxErr[maxIdx]
    trapDensityCm3 = 2.0 * maxSignalAmplitude * nBackgroundDoping
    trapDensityErrCm3 = (2.0 * maxSignalAmplitudeErr * nBackgroundDoping
                         if maxSignalAmplitudeErr is not None else None)

    energyText = f"{activationEnergyEv:.3f}" + (
        f" ± {activationEnergyErrEv:.3f}" if activationEnergyErrEv is not None else "") + " eV"
    captureText = f"{apparentSigmaCm2:.2e}" + (
        f" ± {apparentSigmaErrCm2:.2e}" if apparentSigmaErrCm2 is not None else "") + " cm²"
    densityText = f"{trapDensityCm3:.2e}" + (
        f" ± {trapDensityErrCm3:.2e}" if trapDensityErrCm3 is not None else "") + " cm⁻³"
    dltsc.arrhenius_energyLabel.config(text=energyText)
    dltsc.arrhenius_captureLabel.config(text=captureText)
    dltsc.arrhenius_densityLabel.config(text=densityText)

    dltsc.arrhenius_ax.clear()
    if haveXErr or haveYErr:
        dltsc.arrhenius_ax.errorbar(xInvT, yLnEnT2, xerr=xInvTErrArr, yerr=yLnEnT2ErrArr,
                                    fmt='rs', markersize=8, capsize=4, label='Experimental Extrema Points')
    else:
        dltsc.arrhenius_ax.plot(xInvT, yLnEnT2, 'rs', markersize=8, label='Experimental Extrema Points')
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

    dltsc.log_to_textbox(f"Arrhenius solver: Et={energyText}, sigma={captureText}, Nt={densityText}.")

def _build_arrheniusFrame(parent):
    # Plot on top, parameter/control fields below it -- see _build_rateWindowFrame()
    # for why (the frames now sit side by side rather than top/bottom).
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=3)
    parent.grid_rowconfigure(2, weight=1)
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

    bottomCanvas = tk.Canvas(bottomContainer, highlightthickness=0)
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
    dltsc.arrhenius_ndVar = tk.StringVar(value='1.5e15')
    ttk.Label(matGroup, text='Background Doping Nd (cm⁻³):').grid(
        row=0, column=0, sticky='w', padx=4, pady=2)
    ttk.Entry(matGroup, textvariable=dltsc.arrhenius_ndVar, width=12).grid(
        row=0, column=1, sticky='ew', padx=4, pady=2)
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

    tabControl.add(dltsc.dataAnalysisTab, text='Data Analysis')
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

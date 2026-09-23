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

# Peak-finding method for each rate-window's DLTS-signal-vs-temperature curve.
# Deviating from DrKayisScript.py's own inline scipy pseudo-Voigt curve_fit:
# this reuses impedanceAnalysis_Tools.impdData's shared peak finders instead,
# with the smoothing spline as the (non-parametric, error-free) default and a
# choice of lmfit-based curve-fit shapes -- which also report parameter
# standard errors -- as user-selectable alternatives.
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
    source = dltsc.rateWindow_dataSourceVar.get() if dltsc.rateWindow_dataSourceVar is not None else DATA_SOURCE_AUTO
    processedTransients, resolvedLabel, errorReason = _get_processed_transients_for_source(source)
    if not processedTransients:
        dltsc.log_to_textbox(f"Rate window analysis: {errorReason}")
        if dltsc.rateWindow_statusLabel is not None:
            dltsc.rateWindow_statusLabel.config(text=errorReason)
        return

    dltsc.rateWindow_ax.clear()
    dltsc.rateWindow_signals = dict()
    dltsc.rateWindow_extractedPeaks = dict()
    for row in dltsc.rateWindow_peakTable.get_children():
        dltsc.rateWindow_peakTable.delete(row)

    temperaturesC = sorted(processedTransients.keys())

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

        maxIdx = np.argmax(np.abs(y))
        peakMethod = dltsc.rateWindow_peakMethodVar.get() if dltsc.rateWindow_peakMethodVar is not None else PEAK_METHOD_SPLINE

        try:
            curveType = PEAK_METHOD_CURVETYPE.get(peakMethod)
            if curveType is not None:
                result = iaT.impdData._curveFit_peakFinder(x, y, curveType=curveType)
            else:
                result = iaT.impdData._smoothingSpline_peakFinder(x, y)
            if result == -1:
                raise ValueError("peak finder reported no data")
            tPeak, sPeak, xFit, yFit, tPeakErr, sPeakErr = result
            dltsc.rateWindow_ax.plot(xFit, yFit, '--', alpha=0.5, label=f'Fit {i + 1}')
        except Exception as exc:
            dltsc.log_to_textbox(f"Rate window analysis: Window Set {i + 1} fit failed ({exc}); using raw extremum.")
            tPeak, sPeak = x[maxIdx], y[maxIdx]
            tPeakErr = sPeakErr = None

        dltsc.rateWindow_signals[i] = {'T_k': x, 'Signal': y}
        dltsc.rateWindow_extractedPeaks[i] = {
            'T_peak': tPeak, 'S_peak': sPeak, 'e_n': eN,
            'T_peak_err': tPeakErr, 'S_peak_err': sPeakErr,
        }

        tPeakText = f'{tPeak:.2f}' + (f' ± {tPeakErr:.2f}' if tPeakErr is not None else '')
        sPeakText = f'{sPeak:.5f}' + (f' ± {sPeakErr:.5f}' if sPeakErr is not None else '')
        dltsc.rateWindow_peakTable.insert('', 'end', values=(
            f'Set {i + 1}', f'{eN:.2f}', tPeakText, sPeakText))

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

    statusText = f"Using: {resolvedLabel} ({len(temperaturesC)} temperature(s))."
    if dltsc.rateWindow_statusLabel is not None:
        dltsc.rateWindow_statusLabel.config(text=statusText)
    dltsc.log_to_textbox(
        f"Rate window analysis: computed {len(dltsc.rateWindow_extractedPeaks)} window set(s) "
        f"from {resolvedLabel} ({len(temperaturesC)} temperature(s)).")

def _build_rateWindowFrame(parent):
    # dltsConfig.init() (which would normally seed these as dicts) is not called by
    # DLTSGUI_MainWindow.py, so seed them here to be safe regardless of that wiring.
    if dltsc.rateWindow_signals is None:
        dltsc.rateWindow_signals = dict()
    if dltsc.rateWindow_extractedPeaks is None:
        dltsc.rateWindow_extractedPeaks = dict()

    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=0)
    parent.grid_columnconfigure(1, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Rate Window Analysis', font=('Segoe UI', 10, 'bold')).pack(side='left')

    leftPanel = tk.Frame(parent, width=280)
    leftPanel.grid(row=1, column=0, sticky='ns', padx=4, pady=4)

    rightPanel = tk.Frame(parent)
    rightPanel.grid(row=1, column=1, sticky='nsew', padx=4, pady=4)
    rightPanel.grid_rowconfigure(1, weight=1)
    rightPanel.grid_columnconfigure(0, weight=1)

    # --- Data Source (optional -- 'Auto' resolves to whichever source has data) ---
    srcGroup = tk.LabelFrame(leftPanel, text='Data Source')
    srcGroup.pack(fill='x', pady=(0, 4))
    dltsc.rateWindow_dataSourceVar = tk.StringVar(value=DATA_SOURCE_AUTO)
    ttk.Combobox(srcGroup, textvariable=dltsc.rateWindow_dataSourceVar, values=DATA_SOURCE_OPTIONS,
                state='readonly', width=26).pack(fill='x', padx=4, pady=(4, 2))
    dltsc.rateWindow_statusLabel = ttk.Label(srcGroup, text='No data source resolved yet.',
                                             wraplength=260, justify='left')
    dltsc.rateWindow_statusLabel.pack(fill='x', padx=4, pady=(0, 4))

    # --- Peak-Finding Method ---
    methodGroup = tk.LabelFrame(leftPanel, text='Peak-Finding Method')
    methodGroup.pack(fill='x', pady=(0, 4))
    dltsc.rateWindow_peakMethodVar = tk.StringVar(value=PEAK_METHOD_SPLINE)
    ttk.Combobox(methodGroup, textvariable=dltsc.rateWindow_peakMethodVar, values=PEAK_METHOD_OPTIONS,
                state='readonly', width=26).pack(fill='x', padx=4, pady=4)

    # --- Configure Rate Windows (Double Boxcar) ---
    rwGroup = tk.LabelFrame(leftPanel, text='Configure Rate Windows (Double Boxcar)')
    rwGroup.pack(fill='x', pady=(0, 4))
    dltsc.rateWindow_windowVars = []
    for i, (t1Default, t2Default) in enumerate(DEFAULT_RATE_WINDOWS):
        t1Var = tk.StringVar(value=t1Default)
        t2Var = tk.StringVar(value=t2Default)
        dltsc.rateWindow_windowVars.append((t1Var, t2Var))

        rowFrame = tk.Frame(rwGroup)
        rowFrame.pack(fill='x', padx=4, pady=2)
        ttk.Label(rowFrame, text=f'Set {i + 1}:').pack(side='left')
        ttk.Label(rowFrame, text='t1 (ms):').pack(side='left', padx=(8, 2))
        ttk.Entry(rowFrame, textvariable=t1Var, width=8).pack(side='left')
        ttk.Label(rowFrame, text='t2 (ms):').pack(side='left', padx=(8, 2))
        ttk.Entry(rowFrame, textvariable=t2Var, width=8).pack(side='left')

    # --- Execution Action ---
    calcBtn = tk.Button(leftPanel, text='Compute Boxcar Spectrums', font=('Segoe UI', 9, 'bold'),
                        bg='#bbdefb', command=_calculate_rate_windows)
    calcBtn.pack(fill='x', pady=(0, 4))

    # --- Peak results table ---
    tableGroup = tk.LabelFrame(leftPanel, text='Extracted Peaks')
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

    # --- Plot area (embedded, no popup window) ---
    dltsc.rateWindow_figure = Figure(figsize=(6, 5), dpi=100)
    dltsc.rateWindow_ax = dltsc.rateWindow_figure.add_subplot(1, 1, 1)
    dltsc.rateWindow_ax.set_title('Multi-Window DLTS Signal Spectrum (Pseudo-Voigt Refinement)')
    dltsc.rateWindow_ax.set_xlabel('Temperature (K)')
    dltsc.rateWindow_ax.set_ylabel('DLTS Signal (ΔC / C∞)')
    dltsc.rateWindow_figure.tight_layout(pad=2.0)

    dltsc.rateWindow_canvas = FigureCanvasTkAgg(dltsc.rateWindow_figure, master=rightPanel)
    toolbar = NavigationToolbar2Tk(dltsc.rateWindow_canvas, rightPanel, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.rateWindow_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')
    dltsc.rateWindow_canvas.draw()


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

    # Propagate each rate window's T_peak uncertainty (only available when
    # Rate Window Analysis used the lmfit curve-fit peak method, not the
    # error-free smoothing spline) into this plot's axes: x = 1000/T so
    # dx = 1000*dT/T^2; y = ln(e_n/T^2) = ln(e_n) - 2*ln(T) so dy = 2*dT/T.
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
    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=0)
    parent.grid_columnconfigure(1, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Arrhenius Defect Mapping', font=('Segoe UI', 10, 'bold')).pack(side='left')

    leftPanel = tk.Frame(parent, width=280)
    leftPanel.grid(row=1, column=0, sticky='ns', padx=4, pady=4)

    rightPanel = tk.Frame(parent)
    rightPanel.grid(row=1, column=1, sticky='nsew', padx=4, pady=4)
    rightPanel.grid_rowconfigure(1, weight=1)
    rightPanel.grid_columnconfigure(0, weight=1)

    # --- Material Parameters ---
    matGroup = tk.LabelFrame(leftPanel, text='Material Parameters')
    matGroup.pack(fill='x', pady=(0, 4))
    dltsc.arrhenius_ndVar = tk.StringVar(value='1.5e15')
    ttk.Label(matGroup, text='Background Doping Nd (cm⁻³):').grid(
        row=0, column=0, sticky='w', padx=4, pady=2)
    ttk.Entry(matGroup, textvariable=dltsc.arrhenius_ndVar, width=12).grid(
        row=0, column=1, sticky='ew', padx=4, pady=2)
    matGroup.grid_columnconfigure(1, weight=1)

    # --- Execution Action ---
    solveBtn = tk.Button(leftPanel, text='Execute Arrhenius Signature Solver', font=('Segoe UI', 9, 'bold'),
                         bg='#ffe082', command=_run_arrhenius_solver)
    solveBtn.pack(fill='x', pady=(0, 4))

    # --- Extracted Microscopic Trap Signatures ---
    outGroup = tk.LabelFrame(leftPanel, text='Extracted Microscopic Trap Signatures')
    outGroup.pack(fill='x')
    ttk.Label(outGroup, text='Defect Activation Energy Et (eV):').grid(
        row=0, column=0, sticky='w', padx=4, pady=2)
    dltsc.arrhenius_energyLabel = ttk.Label(outGroup, text='Waiting...')
    dltsc.arrhenius_energyLabel.grid(row=0, column=1, sticky='w', padx=4, pady=2)
    ttk.Label(outGroup, text='Apparent Capture Cross-Sec σ (cm²):').grid(
        row=1, column=0, sticky='w', padx=4, pady=2)
    dltsc.arrhenius_captureLabel = ttk.Label(outGroup, text='Waiting...')
    dltsc.arrhenius_captureLabel.grid(row=1, column=1, sticky='w', padx=4, pady=2)
    ttk.Label(outGroup, text='Calculated Trap Density Nt (cm⁻³):').grid(
        row=2, column=0, sticky='w', padx=4, pady=2)
    dltsc.arrhenius_densityLabel = ttk.Label(outGroup, text='Waiting...')
    dltsc.arrhenius_densityLabel.grid(row=2, column=1, sticky='w', padx=4, pady=2)

    # --- Plot area (embedded, no popup window) ---
    dltsc.arrhenius_figure = Figure(figsize=(6, 5), dpi=100)
    dltsc.arrhenius_ax = dltsc.arrhenius_figure.add_subplot(1, 1, 1)
    dltsc.arrhenius_ax.set_title('Arrhenius Plot Representation for Trap Signature Extraction')
    dltsc.arrhenius_ax.set_xlabel('Reciprocal Temperature (1000 / T) (K⁻¹)')
    dltsc.arrhenius_ax.set_ylabel('ln(e_n / T²)')
    dltsc.arrhenius_figure.tight_layout(pad=2.0)

    dltsc.arrhenius_canvas = FigureCanvasTkAgg(dltsc.arrhenius_figure, master=rightPanel)
    toolbar = NavigationToolbar2Tk(dltsc.arrhenius_canvas, rightPanel, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.arrhenius_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')
    dltsc.arrhenius_canvas.draw()


#---------------------TAB CONSTRUCTION-------------------------#
def construct_dataAnalysisTab():
    tabControl = dltsc.tabControl

    tabControl.add(dltsc.dataAnalysisTab, text='Data Analysis')
    tabControl.pack(expand=1, fill="both")

    dltsc.dataAnalysisTab.grid_rowconfigure(0, weight=1)
    dltsc.dataAnalysisTab.grid_columnconfigure(0, weight=1)

    # Rate Window Analysis (top) and Arrhenius Defect Mapping (bottom), stacked in a
    # resizable pane, matching liveDataTab.construct_livePlotTab()'s auto/manual split.
    analysisPanes = tk.PanedWindow(dltsc.dataAnalysisTab, orient=tk.VERTICAL, sashrelief='raised', sashwidth=6)
    analysisPanes.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')

    rateWindowFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                               highlightthickness=1, highlightcolor='gray')
    arrheniusFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray')
    analysisPanes.add(rateWindowFrame, height=430, stretch='always')
    analysisPanes.add(arrheniusFrame, height=430, stretch='always')

    _build_rateWindowFrame(rateWindowFrame)
    _build_arrheniusFrame(arrheniusFrame)

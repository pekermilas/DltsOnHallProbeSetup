# dataAnalysisTab

## What it's for

`dataAnalysisTab.py` builds the **Quick Analysis** tab. It turns averaged capacitance transients (one per temperature) into double-boxcar DLTS spectra for five rate windows, finds the peak temperature of each spectrum, and fits an Arrhenius line through the peaks. From the fit it reports the defect activation energy, the apparent capture cross-section and the trap density. The code is a tkinter port of tabs 2 and 3 ("Rate Window Analysis" and "Arrhenius Defect Mapping") of `DrKayisScript.py`.

The analysis steps (C∞, S(T), peak finding, the Arrhenius fit and N_T) are the functions of [detailedAnalysisTab](detailedAnalysisTab.md). On averaged transients, Quick Analysis therefore gives the same Et, σ and N_T as the **Standard** result of Detailed Analysis. This needs the same data, the same windows (the defaults are the same), the same search range, the same reverse-bias duration and the smoothing spline. See "Matching Detailed Analysis" below.

## What the user sees

The tab is a horizontal `tk.PanedWindow` with two resizable frames of equal starting width (700 px each). The left frame is **Rate Window Analysis**. The right frame is **Arrhenius Defect Mapping**. Each frame has a plot with a matplotlib navigation toolbar on top and a scrollable control area underneath (requested height `QUICK_CONTROLS_HEIGHT` = 260 px). The mouse wheel scrolls the control area while the pointer is over it.

### Left frame: "Rate Window Analysis"

Plot: title "Multi-Window DLTS Signal Spectrum (Pseudo-Voigt Refinement)" before the first run, "Multi-Window DLTS Signal Spectrum (<peak method>)" after a run. X axis "Temperature (K)", Y axis "DLTS Signal (ΔC / C∞)".

Controls, top row (three groups side by side):

| Group | Widget | Default | What it does |
|---|---|---|---|
| **Data Source** | read-only combobox | `Auto (first available)` | Chooses where the transients come from. Options: `Auto (first available)`, `Qualitative Analysis`, `Automated/Live Data — Live`, `Automated/Live Data — Offline`. See "Data sources" below. |
| **Data Source** | status label | `No data source resolved yet.` | After each **Compute Boxcar Spectrums** click it shows `Using: <source> / <method> (<n> temperature(s)).`, or the reason nothing was computed. |
| **DLTS Signal Calculation** | `Method:` combobox | `Measured C (nearest sample)` | Options: `Measured C (nearest sample)`, `Smoothed C (impdData, spline-interpolated)`. |
| **DLTS Signal Calculation** | `Denoise (Live/Offline-backed Measured C, or Smoothed C, only):` combobox | `None (raw)` | Options: `None (raw)`, `pca`, `wavelet`, `sgolay`, `lowess`. Only used when the signal is computed through an `impdData` instance (Live/Offline). It has no effect for Qualitative Analysis data. |
| **Peak-Finding Method** | combobox | `Smoothing Spline` | Options: `Smoothing Spline`, `Curve Fit (Pseudo-Voigt)`, `Curve Fit (Gaussian)`, `Curve Fit (Lorentzian)`, `Curve Fit (Voigt)`. |
| **Peak-Finding Method** | `Tp search range (K, blank = no bound):` two entries | `250.0` to `400.0` | Only points with lower ≤ T ≤ upper (in K) go to the peak finder. A blank entry means no bound on that side. Bounds are drawn as dotted gray vertical lines. |

**Configure Rate Windows (Double Boxcar)** group: five sets, two per row, each with a `t1 (ms):` and `t2 (ms):` entry. The defaults are Detailed Analysis' standard windows (`detailedAnalysisTab.DEFAULT_STD_WINDOWS`):

| Set | t1 (ms) | t2 (ms) |
|---|---|---|
| Set 1 | 5.0 | 25.0 |
| Set 2 | 10.0 | 50.0 |
| Set 3 | 20.0 | 100.0 |
| Set 4 | 50.0 | 250.0 |
| Set 5 | 100.0 | 490.0 |

The number of sets is the length of `DEFAULT_RATE_WINDOWS`.

**Compute Boxcar Spectrums** (blue button) runs `_calculate_rate_windows()`. It clears the plot and the peak table, computes the DLTS signal S(T) for every set, finds each peak, fills the table and redraws the plot. Each set is drawn as points `RW <n>` (with error bars when errors exist), the fitted curve as a dashed line `Fit <n>`, and the peak as a black `x` with a T_peak error bar. A peak with no T_peak error (on the edge of the search range) is a gray `x`. It logs a summary line to the app log.

**Extracted Peaks** table (`ttk.Treeview`, 4 rows visible, scrolls): columns `Window` (`Set n`), `Emission e_n (s⁻¹)` (2 decimals), `T_peak (K)` (2 decimals, `± err` when available), `Max Extrema ΔC/C∞` (5 decimals, the largest |S| in the search range, with its sign), and `Arrhenius fit`. The last column reads `skipped (no peak)` for a skipped window and `no Tp error (edge)` for an edge peak. After the solver runs it reads `used` or `excluded (edge peak)`.

### Right frame: "Arrhenius Defect Mapping"

Plot: title "Arrhenius Plot Representation for Trap Signature Extraction", X axis "Reciprocal Temperature (1000 / T) (K⁻¹)", Y axis "ln(e_n / T²)".

| Group | Widget | Default | What it does |
|---|---|---|---|
| **Material Parameters** | `Background Doping Nd (cm⁻³):` entry | `3.2e+14` (`DEFAULT_ND`, the same as Detailed Analysis) | Used only for the trap density. Must be a positive number. |
| **Material Parameters** | `Pre-factor γ (cm⁻² s⁻¹ K⁻²):` entry | `1.66e+21` (`DEFAULT_GAMMA`) | Used only for the capture cross-section. Must be positive. A gray hint below reads `(SiC ≈ 1.66e21, Si ≈ 3.256e21)`. |
| (no group) | **Execute Arrhenius Signature Solver** (yellow button) | | Runs `_run_arrhenius_solver()` on the peaks from the last **Compute Boxcar Spectrums**. Needs at least 2 peaks. |
| **Extracted Microscopic Trap Signatures** | `Defect Activation Energy Et (eV):` value label | `Waiting...` | Shows `E ± err eV` (3 decimals). |
| **Extracted Microscopic Trap Signatures** | `Apparent Capture Cross-Sec σ (cm²):` value label | `Waiting...` | Shows `σ ± err cm²` (`.2e`). |
| **Extracted Microscopic Trap Signatures** | `Calculated Trap Density Nt (cm⁻³):` value label | `Waiting...` | Shows `N_T cm⁻³` (`.2e`). |

The solver plots the fitted points as red squares "Experimental Extrema Points" (with x and y error bars from the T_peak error), excluded points as gray `x` "Excluded (peak on search-range edge)", and the fit as a blue line "Linear Fit Reference", drawn from `0.95·min(1000/T)` to `1.05·max(1000/T)`. It logs `Arrhenius solver (T_peak-error weighted|unweighted, n windows[, m excluded]): Et=..., sigma=... (γ=...), Nt=...`.

### Data sources

| Selection | Where the data comes from |
|---|---|
| `Qualitative Analysis` | `dltsc.manual_processedTransients`, filled by **Extract & Average Transients** in the Qualitative Analysis frame of the Live Tools tab. Keys are °C. |
| `Automated/Live Data — Live` | The Run DLTS session in progress: `dltsc.livePlot_liveImpdData` (an `impdData` instance) or, if that is `None`, the averaged snapshot `dltsc.livePlot_liveAllEmissionsData`. |
| `Automated/Live Data — Offline` | A previously loaded run: `dltsc.livePlot_offlineImpdData` or `dltsc.livePlot_offlineAllEmissionsData`. |
| `Auto (first available)` | Measured C: Qualitative Analysis first, then Live, then Offline. Smoothed C: Live `impdData`, then Offline `impdData` (never Qualitative Analysis). |

`Smoothed C` always needs an `impdData` instance (Live or Offline). With Qualitative Analysis, or with no instance, the status label shows the error and nothing is computed.

## Import

```python
import dataAnalysisTab as daT      # alias used in DLTSGUI_MainWindow.py
daT.construct_dataAnalysisTab()
```

`dataAnalysisTab` itself imports `detailedAnalysisTab as dA` for the shared analysis functions and defaults. Elsewhere in the codebase the alias `daT` means `detailedAnalysisTab` (tests and benchmarks use `import detailedAnalysisTab as daT`), so check which module a `daT` refers to before reading code.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `K_BOLTZMANN` | `dA.KB_EV` = `8.617333262145e-5` (float) | Boltzmann constant, eV/K. |
| `DEFAULT_GAMMA` | `'1.66e+21'` (str, from `dA.DEFAULT_GAMMA`) | Default emission pre-factor γ, cm⁻² s⁻¹ K⁻² (SiC value). |
| `DEFAULT_ND` | `'3.2e+14'` (str, from `dA.DEFAULT_ND`) | Default background doping Nd, cm⁻³. |
| `DEFAULT_TPEAK_LO` | `'250.0'` (str, from `dA.DEFAULT_TPEAK_LO`) | Default lower peak-search bound, K. |
| `DEFAULT_TPEAK_HI` | `'400.0'` (str, from `dA.DEFAULT_TPEAK_HI`) | Default upper peak-search bound, K. |
| `QUICK_CONTROLS_HEIGHT` | `260` (int) | Requested height (px) of the scrollable control area under each plot. |
| `DEFAULT_RATE_WINDOWS` | `[('5.0','25.0'), ('10.0','50.0'), ('20.0','100.0'), ('50.0','250.0'), ('100.0','490.0')]` | Default (t1, t2) per set, ms, built from `dA.DEFAULT_STD_WINDOWS`. Its length sets the number of sets. |
| `DATA_SOURCE_AUTO` | `'Auto (first available)'` | Data Source option. |
| `DATA_SOURCE_QUALITATIVE` | `'Qualitative Analysis'` | Data Source option. |
| `DATA_SOURCE_LIVE` | `'Automated/Live Data — Live'` | Data Source option. |
| `DATA_SOURCE_OFFLINE` | `'Automated/Live Data — Offline'` | Data Source option. |
| `DATA_SOURCE_OPTIONS` | list of the four above | Combobox values. |
| `SIGNAL_METHOD_MEASURED` | `'Measured C (nearest sample)'` | Signal method option (default). |
| `SIGNAL_METHOD_SMOOTHED` | `'Smoothed C (impdData, spline-interpolated)'` | Signal method option. |
| `SIGNAL_METHOD_OPTIONS` | list of the two above | Combobox values. |
| `DENOISE_NONE` | `'None (raw)'` | No denoising. |
| `DENOISE_OPTIONS` | `['None (raw)', 'pca', 'wavelet', 'sgolay', 'lowess']` | Combobox values. |
| `PEAK_METHOD_SPLINE` | `'Smoothing Spline'` | Peak method (default). The same finder as Detailed Analysis' `Smoothing Spline (bootstrap)`. |
| `PEAK_METHOD_PSEUDOVOIGT` | `'Curve Fit (Pseudo-Voigt)'` | Peak method. |
| `PEAK_METHOD_GAUSSIAN` | `'Curve Fit (Gaussian)'` | Peak method. |
| `PEAK_METHOD_LORENTZIAN` | `'Curve Fit (Lorentzian)'` | Peak method. |
| `PEAK_METHOD_VOIGT` | `'Curve Fit (Voigt)'` | Peak method. |
| `PEAK_METHOD_OPTIONS` | list of the five above | Combobox values. |
| `PEAK_METHOD_CURVETYPE` | `{Pseudo-Voigt: 'pseudoVoigt', Gaussian: 'gaussian', Lorentzian: 'lorenzian', Voigt: 'voigt'}` | Maps a curve-fit option to the `curveType` argument of `impdData._curveFit_peakFinder`. |

Shared state in `dltsConfig` (`dltsc`) that this module reads or writes:

| Name | Type | Meaning |
|---|---|---|
| `rateWindow_dataSourceVar`, `rateWindow_signalMethodVar`, `rateWindow_denoiseVar`, `rateWindow_peakMethodVar` | `tk.StringVar` | Combobox selections. |
| `rateWindow_tpLoVar`, `rateWindow_tpHiVar` | `tk.StringVar` | Peak-search bounds (K), blank allowed. |
| `rateWindow_windowVars` | list of 5 `(t1Var, t2Var)` `tk.StringVar` pairs | Rate-window entries (ms). |
| `rateWindow_statusLabel` | `ttk.Label` | Data Source status text. |
| `rateWindow_peakTable` | `ttk.Treeview` | Extracted Peaks table. Row ids are `w<i>` (i = set index from 0). |
| `rateWindow_figure`, `rateWindow_ax`, `rateWindow_canvas` | matplotlib `Figure`, `Axes`, `FigureCanvasTkAgg` | Left plot. |
| `rateWindow_signals` | dict `i -> {'T_k', 'Signal', 'Signal_err'}` | Per-set S(T) curves from the last run (T in K). `Signal_err` is `None` when not every point has a usable error. |
| `rateWindow_extractedPeaks` | dict `i -> {'T_peak', 'S_peak', 'e_n', 'T_peak_err', 't1', 't2'}` | Per-set peaks, input to the Arrhenius solver. Skipped sets are left out. `T_peak_err` is `None` for an edge peak. |
| `rateWindow_transients` | `(records, temps, rb_ms)` or `None` | The averaged transients of the last run as Detailed Analysis records. N_T is computed from them. |
| `rateWindow_denoisedEmissions` | dict `T -> dict` | Copy of `impd.dataEmissions` after the last `impdData`-backed window (raw and denoised emissions). |
| `arrhenius_ndVar`, `arrhenius_gammaVar` | `tk.StringVar` | Nd and γ entries. |
| `arrhenius_energyLabel`, `arrhenius_captureLabel`, `arrhenius_densityLabel` | `ttk.Label` | Result labels. |
| `arrhenius_figure`, `arrhenius_ax`, `arrhenius_canvas` | matplotlib objects | Right plot. |
| read only: `manual_processedTransients`, `manual_paramVars['rb_ms']`, `livePlot_liveImpdData`, `livePlot_offlineImpdData`, `livePlot_liveAllEmissionsData`, `livePlot_offlineAllEmissionsData`, `livePlot_liveIngestBusy`, `livePlot_offlineIngestBusy`, `tabControl`, `dataAnalysisTab` | various | Inputs from other tabs and the main window. |

## Analysis method

All times typed in the GUI are in ms. Temperatures are in K inside the analysis (Qualitative Analysis keys are °C and get +273.15).

**Step 1. Get one averaged transient per temperature.** (`_get_processed_transients_for_source`, `_processed_transients_from_automated`, or `impdData.selected_emissions` inside `calculate_delC_normalized`.)

For an averaged Live/Offline snapshot (`_processed_transients_from_automated`):

```text
time_ms    = x * 1000                       # x is pulse-relative time in s
avg_cap_pf = ymean * 1e12   if max|ymean| < 1e-3   (Farads -> pF), else ymean
T_C        = round(T_K - 273.15, 6)         # impdData keys are exact K (298.15 -> 25.0)
```

(That function still stores a `C_infinity` at 90 % of the span, for other callers. The analysis below recomputes C∞.)

**Step 2. Reverse bias and C∞** (`_rb_ms_for_source`, `_transient_records`). The reverse-bias duration `rb_ms` is the **Reverse Bias (ms)** field of Qualitative Analysis for that source; for a Live/Offline snapshot, or when that field is not a positive number, it is the longest transient's span. C∞ is Detailed Analysis' convention:

```text
C_inf = mean C(t) over 0.40 * rb_ms <= t <= 0.90 * rb_ms     # dA._cinf_range_mean
```

**Step 3. Emission rate of each rate window** (`dA._emission_rate`):

```text
e_n = ln(t2 / t1) / ((t2 - t1) * 1e-3)      # t1, t2 in ms -> e_n in s^-1
```

`0 < t1 < t2` is enforced for every set before anything is computed.

**Step 4. DLTS signal S(T).** Two code paths:

a. No `impdData` instance (Qualitative Analysis, or an averaged Live/Offline snapshot), Measured C only. This is `dA._rate_window_signal` on the records of Step 2:

```text
C(t)     = nearest measured sample to t
S(T)     = (C(t2) - C(t1)) / C_inf                          # dimensionless
sigma_S  = hypot(noise(t1), noise(t2)) / |C_inf|
```

`noise(t)` is `dA._cap_noise_at(time_ms, C, t)`: the Rice second-difference estimate `sqrt(sum(d2^2) / (6 * len(d2)))` with `d2 = C[k-1] - 2 C[k] + C[k+1]`, over the ±25 samples around t.

b. `impdData` instance (Live/Offline; always the case for Smoothed C). The code calls

```python
impd.calculate_delC_normalized(t1=t1/1000.0, t2=t2/1000.0, emissionIndex=-1,
    denoiseEmission=(denoise != 'None (raw)'), denoiseMethod=(denoise or 'pca'),
    smoothCapacitance=(method == Smoothed C), plot=False)
```

and uses column 0 (T, K) as x, column 3 (ΔC/C∞) as S, and error column 1 as σ_S. Inside that method (in `impedanceAnalysis_Tools.py`): `emissionIndex=-1` is the ensemble average over all reverse-bias repeats; t1/t2 are clipped to the data range; C(t1), C(t2) and C∞ are the nearest samples (Measured C) or `CubicSpline` values (Smoothed C); **C∞ is the last sample, C(t[-1])**; errors come from the cross-repeat standard deviation `yerr`, propagated with the `uncertainties` package; `S = (C(t2) - C(t1)) / C_inf`.

**Step 5. Peak of S(T)** (`dA._peak_from_signal`, the step Detailed Analysis uses too):

- Only points with `Tp_lo <= T <= Tp_hi` are used. Fewer than 4 points gives a log warning; the peak is then the raw maximum.
- If the largest |S| in the range is negative, S is flipped so the peak is positive.
- A window whose peak is at most `dA.PEAK_MIN_FRAC` (5 %) of max|S| over all temperatures is **skipped**: it gets no peak and does not go to the Arrhenius fit.
- `Smoothing Spline`: `impdData._smoothingSpline_peakFinder`: `scipy.interpolate.UnivariateSpline(k=3)`. With point errors: weights `1/σ_S` and smoothing factor `s = n`. Without: `s = n · noiseVar` where noiseVar is the Rice estimate over S(T) itself. The peak is the maximum on a 100 000-point grid. The T_peak error is the standard deviation of 200 parametric-bootstrap refits (seed 0, 2000-point grid).
- `Curve Fit (...)`: `impdData._curveFit_peakFinder` with lmfit `PseudoVoigtModel`/`GaussianModel`/`LorentzianModel`/`VoigtModel`, weights `1/σ_S` when available. T_peak = `center`, its error = lmfit `stderr`. If the fit raises or returns `-1`, the raw grid maximum is used with no error.
- **Edge guard** (`dA._guard_peak_error`): a peak within 1 % of a grid step of either end of the range (`dA.EDGE_PEAK_FRAC`), or with an error below `dA.MIN_TP_ERR_K` (1e-4 K), keeps its T_peak but loses its error. The signal is still rising out of the range, so it is not a real peak. A spline peak pinned to the edge would otherwise report an error of about 1e-13 K and dominate the weighted fit.

**Step 6. Arrhenius fit** (`_quick_arrhenius` → `dA._arrhenius_fit` → `dA._fit_arrhenius_line`):

```text
x  = 1000 / T_peak                     # K^-1 (times 1000)
y  = ln(e_n / T_peak^2)                # ln(s^-1 K^-2)
dx = 1000 * dT / T_peak^2              # plotted error bars only
dy = 2 * dT / T_peak
```

Windows with no T_peak error are left out of the fit (shown as gray `x`). If fewer than 3 windows have errors, all windows are fitted unweighted. Fewer than 2 fittable windows: no result. The fit is lmfit `LinearModel`, weighted by the effective variance `sig_eff = |-2/T + 1000·slope/T^2| · dT`, re-fitted up to 10 times until the slope changes by ≤ 1e-9·max(|slope|, 1). With fewer than 3 fitted windows, slope and intercept errors are `None`.

**Step 7. Defect parameters:**

```text
E_a     = -slope * 1000 * K_BOLTZMANN                  # eV
dE_a    = 1000 * K_BOLTZMANN * slope_stderr            # eV
sigma   = exp(intercept) / gamma                       # cm^2   (gamma in cm^-2 s^-1 K^-2)
dsigma  = sigma * intercept_stderr                     # cm^2
N_T     = 2 * max_T |(C(rb_ms) - C(2 ms)) / C_inf| * Nd    # cm^-3, dA._trap_density
```

N_T uses the averaged transients of Step 2 (`dltsc.rateWindow_transients`). For an `impdData` source that has no averaged snapshot, it falls back to `2 · max|S_peak| · Nd`. N_T has no error estimate.

## Matching Detailed Analysis

On averaged transients (path a), both tabs call the same functions for every step, so the numbers agree to rounding. Set up both tabs like this:

| Setting | Quick Analysis | Detailed Analysis |
|---|---|---|
| Data | Qualitative Analysis extraction of the run folder | **Load Data** on the same folder |
| Reverse bias | Qualitative Analysis **Reverse Bias (ms)** | **RB duration (ms)**, same value |
| C∞ range | fixed 0.40 to 0.90 | **Start / End (frac RB)** 0.40 / 0.90 (defaults) |
| Signal | `Measured C`, source `Qualitative Analysis` | `Measured C (nearest sample)`, denoise `None (raw)` |
| Windows | the five sets | the five **Standard Windows** (same defaults) |
| Search range | Tp search range | **T min / T max** (same defaults) |
| Peak method | `Smoothing Spline` | `Smoothing Spline (bootstrap)` |
| Nd, γ | same values | same values |

Then Quick Analysis' Et, σ and N_T equal the **Standard** block of the Detailed results. `tests/test_quick_vs_detailed.py` checks this. A Detailed standard row of `0 / 0` is unused, so fewer windows can be compared too.

The `impdData` path (b) normalizes by the last sample and uses cross-repeat errors, so its S(T) differs slightly. The curve-fit peak methods have no Detailed Analysis equivalent. The edge guard, the skip rule and the fit rule still apply to both.

## Functions

### construct_dataAnalysisTab()

Adds the **Quick Analysis** tab to `dltsc.tabControl` and builds both frames.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | |

**Returns** `None`.

**Side effects** Calls `dltsc.tabControl.add(dltsc.dataAnalysisTab, text='Quick Analysis')` and `tabControl.pack(expand=1, fill="both")`; creates the `tk.PanedWindow`, then calls `_build_rateWindowFrame` and `_build_arrheniusFrame`, which create every widget and `dltsc.rateWindow_*` / `dltsc.arrhenius_*` global listed above. `dltsc.dataAnalysisTab` must already be a `ttk.Frame` inside `dltsc.tabControl`.

**Called by** `DLTSGUI_MainWindow.py` (`daT.construct_dataAnalysisTab()`).

**Example** Needs a Tk root and notebook; not useful outside the GUI.

## Internal helpers

### _resolve_impd_for_source(source)

Maps a Data Source label to an `impdData` instance.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `source` | str | | One of the `DATA_SOURCE_*` labels. |

**Returns** `(impd, resolvedLabel)`, or `(None, None)` when that source has no instance. `Qualitative Analysis` always gives `(None, None)`. `Auto` tries `livePlot_liveImpdData`, then `livePlot_offlineImpdData`.

**Side effects** None.

**Called by** `_calculate_rate_windows`.

### _processed_transients_from_automated(mode)

Converts the Automated/Live Data frame's "All Emissions Aligned" snapshot into the Qualitative Analysis shape.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `mode` | str | | `'live'` reads `dltsc.livePlot_liveAllEmissionsData`; any other value reads `dltsc.livePlot_offlineAllEmissionsData`. |

**Returns** dict `T_C -> {'time_ms', 'avg_cap_pf', 'C_infinity'}` (keys in °C, rounded to 1e-6 so a 298.15 K key gives 25.0). `C_infinity` here is the sample nearest 90 % of the span. Entries with empty or mismatched `x`/`ymean` are skipped. Returns `{}` when there is no snapshot.

**Side effects** None.

**Called by** `_get_processed_transients_for_source`, `_calculate_rate_windows` (for N_T on the `impdData` path).

**Example** (runs offline, verified):

```python
import numpy as np
import matplotlib; matplotlib.use('Agg')
import dltsConfig as dltsc
import dataAnalysisTab as daT

t = np.arange(0, 0.5, 1.8666666666666665e-05)          # s
snap = {}
for TK in np.arange(300.0, 360.0, 5.0):
    en = 1.66e21 * 1e-15 * TK**2 * np.exp(-0.6 / (8.617333e-5 * TK))
    snap[TK] = {'x': t, 'ymean': 100e-12 * (1 - 0.01 * np.exp(-en * t))}   # Farads
dltsc.livePlot_offlineAllEmissionsData = snap

pt = daT._processed_transients_from_automated('offline')
print(sorted(pt)[0], pt[sorted(pt)[0]]['C_infinity'])   # 26.85 (degC), ~99.996 (pF)
```

### _get_processed_transients_for_source(source)

Resolves a Data Source label to averaged transients.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `source` | str | | One of the `DATA_SOURCE_*` labels. |

**Returns** `(processedTransients, resolvedLabel, errorReason)`. On success `errorReason` is `None`; on failure the first two are `None` and `errorReason` is a message such as `"Qualitative Analysis has no extracted transients yet."`. `Auto` order: Qualitative Analysis, Live snapshot, Offline snapshot.

**Side effects** None.

**Called by** `_calculate_rate_windows`.

**Example** Continuing the example above: `daT._get_processed_transients_for_source(daT.DATA_SOURCE_AUTO)` returns the 12-temperature dict and `'Automated/Live Data — Offline'`.

### _rb_ms_for_source(label, processedTransients)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `label` | str | | Resolved Data Source label. |
| `processedTransients` | dict | | `T_C -> {'time_ms', ...}`. |

**Returns** the reverse-bias duration in ms (see Step 2).

### _transient_records(processedTransients, rb_ms)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `processedTransients` | dict | | `T_C -> {'time_ms', 'avg_cap_pf', ...}`. |
| `rb_ms` | float | | Reverse-bias duration, ms. |

**Returns** `(records, temps)`: `dA._prepare_signal_data` records (Measured C, no denoise) with C∞ from `dA._cinf_range_mean`, and the sorted °C keys.

### _peak_method_for(peakMethod) and _curve_fit_peak_method(curveType)

`_peak_method_for` turns a `PEAK_METHOD_*` label into a method for `dA._peak_from_signal`: `dA.PEAK_METHOD_SPLINE` for the smoothing spline, or the callable made by `_curve_fit_peak_method(curveType)`. That callable takes `(T, S, S_err)` and returns `(Tp, Tp_err, xFit, yFit)` from `impdData._curveFit_peakFinder`, or the raw grid maximum with no error and no curve if the fit fails.

### _window_peaks(records, temps, windows, tpLo, tpHi, peakMethod)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `records`, `temps` | | | From `_transient_records`. |
| `windows` | list of (t1, t2) | | ms. |
| `tpLo`, `tpHi` | float | | Search range, K (`-inf`/`inf` for no bound). |
| `peakMethod` | str | | A `PEAK_METHOD_*` label. |

**Returns** one dict per window: `t1`, `t2`, `e_n`, `T_k`, `Signal`, `Signal_err`, plus `dA._peak_from_signal`'s keys (`skipped`, and unless skipped `Tp`, `Tp_err`, `S_peak`, `sign`, `xFit`, `yFit`).

### _quick_arrhenius(peaks, gamma, nd, transients=None)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `peaks` | list of dict | | Non-skipped peaks with `T_peak`, `T_peak_err`, `e_n`, `S_peak`. |
| `gamma` | float | | cm⁻² s⁻¹ K⁻². |
| `nd` | float | | cm⁻³. |
| `transients` | `(records, temps, rb_ms)` or None | `None` | For N_T by `dA._trap_density`. |

**Returns** the `dA._arrhenius_fit` dict (`Et`, `Et_se`, `sigma`, `sigma_se`, `R2`, `N`, `N_excluded`, `fit_mask`, `weighted`, `slope`, `intercept`, `x`, `y`, `Tp_arr`, `Tp_err_arr`, ...) plus `Nt`, or `None` if fewer than 2 peaks can be fitted.

**Example** (runs offline, verified; the synthetic run of `tests/test_detailed_peaks.py`, a 0.60 eV trap):

```python
import sys; sys.path.insert(0, 'tests')
import matplotlib; matplotlib.use('Agg')
import dataAnalysisTab as qa, detailedAnalysisTab as dA
from test_detailed_peaks import synthetic_run

pt = {tc: {'time_ms': t, 'avg_cap_pf': c} for tc, (t, c, _) in synthetic_run().items()}
records, temps = qa._transient_records(pt, 500.0)
peaks = [dict(T_peak=p['Tp'], T_peak_err=p['Tp_err'], e_n=p['e_n'], S_peak=p['S_peak'])
         for p in qa._window_peaks(records, temps, dA.DEFAULT_STD_WINDOWS, 290.0, 400.0, qa.PEAK_METHOD_SPLINE)
         if not p['skipped']]
res = qa._quick_arrhenius(peaks, dA.DEFAULT_GAMMA, dA.DEFAULT_ND, (records, temps, 500.0))
print(f"{res['Et']:.4f} +/- {res['Et_se']:.4f} eV, {res['N_excluded']} excluded")
# 0.5957 +/- 0.0005 eV, 1 excluded   (the 100/490 ms window peaks on the 290 K edge)
```

### _calculate_rate_windows()

Command of **Compute Boxcar Spectrums**. Implements Steps 2 to 5 for each set.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | Reads all inputs from the `dltsc.rateWindow_*` Tk variables. |

**Returns** `None`.

**Side effects** Clears and redraws `dltsc.rateWindow_ax`; resets and refills `dltsc.rateWindow_signals`, `dltsc.rateWindow_extractedPeaks`, `dltsc.rateWindow_transients` and the Extracted Peaks table; sets `dltsc.rateWindow_denoisedEmissions` on the `impdData` path; updates the status label; writes to the app log via `dltsc.log_to_textbox`. It stops early (with a log message, before clearing anything) when: no data source has data; Smoothed C has no `impdData`; the resolved Live/Offline source is still ingesting (`livePlot_*IngestBusy`); a Tp bound is non-numeric or upper ≤ lower; a t1/t2 is non-numeric or not `0 < t1 < t2`. It stops part-way if `calculate_delC_normalized` raises.

**Called by** the **Compute Boxcar Spectrums** button.

### _run_arrhenius_solver()

Command of **Execute Arrhenius Signature Solver**. Implements Steps 6 and 7.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | Reads `dltsc.rateWindow_extractedPeaks`, `dltsc.rateWindow_transients`, `dltsc.arrhenius_ndVar`, `dltsc.arrhenius_gammaVar`. |

**Returns** `None`.

**Side effects** Sets the three result labels, fills the `Arrhenius fit` column of the peak table, clears and redraws `dltsc.arrhenius_ax`, logs the result. Stops with a log message when fewer than 2 peaks exist, Nd or γ is not a positive number, the fit raises, or fewer than 2 windows can be fitted.

**Called by** the **Execute Arrhenius Signature Solver** button.

### _build_rateWindowFrame(parent)

Builds the left frame (plot, toolbar, scrollable controls, button, table) inside `parent` and creates the `dltsc.rateWindow_*` widgets and variables. Seeds `dltsc.rateWindow_signals` and `dltsc.rateWindow_extractedPeaks` as empty dicts if they are `None`, because `dltsConfig.init()` is not called by the main window.

### _build_arrheniusFrame(parent)

Builds the right frame (plot, toolbar, Material Parameters, solver button, results group) inside `parent` and creates the `dltsc.arrhenius_*` widgets and variables. Uses the same row weights and control height as the left frame so both plots are the same height.

### _on_mousewheel(event) (nested, one in each `_build_*` function)

Scrolls that frame's control canvas by `-event.delta / 120` units. Bound with `bind_all` while the pointer is over the canvas and unbound when it leaves.

## Notes and limitations

- C∞ on the `impdData` path is the last sample of the (trimmed) emission, not the 40–90 % mean. Results from that path are close to, but not the same as, the averaged-transient path and Detailed Analysis.
- The sign convention is `S = (C(t2) - C(t1)) / C_inf`. A negative peak is flipped before peak finding; `S_peak` keeps the original sign.
- `e_n = ln(t2/t1) / (t2 - t1)` assumes t1 and t2 in ms (the `1e-3` factor). The `impdData` path passes t1/t2 in s and may clip them to the data range, but the table and Arrhenius plot still use the e_n computed from the unclipped GUI values.
- The initial plot title says "(Pseudo-Voigt Refinement)" although the default peak method is `Smoothing Spline`. The title is corrected after the first run.
- On the `impdData` path with `Denoise` = `None (raw)`, `calculate_delC_normalized` still runs the `pca` filter (`filter_emissions(..., recalculate=True)`) and discards it. This costs time but does not change the result.
- If `calculate_delC_normalized` fails on a later set, the function returns before `canvas.draw()`. `rateWindow_extractedPeaks` then holds only the earlier sets.
- If every window's peak lies on the edge of the search range, fewer than 3 windows have errors and all are fitted unweighted. The result is then not meaningful: widen the range or choose windows whose peaks fall inside it.
- With only 2 fitted windows the fit has no residual degrees of freedom; E_a and σ are reported with no error.
- N_T is `2·max|ΔC/C∞|·Nd` from C(rb) − C(2 ms), the small-signal approximation `N_T ≈ 2 (ΔC/C) N_d`. It ignores the λ-region correction.
- σ is the apparent cross-section `exp(intercept)/γ`. It is only as good as the γ entered; the hint gives SiC 1.66e21 and Si 3.256e21.
- `rateWindow_signals` stores T in K under the key `'T_k'`.

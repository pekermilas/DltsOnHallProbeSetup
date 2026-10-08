# detailedAnalysisTab

## What it's for

`detailedAnalysisTab.py` builds the **Detailed Analysis** tab, a port of the standalone `DLTS_APP.py` ("DLTS Multiwindow Analysis") into this app. It loads a whole temperature sweep from a data folder, computes DLTS spectra for many log-spaced rate windows (plus five fixed "standard" windows for comparison), finds each peak with an error estimate, and fits an error-weighted Arrhenius line to get E_a, σ and N_T. It also draws a DLTS spectra panel, a ΔC/C₀(t, T) transient map with a τ(T) overlay, and a rate-window map. Loading and analysis run in the tab's own worker process so the GUI stays responsive.

The per-window steps (C∞, S(T), the peak with its edge guard, the Arrhenius fit with its exclusion rule, N_T) are also what [Quick Analysis](dataAnalysisTab.md) calls. The **Standard** result of this tab therefore equals the Quick Analysis result for the same transients, windows, search range and reverse bias; see [Matching Detailed Analysis](dataAnalysisTab.md#matching-detailed-analysis).

## What the user sees

A header reads **Detailed Analysis** `(DLTS Multiwindow Analysis — ZI MFIA temperature sweep)`. Below it a horizontal `ttk.PanedWindow` has three parts:

1. a scrollable control column on the left (295 px wide, mouse wheel scrolls it while the pointer is over it);
2. the figure area in the middle (takes all extra width), with a matplotlib toolbar under the figure and a status label at the bottom (initial text `Load a data folder to begin.`);
3. a **Results** text box on the right (Consolas 9, dark background, read-only, 57 characters wide, no wrapping, horizontal and vertical scroll bars).

### Control column

Section headings are shown in upper case in the GUI. Spinboxes accept typed values outside the listed range; the range only limits the arrow buttons.

**DATA**

| Widget | Default | What it does |
|---|---|---|
| `Data folder:` entry | empty | Path of the run folder. |
| **Browse** | | Opens a folder dialog ("Select DLTS Data Folder"), puts the path in the entry and logs a description of the folder contents (`liveDataTab._describe_folder_contents`). |
| **Load Data** | | Runs `_detailed_load_data()`: loads every temperature in the folder in the worker process. Disabled while a load or run is in progress. |
| info label | `No data loaded.` | After a load: `<n> temperatures loaded: <Tmin> °C to <Tmax> °C` (blue). |

**ZI MFIA GRID**

| Label | Variable | Default | Spinbox range, step | Used? |
|---|---|---|---|---|
| `Grid offset (s)` | `detailed_gridOffVar` (DoubleVar) | `-0.001` (`DEFAULT_GRID_OFF`) | -0.01 to 0, 0.0001 | No. Passed to `_load_detailed_data` but ignored there. |
| `Grid dt (s)` | `detailed_gridDtVar` (DoubleVar) | `1.86667e-5` (`DEFAULT_GRID_DT`) | 1e-6 to 1e-3, 1e-6 | No. Ignored. |
| `Chunk size` | `detailed_chunkSizeVar` (IntVar) | `32768` (`DEFAULT_CHUNK_SIZE`) | 1024 to 131072, 1024 | No. Ignored. |
| `RB duration (ms)` | `detailed_rbMsVar` (DoubleVar) | `500.0` (`DEFAULT_RB_MS`) | 10 to 2000, 10 | Yes: C∞ window, legacy-file cycle length, N_T reference time, transient-map time range. |

**C₀ ESTIMATION WINDOW** (C∞ is the mean capacitance over `[Start·RB, End·RB]`)

| Label | Variable | Default | Range, step |
|---|---|---|---|
| `Start  (frac RB)` | `detailed_cinfLoVar` | `0.40` | 0.1 to 0.8, 0.05 |
| `End    (frac RB)` | `detailed_cinfHiVar` | `0.90` | 0.3 to 0.99, 0.05 |

These two values are applied at **Load Data** time. Changing them later has no effect until the data is loaded again.

**PHYSICAL CONSTANTS (4H-SIC)**

| Label | Variable | Default | Range, step |
|---|---|---|---|
| `γ (cm⁻²s⁻¹K⁻²)` | `detailed_gammaVar` | `1.66e21` | 1e20 to 1e22, 1e20 |
| `Nᵈ (cm⁻³)` | `detailed_ndVar` | `3.2e14` | 1e12 to 1e17, 1e13 |

**DLTS SIGNAL CALCULATION**

| Label | Variable | Default | Options |
|---|---|---|---|
| `Method:` | `detailed_signalMethodVar` | `Measured C (nearest sample)` | `Measured C (nearest sample)`, `Smoothed C (spline-interpolated)` |
| `Denoise:` | `detailed_denoiseVar` | `None (raw)` | `None (raw)`, `pca`, `wavelet`, `sgolay`, `lowess` |

**PEAK SEARCH RANGE**

| Label | Variable | Default | Range, step |
|---|---|---|---|
| `T min (K)` | `detailed_tpeakLoVar` | `250.0` | 100 to 350, 5 |
| `T max (K)` | `detailed_tpeakHiVar` | `400.0` | 200 to 600, 5 |
| `Peak method:` combobox | `detailed_peakMethodVar` | `Smoothing Spline (bootstrap)` | `Parabolic fit (lmfit)`, `Smoothing Spline (bootstrap)` |

**MULTI-WINDOW PARAMETERS**

| Label | Variable | Default | Range, step | Meaning |
|---|---|---|---|---|
| `N windows` | `detailed_nWinVar` (IntVar) | `16` | 3 to 60, 1 | Number of rate windows. |
| `t₁ min (ms)` | `detailed_t1MinVar` | `5.0` | 1 to 200, 1 | Smallest t1. |
| `t₁ max (ms)` | `detailed_t1MaxVar` | `90.0` | 5 to 450, 5 | Largest t1. |
| `Ratio t₂/t₁` | `detailed_ratioVar` | `5.0` | 2 to 20, 0.5 | t2 = ratio · t1 for every window. |

**STANDARD WINDOWS (REFERENCE)**

| Widget | Default | What it does |
|---|---|---|
| `Show standard-window comparison (0 / 0 = unused)` checkbox (`detailed_stdWinsVar`) | on | Draws the standard-window fit (orange dashed line, diamond markers) on the Arrhenius panel. The standard-window fit is computed and written to Results whether or not this is checked. |
| `t1 / t2  (ms):` five spinbox pairs (`detailed_stdEntries`) | `5/25`, `10/50`, `20/100`, `50/250`, `100/490` (`DEFAULT_STD_WINDOWS`, the same as Quick Analysis' window sets) | t1 range 0 to 490, t2 range 0 to 499, step 1. A row with t1 ≤ 0 or t2 ≤ t1 (for example `0 / 0`) is not used; with no usable row there is no Standard result. |

**DISPLAY**

| Widget | Variable | Default | What it does |
|---|---|---|---|
| `Show DLTS spectra panel` | `detailed_showSpectraVar` | on | Adds the DLTS Spectra panel. |
| `Spectra to plot` spinbox | `detailed_nSpectraVar` (IntVar) | `5` | Range 2 to 16. Number of multi-windows drawn in the spectra panel. |
| `Show 2D transient map` | `detailed_showTmapVar` | on | Adds the ΔC/C₀ transient map panel. |
| `  Overlay τ(T) curve on map` | `detailed_showTauVar` | on | Draws τ(T) from the fit and the (T_p, 1/e_n) points on the transient map. |
| `Show Rate-Window Analysis map` | `detailed_showRwmVar` | on | Adds the rate-window map panel. |

**Actions** (under an empty section divider)

| Button | What it does |
|---|---|
| **Run Analysis** | Disabled until data has been loaded. Runs `_detailed_run_analysis()`: snapshots all parameters, computes everything in the worker process, then draws the figure and fills Results. Status becomes `Done.  Et = <E ± err> eV  Nt = <N_T> cm⁻³`. |
| **Edit Labels & Legends** | Opens the "Edit Labels & Legends" dialog (`_detailed_open_label_editor`). Logs a hint if no analysis has been run yet. |
| **Save Figure...** | Save dialog (default name `DLTS_MultiWindow.png`). Formats: PNG, PDF, SVG, EPS, JPEG, TIFF, BMP. Raster formats are saved at 180 dpi with the figure background; vector formats without a dpi. |
| **Export Results to TXT** | Save dialog (default name `DLTS_Results.txt`); writes the Results text as UTF-8. |

### Figure

The figure is rebuilt on every run. It always has the **Arrhenius Plot** panel. The other panels depend on the three Display checkboxes:

| Spectra | Map | RW map | figsize (in) | Layout |
|---|---|---|---|---|
| on | on | on | 14 × 11.0 | 2×2: Arrhenius, Spectra / Transient map, RW map |
| on | on | off | 13 × 10.5 | Arrhenius, Spectra (width 1.5:1) / Transient map across the bottom |
| on | off | on | 13 × 10.5 | Arrhenius, Spectra / RW map across the bottom |
| off | on | on | 14 × 10.5 | Arrhenius across the top / Transient map, RW map |
| on | off | off | 13 × 5.4 | Arrhenius, Spectra side by side |
| off | on | off | 10 × 10.5 | Arrhenius / Transient map |
| off | off | on | 10 × 10.5 | Arrhenius / RW map |
| off | off | off | 8 × 5.4 | Arrhenius only |

Every panel uses `set_box_aspect(0.9)`. The figure title is "DLTS Multiwindow Analysis".

- **Arrhenius Plot**: x "1000 / T  (K⁻¹)", y "ln(eₙ / T²)  (s⁻¹ K⁻²)". Multi-window points colored by log₁₀ eₙ (plasma colormap, colorbar "log₁₀ eₙ  (s⁻¹)"), error bars from T_p errors, blue fit line labeled `Multi (<N> win)  Et=<E> eV  R²=<R²>` with a shaded 2σ confidence band. Excluded windows are gray `x` markers "Excluded (peak at range edge, no Tp error)". Optional standard-window line and diamonds. A top axis shows °C ticks for 240 to 360 K in 10 K steps (only those inside the x range). A yellow box in the lower-left lists E_a, σ, N_T, R² and (if weighted) χ²ᵣ.
- **DLTS Spectra**: x "Temperature  (°C)", y "ΔC/C₀  (×10⁻³)". One line per selected window (cool colormap), labeled `t=<t1>/<t2> ms  eₙ=<e_n> s⁻¹`; dotted vertical lines at each multi-window T_p.
- **ΔC/C₀  Transient Map**: filled contours (jet, 64 levels, black contour every 6th level) of ΔC/C₀ ×10⁻⁵ vs "Temperature  (K)" and log "Time  (s)". With the τ overlay: white τ(T) line labeled `Z₁₂  τ(T)  Et=<E> eV`, cyan circles "Rate-window peaks  (Tₚ, 1/eₙ)", and a cyan "Z₁₂ defect" arrow at the middle point. Shows "Not enough time points" when the map cannot be built.
- **Rate-Window Analysis Map**: black background, x "1/kT  (eV⁻¹)", log y "T²/eₙ  (K²s)", color N_T/N_D on a log scale (jet). White dashed Arrhenius line and 22 cyan circles "Z₁/₂ (fitted)". Shows "Insufficient data for Rate-Window map" when it cannot be built.

All legends and the results box can be dragged with the left mouse button.

### Edit Labels & Legends dialog

A scrollable `Toplevel` (500×580, minimum 460×340). For each existing panel (Arrhenius Panel, DLTS Spectra Panel, Transient Map Panel, Rate-Window Map Panel) it offers `Title`, `X label`, `Y label` text entries with a point-size spinbox (6 to 28). For each existing legend (Arrhenius Legend, Spectra Legend, Transient Map Legend, Rate-Window Legend) it offers one `Font size` spinbox (6 to 18) and one entry per legend item (`Entry n`). Buttons: **Apply** (applies and redraws), **Apply & Close**, **Close** (discards unapplied edits). Edits are lost on the next **Run Analysis**, which rebuilds the figure.

### Results text

Example layout (numbers from the synthetic example further below):

```text
=======================================================
  DLTS Multiwindow Analysis  —  Results
=======================================================

  Signal     : Measured C (nearest sample)
  Denoise    : None (raw)
  Peak method: Smoothing Spline (bootstrap)

  Multi-window  (16 windows)
    fit  : weighted by Tpeak errors
    Et   = 0.5968 +/- 0.0032 eV
    sn   = 8.904e-16 +/- 1.076e-16 cm2
    slope     = ... K
    intercept = ...
    R2   = ...
    red. chi2 = ...
    Nt   ~ 6.236e+12 cm-3

  Standard  (5 windows)
    ...
    Et uncertainty improvement: <Et_se(std) / Et_se(multi)>x

  Window detail  (multi):
    t1(ms)    t2(ms)     en(s-1)    Tpeak(C)   +/-(K)
  -----------------------------------------------------
       5.0      25.0       80.47       ...        ...
```

`excl.` marks a window left out of the fit. `n/a` means the peak fit gave no T_p error. The fit line reads `UNWEIGHTED (no Tpeak errors)` when no weighting was possible, and adds `, <k> window(s) excluded` when windows were excluded.

## Import

```python
import detailedAnalysisTab as deT   # alias used in DLTSGUI_MainWindow.py
deT.construct_detailedAnalysisTab()

import detailedAnalysisTab as daT   # alias used in tests/test_hdf5_analysis.py and benchmarks/
data, temps, errs = daT._load_detailed_data(folder, None, None, None, 500.0, 0.4, 0.9)
```

`dataAnalysisTab.py` also imports this module, as `dA`, for `_cap_noise_at`, `_valid_errors` and `_fit_arrhenius_line`. In `DLTSGUI_MainWindow.py` the alias `daT` means `dataAnalysisTab`, not this module.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `C0` | `'#2a78d6'` | Blue: multi-window fit, info label text. |
| `C1` | `'#eb6834'` | Orange: standard-window fit. |
| `SURFACE` | `'#fcfcfb'` | Figure/axes background; raster save background. |
| `TEXT_PRI`, `TEXT_SEC`, `TEXT_MUT` | `'#0b0b0b'`, `'#52514e'`, `'#898781'` | Text colors. |
| `GRIDLINE`, `BASELINE` | `'#e1e0d9'`, `'#c3c2b7'` | Grid and axis-spine colors. |
| `CTRL_BG` | `'#f0f0f0'` | Control column and dialog background. |
| `DEFAULT_GRID_OFF` | `-0.001` | Default `Grid offset (s)` (not used by the loader). |
| `DEFAULT_GRID_DT` | `1.86667e-5` | Default `Grid dt (s)` (not used by the loader). |
| `DEFAULT_CHUNK_SIZE` | `32768` | Default `Chunk size` (not used by the loader). |
| `DEFAULT_RB_MS` | `500.0` | Default `RB duration (ms)`. |
| `KB_EV` | `8.617333262145e-5` | Boltzmann constant, eV/K (CODATA 2018). Quick Analysis uses the same value. |
| `DEFAULT_CINF_LO`, `DEFAULT_CINF_HI` | `0.40`, `0.90` | C∞ window as fractions of the reverse bias (`_cinf_range_mean`). |
| `DEFAULT_ND` | `3.2e14` | Default Nd, cm⁻³ (both tabs). |
| `DEFAULT_GAMMA` | `1.66e21` | Default γ, cm⁻² s⁻¹ K⁻² (4H-SiC; both tabs). |
| `PEAK_MIN_FRAC` | `0.05` | A window whose peak is at most this fraction of max\|S\| is skipped (`_peak_from_signal`). |
| `DEFAULT_TPEAK_LO`, `DEFAULT_TPEAK_HI` | `250.0`, `400.0` | Default peak search range, K (both tabs). |
| `DEFAULT_STD_WINDOWS` | `[(5, 25), (10, 50), (20, 100), (50, 250), (100, 490)]` (ms, floats) | Default standard windows, and Quick Analysis' default window sets. |
| `_FOLDER_RE` | `re.compile(r'^(n?)(\d+)C(?:_\d+)?$', re.I)` | Temperature subfolder names: `25C_001`, `85C`, `n10C`. |
| `SIGNAL_METHOD_MEASURED` | `'Measured C (nearest sample)'` | Signal method (default). |
| `SIGNAL_METHOD_SMOOTHED` | `'Smoothed C (spline-interpolated)'` | Signal method. |
| `SIGNAL_METHOD_OPTIONS` | list of the two above | Combobox values. |
| `DENOISE_NONE` | `'None (raw)'` | No denoising. |
| `DENOISE_OPTIONS` | `['None (raw)', 'pca', 'wavelet', 'sgolay', 'lowess']` | Combobox values. |
| `PEAK_METHOD_PARABOLIC` | `'Parabolic fit (lmfit)'` | Peak method. |
| `PEAK_METHOD_SPLINE` | `'Smoothing Spline (bootstrap)'` | Peak method (default). |
| `PEAK_METHOD_OPTIONS` | `[PEAK_METHOD_PARABOLIC, PEAK_METHOD_SPLINE]` | Combobox values. |
| `EDGE_PEAK_FRAC` | `0.01` | A peak within this fraction of a grid step of either end of the peak search range is an edge peak (`_peak_on_edge`) and gets no T_p error. |
| `MIN_TP_ERR_K` | `1e-4` (K) | Smallest T_p error accepted as real; smaller ones are treated as no error. |
| `_FIGURE_SAVE_FILETYPES` | list of 8 `(label, pattern)` tuples | Save Figure dialog file types. |

Shared state in `dltsConfig` (`dltsc`):

| Name | Type | Meaning |
|---|---|---|
| `detailed_data` | dict `T_C -> (t_ms, cap_pF, C_inf)` | Loaded sweep. |
| `detailed_temps` | sorted list of float, °C | Loaded temperatures. |
| `detailed_figure`, `detailed_canvas`, `detailed_figFrame` | `Figure`, `FigureCanvasTkAgg`, `tk.Frame` | Current figure and its container. |
| `detailed_ax1` … `detailed_ax4` | `Axes` or `None` | Arrhenius, Spectra, Transient map, RW map. |
| `detailed_leg1`, `detailed_leg2`, `detailed_legM`, `detailed_legRW` | `Legend` or `None` | Legends of those panels. |
| `detailed_annBox` | `Annotation` | Arrhenius results box. |
| `detailed_lastResMw`, `detailed_lastResStd`, `detailed_lastNt` | dict, dict/None, float | Last run's results. |
| `detailed_loadingBusy`, `detailedProcessingBusy` | bool (or `None` before first use) | Load / Run in progress. |
| `detailed_executor` | `ProcessPoolExecutor` or `None` | The tab's single worker process. Shut down by `DLTSGUI_MainWindow.py` on exit. |
| `detailed_hitTestStale` | bool | True between a canvas resize and its redraw (drag hit-testing). |
| `detailed_*Var`, `detailed_stdEntries` | Tk variables | All control values (see tables above). |
| `detailed_loadButton`, `detailed_runButton`, `detailed_loadInfoLabel`, `detailed_statusLabel`, `detailed_resultsText` | widgets | Buttons, labels, Results text. |
| read: `tabControl`, `detailedAnalysisTab`, `root`, `log_to_textbox` | | Main-window objects. |

## Analysis method

Times are in ms unless noted; temperatures are stored in °C and converted with `T_K = T_C + 273.15`; capacitance is in pF (as returned by the extractors).

**Step 1. Load transients** (`_load_detailed_data`). The folder format is detected in this order:

1. **ZI single-file export**: a file matching `imps_0_sample_param1_avg_header*.csv` directly in the folder. Parsed by `liveDataTab._compute_zi_dataset`; temperatures come from the header's `history_name` (`<n>C_...`), one chunk per temperature; grid offset/delta/chunk size come from the header.
2. **ZI subfolder-per-temperature export** (the original `DLTS_APP.py` format): subfolders named like `0C`, `n10C`, `120C_000`, each with its own `imps_0_sample_param1_avg_<n>.csv` and header. Parsed by `liveDataTab._compute_zi_subfolder_dataset`; chunk 0 of each file is used; grid parameters from each subfolder's header (defaults −0.001 s, 1.86667e-5 s, 32768 if unreadable).
3. **Legacy per-temperature files**: names matching `^[npNP]\d+([pP]\d+)?[cC]?(_\d+)?\.(txt|csv|h5)$` (e.g. `p25p0.h5`, `n10p0.txt`). Parsed by `liveDataTab._compute_legacy_dataset`. For `.txt` (JSON) and `.h5`: `ImpedanceIm · 1e12` is split at each fall of `AuxInput1` through the midpoint of its 0.01/99.99 percentile levels, cut into blocks of `int(rb_ms·1e-3 / 1.8666666666666665e-05)` samples, and averaged; time axis `k · 1.8666666666666665e-05 · 1000` ms, starting at 0 at the trigger.

For the ZI formats the time axis is `(grid_col_offset + k · grid_col_delta) · 1000` ms, and values below 1e-3 in magnitude are scaled by 1e12 (F to pF).

C∞ is then recomputed for every temperature, independent of format:

```text
mask  = (t_ms >= cinf_lo * rb_ms) & (t_ms <= cinf_hi * rb_ms)
C_inf = nanmean(cap[mask])      if any sample is in the mask
      = nanmean(cap)            otherwise
```

With the defaults: mean over 200 to 450 ms of a 500 ms reverse bias.

**Step 2. Prepare the C(t) read-off** (`_prepare_signal_data`, `_denoise_transient`, `_cap_at`). Once per run, each transient is optionally denoised with the `impdData` filters at the same settings as `impdData.filter_emissions`: `pca` (`window_size=100`), `wavelet` (`db4`, `level=4`, `mode='soft'`), `sgolay` (`window_size=None`, `order=2`), `lowess` (`fraction=None`). For Smoothed C a `scipy.interpolate.CubicSpline` is built through the (denoised) curve. `_cap_at(rec, t)` returns the spline value (Smoothed C) or the nearest sample (Measured C; ties go to the earlier sample). C∞ is not recomputed after denoising.

**Step 3. Rate windows** (`_compute_detailed_analysis`):

```text
t1_k = logspace(log10(t1_min), log10(t1_max), N)     # ms
t2_k = ratio * t1_k                                  # ms
e_n  = ln(t2 / t1) / ((t2 - t1) * 1e-3)              # s^-1
```

Defaults give 16 windows from 5/25 ms (e_n = 80.47 s⁻¹) to 90/450 ms (e_n = 4.47 s⁻¹). The five standard windows are processed the same way.

**Step 4. DLTS signal and its error** (`_rate_window_signal`, `_cap_noise_at`):

```text
S(T)    = (C(t2) - C(t1)) / C_inf                         # dimensionless
sigma_S = hypot(noise(t1), noise(t2)) / |C_inf|
noise(t) = sqrt( sum(d2^2) / (6 * len(d2)) ),  d2 = c[k-1] - 2 c[k] + c[k+1]
```

`noise(t)` is the Rice (1984) second-difference estimator over the samples `cap_raw[i-25 : i+26]`, where `i = searchsorted(t_ms, t)`. It always uses the raw (not denoised) transient. It returns NaN when fewer than 5 samples are available.

**Step 5. Peak per window** (`_peak_from_signal`, `_find_peak_full`):

```text
mask = (T_K >= T_min) & (T_K <= T_max)
S_m  = S[mask];  if max(S_m) < |min(S_m)|: S_m = -S_m          # make the peak positive
skip the window if max(S_m) <= 0.05 * max(|S|)  (over all temperatures)
```

- `Smoothing Spline (bootstrap)` (`_find_peak_spline`): `impdData._smoothingSpline_peakFinder(T, S_m, signalYErr=sigma_S)`. Weighted `UnivariateSpline(k=3, s=n)` when all errors are valid, otherwise `s = n · Rice noise variance of S`. T_p is the argmax of |spline| on a 100 000-point grid; T_p error is the standard deviation of 200 bootstrap refits. On an exception: the grid point with the largest S, no error.
- `Parabolic fit (lmfit)` (`_find_peak_parabolic`, `_vertex_stderr`): lmfit `QuadraticModel` on the 5 points (hw = 2) around the grid maximum, in `x = T - T_ref`, weights `1/sigma_S` when valid. If `a < 0` and the vertex lies inside those points: `T_p = T_ref - b/(2a)`, with

```text
J       = (b / (2 a^2), -1 / (2 a))
var(T_p) = J · Cov(a, b) · J^T
```

  Otherwise T_p = T_ref with no error. No error either when `result.covar` is `None` or `nfree < 1`.

**Step 6. Arrhenius fit** (`_arrhenius_fit`, `_fit_arrhenius_line`):

```text
x = 1000 / T_p            # K^-1 (x 1000)
y = ln(e_n / T_p^2)       # ln(s^-1 K^-2)
```

`_find_peak` reports no T_p error for a peak on the edge of the search range (the signal is still rising out of the range, so the grid end is not a real peak) and for any error below `MIN_TP_ERR_K`, whichever peak method is used. Windows with no T_p error are excluded from the fit (`fit_mask`) unless fewer than 3 windows have errors; then all windows are fitted. Fewer than 2 windows returns `None`.

`_fit_arrhenius_line` first fits `y = slope·x + intercept` unweighted (lmfit `LinearModel`). If every T_p error is finite and > 0, it iterates up to 10 times:

```text
sig_eff = | -2/T_p + 1000 * slope / T_p^2 | * sigma_Tp      # effective variance
refit with weights = 1 / sig_eff
stop when |slope_new - slope_old| <= 1e-9 * max(|slope_old|, 1)
```

**Step 7. Defect parameters** (`_arrhenius_fit`, kB = `KB_EV` = `8.617333262145e-5` eV/K):

```text
E_a      = -slope * 1000 * kB                 # eV
dE_a     = slope_stderr * 1000 * kB           # eV
sigma_n  = exp(intercept) / gamma             # cm^2
dsigma_n = sigma_n * intercept_stderr         # cm^2
R^2      = lmfit rsquared
```

With fewer than 3 fitted points, slope/intercept errors and the covariance are set to `None`.

**Step 8. Trap density** (`_trap_density`):

```text
S_ref(T) = (C(rb_ms) - C(2.0 ms)) / C_inf
N_T      = 2 * max_T |S_ref(T)| * Nd              # cm^-3 (Nd in cm^-3)
```

This uses all loaded temperatures, not only the peak-search range.

**Step 9. Display arrays.**

- Spectra (`_prepare_spectra`): windows at indices `round(linspace(0, N-1, min(nSpectra, N)))`; curve `S(T) · 1e3`.
- Transient map (`_prepare_transient_map`): time range `max(2.0, t[1])` to `0.95 · rb_ms` ms; up to 250 log-spaced sample indices; `Z = (C(t) - C_inf) / C_inf`, displayed as `Z · 1e5`; 64 color levels between the 1st and 99th percentile. Needs at least 10 time points.
- τ overlay (`_detailed_plot_transient_map`): `e_n(T) = gamma · sigma_n · T^2 · exp(-E_a / (kB T))`, `tau = 1/e_n` (s), over T from `min(T) − 20` to `max(T) + 20` K.
- Rate-window map (`_prepare_rate_window_map`): 100 log-spaced t1 from t1_min to t1_max, `t2 = ratio · t1`; for every (window, temperature): `x = 1/(kB T)` (eV⁻¹), `y = T^2 / e_n` (K² s), `z = 2 |S|` (= N_T/N_D); points with `z < 1e-8` or `|C_inf| < 1e-30` skipped. Linearly interpolated (`scipy.interpolate.griddata`) onto 220 × 220 points in (x, log10 y); log color scale from the 2nd percentile (≥ 1e-8) to the 98th percentile (≥ 10 × low). Overlay line `y = exp(E_a · x) / (gamma · sigma_n)`. Needs at least 6 points.
- Confidence band on the Arrhenius panel: `half = 2 · sqrt(var_m · x^2 + var_b + 2 x cov_mb)`.
- Arrhenius error bars (`_detailed_arrhenius_errorbars`): `dx = 1000 · dT / T^2`, `dy = 2 · dT / T`.

### Executor model

`_detailed_load_data` and `_detailed_run_analysis` each start a daemon `threading.Thread`. That thread submits the pure function (`_load_detailed_data` or `_compute_detailed_analysis`) to `dltsc.detailed_executor`, a `ProcessPoolExecutor(max_workers=1)` created on first use, and blocks on `future.result()`. The result is handed back to the Tk main thread with `dltsc.root.after(0, apply)`, where widgets are updated and the figure is drawn. The worker process has its own GIL, so parsing and fitting do not stall the GUI. If the worker dies (`BrokenProcessPool`), the executor is dropped and the next Load/Run creates a new one. Load and Run are mutually exclusive (`detailed_loadingBusy`, `detailedProcessingBusy`); both buttons are disabled while either runs. The whole data dict is pickled to the worker on every Run.

## Functions

### construct_detailedAnalysisTab()

Adds the **Detailed Analysis** tab to `dltsc.tabControl` and builds all its widgets.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | |

**Returns** `None`.

**Side effects** `dltsc.tabControl.add(dltsc.detailedAnalysisTab, text='Detailed Analysis')`, `tabControl.pack(expand=1, fill="both")`; creates every `dltsc.detailed_*` variable and widget listed above with the defaults listed above. Run starts disabled. `dltsc.detailedAnalysisTab` must already exist as a `ttk.Frame` in the notebook.

**Called by** `DLTSGUI_MainWindow.py` (`deT.construct_detailedAnalysisTab()`).

**Example** Needs a Tk root and notebook; not useful outside the GUI.

## Internal helpers

### Computation helpers (no Tk; safe outside the GUI)

#### _folder_to_tempC(name)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | | Folder name. |

**Returns** Temperature in °C as float (`'n10C'` → -10.0, `'120C_000'` → 120.0), or `None` if `name` does not match `_FOLDER_RE`.

**Side effects** None. **Called by** nothing in the current code (the loader uses `liveDataTab`'s own identical pattern).

#### _denoise_transient(t_ms, cap, method)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `t_ms` | ndarray | | Time axis, ms. |
| `cap` | ndarray | | Capacitance, pF. |
| `method` | str | | `'pca'`, `'wavelet'`, `'sgolay'`, `'lowess'`; anything else returns `cap` unchanged. |

**Returns** Denoised copy of `cap` (float ndarray, truncated to `len(cap)`). Filter settings are in Step 2.

**Side effects** None. **Called by** `_prepare_signal_data`.

#### _prepare_signal_data(data, temps, signal_method, denoise)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `data` | dict | | `T_C -> (t_ms, cap, c_inf)` from `_load_detailed_data`. |
| `temps` | list of float | | Temperatures to prepare (°C). |
| `signal_method` | str | | `SIGNAL_METHOD_MEASURED` or `SIGNAL_METHOD_SMOOTHED`. |
| `denoise` | str | | One of `DENOISE_OPTIONS`. |

**Returns** dict `T_C -> (t_ms, cap_used, c_inf, cap_raw, spline)`. `cap_used` is denoised (or raw for `None (raw)`); `spline` is a `CubicSpline` through `cap_used` for Smoothed C, else `None`.

**Side effects** None. **Called by** `_compute_detailed_analysis`.

#### _cap_at(rec, tv_ms)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `rec` | tuple | | One `_prepare_signal_data` record. |
| `tv_ms` | float or ndarray | | Time(s), ms. |

**Returns** C at `tv_ms`: spline value, or nearest sample (ties to the earlier sample). Scalar in, float out; array in, array out. Times outside the data give the end sample (Measured C) or a spline extrapolation (Smoothed C).

**Side effects** None. **Called by** `_rate_window_signal`, `_prepare_spectra`, `_prepare_transient_map`, `_prepare_rate_window_map`, `_compute_detailed_analysis`.

#### _cap_noise_at(t_ms, cap, tv_ms, hw=25)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `t_ms` | ndarray | | Time axis, ms (sorted). |
| `cap` | ndarray | | Raw capacitance, pF. |
| `tv_ms` | float | | Time where the noise is wanted, ms. |
| `hw` | int | `25` | Half-width of the sample window. |

**Returns** 1σ sample noise (same unit as `cap`) from the Rice second-difference estimator (Step 4), or `NaN` if fewer than 5 samples fall in the window.

**Side effects** None. **Called by** `_rate_window_signal`; `dataAnalysisTab._calculate_rate_windows`.

#### _rate_window_signal(temps, data, t1, t2)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `temps` | list of float | | Temperatures, °C. |
| `data` | dict | | `_prepare_signal_data` records. |
| `t1`, `t2` | float | | Gate times, ms. |

**Returns** `(S, S_err)`, two ndarrays in `temps` order: `S = (C(t2) - C(t1)) / C_inf` and its 1σ error (Step 4).

**Side effects** None. **Called by** `_compute_arrhenius`.

#### _valid_errors(err)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `err` | ndarray or None | | Candidate 1σ errors. |

**Returns** `err` if it is not `None` and every entry is finite and > 0, else `None`.

**Side effects** None. **Called by** `_find_peak_spline`, `_find_peak_parabolic`, `_fit_arrhenius_line`; `dataAnalysisTab._calculate_rate_windows`.

#### _find_peak(T_arr, S_arr, S_err, method)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `T_arr` | ndarray | | Temperatures, K. |
| `S_arr` | ndarray | | Signal (positive-going peak expected). |
| `S_err` | ndarray | | 1σ errors of `S_arr`. |
| `method` | str or callable | | `PEAK_METHOD_SPLINE` selects the spline; `PEAK_METHOD_PARABOLIC` (or any other string) the parabola; a callable `(T, S, S_err) -> (Tp, Tp_err, xFit, yFit)` is used as is (Quick Analysis passes its lmfit curve-fit finders this way). |

**Returns** `(Tp, Tp_err)` in K. `Tp_err` is `None` when the method gave none, when the peak is on the edge of `T_arr` (`_peak_on_edge`), or when the error is below `MIN_TP_ERR_K` (`_guard_peak_error`); `_arrhenius_fit` then leaves the window out of the weighted fit.

`_find_peak_full(T_arr, S_arr, S_err, method)` takes the same arguments and returns `(Tp, Tp_err, xFit, yFit)`: the same peak plus the fitted curve for plotting (`None, None` for the parabola). `_find_peak` is `_find_peak_full(...)[:2]`.

**Side effects** None. **Called by** `_peak_from_signal`.

**Example**

```python
T = np.arange(300.0, 330.0, 5.0)
deT._find_peak(T, (T - 290) / 100, np.full(T.size, 1e-3), deT.PEAK_METHOD_SPLINE)   # (325.0, None): edge peak
```

#### _peak_on_edge(T_arr, Tp)

`True` if `Tp` is within `EDGE_PEAK_FRAC` × the smallest grid step of either end of `T_arr`, or outside it, or if `T_arr` has fewer than 2 points.

#### _guard_peak_error(T_arr, Tp, Tp_err)

**Returns** `float(Tp_err)`, or `None` when `_peak_on_edge(T_arr, Tp)` or when `Tp_err` is `None`, not finite, or below `MIN_TP_ERR_K`. **Called by** `_find_peak_full`.

#### _find_peak_spline(T_arr, S_arr, S_err)

Parameters as `_find_peak`. **Returns** `(float(Tp), Tp_err, xFit, yFit)` from `impdData._smoothingSpline_peakFinder` (Step 5), or `(T at argmax(S_arr), None, None, None)` on an exception. **Side effects** None. **Called by** `_find_peak_full`.

#### _find_peak_parabolic(T_arr, S_arr, S_err=None, hw=2)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `T_arr` | ndarray | | Temperatures, K. |
| `S_arr` | ndarray | | Signal. |
| `S_err` | ndarray or None | `None` | 1σ errors; used as weights `1/S_err` when valid. |
| `hw` | int | `2` | Points on each side of the grid maximum (5 points in total). |

**Returns** `(Tp, Tp_err)`: the vertex and its error from `_vertex_stderr` when the parabola opens downward and the vertex is inside the fitted points; otherwise `(T_ref, None)`. Also `(T_ref, None)` when fewer than 3 points are available or the fit raises.

**Side effects** None. **Called by** `_find_peak_full`.

#### _vertex_stderr(result, a, b)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `result` | lmfit `ModelResult` | | Quadratic fit. |
| `a`, `b` | float | | Fitted quadratic and linear coefficients. |

**Returns** `sqrt(J · Cov(a,b) · J^T)` with `J = (b/(2a²), −1/(2a))`, or `None` if `covar` is `None`, `nfree < 1`, or the variance is negative or not finite.

**Side effects** None. **Called by** `_find_peak_parabolic`.

#### _fmt_pm(val, err, fmt, sep=' ± ')

| Name | Type | Default | Meaning |
|---|---|---|---|
| `val` | float | | Value. |
| `err` | float or None | | Error. |
| `fmt` | str | | Format spec, e.g. `'.3f'`. |
| `sep` | str | `' ± '` | Separator. |

**Returns** `'val ± err'` or `'val'` when `err` is `None`. `_fmt_pm(1.23456, 0.012, '.3f')` → `'1.235 ± 0.012'`.

**Side effects** None. **Called by** plotting, results and status code.

#### _load_detailed_data(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi)

Loads every temperature in a run folder (Step 1).

| Name | Type | Default | Meaning |
|---|---|---|---|
| `base` | str | | Run folder path. |
| `grid_off` | float | | Ignored. |
| `grid_dt` | float | | Ignored. |
| `chunk_size` | int | | Ignored. |
| `rb_ms` | float | | Reverse-bias duration, ms. Sets the legacy block length and the C∞ window. |
| `cinf_lo` | float | | Start of the C∞ window, fraction of `rb_ms`. |
| `cinf_hi` | float | | End of the C∞ window, fraction of `rb_ms`. |

**Returns** `(data, temps, errorMsgs)`: `data[T_C] = (t_ms, cap_pF, C_inf)`; `temps` sorted °C list; `errorMsgs` list of per-file problems. `({}, [], errorMsgs)` when nothing is recognized.

**Side effects** Reads files only. `os.listdir(base)` raises if `base` does not exist.

**Called by** `_detailed_load_data` (in the worker process); `tests/test_hdf5_analysis.py`; `benchmarks/bench_hdf5.py`; `benchmarks/hardware/hw_analyze.py`.

**Example** (verified on the HDF5 run folder: 6 temperatures, 321 samples each, 0 to 5.973 ms):

```python
import os
os.environ['LOKY_MAX_CPU_COUNT'] = '8'
import matplotlib; matplotlib.use('Agg')
import detailedAnalysisTab as daT

data, temps, errs = daT._load_detailed_data(
    r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655", None, None, None, 6.0, 0.4, 0.9)
print(temps)            # [25.0, 30.0, 35.0, 40.0, 45.0, 50.0]
t_ms, cap, c_inf = data[25.0]
print(len(t_ms), t_ms[1], t_ms[-1], c_inf)   # 321 0.018666... 5.9733... ~5.09e6
```

The JSON run folder `C:\Users\spencer\Desktop\DATA\DLTS\092326\101901` (`p100p0.json` etc.) returns `({}, [], [])`: `.json` is not a recognized extension, and no error message is produced.

#### _cinf_range_mean(t_ms, cap, rb_ms, cinf_lo=DEFAULT_CINF_LO, cinf_hi=DEFAULT_CINF_HI)

C∞ of one averaged transient: `nanmean(cap)` over `cinf_lo·rb_ms ≤ t_ms ≤ cinf_hi·rb_ms`, or over the whole transient if no sample falls in that range. **Called by** `_load_detailed_data`; `dataAnalysisTab._transient_records`.

#### _fit_arrhenius_line(x, y, Tp, Tp_err)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `x` | ndarray | | `1000 / Tp`. |
| `y` | ndarray | | `ln(e_n / Tp²)`. |
| `Tp` | ndarray | | Peak temperatures, K. |
| `Tp_err` | ndarray | | 1σ errors of `Tp`, K (NaN allowed; any NaN makes the fit unweighted). |

**Returns** `(lmfit ModelResult, weighted)`. `weighted` is `False` when `Tp_err` fails `_valid_errors`. Algorithm in Step 6.

**Side effects** None. **Called by** `_arrhenius_fit`.

**Example** (verified; recovers 0.600 eV from exact points):

```python
import numpy as np
import detailedAnalysisTab as daT
Tp = np.array([300., 310., 320., 330.])
en = 1.66e21 * 1e-15 * Tp**2 * np.exp(-0.6 / (8.617333e-5 * Tp))
res, weighted = daT._fit_arrhenius_line(1000 / Tp, np.log(en / Tp**2), Tp, np.full(4, 0.5))
print(-res.params['slope'].value * 1000 * 8.617333e-5, weighted)   # 0.6000000000000011 True
```

#### _emission_rate(t1, t2)

`ln(t2/t1) / ((t2 − t1)·1e-3)`, s⁻¹, for t1 and t2 in ms.

#### _peak_from_signal(T_K, S_full, S_err_full, t_peak_lo, t_peak_hi, peak_method=PEAK_METHOD_SPLINE, peak_min_frac=PEAK_MIN_FRAC)

One window's peak from its S(T) curve (Step 5). Shared with Quick Analysis.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `T_K` | ndarray | | Temperatures, K. |
| `S_full`, `S_err_full` | ndarray, ndarray or None | | S(T) and its 1σ errors over all temperatures. |
| `t_peak_lo`, `t_peak_hi` | float | | Search range, K (`±inf` allowed). |
| `peak_method` | str or callable | `PEAK_METHOD_SPLINE` | As `_find_peak`. |
| `peak_min_frac` | float | `0.05` | Skip threshold, fraction of max\|S\|. |

**Returns** `dict(skipped=True)` when no point is in range or the peak is at most `peak_min_frac·max|S_full|`; otherwise `dict(skipped=False, Tp, Tp_err, S_peak, sign, xFit, yFit)`. `S_peak` is the in-range grid maximum of `sign·S`, given back in the curve's own sign; `yFit` is in the curve's own sign too.

**Called by** `_compute_arrhenius`; `dataAnalysisTab._window_peaks`, `dataAnalysisTab._calculate_rate_windows`.

#### _arrhenius_fit(en_list, Tp_list, Tp_err_list, gamma)

Steps 6 and 7 on a list of peaks. Shared with Quick Analysis.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `en_list` | list of float | | e_n, s⁻¹. |
| `Tp_list` | list of float | | T_p, K. |
| `Tp_err_list` | list of float/None | | T_p errors, K; `None` or NaN = no error. |
| `gamma` | float | | γ, cm⁻² s⁻¹ K⁻². |

**Returns** `None` when fewer than 2 windows can be fitted; otherwise the dict described under `_compute_arrhenius` below, without `Sp_arr`, `peak_method` and `detail`.

**Called by** `_compute_arrhenius`; `dataAnalysisTab._quick_arrhenius`.

#### _trap_density(data, temps, rb_ms, nd)

Step 8: `2 · max_T |(C(rb_ms) − C(2 ms)) / C∞| · nd`, cm⁻³, from `_prepare_signal_data` records. **Called by** `_compute_detailed_analysis`; `dataAnalysisTab._quick_arrhenius`.

#### _compute_arrhenius(windows, temps, data, gamma, t_peak_lo, t_peak_hi, peak_method=PEAK_METHOD_SPLINE, peak_min_frac=0.05)

Steps 4 to 7 for one set of windows: `_rate_window_signal` and `_peak_from_signal` per window, then `_arrhenius_fit`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `windows` | list of (t1, t2) | | Gate times, ms. |
| `temps` | list of float | | Temperatures, °C. |
| `data` | dict | | `_prepare_signal_data` records. |
| `gamma` | float | | γ, cm⁻² s⁻¹ K⁻². |
| `t_peak_lo`, `t_peak_hi` | float | | Peak-search range, K. |
| `peak_method` | str | `PEAK_METHOD_SPLINE` | Peak finder. |
| `peak_min_frac` | float | `0.05` | Skip a window if its in-range peak is ≤ this fraction of max \|S\| over all temperatures. |

**Returns** `None` when fewer than 2 windows can be fitted; otherwise a dict:

| Key | Meaning |
|---|---|
| `en_arr`, `Tp_arr`, `Tp_err_arr`, `Sp_arr` | e_n (s⁻¹), T_p (K), T_p error (K, NaN if none), peak S, for every kept window. |
| `x`, `y` | 1000/T_p and ln(e_n/T_p²) for every kept window. |
| `fit_mask` | bool array, windows used in the fit. |
| `N`, `N_excluded` | Fitted and excluded window counts. |
| `Et`, `Et_se` | E_a and its error, eV. |
| `sigma`, `sigma_se` | σ_n and its error, cm². |
| `slope`, `slope_se`, `intercept`, `intercept_se`, `covar` | Line parameters; `covar` is the lmfit `[slope, intercept]` covariance (or `None`). |
| `R2`, `redchi`, `weighted`, `peak_method` | Fit quality and settings. |
| `detail` | list of `(t1, t2, e_n, T_p in °C, T_p error or None, peak S)`. |

**Side effects** None. **Called by** `_compute_detailed_analysis`.

**Example** see `_compute_detailed_analysis`.

#### _prepare_spectra(mw, temps, data, n_spectra)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `mw` | list of (t1, t2) | | Multi-windows, ms. |
| `temps` | list of float | | °C. |
| `data` | dict | | `_prepare_signal_data` records. |
| `n_spectra` | int | | Number of spectra. |

**Returns** list of `(k, t1, t2, e_n, S·1e3)` (Step 9). **Side effects** None. **Called by** `_compute_detailed_analysis`.

#### _prepare_transient_map(temps, data, rb_ms)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `temps` | list of float | | °C. |
| `data` | dict | | `_prepare_signal_data` records. |
| `rb_ms` | float | | Reverse-bias duration, ms. |

**Returns** `dict(t_s, Z_disp, levels)` (time in s, `(C − C_inf)/C_inf · 1e5` with shape (n_t, n_T), 64 levels), or `None` if fewer than 10 time points fall in the range. Uses the first temperature's time axis for all. **Side effects** None. **Called by** `_compute_detailed_analysis`.

#### _prepare_rate_window_map(temps, data, t1_min, t1_max, ratio)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `temps` | list of float | | °C. |
| `data` | dict | | `_prepare_signal_data` records. |
| `t1_min`, `t1_max` | float | | t1 range, ms. |
| `ratio` | float | | t2/t1. |

**Returns** `dict(Xi, Yi, Zi, z_lo, z_hi, x_min, x_max)`: 220 × 220 grids (Xi in eV⁻¹, Yi in K² s, Zi masked N_T/N_D), color limits, and x range; or `None` if fewer than 6 points. **Side effects** None. **Called by** `_compute_detailed_analysis`.

#### _compute_detailed_analysis(data, temps, p)

Everything **Run Analysis** computes. Runs in the worker process.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `data` | dict | | `_load_detailed_data` output. |
| `temps` | list of float | | °C. |
| `p` | dict | | Parameter snapshot with keys `signalMethod`, `denoise`, `t1Min`, `t1Max`, `nWin`, `ratio`, `stdWins`, `gamma`, `nd`, `tpLo`, `tpHi`, `peakMethod`, `rbMs`, `nSpectra`, `showSpectra`, `showTmap`, `showRwm` (the GUI also passes `showStd`, `showTau`, used only for plotting). |

**Returns** `dict(resMw, resStd, mw, T_K, Nt, spectra, tmap, rwm)`. `resStd` may be `None`; `spectra`, `tmap`, `rwm` are `None` when their panel is off or cannot be built.

**Side effects** None. Raises `ValueError('Multi-window: no peaks found. Check t1 range and temperature bounds.')` when the multi-window fit returns `None`.

**Called by** `_detailed_run_analysis` (through `_run_in_detailed_process`).

**Example** (verified; synthetic 0.60 eV, σ = 1e-15 cm² trap, 0 to 120 °C, GUI defaults):

```python
import os
os.environ['LOKY_MAX_CPU_COUNT'] = '8'
import numpy as np
import matplotlib; matplotlib.use('Agg')
import detailedAnalysisTab as daT

rng = np.random.default_rng(1)
t_ms = np.arange(0, 500.0, 1.8666666666666665e-02)
data = {}
for tc in np.arange(0.0, 121.0, 5.0):
    TK = tc + 273.15
    en = 1.66e21 * 1e-15 * TK**2 * np.exp(-0.60 / (8.617333e-5 * TK))
    cap = 100.0 * (1 - 0.01 * np.exp(-en * t_ms * 1e-3)) + rng.normal(0, 1e-3, t_ms.size)
    mi = (t_ms >= 200) & (t_ms <= 450)
    data[float(tc)] = (t_ms, cap, float(np.mean(cap[mi])))
temps = sorted(data)

p = dict(signalMethod=daT.SIGNAL_METHOD_MEASURED, denoise=daT.DENOISE_NONE,
         nWin=16, t1Min=5.0, t1Max=90.0, ratio=5.0,
         stdWins=[(5, 25), (10, 50), (20, 100), (50, 250), (100, 490)],
         gamma=1.66e21, nd=3.2e14, tpLo=250.0, tpHi=400.0,
         peakMethod=daT.PEAK_METHOD_SPLINE, rbMs=500.0, nSpectra=5,
         showSpectra=True, showTmap=True, showRwm=True)
out = daT._compute_detailed_analysis(data, temps, p)
r = out['resMw']
print(daT._fmt_pm(r['Et'], r['Et_se'], '.4f'))       # 0.5968 ± 0.0032
print(daT._fmt_pm(r['sigma'], r['sigma_se'], '.3e')) # 8.904e-16 ± 1.076e-16
print(f"{out['Nt']:.3e}")                            # 6.236e+12
```

On the same data the five standard windows give E_a = 0.5979 ± 0.0042 eV.

### Worker process helpers

#### _get_detailed_executor()

Returns `dltsc.detailed_executor`, creating a `ProcessPoolExecutor(max_workers=1)` on first use. It is this tab's own executor, separate from the Qualitative Analysis one.

#### _run_in_detailed_process(fn, *args)

Submits `fn(*args)` to the worker and blocks for the result. Call it only from a background thread. On `BrokenProcessPool` it sets `dltsc.detailed_executor = None` and re-raises.

### GUI helpers

#### _set_detailed_buttons_state(state)

Sets **Load Data** to `state`. **Run Analysis** is disabled for `'disabled'`; for any other state it is enabled only if `dltsc.detailed_data` is non-empty.

#### _detailed_browse_folder()

**Browse** command. Folder dialog; sets `detailed_baseVar` and logs the folder contents.

#### _detailed_load_data()

**Load Data** command. Returns silently if a load or run is in progress; logs `please select a valid data folder.` if the path is not a directory. Otherwise reads the Grid, RB and C∞ variables, runs `_load_detailed_data` in the worker (from a daemon thread), and on the main thread stores `dltsc.detailed_data` / `dltsc.detailed_temps`, updates the info and status labels, and logs each load error. With zero temperatures it reports `No recognizable data found (checked ZI single-file, ZI subfolder-per-temperature, and legacy per-temperature formats).`

#### _detailed_run_analysis()

**Run Analysis** command. Logs `load data first.` without data; returns silently when busy. Snapshots every parameter into a dict, runs `_compute_detailed_analysis` in the worker, then on the main thread calls `_detailed_plot` and `_detailed_write_results`, stores `detailed_lastResMw`, `detailed_lastResStd`, `detailed_lastNt`, and sets the status label. Errors appear as `Error: <message>` in the status label and the log.

#### _detailed_plot(out, params)

Destroys the old canvas, builds a new `Figure` with the layout from the Figure table, draws the Arrhenius panel (fit line, 2σ band, colored points, excluded points, optional standard fit, colorbar, results box, °C top axis, legend) and the optional panels, embeds it with `FigureCanvasTkAgg` and a toolbar, and installs drag handlers on each legend and the results box. Uses `Figure()` rather than `plt.figure()` so no extra pyplot window opens. It does not call `draw()`; the resize after packing triggers the single render.

#### _detailed_arrhenius_errorbars(ax, res, color)

Draws x/y error bars (`dx = 1000·dT/T²`, `dy = 2·dT/T`) for fitted windows that have a T_p error.

#### _detailed_install_drag(canvas, fig, artist, kind)

Connects `button_press_event`, `motion_notify_event` and `button_release_event` so a left-drag moves a legend (`kind='legend'`, updates `artist._loc`) or annotation (`kind='annot'`, updates `artist.xyann`). Redraws once before hit-testing only when `dltsc.detailed_hitTestStale` is True. Contains nested `_on_press`, `_on_motion`, `_on_release`. `_detailed_plot` also defines nested `_mark_stale` / `_mark_fresh` that set `detailed_hitTestStale` on resize and draw events.

#### _detailed_plot_transient_map(ax, res_mw, T_K, tmap, params)

Draws the transient map contours, colorbar and optional τ(T) overlay (Step 9). Returns the legend when the overlay was drawn, else `None`.

#### _detailed_plot_rate_window_map(ax, res_mw, rwm, params)

Draws the rate-window map with `pcolormesh` (log color scale), colorbar, Arrhenius line and 22 circles. Returns the legend.

#### _detailed_style_rwm_axes(ax)

Applies labels, title, white ticks and gray spines to the rate-window map axes.

#### _detailed_open_label_editor()

**Edit Labels & Legends** command. Builds the dialog described above. Nested helpers: `section(title)` (divider and heading), `axis_row(parent, label, current_text, current_size, setter_fn)` (text entry plus size spinbox), `apply_all()` (applies every edit and calls `draw_idle()`).

#### _detailed_write_results(res_mw, res_std, Nt, params)

Builds the Results text shown above and writes it into `dltsc.detailed_resultsText`. Nested `fit_block(res)` formats one fit.

#### _detailed_save_figure()

**Save Figure...** command. Logs a hint if there is no figure. `.svg`/`.eps`/`.pdf`: `savefig(path, bbox_inches='tight')`; other extensions: `savefig(path, dpi=180, bbox_inches='tight', facecolor=SURFACE)`. Save errors are logged.

#### _detailed_export_txt()

**Export Results to TXT** command. Logs a hint if Results is empty; otherwise writes it to the chosen file (UTF-8).

#### Nested helpers in construct_detailedAnalysisTab

`section(title)` draws a divider and an upper-case heading; `row(label, widget_factory, **kw)` packs a 15-character label and a widget; `spinbox(parent_, var, lo, hi, inc, fmt='%g', width=9)` builds a `ttk.Spinbox`.

## Notes and limitations

- The **ZI MFIA GRID** fields `Grid offset (s)`, `Grid dt (s)` and `Chunk size` have no effect. `_load_detailed_data` accepts them as `grid_off`, `grid_dt`, `chunk_size` and never uses them; ZI grid values come from each header CSV (or `liveDataTab` defaults).
- Legacy `.txt`/`.h5` files use each file's own `timeStampImps` spacing as the sampling interval; `samplingRateS=1.8666666666666665e-05` s is only the fallback for files without usable time stamps.
- `.json` run files are not loaded (the legacy filename pattern accepts `.txt`, `.csv`, `.h5` only), and the loader returns no error message for them.
- **C₀ Estimation Window** and **RB duration (ms)** are applied at load time for C∞. Changing them without reloading only changes the N_T reference time and the transient-map range.
- The legacy `.h5`/`.txt` extractor multiplies `ImpedanceIm` by 1e12 unconditionally. On the HDF5 test run this gives values near 5e6 "pF", so the stored channel is not a capacitance in F. S = ΔC/C∞ is a ratio and is unaffected by the scale, but the pF label is not meaningful there.
- Labels say ΔC/C₀, but every quantity is normalized by C∞ (the late-time mean).
- Edge peaks no longer dominate the fit. The spline finder puts a peak that is still rising out of the search range on the last grid point in every bootstrap sample, with an "error" of about 1e-13 K; earlier versions kept such windows in the weighted fit, where they swamped the rest. On the 23 Sep run with the GUI-default windows this gave Et = 90.967 ± 7.9e9 eV; now those six edge windows are excluded and the result is 0.693 ± 0.013 eV (0.685 ± 0.015 eV with windows suited to the data). Tests: `tests/test_detailed_peaks.py`.
- N_T is `2·max|S_ref|·Nd` with `S_ref = (C(rb_ms) − C(2 ms))/C∞`, taken over all loaded temperatures, not the peak range. Quick Analysis uses the same definition (`_trap_density`). If `rb_ms` is past the end of a transient, `_cap_at` returns the last sample (Measured C) or extrapolates the spline (Smoothed C).
- The standard-window fit is always computed and written to Results. **Show standard-window comparison** only controls drawing, and the Arrhenius x range includes the standard windows even when they are hidden.
- The Results line `slope = ... K` has the wrong unit. x is `1000/T`, so the slope is in units of 1000 K (slope = −E_a/(1000·kB)).
- The °C top axis uses `k − 273` (not 273.15) and only has ticks for 240 to 360 K.
- The τ overlay and the rate-window map are labeled `Z₁₂` / `Z₁/₂` (the 4H-SiC Z1/2 defect) for any data.
- If `_prepare_transient_map` finds equal 1st and 99th percentiles, it falls back to levels ±1e-4 in the ×1e5 display units, which is a tiny range.
- `_prepare_transient_map` builds its time axis from the first temperature and assumes all transients share it.
- In `_find_peak_parabolic` a vertex outside the 5 fitted points, or an upward-opening parabola, falls back to the grid maximum with no error; that window is then excluded from the weighted fit.
- A failed load keeps the previously loaded data, and **Run Analysis** stays enabled for that old data.
- `_detailed_export_txt` does not catch file-write errors.
- Figure edits made in **Edit Labels & Legends** are lost on the next run.
- Both analysis tabs use `KB_EV` = `8.617333262145e-5` eV/K. (Before, this tab used `8.617333e-5`; the difference in E_a is below 1e-7 relative.)
- The whole `detailed_data` dict is pickled to the worker process on every Run. For long sweeps with 500 ms transients this is tens of MB per run.

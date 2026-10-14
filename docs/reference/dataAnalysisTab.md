# dataAnalysisTab

## What it's for

`dataAnalysisTab.py` builds the **Quick Analysis** tab. It turns averaged capacitance transients (one per temperature) into double-boxcar DLTS spectra for five rate windows, deconvolves each spectrum into peaks inside user-chosen temperature regions, groups the same peak of every set into one trap, and fits one Arrhenius line per trap. For each trap it reports the defect activation energy, the apparent capture cross-section and the trap density. The code is a tkinter port of tabs 2 and 3 ("Rate Window Analysis" and "Arrhenius Defect Mapping") of `DrKayisScript.py`, with a **Peak Deconvolution** frame added between them. Its **Offline Data** column loads a saved data folder and extracts the averaged transients from it (tab 1 of that script, sharing the extraction code of the Live Tools tab).

The signal steps (C∞, S(T)) and the Arrhenius fit are the functions of [detailedAnalysisTab](detailedAnalysisTab.md). The peaks come from the deconvolution finders of [impedanceAnalysis_Tools](impedanceAnalysis_Tools.md#peak-deconvolution), not from Detailed Analysis' single-peak finder, so the tab's results are close to, but no longer identical with, the **Standard** result of Detailed Analysis. The old single-peak path is kept as helper functions for the tests that compare the two tabs. The region helpers (`dA._deconvolve_region` and friends) live in `detailedAnalysisTab.py`, whose Peak Regions can copy a Quick Analysis region's primitives. See "Matching Detailed Analysis" below.

## What the user sees

The tab has a fixed-width **Offline Data** column on the left and, to its right, a horizontal `tk.PanedWindow` with three resizable frames of equal starting width (480 px each), in the order the analysis flows. The left frame of the pane is **Rate Window Analysis**, the middle frame **Peak Deconvolution**, and the right frame **Arrhenius Defect Mapping**. Each frame has a plot with a matplotlib navigation toolbar on top and a scrollable control area underneath (requested height `QUICK_CONTROLS_HEIGHT` = 260 px). The mouse wheel scrolls the control area while the pointer is over it.

### Left column: "Offline Data"

Loads a saved data folder, extracts and averages its transients, and makes them the `Loaded Folder (Offline Data)` Data Source of Rate Window Analysis. This is where saved data is analyzed; the Qualitative Analysis frame of the Live Tools tab only follows a running experiment. The column is 230 px wide and scrolls with the mouse wheel while the pointer is over it (`_build_offlineDataFrame`). The folder scan and the extraction are the Live Tools tab's functions `liveDataTab._scan_folder` and `liveDataTab._extract_transients_async`.

**Directory Loader Config**

- **Select Source Folder** (`_browse_quick_folder(isAppend=False)`): folder picker **Select DLTS Source Folder**, starting in the last selected folder or the working directory. It first logs a one-line preview, `Offline Data: selected <path> -- N item(s): ... — <format guess>` (`liveDataTab._describe_folder_contents`). Then it scans the folder on a background thread and **replaces** the current dataset.
- **Append Source Folder** (`_browse_quick_folder(isAppend=True)`): folder picker **Select DLTS Source Folder to Append**. It **adds** that folder's temperatures to the current dataset. A temperature that is already loaded keeps its first-loaded copy, and the log lists the skipped ones. With nothing loaded yet, it behaves like **Select Source Folder**.
- Label: `Source: (none selected)`, then `Source: <folder>` or `Source: N folder(s) combined (latest: <folder>)`.

The three folder formats (ZI single CSV, ZI subfolder per temperature, legacy per-temperature files, tried in that order) are those of [liveDataTab](liveDataTab.md#_scan_folderdir_path). The output of **Run DLTS** is the legacy format. Every new load, including an append, clears the previous extraction (`dltsc.quickData_processedTransients = {}`), so the Data Source never mixes results from different datasets.

**Available Temperatures Filter**

- A multi-select listbox (8 rows high, scrolls) showing each temperature as `T °C`, sorted. After each load all entries are selected.
- **Select All** and **Clear All**.

**Timing Boundaries** (`dltsc.quickData_paramVars`)

| Label | Key | Default | Used for |
|---|---|---|---|
| Filling Duration (ms): | `fp_ms` | `1.0` | Display only |
| Reverse Bias (ms): | `rb_ms` | `500.0` | Extraction (legacy window length, `C_infinity` at 90 % of it) and the reverse-bias duration of the `Loaded Folder` source (Step 2 below) |

On **Select Source Folder** (not on an append) both fields are preset from the folder when it states them: from `runParams.txt` for a legacy run folder (fill = **State Disable Time** × 1000, reverse bias = **State Enable Time** × 1000), or from the `FP..ms` / `RB..ms` parts of a ZI folder name. The log shows `Offline Data: Reverse Bias set to R ms from the folder.` Otherwise the fields keep their values.

**Execution Action**

- **Extract & Average Transients** (`_extract_quick_transients`, bold, light green): extracts and averages the selected temperatures in the shared process pool and stores the result in `dltsc.quickData_processedTransients`. **Reverse Bias (ms)** must be a positive number, otherwise the log shows `Offline Data: Reverse Bias (ms) must be a positive number.`
- Status label: `Status: Idle`, `Loading <folder>...` / `Appending <folder>...`, `[ZI|Legacy|Mixed] N temperature step(s) from S source(s). Click Extract & Average.`, `Processing N temperature(s)...`, then `N of M temperature(s) extracted. Ready for Compute Boxcar Spectrums.` or `N of M temperature(s) extracted; see log for the rest.` Every skipped temperature is logged as `Offline Data: <reason>`.

**Select Source Folder**, **Append Source Folder** and **Extract & Average Transients** are disabled while a scan or an extraction runs (`_set_quick_buttons_state`).

### Pane, left frame: "Rate Window Analysis"

Plot: title "Multi-Window DLTS Signal Spectrum (Pseudo-Voigt Refinement)" before the first run, "Multi-Window DLTS Signal Spectrum" after a run. X axis "Temperature (K)", Y axis "DLTS Signal (ΔC / C∞)".

Controls, top row (two groups side by side):

| Group | Widget | Default | What it does |
|---|---|---|---|
| **Data Source** | read-only combobox | `Auto (first available)` | Chooses where the transients come from. Options: `Auto (first available)`, `Loaded Folder (Offline Data)`, `Live Run (Qualitative Analysis)`, `Automated/Live Data — Live`, `Automated/Live Data — Offline`. See "Data sources" below. |
| **Data Source** | status label | `No data source resolved yet.` | After each **Compute Boxcar Spectrums** click it shows `Using: <source> / <method> (<n> temperature(s)).`, or the reason nothing was computed. |
| **DLTS Signal Calculation** | `Method:` combobox | `Measured C (nearest sample)` | Options: `Measured C (nearest sample)`, `Smoothed C (spline-interpolated)`. |
| **DLTS Signal Calculation** | `Denoise (any Data Source):` combobox | `None (raw)` | Options: `None (raw)`, `pca`, `wavelet`, `sgolay`, `lowess`. With an `impdData` instance (Live/Offline) it picks `calculate_delC_normalized`'s raw or filtered emission; for averaged transients each transient is denoised with the same filter (`dA._denoise_transient`). |

Peak finding is no longer in this frame; it moved to the Peak Deconvolution frame.

**Configure Rate Windows (Double Boxcar)** group: five sets, two per row, each with a `t1 (ms):` and `t2 (ms):` entry. The defaults are Detailed Analysis' standard windows (`detailedAnalysisTab.DEFAULT_STD_WINDOWS`):

| Set | t1 (ms) | t2 (ms) |
|---|---|---|
| Set 1 | 5.0 | 25.0 |
| Set 2 | 10.0 | 50.0 |
| Set 3 | 20.0 | 100.0 |
| Set 4 | 50.0 | 250.0 |
| Set 5 | 100.0 | 490.0 |

The number of sets is the length of `DEFAULT_RATE_WINDOWS`.

**Compute Boxcar Spectrums** (blue button) runs `_calculate_rate_windows()`. It computes the DLTS signal S(T) of every set into `dltsc.rateWindow_signals`, updates the **Show** list of the Peak Deconvolution frame, and then calls `_run_deconvolution()`, which deconvolves every set, refills the peak table and redraws the plots. It does not search for peaks itself. On the spectrum plot each set is drawn as points `RW <n>` (with error bars when errors exist), each region's total deconvolution fit as a dashed line in the same colour (colour `C<n-1>`, fixed per set), and each extracted peak as a black `x` with a T_peak error bar. A peak with no usable T_peak error is a gray `x`. The bounds of every deconvolution region are dotted gray vertical lines. It logs a summary line to the app log.

**Extracted Peaks** table (`ttk.Treeview`, 6 rows visible, horizontal scrollbar): one row per deconvolved peak per set, with row id `w<set>r<region>p<peak>` (indices from 0). A set and region where the deconvolution found no peak gets one row with id `w<set>r<region>`, showing `R<n>` in the `Peak` column, `—` for T_peak and height, and `no peak` (the fit worked but gave no peak) or `fit failed` in the last column. Columns:

| Column | Content |
|---|---|
| `Window` | `Set n`. |
| `Peak` | Peak id and primitive, for example `R1P1 MirLogN` (short names: `MirLogN`, `Gauss`, `Lorentz`, `Voigt`, `pVoigt`, `Spline`). |
| `e_n (s⁻¹)` | Emission rate of the set, 2 decimals. |
| `T_peak (K)` | 2 decimals, `± err` when the peak has a usable error. |
| `Height ΔC/C∞` | Fitted peak height with its sign, 5 decimals, `± err` when available. |
| `Arrhenius fit` | `—` before the solver runs, or `no Tp error (edge)` / `no Tp error` for a peak without a usable T_peak error. After the solver runs: `used`, `excluded (no Tp error)`, `not selected` or `too few sets`. |

Selecting rows in the table (Ctrl/Shift-click for several) works on peaks (`_on_peak_table_select()`, bound to `<<TreeviewSelect>>`):

- The spectrum plot shows only the sets that have a selected row, and marks only the selected peaks (`_redraw_rate_window_plot()`). With no row selected every set and every peak is drawn.
- The Arrhenius solver uses only the selected peaks (`_selected_peak_rows()`), or every extracted peak when nothing is selected. After the solver runs, a peak left out by the selection reads `not selected`. The solver does not rerun by itself when the selection changes, so that column and the Arrhenius results describe the last solver run.
- Each selected peak that is on the Arrhenius plot from the last solver run gets a star in its set's spectrum colour (`C<n-1>`), with one legend entry `Selected peak(s)` (`_update_arrhenius_highlight()`). Selected peaks that the last solver run didn't plot get no star. With no selection there are no stars.
- The Peak Deconvolution plot switches to the set of the first selected row.

**Show All** (below the table) clears the selection.

### Pane, middle frame: "Peak Deconvolution"

Splits each set's S(T) into peaks, region by region. A region is a temperature range (K) and a list of primitives. Every set is deconvolved in every region with the same primitives, so the k-th peak of a region (counted from low T) is the same trap in every set. Its peak id is `R<region>P<k>` (from 1), and that id is what ties the peaks of the different sets into one trap for the Arrhenius solver.

Plot: two subplots sharing the X axis. The top one shows the displayed set's S(T) (points in the set's colour, with error bars when available) over the regions plus 8 % padding, each region's total fit as a black line `Total fit`, each primitive as a dashed, lightly filled curve `R<n> <short name>`, and each peak as a `▼` (black with a T_peak error bar, gray without a usable error) labelled with its peak id. Regions are shaded light gray, the selected one gold, and labelled `R<n>` at the top. Title `Peak Deconvolution — Set n (e_n = … s⁻¹)`. The bottom subplot shows the residuals (data − fit) of each region, divided by the point errors (`resid. / σ`) when the set has errors, else plain (`residual`). Dragging horizontally on the top plot (a matplotlib `SpanSelector`, minimum span 1 K) fills the **T (K)** entries with the dragged range.

| Group | Widget | Default | What it does |
|---|---|---|---|
| (top row) | `Show:` combobox | `Set 1` | The set the plot shows. Lists the sets of the last **Compute Boxcar Spectrums**. |
| (top row) | **Deconvolve All Sets** (green button) | | Runs `_run_deconvolution()` again with the current regions. Region and primitive edits only take effect after this click. |
| (no group) | fit-quality label | `No fit for this set yet.` | One line per region for the displayed set: `R<n>: χ²ᵣ = …, R² = …, k peak(s)` (plus a message when the fit did not converge), `R<n>: spline, k peak(s) above the prominence`, or the reason there is no fit. |
| **Regions (drag on the plot to pick a range)** | listbox | one region | One line per region: `R<n>: lo–hi K \| primitives` (short names joined by `+`, with `(prom. ≥ p)` for a spline region). Selecting a line loads its bounds and prominence into the entries and lists its primitives. |
| **Regions** | `T (K):` two entries (`from` `to`) | `250` to `400` | Region bounds. Also filled by dragging on the plot. Upper must exceed lower. |
| **Regions** | `Spline min prominence:` entry | `0.02` (`DEFAULT_PROMINENCE`) | For Smoothing Spline regions: the fraction of the region's largest \|S\| a peak must rise above its surroundings. Must be between 0 and 1. |
| **Regions** | **Add Region**, **Update Region**, **Remove Region** | | Add a region with the entered bounds and prominence (and no primitives yet), change the selected region, or remove it (later regions are renumbered). |
| **Primitives of the selected region (list peaks low → high T)** | listbox | | The primitives of the selected region, in order. |
| **Primitives** | combobox | `Mirrored Lognormal (left tail)` | Options: `Mirrored Lognormal (left tail)`, `Gaussian`, `Lorentzian`, `Voigt`, `Pseudo-Voigt`, `Constant Baseline`, `Linear Baseline`, `Smoothing Spline (prominence peaks)`. |
| **Primitives** | **Add**, **Remove**, **▲**, **▼** | | Append the chosen primitive to the selected region, remove the selected primitive, or move it up or down. |
| (no group) | status label | `Compute Boxcar Spectrums, then adjust the regions.` | Result or problem of the last action. |

The default is one region, 250–400 K (`DEFAULT_TPEAK_LO`/`DEFAULT_TPEAK_HI`), with the single primitive `Smoothing Spline (prominence peaks)` and prominence 0.02. Rules for a region (`dA._region_problem`), checked before any fit:

- The upper bound must exceed the lower bound, and the region needs at least one primitive.
- `Smoothing Spline (prominence peaks)` must be the region's only primitive. **Add** refuses to mix it with others.
- Without the spline, at least one primitive must be peak-shaped. Baselines alone give no peak.
- List peak-shaped primitives from low to high T. The fit keeps them in that order, so the k-th listed peak is `P<k>` in every set.

A Smoothing Spline region finds every peak of the spline above the prominence, so different sets can find different numbers of peaks. In that case `P<k>` may not be the same trap in every set, and the log shows `R<n> spline found [...] peak(s) in the sets; its P<n> may not be the same trap in every set -- adjust the prominence or the region.`

### Pane, right frame: "Arrhenius Defect Mapping"

Plot: title "Arrhenius Plot Representation for Trap Signature Extraction", X axis "Reciprocal Temperature (1000 / T) (K⁻¹)", Y axis "ln(e_n / T²)".

| Group | Widget | Default | What it does |
|---|---|---|---|
| **Material Parameters** | `Background Doping Nd (cm⁻³):` entry | `3.2e+14` (`DEFAULT_ND`, the same as Detailed Analysis) | Used only for the trap density. Must be a positive number. |
| **Material Parameters** | `Pre-factor γ (cm⁻² s⁻¹ K⁻²):` entry | `1.66e+21` (`DEFAULT_GAMMA`) | Used only for the capture cross-section. Must be positive. A gray hint below reads `(SiC ≈ 1.66e21, Si ≈ 3.256e21)`. |
| (beside Material Parameters) | **Execute Arrhenius Signature Solver** (yellow button) | | Runs `_run_arrhenius_solver()` on the extracted peaks. Needs one peak id in at least 2 (selected) sets. |
| **Extracted Microscopic Trap Signatures** (below, full width) | `ttk.Treeview`, 4 rows visible, horizontal scrollbar | empty | One row per fitted trap (row id = peak id). Columns `Trap` (peak id), `Et (eV)` (`E ± err`, 3 decimals), `σ (cm²)` (`σ ± err`, `.2e`), `Nt (cm⁻³)` (`N_T ± err`, `.2e`), `Sets` (number of sets in the fit, with `(+m excl.)` when some were excluded). A gray hint below reads `Nt = 2·Nd·ΔC/C∞, ΔC/C∞ = peak height / boxcar factor, averaged over the sets used.` |

The solver fits each trap separately. Each trap has its own colour (matplotlib `Dark2`, distinct from the `C0`–`C9` set colours) and marker (`s`, `o`, `^`, `D`, `v`, `P`, `h` in turn). Fitted points with a T_peak error are filled markers with x and y error bars, fitted points without one (all points of an unweighted fit) are open markers, and excluded points are gray `x`. Each fit line is labelled `R<n>P<k>: Et = E ± err eV` and drawn from `0.98·min(1000/T)` to `1.02·max(1000/T)`. For each trap it logs `Arrhenius solver R<n>P<k> (T_peak-error weighted|unweighted, n sets[, m excluded]): Et=... eV, sigma=... cm² (γ=...), Nt=... cm⁻³.` A trap with fewer than 2 fittable sets is skipped with a log line, and its rows read `too few sets`.

### Data sources

| Selection | Where the data comes from |
|---|---|
| `Loaded Folder (Offline Data)` | `dltsc.quickData_processedTransients`, filled by **Extract & Average Transients** in this tab's Offline Data column (a saved folder). Keys are °C. |
| `Live Run (Qualitative Analysis)` | `dltsc.manual_processedTransients`, filled by the Qualitative Analysis frame of the Live Tools tab, which follows the running experiment's folder. Keys are °C. |
| `Automated/Live Data — Live` | The Run DLTS session in progress: `dltsc.livePlot_liveImpdData` (an `impdData` instance) or, if that is `None`, the averaged snapshot `dltsc.livePlot_liveAllEmissionsData`. |
| `Automated/Live Data — Offline` | A previously loaded run: `dltsc.livePlot_offlineImpdData` or `dltsc.livePlot_offlineAllEmissionsData`. |
| `Auto (first available)` | Measured C: Loaded Folder first, then Live Run (Qualitative Analysis), then Live, then Offline. Smoothed C: Live `impdData`, then Offline `impdData`, then the averaged transients in the Measured C order. |

Loaded Folder and Live Run (Qualitative Analysis) hold averaged transients only, with no `impdData` instance (`_AVERAGED_ONLY_SOURCES`). Without an instance, both methods work on the averaged transients (Step 4a below); `Smoothed C` then reads C(t) from a cubic spline through each transient. When the chosen source has no data, the status label shows the reason and nothing is computed.

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
| `DEFAULT_TPEAK_LO` | `'250.0'` (str, from `dA.DEFAULT_TPEAK_LO`) | Lower bound of the default deconvolution region, K. |
| `DEFAULT_TPEAK_HI` | `'400.0'` (str, from `dA.DEFAULT_TPEAK_HI`) | Upper bound of the default deconvolution region, K. |
| `QUICK_CONTROLS_HEIGHT` | `260` (int) | Requested height (px) of the scrollable control area under each of the three plots. |
| `DEFAULT_RATE_WINDOWS` | `[('5.0','25.0'), ('10.0','50.0'), ('20.0','100.0'), ('50.0','250.0'), ('100.0','490.0')]` | Default (t1, t2) per set, ms, built from `dA.DEFAULT_STD_WINDOWS`. Its length sets the number of sets. |
| `DATA_SOURCE_AUTO` | `'Auto (first available)'` | Data Source option. |
| `DATA_SOURCE_LOADED` | `'Loaded Folder (Offline Data)'` | Data Source option: this tab's Offline Data column. |
| `DATA_SOURCE_QUALITATIVE` | `'Live Run (Qualitative Analysis)'` | Data Source option: the Live Tools tab's Qualitative Analysis frame. |
| `DATA_SOURCE_LIVE` | `'Automated/Live Data — Live'` | Data Source option. |
| `DATA_SOURCE_OFFLINE` | `'Automated/Live Data — Offline'` | Data Source option. |
| `DATA_SOURCE_OPTIONS` | list of the five above | Combobox values. |
| `_AVERAGED_ONLY_SOURCES` | `(DATA_SOURCE_LOADED, DATA_SOURCE_QUALITATIVE)` | Sources that hold averaged transients only (no `impdData` instance). |
| `SIGNAL_METHOD_MEASURED` | `'Measured C (nearest sample)'` | Signal method option (default). |
| `SIGNAL_METHOD_SMOOTHED` | `'Smoothed C (spline-interpolated)'` | Signal method option. |
| `SIGNAL_METHOD_OPTIONS` | list of the two above | Combobox values. |
| `DENOISE_NONE` | `'None (raw)'` | No denoising. |
| `DENOISE_OPTIONS` | `['None (raw)', 'pca', 'wavelet', 'sgolay', 'lowess']` | Combobox values. |
| `PEAK_METHOD_SPLINE` | `'Smoothing Spline'` | Single-peak method of `_window_peaks`. The same finder as Detailed Analysis' `Smoothing Spline (bootstrap)`. Not offered in the UI any more (see "Single-peak helpers" below). |
| `PEAK_METHOD_PSEUDOVOIGT`, `PEAK_METHOD_GAUSSIAN`, `PEAK_METHOD_LORENTZIAN`, `PEAK_METHOD_VOIGT` | `'Curve Fit (Pseudo-Voigt)'`, `'Curve Fit (Gaussian)'`, `'Curve Fit (Lorentzian)'`, `'Curve Fit (Voigt)'` | Single-peak curve-fit methods of `_window_peaks`. Not in the UI. |
| `PEAK_METHOD_OPTIONS` | list of the five above | All single-peak methods. |
| `PEAK_METHOD_CURVETYPE` | `{Pseudo-Voigt: 'pseudoVoigt', Gaussian: 'gaussian', Lorentzian: 'lorenzian', Voigt: 'voigt'}` | Maps a curve-fit option to the `curveType` argument of `impdData._curveFit_peakFinder`. |
| `PRIMITIVE_KEYS`, `PRIMITIVE_SPLINE`, `PRIMITIVE_OPTIONS`, `PRIMITIVE_SHORT`, `DEFAULT_PROMINENCE` | aliases of `dA.PRIMITIVE_KEYS` etc. | Peak Deconvolution primitive labels and their library keys, the spline primitive `'Smoothing Spline (prominence peaks)'`, the primitive combobox values, the short names (`Gauss`, `Spline`, ...) shown in the Extracted Peaks table, the region list and the plot legend, and the default spline prominence `'0.02'`. Defined in [detailedAnalysisTab](detailedAnalysisTab.md#module-constants-and-globals), which shares them with its Peak Regions. |
| `ARRHENIUS_TRAP_MARKERS` | `('s', 'o', '^', 'D', 'v', 'P', 'h')` | Markers of the traps on the Arrhenius plot, in turn. |

Shared state in `dltsConfig` (`dltsc`) that this module reads or writes:

| Name | Type | Meaning |
|---|---|---|
| `rateWindow_dataSourceVar`, `rateWindow_signalMethodVar`, `rateWindow_denoiseVar` | `tk.StringVar` | Combobox selections. |
| `rateWindow_windowVars` | list of 5 `(t1Var, t2Var)` `tk.StringVar` pairs | Rate-window entries (ms). |
| `rateWindow_statusLabel` | `ttk.Label` | Data Source status text. |
| `rateWindow_peakTable` | `ttk.Treeview` | Extracted Peaks table. Row ids are `w<set>r<region>p<peak>`, or `w<set>r<region>` for a `no peak` / `fit failed` row (indices from 0). |
| `rateWindow_figure`, `rateWindow_ax`, `rateWindow_canvas` | matplotlib `Figure`, `Axes`, `FigureCanvasTkAgg` | Left plot. |
| `rateWindow_signals` | dict `i -> {'T_k', 'Signal', 'Signal_err', 't1', 't2', 'e_n'}` | Per-set S(T) curves from the last **Compute Boxcar Spectrums** (T in K, sorted increasing; t1, t2 in ms; e_n in s⁻¹). `Signal_err` is `None` when not every point has a usable error. Input to the deconvolution. |
| `rateWindow_extractedPeaks` | dict row id → `{'set', 'region', 'peakId', 'T_peak', 'T_peak_err', 'S_peak', 'S_peak_err', 'primitive', 'onEdge', 'e_n', 't1', 't2'}` | Every deconvolved peak, keyed by its Extracted Peaks row id. Input to the Arrhenius solver. `T_peak_err` is `None` when the peak has no usable error (see Step 5). `primitive` is the UI label. |
| `rateWindow_rowInfo` | dict row id → `(set index, peakId or None)` | Every Extracted Peaks row, including the `no peak` / `fit failed` rows (peakId `None`). Used to map a selection to its sets. |
| `rateWindow_denoisedEmissions` | dict `T -> dict` | Copy of `impd.dataEmissions` after the last `impdData`-backed window (raw and denoised emissions). |
| `deconv_regions` | list of `{'tLo', 'tHi', 'primitives', 'prominence'}` | The regions (K), their primitive labels (`PRIMITIVE_OPTIONS` values) and the spline prominence. Seeded with the default region. |
| `deconv_results` | dict set index → list of `dA._deconvolve_region` results, one per region | The last deconvolution, drawn by both plots. |
| `deconv_displaySetVar`, `deconv_displaySetCombo` | `tk.StringVar`, `ttk.Combobox` | **Show:** selection (`'Set n'`). |
| `deconv_regionListbox`, `deconv_primitiveListbox` | `tk.Listbox` | Region list and the selected region's primitive list. |
| `deconv_primitiveVar` | `tk.StringVar` | Primitive combobox. |
| `deconv_tLoVar`, `deconv_tHiVar`, `deconv_prominenceVar` | `tk.StringVar` | Region bound entries (K) and the spline min prominence entry. |
| `deconv_fitInfoLabel`, `deconv_statusLabel` | `ttk.Label` | Fit-quality and status text. |
| `deconv_spanSelector` | matplotlib `SpanSelector` | The drag-to-pick-a-range selector on `deconv_ax`. Rebuilt on every redraw. |
| `deconv_figure`, `deconv_ax`, `deconv_residAx`, `deconv_canvas` | matplotlib objects | Middle plot: fit axes and residual axes. |
| `arrhenius_windowPoints` | dict row id → `(1000/T, ln(e_n/T²))` | Arrhenius plot coordinates of each peak the last solver run plotted, used for the selection stars. Cleared by every deconvolution, since the row ids then name new peaks. |
| `arrhenius_highlightArtists` | list of matplotlib `Line2D` | The selection stars currently on the Arrhenius plot. Removed and redrawn on every selection change. |
| `arrhenius_ndVar`, `arrhenius_gammaVar` | `tk.StringVar` | Nd and γ entries. |
| `arrhenius_trapTable` | `ttk.Treeview` | Extracted Microscopic Trap Signatures table. Row ids are the peak ids. |
| `arrhenius_trapResults` | list of dict | The last solver run's `dA._arrhenius_fit` results, one per fitted trap, each with `peakId`, `Nt` and `Nt_err` added. |
| `arrhenius_figure`, `arrhenius_ax`, `arrhenius_canvas` | matplotlib objects | Right plot. |
| `quickData_dataDirectory`, `quickData_datasetRegistry`, `quickData_ziParamsByFile`, `quickData_sourceFolders` | str, dicts, list | Offline Data: last selected folder, temperature → source registry, ZI grid parameters per data file, folders combined so far. |
| `quickData_processedTransients` | dict `T_C -> {'time_ms', 'avg_cap_pf', 'C_infinity', ...}` | Offline Data extraction result: the `Loaded Folder` source. |
| `quickData_paramVars` | dict of `tk.StringVar` (`fp_ms`, `rb_ms`) | Offline Data Timing Boundaries. |
| `quickData_tempListbox`, `quickData_folderLabel`, `quickData_selectFolderButton`, `quickData_appendFolderButton`, `quickData_extractButton`, `quickData_statusLabel` | Tk widgets | Offline Data widgets. |
| `quickData_loadingBusy`, `quickData_processingBusy` | bool | `True` while the folder-scan or the extraction worker runs. |
| read only: `manual_processedTransients`, `manual_paramVars['rb_ms']`, `livePlot_liveImpdData`, `livePlot_offlineImpdData`, `livePlot_liveAllEmissionsData`, `livePlot_offlineAllEmissionsData`, `livePlot_liveIngestBusy`, `livePlot_offlineIngestBusy`, `tabControl`, `dataAnalysisTab` | various | Inputs from other tabs and the main window. |

## Analysis method

All times typed in the GUI are in ms. Temperatures are in K inside the analysis (Loaded Folder and Live Run keys are °C and get +273.15).

**Step 1. Get one averaged transient per temperature.** (`_get_processed_transients_for_source`, `_processed_transients_from_automated`, or `impdData.selected_emissions` inside `calculate_delC_normalized`.)

For an averaged Live/Offline snapshot (`_processed_transients_from_automated`):

```text
time_ms    = x * 1000                       # x is pulse-relative time in s
avg_cap_pf = ymean * 1e12   if max|ymean| < 1e-3   (Farads -> pF), else ymean
T_C        = round(T_K - 273.15, 6)         # impdData keys are exact K (298.15 -> 25.0)
```

(That function still stores a `C_infinity` at 90 % of the span, for other callers. The analysis below recomputes C∞.)

**Step 2. Reverse bias and C∞** (`_rb_ms_for_source`, `_transient_records`). The reverse-bias duration `rb_ms` is the **Reverse Bias (ms)** field of the source's own extraction: the Offline Data column for Loaded Folder, the Qualitative Analysis frame for Live Run; for a Live/Offline snapshot, or when that field is not a positive number, it is the longest transient's span. C∞ is Detailed Analysis' convention:

```text
C_inf = mean C(t) over 0.40 * rb_ms <= t <= 0.90 * rb_ms     # dA._cinf_range_mean
```

**Step 3. Emission rate of each rate window** (`dA._emission_rate`):

```text
e_n = ln(t2 / t1) / ((t2 - t1) * 1e-3)      # t1, t2 in ms -> e_n in s^-1
```

`0 < t1 < t2` is enforced for every set before anything is computed.

**Step 4. DLTS signal S(T).** Two code paths:

a. No `impdData` instance (Loaded Folder, Live Run, or an averaged Live/Offline snapshot). This is `dA._rate_window_signal` on the records of Step 2 (`dA._prepare_signal_data`, with the transient denoised first by `dA._denoise_transient` when **Denoise** is not `None (raw)`):

```text
C(t)     = nearest measured sample to t     (Measured C)
         = cubic spline through C at t      (Smoothed C)
S(T)     = (C(t2) - C(t1)) / C_inf                          # dimensionless
sigma_S  = hypot(noise(t1), noise(t2)) / |C_inf|            # from the raw transient
```

`noise(t)` is `dA._cap_noise_at(time_ms, C, t)`: the Rice second-difference estimate `sqrt(sum(d2^2) / (6 * len(d2)))` with `d2 = C[k-1] - 2 C[k] + C[k+1]`, over the ±25 samples around t.

b. `impdData` instance (Live/Offline; always the case for Smoothed C). The code calls

```python
impd.calculate_delC_normalized(t1=t1/1000.0, t2=t2/1000.0, emissionIndex=-1,
    denoiseEmission=(denoise != 'None (raw)'), denoiseMethod=(denoise or 'pca'),
    smoothCapacitance=(method == Smoothed C), plot=False)
```

and uses column 0 (T, K) as x, column 3 (ΔC/C∞) as S, and error column 1 as σ_S. Inside that method (in `impedanceAnalysis_Tools.py`): `emissionIndex=-1` is the ensemble average over all reverse-bias repeats; t1/t2 are clipped to the data range; C(t1), C(t2) and C∞ are the nearest samples (Measured C) or `CubicSpline` values (Smoothed C); **C∞ is the last sample, C(t[-1])**; errors come from the cross-repeat standard deviation `yerr`, propagated with the `uncertainties` package; `S = (C(t2) - C(t1)) / C_inf`.

**Step 5. Peak deconvolution** (`_run_deconvolution` → `dA._deconvolve_region`, for every set and every region; Detailed Analysis runs the same helper for its regions with primitives):

- Only points with `tLo <= T <= tHi` are used. A region with fewer than 5 points gives no fit (`only n temperature(s) in lo–hi K`).
- Point errors `σ_S` are used only when every point in the region has a usable (finite, > 0) error.
- **Smoothing Spline region**: `impdData._smoothingSpline_multiPeakFinder(x, y, minProminence=prominence, signalYErr=σ_S)`. The same weighted `UnivariateSpline(k=3)` as Detailed Analysis' spline finder, flipped first if its dominant extremum is negative. Every local maximum whose prominence is at least `prominence · max|spline|` is a peak. A peak needs a drop on both sides, so a signal still rising at a region end gives no peak there. T_peak and height errors are the standard deviations of 200 parametric-bootstrap refits (seed 0). There is no χ²ᵣ or R² for a spline region.
- **Primitive region**: `impdData._deconvolve_peaks(x, y, primitives, signalYErr=σ_S)`, one lmfit composite fit of the listed primitives, weighted `1/σ_S` when available. T_peak is each peak's fitted `center`, the height its `height`, and their errors the lmfit standard errors. The fit keeps the peaks in their listed order. A peak whose center ends on either end of the region (within `iaT.DECONV_EDGE_FRAC` of the smallest grid step) is `onEdge`. Baselines give no peak. The fit reports χ²ᵣ and R².
- **Usable T_peak error** (`dA._usable_tp_err`): a peak on the region's edge, or with no error, a non-finite error or an error below `dA.MIN_TP_ERR_K` (1e-4 K), keeps its T_peak but its error is set to `None`. It is then left out of the weighted Arrhenius fit, like Detailed Analysis' edge guard.
- Peak `P<k>` of region `R<r>` is the k-th peak of that region counted from low T. The same id in different sets is one trap.

**Step 6. Arrhenius fit, one per trap** (`_run_arrhenius_solver` → `dA._arrhenius_fit` → `dA._fit_arrhenius_line`). The peaks (only the selected rows, or all when none is selected) are grouped by peak id. Each id with at least 2 sets is fitted separately:

```text
x  = 1000 / T_peak                     # K^-1 (times 1000)
y  = ln(e_n / T_peak^2)                # ln(s^-1 K^-2)
dx = 1000 * dT / T_peak^2              # plotted error bars only
dy = 2 * dT / T_peak
```

Within a trap, sets with no T_peak error are left out of the fit (gray `x`, `excluded (no Tp error)`). If fewer than 3 sets have errors, all sets are fitted unweighted. Fewer than 2 fittable sets: no result for that trap (`too few sets`). The fit is lmfit `LinearModel`, weighted by the effective variance `sig_eff = |-2/T + 1000·slope/T^2| · dT`, re-fitted up to 10 times until the slope changes by ≤ 1e-9·max(|slope|, 1). With fewer than 3 fitted sets, slope and intercept errors are `None`.

**Step 7. Defect parameters, per trap:**

```text
E_a     = -slope * 1000 * K_BOLTZMANN                  # eV
dE_a    = 1000 * K_BOLTZMANN * slope_stderr            # eV
sigma   = exp(intercept) / gamma                       # cm^2   (gamma in cm^-2 s^-1 K^-2)
dsigma  = sigma * intercept_stderr                     # cm^2
r       = t2 / t1
f(r)    = r^(-1/(r-1)) - r^(-r/(r-1))                  # dA._boxcar_peak_factor
N_T,s   = 2 * Nd * |S_peak| / f(r)                     # cm^-3, one value per used set
dN_T,s  = 2 * Nd * dS_peak / f(r)
```

`f(r)` is `exp(-e t1) - exp(-e t2)` at the rate-window emission rate: the peak height of the double-boxcar signal of an ideal exponential transient with amplitude ΔC/C∞ = 1. So `|S_peak| / f(r)` is the full ΔC/C∞ of the trap, and `N_T ≈ 2 (ΔC/C∞) Nd` is the small-signal trap density. N_T of the trap combines the sets used in its Arrhenius fit (`dA._trap_density_from_peaks`, also Detailed Analysis' per-trap N_T):

- When every used peak has a height error: the error-weighted mean (weights `1/dN_T,s²`), with error `sqrt(1/Σw)`, multiplied by `sqrt(χ²ᵣ)` (Birge ratio) when the sets scatter more than their errors (χ²ᵣ > 1).
- Otherwise: the plain mean and its standard error (`None` for a single set).

N_T used to be `dA._trap_density` on the averaged transients (`2 · max_T |(C(rb_ms) − C(2 ms)) / C_inf| · Nd`, no error). That definition is now only used by `_quick_arrhenius`. The per-trap N_T separates the traps of one region and carries an error.

## Matching Detailed Analysis

On averaged transients (path a), both tabs compute the same S(T) and use the same Arrhenius line fit. Set up both tabs like this:

| Setting | Quick Analysis | Detailed Analysis |
|---|---|---|
| Data | Offline Data extraction of the run folder | **Load Data** on the same folder |
| Reverse bias | Offline Data **Reverse Bias (ms)** | **RB duration (ms)**, same value |
| C∞ range | fixed 0.40 to 0.90 | **Start / End (frac RB)** 0.40 / 0.90 (defaults) |
| Signal | `Measured C`, source `Loaded Folder (Offline Data)` (or `Auto`) | `Measured C (nearest sample)`, denoise `None (raw)` |
| Windows | the five sets | the five **Standard Windows** (same defaults) |
| Range | the default region, 250–400 K, `Smoothing Spline (prominence peaks)` | the default peak region R1, 250–400 K, default method `Smoothing Spline (bootstrap)` |
| Nd, γ | same values | same values |

The peaks still differ slightly. The multi-peak spline finder can return several peaks per region where Detailed Analysis' default method takes the single largest |S|, it uses a 20 000-point grid and matches bootstrap peaks within each peak's catchment, and it returns no peak at all where Detailed Analysis reports an edge peak without error. With one clear peak in the region, R1P1's Et and σ are close to the **Standard** part of Detailed Analysis' R1P1 block, not identical.

To find the peaks the same way in both tabs, add a Detailed Analysis peak region that overlaps the Quick Analysis region (or pick `Quick R<n>` in its method box): it then copies the region's primitives and runs the same `dA._deconvolve_region`, and its per-trap N_T is the same `dA._trap_density_from_peaks`.

The exact match is kept for the single-peak helpers `_window_peaks` and `_quick_arrhenius` (see "Single-peak helpers" below). With `PEAK_METHOD_SPLINE` they give the same Et, σ and N_T as the **Standard** block of the Detailed results. `tests/test_quick_vs_detailed.py` checks this. A Detailed standard row of `0 / 0` is unused, so fewer windows can be compared too.

The `impdData` path (b) normalizes by the last sample and uses cross-repeat errors, so its S(T) differs slightly.

## Functions

### construct_dataAnalysisTab()

Adds the **Quick Analysis** tab to `dltsc.tabControl` and builds the Offline Data column and the three analysis frames.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | |

**Returns** `None`.

**Side effects** Calls `dltsc.tabControl.add(dltsc.dataAnalysisTab, text='Quick Analysis')` and `tabControl.pack(expand=1, fill="both")`; builds the Offline Data column (`_build_offlineDataFrame`) in grid column 0, creates the `tk.PanedWindow` in column 1 with three frames (480 px each, `stretch='always'`), then calls `_build_rateWindowFrame`, `_build_arrheniusFrame` and, last, `_build_deconvolutionFrame` (its first redraw also redraws the other two plots). Together they create every widget and `dltsc.quickData_*` / `dltsc.rateWindow_*` / `dltsc.deconv_*` / `dltsc.arrhenius_*` global listed above. `dltsc.dataAnalysisTab` must already be a `ttk.Frame` inside `dltsc.tabControl`.

**Called by** `DLTSGUI_MainWindow.py` (`daT.construct_dataAnalysisTab()`).

**Example** Needs a Tk root and notebook; not useful outside the GUI.

## Internal helpers

### _resolve_impd_for_source(source)

Maps a Data Source label to an `impdData` instance.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `source` | str | | One of the `DATA_SOURCE_*` labels. |

**Returns** `(impd, resolvedLabel)`, or `(None, None)` when that source has no instance. `Loaded Folder` and `Live Run (Qualitative Analysis)` always give `(None, None)`. `Auto` tries `livePlot_liveImpdData`, then `livePlot_offlineImpdData`.

**Side effects** None.

**Called by** `_calculate_rate_windows`.

### _processed_transients_from_automated(mode)

Converts the Automated/Live Data frame's "All Emissions Aligned" snapshot into the averaged-transient shape of the Loaded Folder and Live Run sources.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `mode` | str | | `'live'` reads `dltsc.livePlot_liveAllEmissionsData`; any other value reads `dltsc.livePlot_offlineAllEmissionsData`. |

**Returns** dict `T_C -> {'time_ms', 'avg_cap_pf', 'C_infinity'}` (keys in °C, rounded to 1e-6 so a 298.15 K key gives 25.0). `C_infinity` here is the sample nearest 90 % of the span. Entries with empty or mismatched `x`/`ymean` are skipped. Returns `{}` when there is no snapshot.

**Side effects** None.

**Called by** `_get_processed_transients_for_source`.

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

**Returns** `(processedTransients, resolvedLabel, errorReason)`. On success `errorReason` is `None`; on failure the first two are `None` and `errorReason` is a message such as `"Offline Data has no extracted transients yet: select a folder, then click Extract & Average Transients."` or `"Qualitative Analysis (live run) has no extracted transients yet."`. `Auto` order: Loaded Folder, Live Run (Qualitative Analysis), Live snapshot, Offline snapshot.

**Side effects** None.

**Called by** `_calculate_rate_windows`.

**Example** Continuing the example above: `daT._get_processed_transients_for_source(daT.DATA_SOURCE_AUTO)` returns the 12-temperature dict and `'Automated/Live Data — Offline'`.

### _rb_ms_for_source(label, processedTransients)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `label` | str | | Resolved Data Source label. |
| `processedTransients` | dict | | `T_C -> {'time_ms', ...}`. |

**Returns** the reverse-bias duration in ms (see Step 2): `quickData_paramVars['rb_ms']` for `Loaded Folder`, `manual_paramVars['rb_ms']` for `Live Run (Qualitative Analysis)`, when that is a positive number; otherwise the longest transient's span.

### _transient_records(processedTransients, rb_ms, denoise=DENOISE_NONE, smoothed=False)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `processedTransients` | dict | | `T_C -> {'time_ms', 'avg_cap_pf', ...}`. |
| `rb_ms` | float | | Reverse-bias duration, ms. |
| `denoise` | str | `'None (raw)'` | A `DENOISE_OPTIONS` value, applied to each transient by `dA._denoise_transient`. |
| `smoothed` | bool | `False` | `True` reads C(t) from a cubic spline (Smoothed C), `False` from the nearest sample (Measured C). |

**Returns** `(records, temps)`: `dA._prepare_signal_data` records with C∞ from `dA._cinf_range_mean`, and the sorted °C keys.

### Single-peak helpers

`_peak_method_for`, `_curve_fit_peak_method`, `_window_peaks`, `_quick_arrhenius` and the `PEAK_METHOD_*` constants are the single-peak path the tab used before Peak Deconvolution. The UI no longer calls them. They are kept for `tests/test_quick_vs_detailed.py` and the hardware benchmarks, which compare this path with Detailed Analysis.

#### _peak_method_for(peakMethod) and _curve_fit_peak_method(curveType)

`_peak_method_for` turns a `PEAK_METHOD_*` label into a method for `dA._peak_from_signal`: `dA.PEAK_METHOD_SPLINE` for the smoothing spline, or the callable made by `_curve_fit_peak_method(curveType)`. That callable takes `(T, S, S_err)` and returns `(Tp, Tp_err, xFit, yFit)` from `impdData._curveFit_peakFinder`, or the raw grid maximum with no error and no curve if the fit fails.

#### _window_peaks(records, temps, windows, tpLo, tpHi, peakMethod)

| Name | Type | Default | Meaning |
|---|---|---|---|
| `records`, `temps` | | | From `_transient_records`. |
| `windows` | list of (t1, t2) | | ms. |
| `tpLo`, `tpHi` | float | | Search range, K (`-inf`/`inf` for no bound). |
| `peakMethod` | str | | A `PEAK_METHOD_*` label. |

**Returns** one dict per window: `t1`, `t2`, `e_n`, `T_k`, `Signal`, `Signal_err`, plus `dA._peak_from_signal`'s keys (`skipped`, and unless skipped `Tp`, `Tp_err`, `S_peak`, `sign`, `xFit`, `yFit`).

#### _quick_arrhenius(peaks, gamma, nd, transients=None)

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

Command of **Compute Boxcar Spectrums**. Implements Steps 2 to 4 for each set, then hands over to `_run_deconvolution()` (Step 5).

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | Reads all inputs from the `dltsc.rateWindow_*` Tk variables. |

**Returns** `None`.

**Side effects** Replaces `dltsc.rateWindow_signals` (each set's S(T) sorted by T, with `t1`, `t2`, `e_n`); sets `dltsc.rateWindow_denoisedEmissions` on the `impdData` path; updates the status label and the **Show** list of the Peak Deconvolution frame (resetting it to `Set 1` when the old choice is gone); writes to the app log via `dltsc.log_to_textbox`; then calls `_run_deconvolution()`, which refills the peak table and redraws the plots. It stops early (with a log message, leaving the previous spectra and peaks in place) when: the chosen data source has no data; the resolved Live/Offline source is still ingesting (`livePlot_*IngestBusy`); a t1/t2 is non-numeric or not `0 < t1 < t2`; `calculate_delC_normalized` raises for a set.

**Called by** the **Compute Boxcar Spectrums** button.

### _selected_peak_rows()

**Returns** the set of row ids selected in the Extracted Peaks table (empty when nothing is selected or the table does not exist yet).

### _redraw_rate_window_plot() and _show_all_rate_windows()

`_redraw_rate_window_plot` redraws the spectrum plot from `dltsc.rateWindow_signals`, `dltsc.deconv_results`, `dltsc.rateWindow_extractedPeaks` and `dltsc.deconv_regions`, limited to the selection as described under "Rate Window Analysis". `_show_all_rate_windows` (**Show All**) clears the table selection, which fires `<<TreeviewSelect>>` and redraws everything.

### Peak Deconvolution helpers

#### _run_deconvolution()

Command of **Deconvolve All Sets**, and the last step of **Compute Boxcar Spectrums**. Implements Step 5.

**Side effects** Checks every region with `dA._region_problem` first; any problem (or no region) is logged and shown in the status label, and nothing changes. Otherwise it clears and refills the Extracted Peaks table, replaces `dltsc.deconv_results`, `dltsc.rateWindow_extractedPeaks` and `dltsc.rateWindow_rowInfo`, clears `dltsc.arrhenius_windowPoints` (the old stars no longer match the new row ids; the old Arrhenius results stay on screen), redraws the spectrum and deconvolution plots, logs each region's fit message, the spline peak-count warning, and `Peak deconvolution: Deconvolved n set(s) in m region(s): k peak(s) extracted.` Logs `click Compute Boxcar Spectrums first` when there are no spectra.

#### Shared region helpers (in detailedAnalysisTab)

`_deconvolve_region(sig, region)` (one `dltsc.rateWindow_signals` entry deconvolved in one `dltsc.deconv_regions` entry), `_region_problem(region)` and `_usable_tp_err(tpErr, onEdge)` are defined in `detailedAnalysisTab.py` and called here as `dA._deconvolve_region` etc., so Detailed Analysis' Peak Regions run the same code. They are documented under [Peak-region helpers](detailedAnalysisTab.md#peak-region-helpers-shared-with-quick-analysis).

#### _region_text(r, region)

The region's line in the region list.

#### Region and primitive editing

`_on_region_select`, `_read_region_entries`, `_add_region`, `_update_region`, `_remove_region`, `_add_primitive`, `_remove_primitive`, `_move_primitive(step)`, `_refresh_region_widgets(selectIndex=None, primitiveIndex=None)` and `_regions_changed(message)` edit `dltsc.deconv_regions` from the Regions and Primitives widgets. After an edit the lists, the region shading and the bound lines are redrawn, and the status label asks for **Deconvolve All Sets**: the fits are not recomputed. `_read_region_entries` rejects non-numeric values, upper ≤ lower, and a prominence outside 0 < p < 1. `_on_span_select(tLo, tHi)` is the `SpanSelector` callback: it fills the **T (K)** entries (1 decimal).

#### _redraw_deconv_plot(), _display_set_index() and _selected_region_index()

`_redraw_deconv_plot` draws the set chosen in **Show** (`_display_set_index`, 0-based) as described under "Peak Deconvolution", shades the region selected in the region list (`_selected_region_index`, `None` when none), fills the fit-quality label, and rebuilds the `SpanSelector` (clearing the axes removes it).

#### _build_deconvolutionFrame(parent)

Builds the middle frame inside `parent` and creates the `dltsc.deconv_*` widgets and variables. Seeds `dltsc.deconv_regions` with the default region when it is empty and `dltsc.deconv_results` with an empty dict. Uses the same row weights and control height as the other frames, so the three plots are the same height.

### Arrhenius helpers

#### _run_arrhenius_solver()

Command of **Execute Arrhenius Signature Solver**. Implements Steps 6 and 7.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | Reads `dltsc.rateWindow_extractedPeaks` (limited to the rows selected in `dltsc.rateWindow_peakTable`, all when none), `dltsc.arrhenius_ndVar`, `dltsc.arrhenius_gammaVar`. |

**Returns** `None`.

**Side effects** Clears and refills `dltsc.arrhenius_trapTable`, `dltsc.arrhenius_trapResults` and `dltsc.arrhenius_windowPoints`, fills the `Arrhenius fit` column of the peak table, clears and redraws `dltsc.arrhenius_ax` (one line per trap, then the selection stars), logs one line per trap. Stops with a log message, before changing anything, when there are no extracted peaks, no peak id has at least 2 (selected) sets, or Nd or γ is not a positive number. A trap whose fit raises or has fewer than 2 fittable sets is skipped with a log line.

**Called by** the **Execute Arrhenius Signature Solver** button.

#### _boxcar_peak_factor and _trap_density_from_peaks (in detailedAnalysisTab)

The per-trap N_T of Step 7 is `dA._trap_density_from_peaks(peaks, nd)` (peaks with `S_peak`, `S_peak_err` or `None`, `t1`, `t2`; returns `(Nt, Nt_err)` in cm⁻³), which uses `dA._boxcar_peak_factor(t1, t2)`. Both are documented under [Peak-region helpers](detailedAnalysisTab.md#peak-region-helpers-shared-with-quick-analysis).

#### _trap_style(trapIndex), _update_arrhenius_highlight() and _on_peak_table_select()

`_trap_style` returns the `(colour, marker)` of a trap (`Dark2`, `ARRHENIUS_TRAP_MARKERS`). `_update_arrhenius_highlight` removes the old selection stars and draws one per selected peak in `dltsc.arrhenius_windowPoints`. `_on_peak_table_select` (bound to `<<TreeviewSelect>>`) redraws the spectrum plot and the stars, and shows the first selected row's set in the Peak Deconvolution plot.

### _build_rateWindowFrame(parent)

Builds the left frame (plot, toolbar, scrollable controls, button, table) inside `parent` and creates the `dltsc.rateWindow_*` widgets and variables. Seeds `dltsc.rateWindow_signals`, `dltsc.rateWindow_extractedPeaks` and `dltsc.rateWindow_rowInfo` as empty dicts if they are `None`, because `dltsConfig.init()` is not called by the main window.

### _build_arrheniusFrame(parent)

Builds the right frame (plot, toolbar, Material Parameters, solver button, trap table) inside `parent` and creates the `dltsc.arrhenius_*` widgets and variables. Uses the same row weights and control height as the other frames so the plots are the same height.

### Offline Data column

#### _build_offlineDataFrame(parent)

Builds the Offline Data column inside `parent`: the bold heading, a 230 px scrollable canvas, and the four groups described under "Left column: Offline Data". Seeds `quickData_datasetRegistry`, `quickData_ziParamsByFile`, `quickData_sourceFolders` and `quickData_processedTransients` if they are `None`, sets both busy flags to `False`, and creates the `dltsc.quickData_*` widgets and `quickData_paramVars`.

#### _browse_quick_folder(isAppend=False)

**Select Source Folder** (`isAppend=False`) and **Append Source Folder** (`isAppend=True`) handler. It does nothing while a scan or an extraction is busy (`_quick_busy`). An append with an empty registry is treated as a first load. After the folder dialog it logs the preview and calls `_scan_quick_folder_async(dir_path, isAppend)`.

#### _scan_quick_folder_async(dir_path, isAppend)

Sets `quickData_loadingBusy`, disables the buttons, and runs `liveDataTab._scan_folder(dir_path)` on a daemon thread. `apply()` on the Tk thread:

- replaces (`isAppend=False`) or merges (`isAppend=True`, first-loaded copy wins) `quickData_datasetRegistry` and `quickData_sourceFolders`; a replacing load also sets `quickData_dataDirectory`, clears `quickData_ziParamsByFile`, and presets **Filling Duration** / **Reverse Bias** from the scan's `fpMs` / `rbMs` when they are not `None`;
- adds the scan's ZI grid parameters to `quickData_ziParamsByFile`;
- clears `quickData_processedTransients`;
- refills the temperature listbox and selects every entry;
- logs the scan errors and sets the status `[<format>] N temperature step(s) from S source(s). Click Extract & Average.`

#### _extract_quick_transients()

**Extract & Average Transients** handler. Returns silently when nothing is loaded or a worker is busy. Logs an error when no temperature is selected or **Reverse Bias (ms)** is not a positive number. Otherwise it sets `quickData_processingBusy`, disables the buttons, and calls `liveDataTab._extract_transients_async(quickData_datasetRegistry, selectedTemps, rbMs, quickData_ziParamsByFile, apply)`. `apply()` stores the result in `quickData_processedTransients`, logs each error, sets the status, and logs `Offline Data: extracted N averaged transient(s) (Data Source 'Loaded Folder (Offline Data)').`

#### _set_quick_buttons_state(state) and _quick_busy()

`_set_quick_buttons_state` sets `state` (`'normal'` or `'disabled'`) on **Select Source Folder**, **Append Source Folder** and **Extract & Average Transients**. `_quick_busy` returns `True` while `quickData_loadingBusy` or `quickData_processingBusy` is set.

### _on_mousewheel(event) (nested, one in each `_build_*` function)

Scrolls that frame's control canvas by `-event.delta / 120` units. Bound with `bind_all` while the pointer is over the canvas and unbound when it leaves.

## Notes and limitations

- C∞ on the `impdData` path is the last sample of the (trimmed) emission, not the 40–90 % mean. Results from that path are close to, but not the same as, the averaged-transient path and Detailed Analysis.
- The sign convention is `S = (C(t2) - C(t1)) / C_inf`. A region whose dominant extremum is negative is flipped before deconvolution; `S_peak` keeps the original sign.
- `e_n = ln(t2/t1) / (t2 - t1)` assumes t1 and t2 in ms (the `1e-3` factor). The `impdData` path passes t1/t2 in s and may clip them to the data range, but the table and Arrhenius plot still use the e_n computed from the unclipped GUI values.
- The initial spectrum plot title says "(Pseudo-Voigt Refinement)". It reads "Multi-Window DLTS Signal Spectrum" after the first run.
- On the `impdData` path with `Denoise` = `None (raw)`, `calculate_delC_normalized` still runs the `pca` filter (`filter_emissions(..., recalculate=True)`) and discards it. This costs time but does not change the result.
- If `calculate_delC_normalized` fails on a later set, the function returns before storing any spectra, so the previous run's spectra and peaks stay.
- Region and primitive edits do not refit by themselves. The table, the plots and the Arrhenius input keep the last deconvolution until **Deconvolve All Sets** or **Compute Boxcar Spectrums** is clicked.
- The peak id is a position (k-th peak of a region from low T), not an identity check. If a spline region misses a peak in one set (below the prominence, or still rising at the region edge), the later peaks of that set shift to a lower `P<k>` and are grouped with the wrong trap. Check the log warning for spline regions and the per-set peak rows.
- If every peak of a trap has no usable T_peak error (on the region edge), fewer than 3 sets have errors and all are fitted unweighted. The result is then not meaningful: widen the region or choose windows whose peaks fall inside it.
- With only 2 fitted sets the fit has no residual degrees of freedom; E_a and σ are reported with no error.
- N_T is `2·Nd·|S_peak|/f(r)`, the small-signal approximation `N_T ≈ 2 (ΔC/C) N_d` with ΔC/C∞ recovered from the boxcar peak height of an ideal exponential. It ignores the λ-region correction.
- σ is the apparent cross-section `exp(intercept)/γ`. It is only as good as the γ entered; the hint gives SiC 1.66e21 and Si 3.256e21.
- `rateWindow_signals` stores T in K under the key `'T_k'`.

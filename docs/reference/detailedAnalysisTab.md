# detailedAnalysisTab

## What it's for

`detailedAnalysisTab.py` builds the **Detailed Analysis** tab, a port of the standalone `DLTS_APP.py` ("DLTS Multiwindow Analysis") into this app. It loads a whole temperature sweep from a data folder, computes DLTS spectra for many log-spaced rate windows (plus five fixed "standard" windows for comparison), finds the peaks inside one or more user-chosen **peak regions** with an error estimate, groups the same peak of every window into one trap, and fits one error-weighted Arrhenius line per trap to get E_a, σ and N_T. It also draws a DLTS spectra panel, a ΔC/C₀(t, T) transient map with τ(T) overlays, and a rate-window map, each panel with its own toolbar, the maps and the Arrhenius plot in 2D or 3D. Loading and analysis run in the tab's own worker process so the GUI stays responsive.

A peak region either uses this tab's single-peak finder (the default, one peak per region and window, as the old Peak Search Range) or the peak primitives of a [Quick Analysis](dataAnalysisTab.md) Peak Deconvolution region, deconvolved with the same shared helpers (see "Peak regions" under Analysis method). Quick Analysis shares this tab's C∞, S(T), Arrhenius fit and region helpers. With the default single-peak region its results are close to this tab's **Standard** result but not identical; see [Matching Detailed Analysis](dataAnalysisTab.md#matching-detailed-analysis).

## What the user sees

A header reads **Detailed Analysis** `(DLTS Multiwindow Analysis — ZI MFIA temperature sweep)`. Below it a horizontal `ttk.PanedWindow` has three parts:

1. a scrollable control column on the left (295 px wide, mouse wheel scrolls it while the pointer is over it);
2. the figure area in the middle (takes all extra width): the plot panels, each with its own matplotlib toolbar on top (see Figure), and a status label at the bottom (initial text `Load a data folder to begin.`);
3. a **Results** text box on the right (Consolas 9, dark background, read-only, 57 characters wide, no wrapping, horizontal and vertical scroll bars).

### Control column

Section headings are shown in upper case in the GUI. Spinboxes accept typed values outside the listed range; the range only limits the arrow buttons.

**DATA**

| Widget | Default | What it does |
|---|---|---|
| `Data folder:` entry | empty | Path of the run folder. |
| **Browse** | | Opens a folder dialog ("Select DLTS Data Folder"), puts the path in the entry and logs a description of the folder contents (`liveDataTab._describe_folder_contents`). |
| **Load Data** | | Runs `_detailed_load_data()`: loads every temperature in the folder in the worker process. Disabled while a load or run is in progress. |
| info label | `No data loaded.` | After a load: `<n> temperatures loaded: <Tmin> K to <Tmax> K` (blue; the stored °C + 273.15, no decimals). |

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

**PEAK REGIONS**

A gray hint reads `Drag across the DLTS Spectra panel (after a run) or type T min / max, then Add Region. A new region uses the primitives of the Quick Analysis region overlapping it most, else the default peak method below.`

| Widget | Variable | Default | What it does |
|---|---|---|---|
| region list (`tk.Listbox`, 4 rows) | `detailed_regionListbox` | one region, `R1: 250–400 K \| default` | One line per region: `R<n>: <lo>–<hi> K \| <method>[ [Quick R<m>]]`, where method is `default` or the short primitive names (`Gauss + Gauss`, `Spline (prom. ≥ 0.02)`). Selecting a line copies its bounds into T min / T max and its method into the method box. |
| `T min (K)` spinbox | `detailed_tpeakLoVar` | `250.0` | Range 50 to 1000, step 5. Lower bound for Add / Update. |
| `T max (K)` spinbox | `detailed_tpeakHiVar` | `400.0` | Range 50 to 1000, step 5. Upper bound for Add / Update. |
| **Add Region** | | | Appends a region with the T min / T max bounds (`_detailed_add_region`). It takes the primitives (and prominence) of the Quick Analysis region (`dltsc.deconv_regions`) that overlaps it most, copied, with source `Quick R<n>`; with no overlapping usable Quick region it uses the default single-peak finder. The status label and the log say which. |
| **Update** | | | Moves the selected region to the T min / T max bounds; its method is kept. |
| **Remove** | | | Deletes the selected region; later regions are renumbered. |
| `Method of the selected region:` combobox | `detailed_regionMethodVar` | `Default (Peak method below)` | Read-only. Choices: `Default (Peak method below)` plus one entry per usable Quick Analysis region, `Quick R<n> (<lo>–<hi> K): <primitives>`. The list is rebuilt each time it opens (`postcommand`), so it follows Quick Analysis' current regions. Choosing an entry copies that method into the selected region. |
| `Default peak method (one peak per region):` combobox | `detailed_peakMethodVar` | `Smoothing Spline (bootstrap)` | `Parabolic fit (lmfit)`, `Smoothing Spline (bootstrap)`. Used by every region without primitives. |

T min / T max (or a drag on the spectra panel, which fills them) alone change nothing: a region is only created or moved by **Add Region** / **Update**. Region edits do not refit; the status asks for **Run Analysis**, which uses the regions as they are then. A region keeps its own copy of a Quick Analysis method, so later edits in Quick Analysis do not change it.

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
| `Show standard-window comparison (0 / 0 = unused)` checkbox (`detailed_stdWinsVar`) | on | Draws each trap's standard-window fit (dashed line and diamond markers in the trap's colour) on the Arrhenius panel. The standard-window fits are computed and written to Results whether or not this is checked. Toggling it redraws the Arrhenius panel at once, like the Display options. |
| `t1 / t2  (ms):` five spinbox pairs (`detailed_stdEntries`) | `5/25`, `10/50`, `20/100`, `50/250`, `100/490` (`DEFAULT_STD_WINDOWS`, the same as Quick Analysis' window sets) | t1 range 0 to 490, t2 range 0 to 499, step 1. A row with t1 ≤ 0 or t2 ≤ t1 (for example `0 / 0`) is not used; with no usable row there is no Standard result. |

**DISPLAY**

The options are grouped per panel. Each one applies at once to the last run's plots (`_detailed_on_display_change`), redrawing only the panel it concerns from the cached result (`detailed_lastOut`, `detailed_lastParams`); no re-run is needed. Before the first run they do nothing.

| Widget | Variable | Default | What it does |
|---|---|---|---|
| **Arrhenius plot** (bold heading; the panel is always shown) | | | |
| `View` combobox | `detailed_arrViewVar` | `2D` | `2D`, `3D (peak height up)` (`ARR_VIEW_OPTIONS`). |
| `Labels` combobox | `detailed_arrLabelsVar` | `Trap ids` | `Trap ids`, `Legend`, `Results (Et, σ, Nt)`, `None` (`ARR_LABEL_OPTIONS`). |
| `Show DLTS spectra panel` checkbox | `detailed_showSpectraVar` | on | Adds the DLTS Spectra panel (rebuilds the panel grid). |
| `Spectra to plot` spinbox | `detailed_nSpectraVar` (IntVar) | `5` | Range 2 to 60. Number of multi-window spectra drawn, spread evenly over the windows (at most N windows; a non-number counts as 5). |
| `Labels` combobox | `detailed_specLabelsVar` | `Trap ids` | `Trap ids`, `Legend`, `Region names`, `None` (`SPEC_LABEL_OPTIONS`). |
| `Show transient map` checkbox | `detailed_showTmapVar` | on | Adds the ΔC/C₀ transient map panel. |
| `  Overlay τ(T) curve on map` checkbox | `detailed_showTauVar` | on | Draws each trap's τ(T) from its fit and its (T_p, 1/e_n) points on the transient map. |
| `View` combobox | `detailed_tmapViewVar` | `2D colour map` | `2D colour map`, `3D isohypse surface` (`MAP_VIEW_OPTIONS`). |
| `Labels` combobox | `detailed_tmapLabelsVar` | `Trap ids` | `Trap ids`, `Legend`, `None` (`MAP_LABEL_OPTIONS`). |
| `Show Rate-Window Analysis map` checkbox | `detailed_showRwmVar` | on | Adds the rate-window map panel. |
| `View` combobox | `detailed_rwmViewVar` | `2D colour map` | As for the transient map. |
| `Labels` combobox | `detailed_rwmLabelsVar` | `Trap ids` | `Trap ids`, `Legend`, `None`. |

`Labels` picks the one set of labels a panel shows: `Trap ids` writes each trap's id (`R<r>P<k>`) in bold in its colour on the plot; `Legend` adds the panel's legend; `Results (Et, σ, Nt)` adds a text legend with each trap's fit results; `Region names` writes `R<n>` at the top-left of each shaded peak region; `None` shows no labels. Legends are always placed outside the plot area, at the panel figure's right (`fig.legend(loc='outside right upper')`, 8 pt).

**Actions** (under an empty section divider)

| Button | What it does |
|---|---|
| **Run Analysis** | Disabled until data has been loaded. Runs `_detailed_run_analysis()`: checks the peak regions, snapshots all parameters, computes everything in the worker process (every panel's data and every window's spectrum, whatever the Display options), then draws the shown panels and fills Results. Status becomes `Done.  R1P1: Et = <E ± err> eV   R1P2: Et = ...` (one entry per trap). |
| **Edit Labels & Legends** | Opens the "Edit Labels & Legends" dialog (`_detailed_open_label_editor`). Logs a hint if no analysis has been run yet. |
| **Save Figure...** | Save dialog (default name `DLTS_MultiWindow.png`). Saves one combined figure of the shown panels, laid out as on screen and drawn with the current Display options (`_detailed_combined_figure`). Formats: PNG, PDF, SVG, EPS, JPEG, TIFF, BMP. Raster formats are saved at 180 dpi on a white background; vector formats without a dpi. Logs a hint if no analysis has been run yet. Each panel's own toolbar saves that panel alone. |
| **Export Results to TXT** | Save dialog (default name `DLTS_Results.txt`); writes the Results text as UTF-8. |

### Figure

Each panel is its own matplotlib `Figure` (6 × 4.5 in, constrained layout) in a `FigureCanvasTkAgg` with its own `NavigationToolbar2Tk` (pan, zoom, Home/Back, save) above it. The panels are gridded 2×2 in `detailed_figFrame`:

| | column 1 | column 2 |
|---|---|---|
| top row | Arrhenius Plot (always) | DLTS Spectra |
| bottom row | ΔC/C₀ Transient Map | Rate-Window Analysis Map |

Only shown panels are placed. A panel alone in its row spans both columns (for example Arrhenius alone when the spectra are off); a row with no shown panel is dropped, and the shown rows share the height equally. Showing or hiding a panel rebuilds the grid (`_detailed_layout_panels`); every other Display option redraws just its panel (`_detailed_draw_panel`). A redraw resets that panel's toolbar history, so Home returns to the new drawing's view.

**Linked temperature axes.** The two panels of a row show the same temperatures: zooming, panning, Home or Back on one sets the partner's x limits to the same temperature range, converted between the two x axes (1000/T ↔ T on the top row, T ↔ 1/kT on the bottom row; `_reciprocal_1000`, `_reciprocal_kT`). This works between 2D panels only (not for a 3D view), and is connected after a panel's first draw, so autoscaling never propagates; only the user's changes do (`_detailed_link_panel`, `_detailed_follow_xlim`).

Styling follows Quick Analysis: matplotlib's default colours and font sizes, black axes, and a dotted grid on the line plots (Arrhenius 2D, Spectra). There is no overall figure title.

Each trap (peak id `R<r>P<k>`, see Analysis method) has its own colour from `TRAP_COLORS`, in peak-id order; the first is `C0` (blue), the single-trap colour of earlier versions.

All temperatures shown in this tab are in kelvin (axes, region bounds, span selection, Results).

- **Arrhenius Plot**, 2D view: x "1000 / T (K⁻¹)", y "ln(eₙ / T²) (s⁻¹ K⁻²)". Per trap: multi-window points colored by log₁₀ eₙ (plasma colormap, one shared colorbar "log₁₀ eₙ (s⁻¹)") with an edge in the trap colour, error bars from T_p errors, a fit line in the trap colour labeled `<id> multi (<N>): <E ± err> eV` with a shaded 2σ confidence band. Excluded windows are black `x` markers "Excluded (no Tp error)" (one legend entry for all traps). Standard-window fit per trap (when **Show standard-window comparison** is on): dashed line in the trap colour labeled `<id> standard (<N>): <E ± err> eV`, its error bars, and diamonds with a black edge (legend entry "Standard windows"); the x range then includes them. The plot has no frame: only the left and bottom spines. Temperature "T (K)" is shown along the top (`secondary_xaxis`, about 5 tick labels, no tick marks or spine). Labels: `Trap ids` puts each trap's id at the high-temperature (left) end of its line; `Legend` shows the line/marker legend; `Results (Et, σ, Nt)` shows a monospace text legend with, per trap, `<id>  (<N> pts, weighted|unweighted)`, E_a, σₙ, N_T ± err (from peak heights), R² and (if weighted) χ²ᵣ, then `Nt (all traps, transient) = <N_T>` (`_detailed_results_legend`).
- **Arrhenius Plot**, 3D view (`3D (peak height up)`): each trap's fit lines lie on the floor (multi solid, standard dashed), and every window's point stands on a stem at its peak height z = |ΔC/C₀| ×10⁻³ (circles for multi-windows, diamonds for standard windows, black `x` for excluded ones), so one trap's points should sit at about one height. Axes "1000 / T (K⁻¹)", "ln(eₙ / T²)", "Peak |ΔC/C₀| (×10⁻³)". `Trap ids` labels each trap's tallest point. No colorbar and no temperature axis.
- **DLTS Spectra**: x "Temperature (K)", y "ΔC/C₀ (×10⁻³)", a black line at 0. Each peak region shaded light gray (`Region names` labels it `R<n>` at its top-left). One line per shown window (cool colormap by window index), labeled `<t1>/<t2> ms (eₙ = <e_n> s⁻¹)`; dotted vertical lines in the trap colour at every multi-window T_p of every trap; ▼ markers in the trap colour at each shown spectrum's own peaks (gray for a peak whose trap had no fit), legend entry "Peaks (trap colour)". `Trap ids` writes each trap id in bold above that trap's tallest marker. Dragging across this panel picks a peak-region range in K (see Peak Regions); legends are outside the axes, so they never interfere with the selection.
- **ΔC/C₀ Transient Map**, 2D colour map: filled contours (jet, 64 levels, thin black contour every 6th level) of ΔC/C₀ ×10⁻⁵ vs "Temperature (K)" and log "Time (s)"; colorbar "ΔC/C₀ (×10⁻⁵)" with at most ~7 ticks. With the τ overlay, per trap in its colour with a white outline: τ(T) line labeled `<id> τ(T), Et = <E> eV` and open circles at (T_p, 1/e_n) labeled `<id> peaks (Tₚ, 1/eₙ)`. `Trap ids` writes the id above the top of the trap's column of circles, or below its bottom for every other trap, so neighbouring ids do not collide. A trap whose τ(T) falls outside the time range is skipped. Shows "Not enough time points" when the map cannot be built.
- **ΔC/C₀ Transient Map**, 3D isohypse surface: the same values as a surface over (T, log₁₀ t) in the same jet colours (clipped to the colour range, at most about 90 × 90 facets), with black isohypses (every 6th level) on the surface and coloured ones projected on the floor (`_detailed_isohypse_surface`). The τ(T) curves and circles lie on the floor. Axes "Temperature (K)", "log₁₀ t (s)", "ΔC/C₀ (×10⁻⁵)".
- **Rate-Window Analysis Map**, 2D colour map: black background, x "1/kT (eV⁻¹)", log y "T²/eₙ (K² s)", colour N_T/N_D on a log scale (jet, colorbar "Nₜ / N_D"). Per trap, in its colour with a white outline: dashed Arrhenius line `<id> Arrhenius, Et = <E> eV` and 22 open circles `<id> (fitted)`. `Trap ids` labels the middle visible circle. Shows "Insufficient data for Rate-Window map" when it cannot be built.
- **Rate-Window Analysis Map**, 3D isohypse surface: log₁₀(N_T/N_D) as a surface over (1/kT, log₁₀ T²/eₙ), same colours and isohypses as above; each trap's dashed Arrhenius line lies on the floor (no circles). Axes "1/kT (eV⁻¹)", "log₁₀ T²/eₙ (K² s)", "log₁₀ Nₜ/N_D".

Legends and labels are fixed (they cannot be dragged); a left-drag on the spectra panel is the region selection, unless the toolbar's pan or zoom mode is on.

### Edit Labels & Legends dialog

A scrollable `Toplevel` (500×580, minimum 460×340). For each existing panel (Arrhenius Panel, DLTS Spectra Panel, Transient Map Panel, Rate-Window Map Panel) it offers `Title`, `X label`, `Y label` text entries with a point-size spinbox (6 to 28). For each existing legend (Arrhenius Legend, Spectra Legend, Transient Map Legend, Rate-Window Legend) it offers one `Font size` spinbox (6 to 18) and one entry per legend item (`Entry n`); a legend exists only when that panel's Labels choice is `Legend` (or `Results (Et, σ, Nt)` for the Arrhenius panel). The z label of a 3D view is not offered. Buttons: **Apply** (applies and redraws every panel canvas), **Apply & Close**, **Close** (discards unapplied edits). Edits last until the panel is redrawn: any Display change affecting it, or the next **Run Analysis**.

### Results text

Example layout (numbers from the synthetic example further below):

```text
=======================================================
  DLTS Multiwindow Analysis  —  Results
=======================================================

  Signal     : Measured C (nearest sample)
  Denoise    : None (raw)
  Peak regions:
    R1: 250-400 K, single peak, Smoothing Spline (bootstrap)

-------------------------------------------------------
  Trap R1P1  (single peak, Smoothing Spline (bootstrap))
  Multi-window  (16 windows)
    fit  : weighted by Tpeak errors
    Et   = 0.5968 +/- 0.0032 eV
    sn   = 8.904e-16 +/- 1.076e-16 cm2
    slope     = ... K
    intercept = ...
    R2   = ...
    red. chi2 = ...
    Nt   = ... +/- ... cm-3  (2 Nd dC/C, from peak heights)
  Standard  (5 windows)
    ...
    Et uncertainty improvement: <Et_se(std) / Et_se(multi)>x

  Window detail  (multi):
    t1(ms)    t2(ms)     en(s-1)    Tpeak(K)   +/-(K)
  -----------------------------------------------------
       5.0      25.0       80.47       ...        ...

-------------------------------------------------------
  Nt (all traps, transient amplitude) ~ 6.236e+12 cm-3
```

A region with primitives is listed with its short primitive names and `  (from Quick R<n>)` when its method came from Quick Analysis. There is one `Trap` block per fitted trap, in peak-id order; a trap's **Standard** part appears only when the standard windows gave a fit for the same peak id. The per-trap `Nt` is `_trap_density_from_peaks` over the windows used in the fit; the last line is the total `_trap_density` (Step 8). `excl.` marks a window left out of the fit. `n/a` means the peak fit gave no T_p error. The fit line reads `UNWEIGHTED (no Tpeak errors)` when no weighting was possible, and adds `, <k> window(s) excluded` when windows were excluded.

## Import

```python
import detailedAnalysisTab as deT   # alias used in DLTSGUI_MainWindow.py
deT.construct_detailedAnalysisTab()

import detailedAnalysisTab as daT   # alias used in tests/test_hdf5_analysis.py and benchmarks/
data, temps, errs = daT._load_detailed_data(folder, None, None, None, 500.0, 0.4, 0.9)
```

`dataAnalysisTab.py` also imports this module, as `dA`, for the shared signal, peak and Arrhenius functions and defaults, including the peak-region helpers (`PRIMITIVE_*` and `DEFAULT_PROMINENCE`, which it re-exports under the same names, `_region_problem`, `_deconvolve_region`, `_trap_density_from_peaks`). In `DLTSGUI_MainWindow.py` the alias `daT` means `dataAnalysisTab`, not this module.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `C0` | `'#2a78d6'` | Blue: first trap's colour, info label text, region-drag highlight. |
| `C1` | `'#eb6834'` | Orange: fourth trap colour. |
| `TRAP_COLORS` | `(C0, '#1b9e77', '#9b59b6', C1, '#d4a017', '#e7298a', '#3f4f75')` | One colour per trap in peak-id order, cycling (`_detailed_trap_color`). |
| `TEXT_PRI`, `TEXT_SEC`, `TEXT_MUT` | `'#0b0b0b'`, `'#52514e'`, `'#898781'` | Text colors of the control column and dialogs. |
| `SURFACE`, `GRIDLINE`, `BASELINE` | `'#fcfcfb'`, `'#e1e0d9'`, `'#c3c2b7'` | Unused (the plots now use matplotlib's default styling). |
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
| `DEFAULT_TPEAK_LO`, `DEFAULT_TPEAK_HI` | `250.0`, `400.0` | Bounds of the default peak region, K (both tabs). |
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
| `EDGE_PEAK_FRAC` | `0.01` | A peak within this fraction of a grid step of either end of its peak region is an edge peak (`_peak_on_edge`) and gets no T_p error. |
| `MIN_TP_ERR_K` | `1e-4` (K) | Smallest T_p error accepted as real; smaller ones are treated as no error. |
| `PRIMITIVE_SPLINE` | `'Smoothing Spline (prominence peaks)'` | The spline primitive. Not a fit component: a spline region uses `impdData._smoothingSpline_multiPeakFinder`. Shared with Quick Analysis. |
| `PRIMITIVE_KEYS` | `{'Mirrored Lognormal (left tail)': 'mirroredLognormal', 'Gaussian': 'gaussian', 'Lorentzian': 'lorentzian', 'Voigt': 'voigt', 'Pseudo-Voigt': 'pseudoVoigt', 'Constant Baseline': 'constant', 'Linear Baseline': 'linear'}` | Primitive label → `iaT.DECONV_PRIMITIVES` key. |
| `PRIMITIVE_OPTIONS` | the `PRIMITIVE_KEYS` labels, then `PRIMITIVE_SPLINE` | All primitive labels (Quick Analysis' primitive combobox). |
| `PRIMITIVE_SHORT` | `MirLogN`, `Gauss`, `Lorentz`, `Voigt`, `pVoigt`, `Const`, `Linear`, `Spline` | Short primitive names used in region lists, Results and legends of both tabs. |
| `DEFAULT_PROMINENCE` | `'0.02'` (str) | Default spline minimum prominence, as a fraction of the region's largest \|S\|. |
| `METHOD_DEFAULT` | `'Default (Peak method below)'` | First choice of the region method combobox: no primitives, use the default peak method. |
| `_FIGURE_SAVE_FILETYPES` | list of 8 `(label, pattern)` tuples | Save Figure dialog file types. |
| `PANEL_ARRHENIUS`, `PANEL_SPECTRA`, `PANEL_TMAP`, `PANEL_RWM` | `'arr'`, `'spec'`, `'tmap'`, `'rwm'` | Panel keys of the `detailed_figures` etc. dicts. |
| `PANEL_ROWS` | `((PANEL_ARRHENIUS, PANEL_SPECTRA), (PANEL_TMAP, PANEL_RWM))` | The 2×2 panel grid. |
| `PANEL_LINKS` | dict panel key → `(partner key, x-axis map)` | Row partner of each panel and the map from its x axis to the partner's (`_reciprocal_1000` on the top row, `_reciprocal_kT` on the bottom row). |
| `ARR_VIEW_2D`, `ARR_VIEW_3D`, `ARR_VIEW_OPTIONS` | `'2D'`, `'3D (peak height up)'`, list of both | Arrhenius View choices. |
| `MAP_VIEW_2D`, `MAP_VIEW_3D`, `MAP_VIEW_OPTIONS` | `'2D colour map'`, `'3D isohypse surface'`, list of both | Map View choices. |
| `LABELS_TRAP_IDS`, `LABELS_LEGEND`, `LABELS_NONE`, `ARR_LABELS_RESULTS`, `SPEC_LABELS_REGIONS` | `'Trap ids'`, `'Legend'`, `'None'`, `'Results (Et, σ, Nt)'`, `'Region names'` | Labels choices. |
| `ARR_LABEL_OPTIONS`, `SPEC_LABEL_OPTIONS`, `MAP_LABEL_OPTIONS` | lists | Labels combobox values of the Arrhenius, Spectra and both map panels (Trap ids first, None last). |
| `MAP_STROKE` | `[withStroke(linewidth=3.5, foreground='white')]` | White outline of trap curves, circles and ids on the jet maps. |

Shared state in `dltsConfig` (`dltsc`):

| Name | Type | Meaning |
|---|---|---|
| `detailed_data` | dict `T_C -> (t_ms, cap_pF, C_inf)` | Loaded sweep. |
| `detailed_temps` | sorted list of float, °C | Loaded temperatures. |
| `detailed_figFrame` | `tk.Frame` | Container the panels are gridded into. |
| `detailed_figures`, `detailed_canvases` | dict panel key → `Figure` / `FigureCanvasTkAgg` | One entry per shown panel (keys `PANEL_*`). |
| `detailed_panelAxes` | dict panel key → `Axes` (2D or 3D) | Each shown panel's main axes. |
| `detailed_panelLegends` | dict panel key → `Legend` or `None` | Each shown panel's side legend (per its Labels choice). |
| `detailed_linkCids` | dict panel key → int | Pending `draw_event` connection that links the panel's x axis to its row partner after its first draw. |
| `detailed_linkBusy` | bool | True while one linked panel sets its partner's x limits (stops the echo back). |
| `detailed_lastOut`, `detailed_lastParams` | dict, dict | Last run's `_compute_detailed_analysis` result and parameter snapshot; every panel is drawn from them. |
| `detailed_lastResMw`, `detailed_lastResStd` | dict, dict/None | Last run's first trap: multi-window and standard result (kept for callers that read one trap). |
| `detailed_lastNt` | float | Last run's total N_T (all traps, transient amplitude, `_trap_density`). |
| `detailed_lastTraps`, `detailed_lastTrapsStd` | list of dict | Last run's multi-window / standard results, one per trap (`_compute_trap_arrhenius`). |
| `detailed_regions` | list of `{'tLo', 'tHi', 'primitives', 'prominence', 'source'}` | The peak regions (K). `primitives` is `[]` for the default single-peak finder, else `PRIMITIVE_OPTIONS` labels; `source` is `'Quick R<n>'` or `None`. Seeded with the default region (250–400 K, no primitives) by `construct_detailedAnalysisTab` when empty. |
| `detailed_regionListbox`, `detailed_regionMethodVar`, `detailed_regionMethodCombo` | `tk.Listbox`, `tk.StringVar`, `ttk.Combobox` | Region list and the selected region's method box. |
| `detailed_spanSelector` | `SpanSelector` or `None` | Region picker on the DLTS Spectra panel; `None` when that panel is off. |
| read: `deconv_regions` | list | Quick Analysis' Peak Deconvolution regions, the source of region methods. |
| `detailed_loadingBusy`, `detailedProcessingBusy` | bool (or `None` before first use) | Load / Run in progress. |
| `detailed_executor` | `ProcessPoolExecutor` or `None` | The tab's single worker process. Shut down by `DLTSGUI_MainWindow.py` on exit. |
| `detailed_*Var`, `detailed_stdEntries` | Tk variables | All control values (see tables above), including the Display `View` / `Labels` variables `detailed_arrViewVar`, `detailed_tmapViewVar`, `detailed_rwmViewVar`, `detailed_arrLabelsVar`, `detailed_specLabelsVar`, `detailed_tmapLabelsVar`, `detailed_rwmLabelsVar`. |
| `detailed_loadButton`, `detailed_runButton`, `detailed_loadInfoLabel`, `detailed_statusLabel`, `detailed_resultsText` | widgets | Buttons, labels, Results text. |
| read: `tabControl`, `detailedAnalysisTab`, `root`, `log_to_textbox` | | Main-window objects. |

## Analysis method

Times are in ms unless noted; temperatures are stored in °C (the keys of `detailed_data`) and converted with `T_K = T_C + 273.15`, and everything computed from them, shown or reported is in K; capacitance is in pF (as returned by the extractors).

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

**Step 5. Peaks per window and region** (`_compute_trap_arrhenius`, `_window_region_peaks`). Every window's S(T) is searched in every peak region, in list order:

- **Region with primitives** (from Quick Analysis): `_deconvolve_region`, the Peak Deconvolution of Quick Analysis (its [Step 5](dataAnalysisTab.md#analysis-method)): a Smoothing Spline region gives every peak above the region's prominence, a primitive region one peak per peak-shaped primitive, each with T_p, height and their errors. A peak on the region edge, or with an error below `MIN_TP_ERR_K`, keeps its T_p but has no T_p error (`_usable_tp_err`).
- **Region without primitives** (default): this tab's single-peak finder over the region, `_peak_from_signal(T_K, S, S_err, tLo, tHi, peak method)`, as below. The region then acts exactly like the old Peak Search Range. Such a peak has no height error.

Peak `P<k>` of region `R<r>` is the k-th peak of that region in that window, counted from low T; the same peak id in different windows is one trap. A region fit failure is recorded as a message (`<t1>/<t2> ms, R<r>: <message>`) and that window simply has no peak there.

The single-peak finder (`_peak_from_signal`, `_find_peak_full`) works on one region:

```text
mask = (T_K >= tLo) & (T_K <= tHi)
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

**Step 6. Arrhenius fit, one per trap** (`_compute_trap_arrhenius` → `_arrhenius_fit`, `_fit_arrhenius_line`). The peaks are grouped by peak id and each trap is fitted on its own windows, separately for the multi-window and the standard set:

```text
x = 1000 / T_p            # K^-1 (x 1000)
y = ln(e_n / T_p^2)       # ln(s^-1 K^-2)
```

`_find_peak` reports no T_p error for a peak on the edge of its region (the signal is still rising out of the region, so the grid end is not a real peak) and for any error below `MIN_TP_ERR_K`, whichever peak method is used. Windows with no T_p error are excluded from the fit (`fit_mask`) unless fewer than 3 windows have errors; then all windows are fitted. A trap with fewer than 2 fittable windows gets no line (message `<id>: fewer than 2 windows can be fitted; no Arrhenius line.`). Traps are ordered by peak id, numerically (`_peak_id_order`: R2 before R10).

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

**Step 8. Trap density.** Two values are reported.

Per trap (`_trap_density_from_peaks`, shared with Quick Analysis), from the peak heights of the windows used in that trap's fit:

```text
r      = t2 / t1
f(r)   = r^(-1/(r-1)) - r^(-r/(r-1))                # _boxcar_peak_factor
N_T,w  = 2 * Nd * |S_peak| / f(r)                   # cm^-3, one value per window
```

combined as the error-weighted mean (error scaled by `sqrt(χ²ᵣ)` when > 1) when every peak has a height error, else the plain mean and its standard error. Default-method (single-peak) peaks have no height error, so their N_T is always the plain mean.

Total (`_trap_density`), the value earlier versions reported as N_T:

```text
S_ref(T) = (C(rb_ms) - C(2.0 ms)) / C_inf
N_T      = 2 * max_T |S_ref(T)| * Nd              # cm^-3 (Nd in cm^-3)
```

This uses all loaded temperatures, not only the peak regions, and does not separate traps.

**Step 9. Display arrays.**

- Spectra (`_prepare_spectra`): windows at indices `round(linspace(0, N-1, min(nSpectra, N)))`; curve `S(T) · 1e3`. The tab passes `nSpectra = N`, so every window's spectrum is computed; the panel then shows `Spectra to plot` of them at indices `unique(round(linspace(0, N-1, min(n, N))))` (`_detailed_shown_spectra`).
- Transient map (`_prepare_transient_map`): time range `max(2.0, t[1])` to `0.95 · rb_ms` ms; up to 250 log-spaced sample indices; `Z = (C(t) - C_inf) / C_inf`, displayed as `Z · 1e5`; 64 color levels between the 1st and 99th percentile. Needs at least 10 time points.
- τ overlay (`_detailed_tau_curves`), per trap: `e_n(T) = gamma · sigma_n · T^2 · exp(-E_a / (kB T))`, `tau = 1/e_n` (s), over T from `min(T) − 20` to `max(T) + 20` K (600 points). Only the part within 0.5× to 2× the map's time range is kept and then clipped to that range; the same for the (T_p, 1/e_n) points.
- Rate-window map (`_prepare_rate_window_map`): 100 log-spaced t1 from t1_min to t1_max, `t2 = ratio · t1`; for every (window, temperature): `x = 1/(kB T)` (eV⁻¹), `y = T^2 / e_n` (K² s), `z = 2 |S|` (= N_T/N_D); points with `z < 1e-8` or `|C_inf| < 1e-30` skipped. Linearly interpolated (`scipy.interpolate.griddata`) onto 220 × 220 points in (x, log10 y); log color scale from the 2nd percentile (≥ 1e-8) to the 98th percentile (≥ 10 × low). Overlay line per trap `y = exp(E_a · x) / (gamma · sigma_n)`. Needs at least 6 points.
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

**Side effects** `dltsc.tabControl.add(dltsc.detailedAnalysisTab, text='Detailed Analysis')`, `tabControl.pack(expand=1, fill="both")`; creates every `dltsc.detailed_*` variable and widget listed above with the defaults listed above, seeds `dltsc.detailed_regions` with the default region when it is empty, and selects R1 in the region list. Run starts disabled. `dltsc.detailedAnalysisTab` must already exist as a `ttk.Frame` in the notebook.

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

**Side effects** None. **Called by** `_compute_trap_arrhenius`, `_compute_arrhenius`.

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

**Called by** `_window_region_peaks` (regions without primitives), `_compute_arrhenius`; `dataAnalysisTab._window_peaks`, `dataAnalysisTab._calculate_rate_windows`.

#### _arrhenius_fit(en_list, Tp_list, Tp_err_list, gamma)

Steps 6 and 7 on a list of peaks. Shared with Quick Analysis.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `en_list` | list of float | | e_n, s⁻¹. |
| `Tp_list` | list of float | | T_p, K. |
| `Tp_err_list` | list of float/None | | T_p errors, K; `None` or NaN = no error. |
| `gamma` | float | | γ, cm⁻² s⁻¹ K⁻². |

**Returns** `None` when fewer than 2 windows can be fitted; otherwise the dict described under `_compute_arrhenius` below, without `Sp_arr`, `peak_method` and `detail`.

**Called by** `_compute_trap_arrhenius`, `_compute_arrhenius`; `dataAnalysisTab._quick_arrhenius`, `dataAnalysisTab._run_arrhenius_solver`.

#### _trap_density(data, temps, rb_ms, nd)

Step 8, total: `2 · max_T |(C(rb_ms) − C(2 ms)) / C∞| · nd`, cm⁻³, from `_prepare_signal_data` records. **Called by** `_compute_detailed_analysis`; `dataAnalysisTab._quick_arrhenius`.

#### _compute_arrhenius(windows, temps, data, gamma, t_peak_lo, t_peak_hi, peak_method=PEAK_METHOD_SPLINE, peak_min_frac=0.05)

Steps 4 to 7 for one set of windows and one peak-search range, the single-trap path the tab used before peak regions: `_rate_window_signal` and `_peak_from_signal` per window, then `_arrhenius_fit`. The tab now uses `_compute_trap_arrhenius`; a single region without primitives gives exactly this result (`tests/test_peak_deconvolution.py`).

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
| `detail` | list of `(t1, t2, e_n, T_p in K, T_p error or None, peak S)`. |

**Side effects** None. **Called by** `tests/test_peak_deconvolution.py` (no longer by the tab).

#### Peak-region helpers (shared with Quick Analysis)

These live in the "PEAK REGIONS (SHARED WITH QUICK ANALYSIS)" section so both tabs, and this tab's worker process, can run them. A region is a dict `{'tLo', 'tHi' (K), 'primitives' (list of PRIMITIVE_OPTIONS labels), 'prominence' (float)}`, plus `'source'` in this tab. Quick Analysis calls them as `dA.*`; its reference documents the method in [Steps 5 and 7](dataAnalysisTab.md#analysis-method).

| Function | Returns |
|---|---|
| `_region_problem(region)` | Why a region cannot be deconvolved (upper bound ≤ lower, no primitives, Smoothing Spline mixed with other primitives, no peak-shaped primitive), or `None`. |
| `_usable_tp_err(tpErr, onEdge)` | `float(tpErr)`, or `None` for an edge peak or a `None` / non-finite / below-`MIN_TP_ERR_K` error. |
| `_deconvolve_region(sig, region)` | One window's S(T) (`sig = {'T_k', 'Signal', 'Signal_err'}`) deconvolved inside a region with primitives: dict `ok`, `message`, `x`, `residual`, `residualNorm`, `xf`/`yf`, `componentCurves`, `peaks` (`{T_peak, T_peak_err, S_peak, S_peak_err, primitive, onEdge}`, low to high T), `redchi`, `rsquared`. Fewer than 5 points in the region, or an exception, gives `ok=False` with a message. |
| `_boxcar_peak_factor(t1, t2)` | `f(r) = r^(-1/(r-1)) - r^(-r/(r-1))`, `r = t2/t1`: the double-boxcar peak height of a unit exponential transient. `_boxcar_peak_factor(20.0, 100.0)` ≈ 0.535. |
| `_trap_density_from_peaks(peaks, nd)` | `(Nt, Nt_err)` in cm⁻³ from peaks `{S_peak, S_peak_err or None, t1, t2}` (Step 8). `Nt_err` is `None` for a single peak without a height error. |
| `_region_method_text(region, peak_method)` | How the region finds peaks: short primitive names joined by ` + ` (with ` (prom. ≥ <p>)` for a spline region), or `single peak, <peak_method>` without primitives. |
| `_peak_id_order(peakId)` | Sort key `(r, k)` of `'R<r>P<k>'` as integers. |

#### _window_region_peaks(T_K, S, S_err, region, peak_method, peak_min_frac=PEAK_MIN_FRAC)

Peaks of one window's S(T) inside one region (Step 5): `_deconvolve_region` when the region has primitives, else `_peak_from_signal` over `[tLo, tHi]` with `peak_method`.

**Returns** `(peaks, message)`: peaks as `[{T_peak, T_peak_err, S_peak, S_peak_err, primitive, onEdge}]`, low to high T; `message` is `''` unless the deconvolution failed. A single-peak result has `S_peak_err=None`, `primitive=peak_method` and `onEdge = (Tp_err is None)`; a skipped window gives `([], '')`.

**Side effects** None. **Called by** `_compute_trap_arrhenius`.

#### _compute_trap_arrhenius(windows, temps, data, gamma, regions, peak_method=PEAK_METHOD_SPLINE, nd=DEFAULT_ND, peak_min_frac=PEAK_MIN_FRAC)

Steps 4 to 8 for one set of windows and all regions: every region's peaks in every window, grouped by peak id, one `_arrhenius_fit` per trap.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `windows` | list of (t1, t2) | | Gate times, ms. |
| `temps` | list of float | | Temperatures, °C. |
| `data` | dict | | `_prepare_signal_data` records. |
| `gamma` | float | | γ, cm⁻² s⁻¹ K⁻². |
| `regions` | list of dict | | Peak regions (see above). |
| `peak_method` | str | `PEAK_METHOD_SPLINE` | Single-peak finder for regions without primitives. |
| `nd` | float | `DEFAULT_ND` | Nd, cm⁻³, for the per-trap N_T. |
| `peak_min_frac` | float | `0.05` | Skip threshold of the single-peak finder. |

**Returns** `(traps, windowPeaks, messages)`:

- `traps`: one dict per trap with at least 2 fittable windows, in peak-id order: the `_arrhenius_fit` keys plus `peakId`, `region` (0-based index), `method` and `peak_method` (both `_region_method_text`), `win_idx` (window index of each point), `Sp_arr` (|S_peak|), `detail` (rows `(t1, t2, e_n, T_p in K, T_p error or None, |S_peak|)`), `Nt`, `Nt_err` (`_trap_density_from_peaks` over the fitted windows).
- `windowPeaks[w]`: list of `(peakId, peak)` found in window `w`, including peaks of traps without a fit.
- `messages`: region fit failures and traps with too few windows.

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
| `p` | dict | | Parameter snapshot with keys `signalMethod`, `denoise`, `t1Min`, `t1Max`, `nWin`, `ratio`, `stdWins`, `gamma`, `nd`, `regions`, `tpLo`, `tpHi`, `peakMethod`, `rbMs`, `nSpectra`, `showSpectra`, `showTmap`, `showRwm` (the GUI also passes `showStd`, `showTau`, unused here). The GUI always passes `showSpectra`, `showTmap`, `showRwm` (and `showStd`, `showTau`) as `True` and `nSpectra` = N windows, so the result holds every panel's data and the Display options can change the plots without a re-run. `regions` is optional: when it is missing or empty, one region `[tpLo, tpHi]` without primitives is used, the old single-peak behaviour. |

**Returns** a dict:

| Key | Meaning |
|---|---|
| `traps`, `trapsStd` | `_compute_trap_arrhenius` trap lists for the multi-windows and the usable standard windows (`[]` when there are none). |
| `resMw` | `traps[0]`, the first trap (for callers that read one trap). |
| `resStd` | The standard-window trap with the same peak id as `resMw`, or `None`. |
| `windowPeaks` | Per multi-window, the `(peakId, peak)` list (spectra markers). |
| `regions` | The regions used. |
| `messages` | Fit messages of both sets (standard ones prefixed `standard `). |
| `mw`, `T_K` | Multi-windows `(t1, t2)` in ms; temperatures in K. |
| `Nt` | Total `_trap_density`, cm⁻³. |
| `spectra`, `tmap`, `rwm` | Display arrays; `None` when their `show*` flag is false or the map cannot be built. |

**Side effects** None. Raises `ValueError('Multi-window: no peaks found. Check the t1 range and the peak regions.')` when no trap has a multi-window fit.

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

On the same data the five standard windows give E_a = 0.5979 ± 0.0042 eV. `p` has no `regions`, so this is the default region 250–400 K with the spline finder; `out['traps']` holds the one trap `R1P1`. To deconvolve two overlapping traps instead, pass for example `regions=[dict(tLo=250.0, tHi=420.0, primitives=['Gaussian', 'Gaussian'], prominence=0.02, source=None)]`, which gives traps `R1P1` and `R1P2` (`tests/test_peak_deconvolution.py`).

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

**Run Analysis** command. Logs `load data first.` without data; returns silently when busy. Then checks the peak regions: with none it reports `Peak regions: add at least one peak region.`; a region with upper ≤ lower bound, or with primitives that fail `_region_problem`, is reported as `Peak regions: R<n>: <problem>; ...` in the status label and the log, and nothing runs. Otherwise it snapshots every parameter into a dict (including copies of `dltsc.detailed_regions`, so later region edits cannot change a running analysis; `showStd`, `showSpectra`, `showTmap`, `showTau`, `showRwm` are always `True` and `nSpectra` is N windows, so no Display variable is read), runs `_compute_detailed_analysis` in the worker, then on the main thread calls `_detailed_plot` and `_detailed_write_results`, stores `detailed_lastResMw`, `detailed_lastResStd`, `detailed_lastNt`, `detailed_lastTraps`, `detailed_lastTrapsStd`, logs up to 10 fit messages (then `... and <n> more fit message(s).`), and sets the status label to `Done.` plus each trap's `<id>: Et = <E ± err> eV`. Errors appear as `Error: <message>` in the status label and the log.

#### Peak region controls

The "PEAK REGIONS (CONTROLS)" section edits `dltsc.detailed_regions` from the Peak Regions widgets. Every edit refreshes the region list and reports `<message>  Run Analysis to refit.` in the status label (and the message in the log) through `_detailed_regions_changed(message)`; nothing is recomputed.

| Function | What it does |
|---|---|
| `_detailed_add_region()` | **Add Region**. Reads the bounds (`_detailed_region_bounds`), gives the new region the method of `_detailed_best_quick_method(tLo, tHi)` and appends it. Reports `R<n> added (<lo>–<hi> K) with the method of Quick R<m> (...)`, or `... no Quick Analysis region covers it, so it uses the default <peak method>.` |
| `_detailed_update_region()` | **Update**. Moves the selected region to the bounds (`R<n> moved to ...`). |
| `_detailed_remove_region()` | **Remove**. Deletes the selected region (`R<n> removed (later regions renumbered).`). |
| `_detailed_apply_method()` | Method combobox selection: gives the selected region the chosen Quick Analysis method, or the default finder for `Default (Peak method below)`. |
| `_detailed_refresh_method_options()` | `postcommand` of the method combobox: `METHOD_DEFAULT` plus `_detailed_quick_methods()` labels. |
| `_detailed_quick_methods()` | `[(label, quick region)]` for every Quick Analysis region in `dltsc.deconv_regions` that passes `_region_problem`; label `Quick R<n> (<lo>–<hi> K): <primitives>`. |
| `_detailed_best_quick_method(tLo, tHi)` | The Quick method whose region overlaps `[tLo, tHi]` by the most kelvin, or `None` if none overlaps. |
| `_detailed_set_region_method(region, method)` | Copies the Quick region's primitives and prominence into `region` with `source='Quick R<n>'`, or sets `primitives=[]`, the default prominence and `source=None` when `method` is `None`. |
| `_detailed_region_bounds()` | `(tLo, tHi)` from T min / T max, or `None` with a status message when they are not numbers or T max ≤ T min. |
| `_detailed_on_region_select()` | List selection: copies the region's bounds into T min / T max and its method into the method box. |
| `_detailed_refresh_regions(selectIndex=None)`, `_detailed_region_text(r, region)`, `_detailed_selected_region()` | Rebuild the list (also when the default peak method changes), format one line, and return the selected index (or `None`). |
| `_detailed_on_span_select(tLo, tHi)` | `SpanSelector` callback on the DLTS Spectra panel (x axis in K): fills T min / T max (1 decimal) and shows `Picked <lo>–<hi> K: click Add Region (or Update Region).` |
| `_detailed_trap_color(trapIndex)` | `TRAP_COLORS[trapIndex % len(TRAP_COLORS)]`. |

#### Plotting

The "PLOTTING", "LINKED TEMPERATURE AXES", "ARRHENIUS PANEL", "DLTS SPECTRA PANEL", "TRANSIENT MAP PANEL", "RATE-WINDOW ANALYSIS MAP PANEL" and "DISPLAY OPTIONS" sections draw the panels described under Figure. Artist creation only: every array was computed in the worker. Panels are built with `Figure()`, never `pyplot`, so no extra pyplot window opens. A panel-drawing function takes a `Figure` or `SubFigure` and the Display options dict and returns `(ax, legend)`, so the same code draws the on-screen panels and the saved figure.

| Function | What it does |
|---|---|
| `_detailed_plot(out, params)` | Stores `out` / `params` as `dltsc.detailed_lastOut` / `detailed_lastParams`, then `_detailed_layout_panels()`. Called after each run. |
| `_detailed_layout_panels()` | Destroys the old panel widgets (and forgets their entries), then for each shown panel creates a holder frame gridded as in the Figure table, a `Figure(figsize=(6.0, 4.5), layout='constrained')`, its `FigureCanvasTkAgg` (requested size 1×1, so packing sizes it) and a `NavigationToolbar2Tk` above it, and draws it with `_detailed_draw_panel(key, draw=False)`. No explicit draw: the resize after packing triggers the single render. Does nothing before the first run. |
| `_detailed_forget_panel(key)` | Drops the panel's entries from `detailed_figures`, `detailed_canvases`, `detailed_panelAxes`, `detailed_panelLegends`, `detailed_linkCids`; for the spectra panel also sets `detailed_spanSelector = None`. |
| `_detailed_draw_panel(key, draw=True)` | Clears the panel's figure and redraws it from the last result with the current Display options; stores its axes and legend; resets the toolbar history; for the spectra panel creates `dltsc.detailed_spanSelector` (horizontal `SpanSelector`, `minspan=1.0` K, keeping the x limits the selector would otherwise stretch to 0); then `_detailed_link_panel(key)` and `draw_idle()` (when `draw`). |
| `_detailed_redraw(*keys)` | `_detailed_draw_panel` for each given panel that is shown. |
| `_detailed_display()` | The Display options now, as a dict: `showSpectra`, `showTmap`, `showRwm`, `showTau`, `showStd`, `nSpectra` (at least 1; 5 if the spinbox does not hold a number), `arrView`, `tmapView`, `rwmView`, `arrLabels`, `specLabels`, `tmapLabels`, `rwmLabels`. |
| `_detailed_shown_panels(disp)` | Rows of `PANEL_ROWS` keeping the shown panels (Arrhenius always), empty rows dropped. |
| `_detailed_draw_panel_on(fig, key, out, params, disp)` | Dispatches to the panel's drawing function below. |
| `_detailed_side_legend(fig, handles, labels, **kw)` | `fig.legend(..., loc='outside right upper', fontsize=8)`, or `None` without handles. |
| `_detailed_link_panel(key)` | Replaces the panel's pending link with a one-shot `draw_event` handler that, after the first draw, connects the 2D axes' `xlim_changed` callback to `_detailed_follow_xlim`. |
| `_detailed_follow_xlim(key, ax)` | Converts `ax`'s x limits with the `PANEL_LINKS` map and sets them on the row partner (if shown and 2D), guarded by `detailed_linkBusy`; skipped for non-positive or non-finite limits. |
| `_reciprocal_1000(v)`, `_reciprocal_kT(v)` | `1000/v` (1000/T ↔ T) and `1/(KB_EV·v)` (T ↔ 1/kT); each is its own inverse. Division warnings suppressed. |
| `_detailed_arrhenius_errorbars(ax, res, color)` | x/y error bars (`dx = 1000·dT/T²`, `dy = 2·dT/T`) for fitted windows that have a T_p error. |
| `_detailed_fit_label(res, kind)` | `'<id> <kind> (<N>): <Et ± err> eV'`. |
| `_detailed_results_legend(fig, out)` | The `Results (Et, σ, Nt)` text legend (monospace, invisible handles). |
| `_detailed_draw_arrhenius(fig, out, disp)` | Arrhenius panel, 2D view (or `_detailed_draw_arrhenius_3d` for the 3D view). |
| `_detailed_draw_arrhenius_3d(fig, out, traps, stdById, disp)` | Arrhenius panel, 3D view (peak height as z). |
| `_detailed_shown_spectra(spectra, nSpectra)` | `nSpectra` of the computed spectra, spread evenly over the windows. |
| `_detailed_draw_spectra(fig, out, disp)` | DLTS Spectra panel. |
| `_detailed_tau_curves(traps, T_K, t_s, gamma)` | Per trap with a visible τ(T): `(index, res, T, τ(T), Tp, 1/eₙ)` on the map's time range (Step 9). |
| `_detailed_draw_transient_map(fig, out, params, disp)` | Transient map panel, 2D or 3D. |
| `_detailed_isohypse_surface(ax, X, Y, Z, norm, levels, cmap='jet')` | 3D surface (at most ~90 × 90 facets) with black isohypses every 6th level on it and coloured ones projected on the floor at `levels[0]`; sets the z limits and returns a `ScalarMappable` for the colorbar. |
| `_detailed_draw_rate_window_map(fig, out, params, disp)` | Rate-window map panel, 2D or 3D. |
| `_detailed_on_display_change(*keys)` | Trace callback of every Display variable and of `detailed_stdWinsVar`: redraws the given panels, or (no keys: a Show checkbox changed) rebuilds the grid. Does nothing before the first run. |

#### _detailed_open_label_editor()

**Edit Labels & Legends** command. Builds the dialog described above from `detailed_panelAxes` and `detailed_panelLegends`; logs a hint and returns when no panel exists yet. Nested helpers: `section(title)` (divider and heading), `axis_row(parent, label, current_text, current_size, setter_fn)` (text entry plus size spinbox), `apply_all()` (applies every edit and calls `draw_idle()` on every panel canvas).

#### _detailed_write_results(out, params)

Builds the Results text shown above from the `_compute_detailed_analysis` result (settings, peak regions, one block per trap, total N_T) and writes it into `dltsc.detailed_resultsText`. Nested `fit_block(res)` formats one fit.

#### _detailed_save_figure()

**Save Figure...** command. Logs a hint if no analysis has been run (`detailed_lastOut` is `None`). Builds the figure with `_detailed_combined_figure(detailed_lastOut, detailed_lastParams, _detailed_display())`, then `.svg`/`.eps`/`.pdf`: `savefig(path, bbox_inches='tight')`; other extensions: `savefig(path, dpi=180, bbox_inches='tight', facecolor='white')`. Save errors are logged. Label-editor edits are not in the saved figure, which is drawn afresh.

#### _detailed_combined_figure(out, params, disp)

**Returns** a new `Figure(figsize=(14, 5.5 · rows), layout='constrained')` with one `SubFigure` per shown panel on a rows × 2 grid, laid out as on screen (a panel alone in its row spans it), each drawn by the same panel function as on screen.

#### _detailed_export_txt()

**Export Results to TXT** command. Logs a hint if Results is empty; otherwise writes it to the chosen file (UTF-8).

#### Nested helpers in construct_detailedAnalysisTab

`section(title)` draws a divider and an upper-case heading; `row(label, widget_factory, **kw)` packs a 15-character label and a widget; `spinbox(parent_, var, lo, hi, inc, fmt='%g', width=9)` builds a `ttk.Spinbox`; `combo_row(label, var, options)` packs a 9-character label and a read-only combobox (Display `View` / `Labels`); `panel_heading(text, var=None)` packs a bold Display panel heading, or a checkbox when `var` is given. After the Display widgets, a `trace_add('write', ...)` on each Display variable and on `detailed_stdWinsVar` calls `_detailed_on_display_change` with the panel(s) it affects.

## Notes and limitations

- The **ZI MFIA GRID** fields `Grid offset (s)`, `Grid dt (s)` and `Chunk size` have no effect. `_load_detailed_data` accepts them as `grid_off`, `grid_dt`, `chunk_size` and never uses them; ZI grid values come from each header CSV (or `liveDataTab` defaults).
- Legacy `.txt`/`.h5` files use each file's own `timeStampImps` spacing as the sampling interval; `samplingRateS=1.8666666666666665e-05` s is only the fallback for files without usable time stamps.
- `.json` run files are not loaded (the legacy filename pattern accepts `.txt`, `.csv`, `.h5` only), and the loader returns no error message for them.
- **C₀ Estimation Window** and **RB duration (ms)** are applied at load time for C∞. Changing them without reloading only changes the N_T reference time and the transient-map range.
- The legacy `.h5`/`.txt` extractor multiplies `ImpedanceIm` by 1e12 unconditionally. On the HDF5 test run this gives values near 5e6 "pF", so the stored channel is not a capacitance in F. S = ΔC/C∞ is a ratio and is unaffected by the scale, but the pF label is not meaningful there.
- Labels say ΔC/C₀, but every quantity is normalized by C∞ (the late-time mean).
- Edge peaks no longer dominate the fit. The spline finder puts a peak that is still rising out of the search range on the last grid point in every bootstrap sample, with an "error" of about 1e-13 K; earlier versions kept such windows in the weighted fit, where they swamped the rest. On the 23 Sep run with the GUI-default windows this gave Et = 90.967 ± 7.9e9 eV; now those six edge windows are excluded and the result is 0.693 ± 0.013 eV (0.685 ± 0.015 eV with windows suited to the data). Tests: `tests/test_detailed_peaks.py`.
- The total N_T is `2·max|S_ref|·Nd` with `S_ref = (C(rb_ms) − C(2 ms))/C∞`, taken over all loaded temperatures, not the peak regions, so it sums every trap. `_quick_arrhenius` uses the same definition (`_trap_density`). If `rb_ms` is past the end of a transient, `_cap_at` returns the last sample (Measured C) or extrapolates the spline (Smoothed C). The per-trap N_T comes from the peak heights instead (Step 8).
- The standard-window fits are always computed and written to Results. **Show standard-window comparison** only controls drawing. When the standard windows are shown, the Arrhenius x range includes them.
- The Results line `slope = ... K` has the wrong unit. x is `1000/T`, so the slope is in units of 1000 K (slope = −E_a/(1000·kB)).
- The peak id is a position (k-th peak of a region in a window, from low T), not an identity check. If a window misses a peak of a multi-peak region (below the spline prominence, or still rising at the region edge), its later peaks shift to a lower `P<k>` and join the wrong trap. Check the ▼ markers on the spectra panel and the window detail of each trap.
- A region's T bounds only change with **Add Region** / **Update**; typing T min / T max or dragging on the spectra panel without clicking one of them has no effect on the next run. A region's Quick Analysis method is a copy taken when it was assigned.
- The region selector exists only on the DLTS Spectra panel, so the first region change after loading has to be typed (or the default region used) until a run has drawn the panel.
- `resMw` / `resStd` and `detailed_lastResMw` / `detailed_lastResStd` describe only the first trap. With several regions or primitives, read `traps` / `detailed_lastTraps`.
- If `_prepare_transient_map` finds equal 1st and 99th percentiles, it falls back to levels ±1e-4 in the ×1e5 display units, which is a tiny range.
- `_prepare_transient_map` builds its time axis from the first temperature and assumes all transients share it.
- In `_find_peak_parabolic` a vertex outside the 5 fitted points, or an upward-opening parabola, falls back to the grid maximum with no error; that window is then excluded from the weighted fit.
- A failed load keeps the previously loaded data, and **Run Analysis** stays enabled for that old data.
- `_detailed_export_txt` does not catch file-write errors.
- Figure edits made in **Edit Labels & Legends** last only until the panel is redrawn (a Display change affecting it, or the next run), and are not in the figure written by **Save Figure...** (a panel's own toolbar save keeps them).
- The Display options redraw from the last result, which was computed with the parameters of that run. Changes to any analysis parameter (windows, regions, constants, signal method) only take effect at the next **Run Analysis**.
- The linked temperature axes work between 2D panels only; with a 3D view on either side of a row, zooming does not propagate.
- Both analysis tabs use `KB_EV` = `8.617333262145e-5` eV/K. (Before, this tab used `8.617333e-5`; the difference in E_a is below 1e-7 relative.)
- The whole `detailed_data` dict is pickled to the worker process on every Run. For long sweeps with 500 ms transients this is tens of MB per run.

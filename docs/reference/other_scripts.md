# Other scripts

This page covers the files in the repository that are not part of the GUI tabs or the instrument/analysis libraries:

| File | What it is |
|---|---|
| `runDLTS.py` | Old command-line run script. Does not work with the current `runDlts_Tools`. |
| `DLTS_APP.py` | Standalone tkinter app "DLTS Multiwindow Analysis". Ported into the **Detailed Analysis** tab. |
| `DrKayisScript.py` | Standalone PyQt6 app "Offline DLTS Core Transient & Defect Signature Suite". Ported into the **Qualitative Analysis** section of the Live Tools tab and the **Quick Analysis** tab. |
| `scrapwork.py` | Scratch script for trying MFIA DAQ acquisitions. Talks to the instrument when run. |
| `postprocessingTab.py` | Empty file (0 bytes). Placeholder; imported by nothing. |
| `tests/` | pytest test suite (no hardware needed). |
| `benchmarks/bench_hdf5.py` | Synthetic HDF5 vs JSON benchmark (no hardware). |
| `benchmarks/hardware/` | Real-hardware HDF5 benchmark. Moves the stage and biases the sample. |

The standard way to run a measurement is the GUI (`DLTSGUI_MainWindow.py`, see [DLTSGUI_MainWindow.md](DLTSGUI_MainWindow.md)).

## runDLTS.py

### What it's for

An early entry point for running a DLTS scan without the GUI. It imports the instrument and analysis modules, sets `LOKY_MAX_CPU_COUNT=4`, reloads `impedanceAnalysis_Tools`, and under `if __name__ == '__main__':` does:

```python
run = rdT.dltsRun()
run.initSetup()
run.runExperiment()
run.finishExperiment()
```

The rest of the file is commented-out analysis calls with hard-coded paths on other PCs.

### Command line

```text
python runDLTS.py
```

**This does not work.** `runDlts_Tools.dltsRun` has no methods `initSetup`, `runExperiment` or `finishExperiment`; the current names are `init_experiment()`, `run_experiment()` and `finish_experiment()`. The script stops with `AttributeError: 'dltsRun' object has no attribute 'initSetup'` right after the imports. It does not reach any instrument. Even with the names fixed, `dltsRun` reads its parameters from the GUI state in `dltsConfig` (`dltsc.impDev`, `dltsc.tempDev`, `dltsc.z_params_vars`, ...), which this script never sets up.

To run a scan without the GUI, follow `benchmarks/hardware/hw_common.py` and `hw_run.py`, which fill the same `dltsConfig` state headlessly.

Importing it also needs `pyserial` (`import serial`), `h5py`, `lmfit`, `pandas` and everything `impedanceAnalysis_Tools` imports.

## DLTS_APP.py

### What it's for

"DLTS Multiwindow Analysis - Interactive GUI App v1.3", a self-contained tkinter program. It loads a ZI MFIA temperature sweep exported as one subfolder per temperature, computes rate-window DLTS spectra for many windows, and fits an Arrhenius line to get the trap activation energy `Et`, the apparent capture cross-section and an estimate of the trap density `Nt`. The banner reads "SiC PiN Diode Deep Level Transient Spectroscopy" and the physical-constant defaults are for 4H-SiC.

It needs only `numpy`, `pandas`, `scipy` and `matplotlib` (plus tkinter). It does not import any other module of this repository.

### Relation to the GUI

The **Detailed Analysis** tab (`detailedAnalysisTab.py`) is a port of this app: the same palette, grid defaults, folder convention and multi-window Arrhenius pipeline, rewritten as module-level functions with `dltsc.detailed_*` globals, background workers instead of blocking calls, and log lines instead of message boxes. The tab also reads the other data formats (single combined ZI export, JSON `.txt` and `.h5` step files) through `liveDataTab`'s loaders, and adds peak-finding and fit options. See [data_formats.md](data_formats.md#zurich-instruments-mfia-csv-exports).

### How to launch

```text
python DLTS_APP.py
```

(The docstring says `python DLTS_App.py`; on Windows the case does not matter.) The window opens maximized. Browse to a data folder, click **Load Data**, then **Run Analysis**.

### Data it reads

`load_data()` scans the chosen folder for subfolders named like `25C_001`, `85C` or `n10C` (`_folder_re`, `n` = negative). In each it reads exactly `dev32271_imps_0_sample_param1_avg_00000.csv` (`;`-separated, columns `chunk;timestamp;value`), keeps chunk `0`, and skips the subfolder if the file is missing or has fewer than 100 rows. Values are multiplied by 1e12 (F to pF) unconditionally. The time axis is `grid_off + k * grid_dt` (s), converted to ms.

### Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `C0`, `C1`, `SURFACE`, `TEXT_PRI`, `TEXT_SEC`, `TEXT_MUT`, `GRIDLINE`, `BASELINE` | hex color strings | Plot palette. |
| `DEFAULT_GRID_OFF` | `-0.001` | ZI grid column offset, s (time of the first sample relative to reverse-bias start). |
| `DEFAULT_GRID_DT` | `1.86667e-5` | ZI grid column spacing, s. |
| `DEFAULT_CHUNK_SIZE` | `32768` | Samples per temperature. |
| `DEFAULT_RB_MS` | `500.0` | Reverse-bias duration, ms. |
| `_folder_re` | `re.compile(r'^(n?)(\d+)C(?:_\d+)?$', re.IGNORECASE)` | Temperature subfolder name. |

### Functions

#### folder_to_tempC(name)

Temperature in °C from a subfolder name (`'n10C'` gives `-10.0`), or `None` if the name does not match `_folder_re`.

#### cap_at(t_ms, cap, tv_ms)

Capacitance at time `tv_ms`, linearly interpolated with `np.interp`. Returns `float`.

#### find_peak_parabolic(T_arr, S_arr, hw=2)

Peak temperature of a DLTS spectrum: fits a parabola to the `2*hw+1` points around the maximum of `S_arr` and returns its vertex if it opens downward and lies inside that range; otherwise the temperature of the maximum sample.

#### load_data(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi)

Loads all temperature subfolders under `base` (see [Data it reads](#data-it-reads)). `C_inf` (the steady-state capacitance C0) is the mean over `cinf_lo * rb_ms <= t <= cinf_hi * rb_ms`, or the mean of the whole transient if that range is empty. Returns `(data, temps)`: `data[T_C] = (t_ms, cap_pF, c_inf)` and the sorted list of temperatures.

#### compute_arrhenius(windows, temps, data, gamma, t_peak_lo, t_peak_hi, peak_min_frac=0.05)

For each rate window `(t1, t2)` in ms: the signal `S(T) = (C(t2) - C(t1)) / C_inf`, flipped in sign if its minimum is larger in magnitude than its maximum, restricted to `t_peak_lo <= T <= t_peak_hi` (K). Windows whose peak is at most `peak_min_frac` of the largest `|S|` are skipped. The peak temperature comes from `find_peak_parabolic()` and the emission rate from `en = ln(t2/t1) / ((t2 - t1) * 1e-3)` (s⁻¹). A `linregress` of `ln(en/Tp²)` against `1000/Tp` gives `Et = -slope * 1000 * kB` (eV, `kB = 8.617333e-5` eV/K), its standard error, and `sigma = exp(intercept) / gamma`. Returns `None` if fewer than 2 windows give a peak, else a `dict` with `en_arr`, `Tp_arr`, `Sp_arr`, `Et`, `Et_se`, `sigma`, `R2`, `N`, `slope`, `intercept`, `x`, `y`, `detail` (rows `(t1, t2, en, Tp_C, peak)`).

### Class DLTSApp(root)

The main window. `root` is a `tk.Tk`. Main methods:

| Method | Purpose |
|---|---|
| `__init__(self, root)` | Sets the title, maximizes the window, builds the UI. |
| `_build_ui(self)` | Banner, scrollable control panel on the left, figure and results box on the right, status bar. |
| `_build_controls(self)` | All input sections (defaults in the table below) and the action buttons. |
| `_section(self, title)`, `_row(self, label, widget_factory, **kw)`, `_spinbox(self, parent, var, lo, hi, inc, fmt='%g', width=9)` | Layout helpers. |
| `_browse(self)` | Folder dialog for the data folder. |
| `_set_status(self, msg, color='#8fb4d8')` | Sets the status bar text. The `color` argument is ignored. |
| `_log(self, text)` | Replaces the results box text. |
| `_load_data(self)` | Calls `load_data()` with the current settings; enables **Run Analysis** on success. |
| `_run(self)` | Builds `N windows` log-spaced `t1` values from `t1 min` to `t1 max` with `t2 = ratio * t1`, runs `compute_arrhenius()` for them and for the 5 standard windows, estimates `Nt = 2 * max|S_ref| * Nd` with `S_ref = (C(RB duration) - C(2 ms)) / C_inf`, then plots and writes the results. |
| `_plot(self, res_mw, res_std, mw, std_wins, T_K, Nt)` | Draws the enabled panels (Arrhenius plot, DLTS spectra, 2D transient map, rate-window map). |
| `_install_drag(canvas, fig, artist, kind)` (static) | Mouse dragging for legends (`kind='legend'`) and the results annotation (`'annot'`). |
| `_plot_transient_map(self, ax, res_mw, T_K)` | Filled contour of ΔC/C0(t, T) on a log time axis, optional τ(T) = 1/en(T) overlay. |
| `_plot_rate_window_map(self, ax, res_mw)` | Nt/N_D map in (1/kT, T²/en) space with the Arrhenius line and a Z1/2 marker. |
| `_style_rwm_axes(self, ax)` | Black-background styling for that map. |
| `_open_label_editor(self)` | Dialog to edit titles, axis labels, legend text and font sizes. |
| `_write_results(self, res_mw, res_std, Nt)` | Text summary: Et ± error, σn, R², Nt, the Et-error improvement of multi-window over the 5 standard windows, and the per-window table. |
| `_save_png(self)` | Saves the figure (180 dpi). |
| `_export_txt(self)` | Saves the results text. |

Input defaults:

| Section | Setting | Default |
|---|---|---|
| ZI MFIA Grid | Grid offset (s), Grid dt (s), Chunk size, RB duration (ms) | `-0.001`, `1.86667e-5`, `32768`, `500` |
| C0 Estimation Window | Start, End (fraction of RB) | `0.40`, `0.90` |
| Physical Constants (4H-SiC) | γ (cm⁻² s⁻¹ K⁻²), N_D (cm⁻³) | `1.66e21`, `3.2e14` |
| Peak Search Range | T min, T max (K) | `250`, `400` |
| Multi-Window Parameters | N windows, t1 min (ms), t1 max (ms), ratio t2/t1 | `16`, `5`, `90`, `5` |
| Standard Windows | t1/t2 (ms) | `5/25`, `10/50`, `20/100`, `50/250`, `100/490` |
| Display | Spectra panel, spectra count, 2D transient map, τ overlay, rate-window map | on, `5`, on, on, on |

## DrKayisScript.py

### What it's for

"Offline DLTS Core Transient & Defect Signature Suite (v8 - ZI/SiC Format)", a PyQt6 program with three tabs that form a pipeline:

1. **Transient Extraction**: pick a folder, choose temperatures, extract and average the capacitance transients.
2. **Rate Window Analysis**: four double-boxcar rate windows, one DLTS spectrum each, peak found with a pseudo-Voigt fit.
3. **Arrhenius Defect Mapping**: straight-line fit of `ln(en/T²)` against `1000/T`, giving Et, the apparent capture cross-section and Nt.

### Relation to the GUI

| DrKayisScript.py tab | Ported to |
|---|---|
| 1. Transient Extraction | Qualitative Analysis in the **Live Tools** tab (`liveDataTab.py`: `_compute_zi_dataset`, `_compute_legacy_dataset`, `_compute_zi_transients`, `_compute_legacy_transients`, `_LEGACY_FILENAME_PATTERN`) |
| 2. Rate Window Analysis | **Quick Analysis** tab (`dataAnalysisTab.py`) |
| 3. Arrhenius Defect Mapping | **Quick Analysis** tab (`dataAnalysisTab.py`) |

The ports changed some things, as noted in their source comments. For example, Qualitative Analysis finds fill pulses with a threshold midway between the file's two excitation levels instead of the fixed -2.5 V used here, also reads `.h5` step files and a subfolder-per-temperature ZI export, and runs off the GUI thread. Quick Analysis makes the capture-cross-section prefactor a user input (fixed here at the silicon value `3.256e21`) and uses lmfit instead of `scipy.optimize.curve_fit`.

### How to launch

```text
python DrKayisScript.py
```

It needs PyQt6, which is **not installed** in the lab's Python (`C:\Users\spencer\anaconda3\python.exe`: `ModuleNotFoundError: No module named 'PyQt6'`). Install it with `pip install PyQt6` first. At start-up the app tries to load a hard-coded folder on another PC (`C:\Users\ikayi\OneDrive\Desktop\DLTS_SiC_PiN_DevR6C7_FP0V1ms_RB-5V500ms_...`) and silently skips it if it does not exist.

### Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `K_BOLTZMANN` | `8.617333262145e-5` | Boltzmann constant, eV/K. |
| `C_CONSTANT_SI` | `3.256e21` | Prefactor γ used for the capture cross-section: `sigma = exp(intercept) / C_CONSTANT_SI`. Labeled for Si in the code. |

### Class DLTSSuiteApp()

A `QMainWindow`. State kept on the instance: `dataset_registry` (temperature to data source), `processed_transients` (temperature to `{'time_ms', 'avg_cap_pf', 'C_infinity'}`), `rate_window_signals`, `extracted_peaks`, the ZI grid parameters (`zi_grid_col_offset = -0.001`, `zi_grid_col_delta = 1.86667e-05`, `zi_chunk_size = 32768`), and `sampling_rate_s = 1.8666666666666665e-05` for legacy files.

| Method | Purpose |
|---|---|
| `__init__(self)` | Sets up state and UI; loads the hard-coded default folder if it exists. |
| `init_ui(self)` | Creates the three tabs. |
| `setup_transient_tab(self)` | Folder button, temperature check list, timing fields (fill 1.0 ms, reverse bias 500 ms, slice 2 to 490 ms), **Extract & Average Transients** button, plot. |
| `browse_folder(self)` | Folder dialog, then `load_directory_path()`. |
| `load_directory_path(self, dir_path)` | Uses the ZI loader if a `*imps_0_sample_param1_avg_header*.csv` is in the folder, else the legacy loader; fills the temperature list. |
| `_load_zi_dataset(self, dir_path, header_filename)` | Single combined ZI export: grid parameters from the header's first row, temperature per chunk from `history_name` (`^(\d+)C_`), timing fields from `FP...ms` / `RB...ms` in the folder name. |
| `_load_legacy_dataset(self, dir_path)` | Per-temperature `.txt` (JSON) and `.csv` files matching `^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt\|csv)$`; multi-chunk CSVs use the fixed map chunk 0..8 = 120..160 °C. |
| `process_raw_transients(self)` | Runs the ZI or legacy extraction for the checked temperatures, with `C_inf` taken at 0.9 × reverse bias, and plots them. |
| `_process_zi_transients(self, selected_temps, c_inf_target_ms, execution_errors)` | Reads the data CSV once and cuts out each chunk; F to pF if values are below 1e-3. |
| `_process_legacy_transients(self, selected_temps, rb_duration_ms, c_inf_target_ms, execution_errors)` | JSON `.txt`: fill pulses where `AuxInput1` falls below -2.5 V, averages the following reverse-bias windows of `ImpedanceIm` × 1e12. CSV: see [data_formats.md](data_formats.md#3-legacy-csv-files). |
| `setup_rate_window_tab(self)` | Four window pairs (t1/t2 = 10/50, 20/100, 50/250, 100/490 ms), **Compute Boxcar Spectrums** button, peak table, plot. |
| `_pseudo_voigt(self, x, amp, center, fwhm, eta, offset)` | Pseudo-Voigt peak shape for the spectrum fit. |
| `calculate_rate_windows(self)` | For each window: `en = ln(t2/t1)/((t2 - t1)·1e-3)`, `S(T) = (C(t2) - C(t1))/C_inf` at the nearest samples, pseudo-Voigt fit for the peak (falls back to the largest-magnitude sample if the fit fails). |
| `setup_arrhenius_tab(self)` | N_D input (default `1.5e15` cm⁻³), solver button, result labels, plot. |
| `run_arrhenius_solver(self)` | Linear fit, `Et = -slope·1000·kB`, `sigma = exp(intercept)/C_CONSTANT_SI`, `Nt = 2·max|S_peak|·N_D`. Needs at least 2 windows. |

## scrapwork.py

A scratch file for trying triggered MFIA DAQ acquisitions by hand. It is not used by the application.

At import it creates a `ziDevice`, connects to the MFIA and loads parameters, then runs `runThis(daq_module, numReps, numPoints)` (1024 points, 100 repetitions), which sets up the DAQ module the way `ziDevice.pull_data(trigger=True)` does, busy-waits for completion, builds the 8 channels and plots them. The rest of the file (from about line 99 to the end, 910 lines in total) is commented-out analysis experiments.

Do not run it next to a measurement: it talks to the instrument. As written it also calls `impdDev.connectDevice()` and `impdDev.loadParams()`, which no longer exist (the methods are `connect_device()` and `load_params()`), so it stops with `AttributeError` before the connection.

## postprocessingTab.py

An empty file (0 bytes). No module imports it. `DLTSGUI_MainWindow.py` creates a frame `dltsc.postprocessingTab` but never adds it to the notebook, and the call `ppT.construct_postprocessingTab()` there is commented out. `dltsConfig.postprocessingTab` starts as `None`. It is a placeholder for a future tab.

## tests/

### How to run

From the repository folder:

```text
python -m pytest tests -q
```

On the lab PC (Python 3.13.9, pytest 8.3.4) the suite gave `163 passed in 46.53s` on 28 Sep 2026. Set `LOKY_MAX_CPU_COUNT` (for example `$env:LOKY_MAX_CPU_COUNT = 8` in PowerShell) to avoid scikit-learn's CPU-count warning. No instrument is needed or touched: the tests use synthetic data and fake devices.

`conftest.py` puts the repository root on `sys.path`, selects matplotlib's `Agg` backend, and provides:

| Name | Meaning |
|---|---|
| `SAMPLE_DT_S = 1.8666666666666665e-05` | Sample interval the app assumes (s). |
| `TICKS_PER_SAMPLE = 1120` | 60 MHz clock ticks per sample. |
| `make_step(T, n=2**14, seed=0, fill_ms=1.0, rb_ms=500.0)` | Synthetic `pull_data()` output for one temperature: 0 V / -5 V fill-pulse train on `AuxInput1`, a capacitance transient on `ImpedanceIm` whose time constant depends on `T`, integer `uint64` tick stamps. |
| `step_file_name(T, ext)` | The file name `init_experiment()` gives setpoint `T`, e.g. `n10p0.h5`. |
| `zi_device` fixture | A `ziDevice` created without `__init__` and without a connection, enough for its file writers. |
| `write_run(dev, folder, temps, ext, n=2**14, rb_ms=500.0)` | Writes one step file per temperature plus `runParams.txt`, as a run does. |

### Test files

| File | What it covers |
|---|---|
| `test_cleanup_time_axis.py` | `impdData.cleanup_data()` with both kinds of tick-stamp channel: integer 60 MHz clock ticks and the seconds axis of triggered runs. The seconds axis keeps its origin and units, a missing sample is interpolated, clock ticks are still filled and converted, and the axis kind is detected. |
| `test_convert_h5_to_text.py` | `convert_h5_to_text.py`: exact `.txt` and `.json` exports, NaN stage temperature as `null`, float tick stamps, unequal channel lengths, refusal of `p25p0.txt` / `p25p0.json` / `n10p0.txt` as output names, exports ignored by the folder scan, nothing left behind after a failed verification, the CLI. |
| `test_convert_json_to_h5.py` | `convert_json_to_h5.py`: `setpoint_from_name()` for accepted and rejected names, conversion with originals moved to `json_originals`, the root attributes of converted files, converted runs reading exactly like the JSON originals, triggered runs with float tick stamps, `--delete-json`, `--keep-json`, `--dry-run`, skipping existing `.h5` unless `--overwrite`, running twice, `--recursive`, unreadable files, failed verification, missing `runParams.txt`, a non-folder argument. |
| `test_hdf5_analysis.py` | The analysis code on HDF5 runs, each compared with the same run in JSON `.txt`: the Live Tools offline pipeline, live ingest, `read_data()` with mixed `.txt` and `.h5`, `append_data()` across formats, the folder scan (finds `.h5`, ignores partial `.tmp` files), Qualitative Extract & Average, Detailed Analysis loading (also a mixed folder), and the live watcher picking up `.h5` files only once renamed into place. |
| `test_hdf5_run.py` | `dltsRun` writing HDF5 through the real `_run_single_step()` / `run_experiment()` with fake devices: one file per step, stage temperature unreadable (step still succeeds) or read only once, Redo and Remove & Retake replacing only the selected steps, GUI closed during an acquisition or a retake (nothing written), a failed write marking the step failed and keeping the previous file. |
| `test_hdf5_writer.py` | `ziDevice.writeDataH5()` and `read_h5_record()`: lossless round trip with native dtypes, tick stamps beyond float precision, float tick stamps from triggered runs, a triggered step analysing like JSON, attributes, NaN for missing temperatures, empty channels, creating a missing parent folder, reader dtypes matching JSON, reading only some channels, overwrite, the file appearing only once complete, failure handling (no data file, previous file kept, temp file cleaned up), rename retries while the target is locked and giving up if it stays locked. |
| `test_detailed_peaks.py` | Detailed Analysis peak errors: a peak on the edge of the search range (spline and parabolic) or with an error below `MIN_TP_ERR_K` gets no error, `_peak_on_edge`, and a synthetic 0.60 eV trap with the search range cut so slow windows peak on its edge: those windows are excluded and Et stays at 0.60 eV (the old behaviour gave 0.99 eV). |
| `test_quick_vs_detailed.py` | Quick Analysis and Detailed Analysis on the same synthetic 0.60 eV run, windows and search range give the same Et, its error, σ, R², fitted/excluded counts and Nt, with and without edge peaks; Quick Analysis excludes edge-peak windows; a curve-fit peak on the range edge loses its error; both tabs have the same default windows, search range, γ, Nd and kB. |
| `test_temperatures_and_gaps.py` | `impdData` temperature keys from step file names and ZI history names (exact kelvin, decimals kept, `C`/`_N` suffixes, names without a temperature rejected) and Quick Analysis' °C conversion; `_gap_remove`: forward gaps, backward jumps from appended records, several gaps, seconds axes, unsigned ticks, uniform data untouched, small jitter kept. |
| `test_run_folder_and_serial.py` | `dltsRun.init_experiment()` refusing an empty or relative Data Root Folder and building `Root\MMDDYY\HHMMSS\` paths; `mK2000B` serial timeouts: timeouts set on connect, `read_temp()` retrying a missed reply, raising `TimeoutError` when the controller stays silent (lock released), and `go_to_temp()` failing instead of hanging. |
| `test_standalone_helpers.py` | No-GUI helpers: `ziDevice.configure()` (defaults with overrides, needs a connection to push, rejects unknown names), `mK2000B.configure()` (grid and motion attributes, rejects unknown names), and `dltsConfig.log_to_textbox()` printing when there is no GUI. |
| `test_transient_extraction.py` | Qualitative Extract & Average's pulse search (`liveDataTab._compute_legacy_transients` / `_find_reverse_bias_starts`) for the GUI default pulse levels and for a short fill pulse, the message for a constant excitation, a transient from a default-level run, the reasons given for skipped temperatures, `_legacy_run_timing()` from `runParams.txt` (and `None` when missing), and `_capacitance_axis_units()`. |

## benchmarks/bench_hdf5.py

### What it's for

Re-runs the HDF5 vs JSON measurements on synthetic data (from `tests/conftest.make_step`), through the application's own writers and readers. No hardware is used.

### Command line

```text
python benchmarks/bench_hdf5.py
```

It takes a few minutes and writes about 650 MB of synthetic data to `benchmarks/benchdata/`, which is deleted at the end. The results are written to `benchmarks/bench_results.json` (overwriting the stored results) and printed as it goes.

### What it measures

| Section | Measurement |
|---|---|
| Write | File size and write time of one step with 2^16 and 2^20 points, JSON vs HDF5, and whether both read back losslessly. |
| Run folder | Total size of a 40-temperature run (-50 to 145 °C in 5 °C steps, 2^16 points per step) in each format. |
| Offline load | Time of `read_data()`, `cleanup_data()`, `selected_emissions()` and `filter_emissions('pca')` for the whole run, and whether the results are identical. |
| Qualitative Extract & Average | `_compute_legacy_dataset()` + `_compute_legacy_transients()` time, and identical transients. |
| Detailed Analysis | `_load_detailed_data()` time, and identical data. |
| Live ingest | Time to append and process the 40th temperature. |
| Peak memory | `tracemalloc` peak while reading one temperature. |

The stored `bench_results.json` shows, for example, 583.9 MB (JSON) against 71.3 MB (HDF5) for the 40-temperature run, 4.56 s against 0.59 s to read it, and identical analysis results in every section.

## benchmarks/hardware/

A real-hardware benchmark: a short temperature scan on the MFIA and the Instec mK2000B, run through the application's own run code (not the GUI) with HDF5 output, then checked file by file and compared with the same data written as JSON. The run folder `DATA\DLTS\092826\114655` used as the example in [data_formats.md](data_formats.md) matches its default settings.

**This moves the stage and biases the mounted sample.** Only run it when the sample and the temperature range are safe. The MFIA uses the GUI's default parameters.

### Steps

```text
python benchmarks/hardware/hw_preflight.py            # stage read-only, times 2^18-point pulls
python benchmarks/hardware/hw_run.py                  # about 65 min with the defaults
python benchmarks/hardware/hw_analyze.py OUTPUT_DIR   # the folder hw_run.py printed
python benchmarks/hardware/build_report.py OUTPUT_DIR --pdf benchmarks/hardware/reports/HDF5_Hardware_Benchmark_YYYY-MM-DD.pdf
```

| File | Purpose |
|---|---|
| `hw_common.py` | Headless stand-in for the Input Parameters tab: fills the same `dltsConfig` state with the GUI defaults, redirects `log_to_textbox()` to a log file, and connects the instruments (`setup_gui_state()`, `connect_impedance()`, `connect_temperature()`). `DEFAULT_OUTPUT` is `benchmarks/hardware/output`. |
| `hw_preflight.py` | Reads the stage temperature once (no ramp; the controller is left as it was), connects the MFIA and times `pull_data(trigger=True)` at the requested size to check it finishes well inside its 60 s completion timeout. Options: `--points` (log2 of points, default 18), `--reps` (list, default `1 2 10`), `--out`. The stage is only read, but the MFIA is connected, gets its parameters pushed (`reload_params()`) and runs real acquisitions. |
| `hw_run.py` | The run, in the GUI's sequence: connect and push parameters, `init_experiment`, `run_experiment`, `finish_experiment`, return to room temperature, Redo one step, return, Remove & Retake another step, return, disconnect. Logs the stage temperature every 10 s, per-step timings, and repeats the live-ingest work on each file. A watchdog aborts and parks the stage at room temperature if a step does not stabilize within `--step-limit` minutes. Options: `--start 25`, `--stop 50`, `--step 5`, `--room 30`, `--points 18`, `--reps 100`, `--root C:\Users\spencer\Desktop\DATA\DLTS`, `--redo 45`, `--retake 40`, `--no-redo`, `--no-retake`, `--step-limit 40`, `--out`. |
| `hw_analyze.py` | Checks the run folder (one `.h5` per temperature plus `runParams.txt`, no leftover `.tmp` files, and more), writes a JSON copy of the run to `OUTPUT_DIR\json_copy\` and compares both formats through the analysis code. Writes `analysis.json`. Without an argument it uses the newest `output\run_*` folder. Nothing is written to the data folder. |
| `build_report.py` | Builds `report.html` from `analysis.json` and `report_template.html`. `--notes FILE.html` adds a "Found during the run" section; `--pdf OUT.pdf` prints it with headless Microsoft Edge (looked up under `C:\Program Files (x86)\Microsoft\Edge\...` and `C:\Program Files\Microsoft\Edge\...`). |
| `report_template.html` | The report page (interactive charts, print styles for the PDF). |
| `notes/2026-09-28.html` | Findings for the 28 Sep 2026 run's report. |
| `reports/HDF5_Hardware_Benchmark_2026-09-28.pdf` | The stored report of that run. |

Everything the scripts write goes to `benchmarks/hardware/output/run_<timestamp>/` (git-ignored): the run log, stage-temperature log, timings, `analysis.json`, `report.html` and the JSON copy of the run (about 60 MB per 2^18-point step). The run's data files stay in the Data Root Folder. See also `benchmarks/hardware/README.md`.

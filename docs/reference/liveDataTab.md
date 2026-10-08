# liveDataTab

## What it's for

`liveDataTab.py` builds the **Live Tools** tab. From this tab you start a DLTS temperature scan and control it: pause, resume, redo steps, or remove and retake them. The tab shows each temperature's emission transients as the files arrive or from a finished run. Its **Qualitative Analysis** section extracts and averages capacitance transients from a data folder in any of the three supported formats. The pure extraction functions (`_compute_*`) are also used by the Detailed Analysis tab and by the tests and benchmarks.

## What the user sees

The tab has three stacked areas:

1. The **Run DLTS** button across the top, in a frame 52 px high.
2. A vertical `tk.PanedWindow` with a draggable sash. The top pane is **Automated / Live Data** and the bottom pane is **Qualitative Analysis**. Both start 460 px high and both stretch.
3. No log. Every message goes to the log box on the **Input Parameters** tab.

### Run DLTS

**Run DLTS** (Segoe UI 14 bold, `dltsc.run_button`) calls `start_thread()`. It does nothing if `dltsc.run_busy` is already set. Otherwise, on the Tk thread, it:

- sets `run_busy = True`, `run_pauseRequested = False`, and `run_paused = False`;
- sets the buttons to the `running` state (only **Pause** enabled);
- clears the Live view state (`_reset_live_plot_state('live')`), which bumps `dltsc.livePlot_liveRunToken` and switches the view to **Live**;
- starts the output-file watcher (`_schedule_live_poll`);
- starts a daemon thread running `start_dlts()`;
- starts the step-list refresh loop (`_poll_step_listbox_while_busy`, every 500 ms while `run_busy`).

`start_dlts()` creates `runDlts_Tools.dltsRun()` and stores it in `dltsc.run_dltsInstance`. It calls `init_experiment()`, which checks the devices and parameters, builds the temperature grid, creates the output folder, and publishes `dltsc.run_dataFileNames`. It marks every grid step `pending` and then calls `run_experiment()`. When the run returns, `_handle_run_status(status, isMainSequence=True)` runs on the Tk thread.

The **Input Parameters** tab must be set up first. Both devices must have been created with **Connect + Get Params**, or `init_experiment()` fails with `Error: Failed to initialize the experiment.`

### Automated / Live Data (top pane)

Header row, left to right:

| Widget | What it does |
|---|---|
| **Automated / Live Data** (bold label) | Heading. |
| **View:** radio buttons **Live** / **Offline** | `_on_mode_toggle()`. Switches which dataset is drawn. Live and Offline each keep their own data (`dltsc.livePlot_live*` and `dltsc.livePlot_offline*`) and their own last-selected temperature, so switching never discards anything. |
| **Load Existing Run (Offline)** | `_load_offline_run()`. File picker **Select DLTS Data Files (Offline Run)** with filters `*.txt *.json *.h5`, `*.h5`, `*.csv`, and all files. Select all step files of a run. Loading runs on a background thread and replaces the previous Offline data. |
| **Dataset:** dropdown | Read-only. One entry per temperature, labeled `K (°C)`, for example `298.15 (25)`. The Kelvin value is `impdData.dataTemps` (exact K, a float); the Celsius value is `round(K - 273.15)`. Choosing one redraws from cached results (`_on_dataset_selected`). |
| **Denoise Method:** dropdown | Read-only. `pca` (default), `wavelet`, `sgolay`, `lowess`. Changing it recomputes `impdData.filter_emissions()` for the displayed mode on a background thread (`_recompute_denoise_and_redraw`). |
| Status label | For example `Waiting for data...`, `Processing N new file(s)...`, `Live: N temperature(s) loaded.`, `Run complete: N temperature(s) loaded.`, `Loading N offline file(s) — this can take a while for many temperatures...`, `Offline: N temperature(s) loaded.` |

**Run Control** column (left, 250 px wide, `tk.LabelFrame`):

| Button | Enabled when | What it does |
|---|---|---|
| **Pause** | running | `_pause_run()`: sets `dltsc.run_pauseRequested = True`, disables itself, and logs `Pause requested; the run will stop after the current temperature step completes.` `run_experiment()` checks the flag before each step. The stage stays at its current temperature. |
| **Resume** | paused; or idle after a run, if `currentStepIndex < len(tempGrid)` | `_resume_run()`: logs `Resuming run...` and runs the main sequence from `dltsRun.currentStepIndex` on a new thread, reusing the same instance and connected devices. |
| **Redo Selected** | paused, or idle after a run | `_redo_selected_steps()`: runs only the selected steps in ascending order and overwrites their files. It does not move the resume point. With nothing selected it logs `Redo: select at least one step from the list first.` |
| **Remove & Retake Selected** | paused, or idle after a run | `_retake_selected_steps()`: like Redo, but deletes each step's existing file first (`deleteFirst=True`). |

Below the buttons, a multi-select listbox (`dltsc.run_stepListbox`) shows each grid step as `N. T.TT °C — status`. The status is `pending`, `running`, `done`, `failed`, `paused`, or `aborted`, taken from `dltsRun.stepStatus`. The selection survives refreshes.

Button states (`_set_run_control_buttons`):

| Mode | Run DLTS | Pause | Resume | Redo / Retake |
|---|---|---|---|---|
| `idle` (startup) | on | off | off | off |
| `running` | off | on | off | off |
| `paused` | off | off | on | on |
| `returning` (stage ramping to room temperature, or GUI closing) | off | off | off | off |
| `idle_with_instance` (finished or failed, devices still connected) | on | off | on if steps remain | on |

End of a run (`_handle_run_status`):

- `completed`, main sequence: calls `finish_experiment()`, which writes `runParams.txt` into the run folder on the Tk thread. Logs `DLTS run completed!`, then returns the stage to room temperature.
- `completed`, Redo/Retake: logs `Redo/Retake completed.` and returns the stage to room temperature. `runParams.txt` is not rewritten.
- `paused`: logs `Run paused. Click Resume to continue, or Redo/Remove & Retake specific steps below.` The stage stays where it is.
- `error`: logs `Run stopped due to an error. Devices remain connected; Resume/Redo/Retake are available.` and returns the stage to room temperature.
- `aborted`, or the GUI is closing: logs `Run stopped: GUI is closing.` and does nothing else. The close handler in `DLTSGUI_MainWindow` has already commanded the ramp.

The return to room temperature (`_return_to_room_temp_async`) runs `dltsRun.return_to_room_temp()` on a daemon thread. That call ramps to **Room Temperature (C)** at **Room Ramp (C/min)** and waits until the stage is within 0.5 °C, up to the expected ramp time plus 900 s. Meanwhile `run_busy` stays `True` and all buttons are off (`returning`).

Plot area (right): one matplotlib figure (10 × 4 in, 100 dpi) with a navigation toolbar and two side-by-side axes:

- **Emission 0 (T = *K* K)**: the raw mean of the first emission cluster (`ymean`, grey) and, if present, the denoised curve (`yFiltered`, orange, legend `Denoised (<method>)`). X axis **Time (s)**, y axis **Impedance Im (F)**.
- **All Emissions Aligned (T = *K* K)**: every emission block for that temperature, colored with the viridis colormap. A legend (`#1`, `#2`, ...) appears when there are 12 blocks or fewer.

With no data, both axes show `Waiting for data...`.

Live watcher: `_schedule_live_poll` checks `dltsc.run_dataFileNames` once a second. It picks up files that exist and have not been ingested yet, and hands them to `_ingest_files_async`. That function reads the first file with `impdData.read_data()` and each later file with `append_data()`. It then runs `cleanup_data()`, a forced re-clustering (`selected_emissions(0)`), `filter_emissions(method)`, and `selected_emissions(-1)` on a background thread. Polling stops once every listed file has been ingested.

### Qualitative Analysis (bottom pane)

A left column (230 px, scrollable with the mouse wheel while the pointer is over it) and a plot on the right.

**Directory Loader Config**

- **Select Source Folder** (`_browse_manual_folder`): folder picker **Select DLTS Source Folder**, starting in the last folder or the working directory. It first logs a one-line preview: `Manual analysis: selected <path> -- N item(s): ... — <format guess>`. Then it scans the folder on a background thread and **replaces** the current dataset.
- **Append Source Folder** (`_append_manual_folder`): folder picker **Select DLTS Source Folder to Append**. It **adds** that folder's temperatures to the current dataset. A temperature that is already loaded keeps its first-loaded copy, and the log lists the skipped ones. With nothing loaded yet, it behaves like **Select Source Folder**.
- Label: `Source: (none selected)`, then `Source: <folder>` or `Source: N folder(s) combined (latest: <folder>)`.

Both buttons, and **Extract & Average Transients**, are disabled while a scan or an extraction is running.

Three folder formats are detected, in this order:

| Format | Registry tag | How it is recognized | Temperatures from |
|---|---|---|---|
| ZI single CSV | `'zi'` | A file matching `*imps_0_sample_param1_avg_header*.csv` directly in the folder | `history_name` in the header CSV, pattern `^(\d+)C_` (non-negative whole °C only); one chunk per temperature in one data CSV |
| ZI subfolder per temperature | `'zi_subfolder'` | Subfolders named like `0C`, `100C`, `n10C`, `120C_000` (`_ZI_SUBFOLDER_PATTERN`), each with its own `*imps_0_sample_param1_avg_<n>.csv` | Subfolder name; `n` means negative |
| Legacy per-temperature files | plain path or `'legacy_chunk'` | File names matching `_LEGACY_FILENAME_PATTERN`, for example `p25p0.txt`, `n10p5.h5`, `P120C_001.csv`; plus semicolon CSVs with `chunk`, `smoothed_value`, or `timestamp` in their header | File name, or a fixed chunk-to-temperature map for multi-chunk CSVs |

The output of **Run DLTS** (`p25p0.txt` or `.h5` files) is the legacy per-temperature format.

**Available Temperatures Filter**

- A multi-select listbox (3 rows high, scrolls) showing each temperature as `T °C`, sorted. After each scan all entries are selected.
- **Select All** and **Clear All**.

**Timing Boundaries** (`dltsc.manual_paramVars`)

| Label | Key | Default | Used for |
|---|---|---|---|
| Filling Duration (ms): | `fp_ms` | `1.0` | Display only |
| Reverse Bias (ms): | `rb_ms` | `500.0` | Extraction: legacy window length, and `C_infinity` at 90 % of it |
| Analysis Slice Start (ms): | `slice_start` | `2.0` | Plot only: the Qualitative plot starts here (`_plot_slice_ms`) |
| Analysis Slice End (ms): | `slice_end` | `490.0` | Plot only: the Qualitative plot ends here |

These fields are filled automatically on a **Select Source Folder** scan, but not on an append:

- Legacy folder: from `runParams.txt` in that folder (`_legacy_run_timing`). Fill = **State Disable Time** × 1000, reverse bias = **State Enable Time** × 1000, slice end = 0.98 × reverse bias. The log shows `Manual analysis: Timing Boundaries set from runParams.txt (fill F ms, reverse bias R ms).` `runParams.txt` exists only after a main sequence completed.
- ZI formats: from the folder name, regexes `FP\w+?(\d+(?:\.\d+)?)ms` and `RB[\w\+\-]+?(\d+(?:\.\d+)?)ms`, for example `..._FP_1ms_RB-5V_500ms`. Slice end = 0.98 × RB.

**Execution Action**

- **Extract & Average Transients** (`_process_raw_transients`, bold, light green): reads **Reverse Bias (ms)**. A non-numeric value logs `Manual analysis: Reverse Bias (ms) must be numeric.` It splits the selected temperatures by format tag and submits `_compute_mixed_transients` to a single-worker `ProcessPoolExecutor` (`dltsc.manual_transientExecutor`, created on first use and reused). A background thread waits for the result, and the plot is drawn on the Tk thread. The results are stored in `dltsc.manual_processedTransients`. The Quick Analysis tab (`dataAnalysisTab`) reads them from there.
- Status label: `Status: Idle`, `Processing N temperature(s)...`, `Transients ensembled completely — N traces.`, or `N of M traces; see log for the rest.` Every skipped temperature is logged with its reason, for example `Manual analysis: 25.0°C: no fill pulses found: ...`.

Plot: **Averaged Capacitance Transients Profile**, x axis **Time from Reverse Bias Start (ms)**, one line per temperature. Only the Analysis Slice (Start to End) is drawn, so the fill-pulse edge at t = 0 does not set the y scale; the extracted data passed to other tabs is not cut. Up to `_MAX_LEGEND_TRACES` (10) traces get a legend (`T°C`, upper right); more traces are colored by temperature (plasma colormap) with a **Temperature (°C)** color bar instead. The y axis is **Capacitance (pF)**, or nF, µF, or mF chosen from the largest value (`_capacitance_axis_units`). Offset notation is off. Each curve is thinned to at most 3000 points for drawing (`_downsample_for_plot`). With no results, the plot shows `No transients extracted. See the log for the reason per temperature.`

## Import

```python
import liveDataTab as ldT
```

Importing the module creates no widgets. It imports `numpy`, `pandas`, `matplotlib` (including `FigureCanvasTkAgg`), `dltsConfig`, `impedanceAnalysis_Tools`, and `runDlts_Tools`. The `_compute_*` functions and `_find_reverse_bias_starts`, `_legacy_run_timing`, `_capacitance_axis_units`, and `_downsample_for_plot` need no Tk and no hardware.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `DENOISE_METHODS` | `['pca', 'wavelet', 'sgolay', 'lowess']` | Options of the **Denoise Method:** dropdown, passed to `impdData.filter_emissions(method=...)`. The first entry is the default. |
| `_LEGACY_FILENAME_PATTERN` | `re.compile(r'^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt\|csv\|h5)$')` (backslashes before the pipes are table escaping only) | Legacy step file name: sign (`p`/`n`), whole degrees, optional `p` + decimals, optional `C`, optional `_NNN`, extension `.txt`, `.csv`, or `.h5` (lower case only). Groups: sign, integer part, decimal part, extension. |
| `_ZI_REGISTRY_TAGS` | `('zi', 'zi_subfolder')` | Registry tags that count as ZI in `_registry_format_label`. |
| `_ZI_SUBFOLDER_PATTERN` | `re.compile(r'^(n?)(\d+)C(?:_\d+)?$', re.IGNORECASE)` | ZI per-temperature subfolder name. Group 1 is `n` for negative, group 2 is whole degrees. |
| `_MAX_PLOT_POINTS` | `3000` | Default point limit of `_downsample_for_plot`. |
| `_MAX_LEGEND_TRACES` | `10` | Above this many traces the Qualitative plot uses a temperature color bar instead of a legend. |
| `_manualColorbar` | `None` or matplotlib `Colorbar` | The Qualitative plot's current color bar; removed before each redraw. |
| `_MIN_PULSE_HEIGHT_V` | `0.05` (V) | Smallest excitation swing that `_find_reverse_bias_starts` treats as real pulsing. |

Fixed values inside functions:

| Where | Value | Meaning |
|---|---|---|
| `_process_raw_transients` | `samplingRateS = dltsc.manual_samplingRate or 1.8666666666666665e-05` | Fallback sample period (s) for legacy files, about 53.57 kSa/s. `.txt`/`.h5` step files use their own `timeStampImps` spacing instead; `dltsc.manual_samplingRate` is never set anywhere. |
| `_process_raw_transients` | `cInfTargetMs = 0.90 * rb_ms` | Time at which `C_infinity` is read. |
| ZI defaults | `gridColOffset = -0.001` s, `gridColDelta = 1.86667e-05` s, `chunkSize = 32768` | Used when a ZI header CSV is missing or unreadable. |
| `_compute_legacy_dataset` | chunk map `{0: 120.0, 1: 125.0, ..., 8: 160.0}` | Temperatures assigned to chunks of a multi-chunk legacy CSV. |

`dltsConfig` globals owned by this tab:

| Group | Names |
|---|---|
| Run control | `run_button`, `run_pauseButton`, `run_resumeButton`, `run_redoButton`, `run_retakeButton`, `run_stepListbox`, `run_dltsInstance`, `run_busy`, `run_pauseRequested`, `run_paused` |
| Read from other modules | `run_dataFileNames` (written by `runDlts_Tools.init_experiment`), `app_closing` (written by `DLTSGUI_MainWindow`) |
| Automated plot | `livePlot_activeMode`, `livePlot_modeVar`, `livePlot_denoiseMethodVar`, `livePlot_datasetVar`, `livePlot_datasetCombo`, `livePlot_figure`, `livePlot_axEmission0`, `livePlot_axAllEmissions`, `livePlot_canvas`, `livePlot_statusLabel` |
| Live state | `livePlot_liveImpdData`, `livePlot_liveEmission0Data`, `livePlot_liveAllEmissionsData`, `livePlot_liveDatasetSel`, `livePlot_liveRunToken`, `livePlot_pollAfterId`, `livePlot_processedFiles`, `livePlot_liveIngestBusy` |
| Offline state | `livePlot_offlineImpdData`, `livePlot_offlineEmission0Data`, `livePlot_offlineAllEmissionsData`, `livePlot_offlineDatasetSel`, `livePlot_offlineRunToken`, `livePlot_offlineIngestBusy` |
| Qualitative Analysis | `manual_dataDirectory`, `manual_datasetRegistry`, `manual_ziMode`, `manual_ziParamsByFile`, `manual_ziDataFile`, `manual_ziGridColOffset`, `manual_ziGridColDelta`, `manual_ziChunkSize`, `manual_sourceFolders`, `manual_samplingRate` (read only), `manual_processedTransients`, `manual_paramVars`, `manual_tempListbox`, `manual_folderLabel`, `manual_selectFolderButton`, `manual_appendFolderButton`, `manual_extractButton`, `manual_processingBusy`, `manual_loadingBusy`, `manual_transientExecutor`, `manual_figure`, `manual_ax`, `manual_canvas`, `manual_statusLabel` |

The snapshot dicts (`livePlot_*Emission0Data`, `livePlot_*AllEmissionsData`) map the Kelvin temperature to a copy of that temperature's `impdData.dataEmissions` record. The redraw reads the keys `xTimeStampImps` (or `x`), `ymean` (or `y`), and `yFiltered` for emission 0, and `xTimeStampImps` (or `x`) and `y` (1-D or 2-D, one column per block) for all emissions.

## Functions

### start_thread()

The **Run DLTS** handler. See "Run DLTS" above for the full sequence.

**Returns** `None`.

**Side effects** Sets `run_busy`, `run_pauseRequested`, and `run_paused`. Resets the Live state and bumps `livePlot_liveRunToken`. Schedules `root.after` callbacks for the file watcher and the step list. Starts a daemon thread running `start_dlts`.

**Called by** the **Run DLTS** button.

### start_dlts()

The body of the run thread. It creates `rdT.dltsRun()` and stores it in `dltsc.run_dltsInstance`. It calls `init_experiment()`; on failure (`< 0`) it logs the error and uses `root.after` to clear `run_busy` and return the buttons to `idle`. On success it marks every step `pending`, schedules a step-list refresh, calls `run_experiment()` (blocking: this is the whole scan), and schedules `_handle_run_status(status, isMainSequence=True)`.

**Returns** `None`.

**Side effects** Drives the hardware through `runDlts_Tools` (stage moves, MFIA acquisition), writes the step data files, and writes to the log from the background thread.

**Called by** the thread started in `start_thread()`.

### construct_livePlotTab()

Adds `dltsc.livePlotTab` to the notebook as **Live Tools** and builds the **Run DLTS** button, the paned window, `_build_autoPlotFrame`, and `_build_manualPlotFrame`.

**Returns** `None`.

**Side effects** Creates every widget on this tab and writes the widget globals listed above.

**Called by** `DLTSGUI_MainWindow` at startup.

## Internal helpers

### Run control

#### _pause_run()

When `run_busy`, sets `dltsc.run_pauseRequested = True`, disables **Pause**, and logs the pause request. The run stops before the next step, not during the current one.

#### _run_control_thread(indices=None, deleteFirst=False, isMainSequence=False)

The shared launcher for Resume, Redo, and Retake. It does nothing if there is no `run_dltsInstance` or if `run_busy` is set. Otherwise it sets `run_busy`, clears `run_pauseRequested`, sets the buttons to `running`, and starts a daemon thread calling `run_dltsInstance.run_experiment(indices=indices, deleteFirst=deleteFirst)`. The result goes to `_handle_run_status` through `root.after`. It also starts the step-list refresh loop. It does not restart the Live file watcher.

#### _resume_run()

Logs `Resuming run...` and calls `_run_control_thread(indices=None, isMainSequence=True)`.

#### _get_selected_step_indices()

Returns `list(run_stepListbox.curselection())`, or `[]` if the listbox does not exist.

#### _redo_selected_steps()

For the selected steps, logs `Redoing N step(s)...` and calls `_run_control_thread(indices, deleteFirst=False)`.

#### _retake_selected_steps()

For the selected steps, logs `Removing and retaking N step(s)...` and calls `_run_control_thread(indices, deleteFirst=True)`.

#### _set_run_control_buttons(mode)

Enables or disables the five run buttons according to the table in "What the user sees". `mode` is one of `'idle'`, `'running'`, `'paused'`, `'returning'`, `'idle_with_instance'`; any other value acts as `'idle'`. `DLTSGUI_MainWindow.on_closing` calls it with `'returning'`.

#### _handle_run_status(status, isMainSequence)

Runs on the Tk thread when a run thread ends. It clears `run_busy`, refreshes the step list, and then acts on `status` (`'completed'`, `'paused'`, `'error'`, `'aborted'`) as described in "End of a run".

#### _return_to_room_temp_async()

Sets `run_busy = True` and the buttons to `returning`. It starts a daemon thread calling `run_dltsInstance.return_to_room_temp()`. When that returns, it clears `run_busy` and, unless the GUI is closing, sets `idle_with_instance`.

#### _refresh_step_listbox()

Rebuilds the step list from `run_dltsInstance.tempDevice.tempGrid` and `run_dltsInstance.stepStatus`, keeping the current selection.

#### _poll_step_listbox_while_busy()

Calls `_refresh_step_listbox()` and reschedules itself every 500 ms while `run_busy` is true.

### Automated / Live Data

#### _active_impd()

Returns `livePlot_offlineImpdData` in Offline mode, otherwise `livePlot_liveImpdData`.

#### _active_emission0Data()

Returns the emission-0 snapshot dict of the active mode, or `{}`.

#### _active_allEmissionsData()

Returns the all-emissions snapshot dict of the active mode, or `{}`.

#### _mode_label(mode)

Returns `'Live'` for `'live'`, otherwise `'Offline'`.

#### _reset_auto_plot_placeholder()

Clears both axes, draws `Waiting for data...` with the titles **Emission 0** and **All Emissions Aligned**, and empties the **Dataset:** dropdown.

#### _reset_live_plot_state(mode)

Clears one mode's state and then calls `_set_livePlot_mode(mode)`. For `'live'` it bumps `livePlot_liveRunToken`, clears the Live impdData, snapshots, selection, and `livePlot_processedFiles`, clears `livePlot_liveIngestBusy`, and cancels any pending poll. For `'offline'` it bumps `livePlot_offlineRunToken` and clears the Offline state. The other mode is left untouched.

#### _set_livePlot_mode(newMode)

Remembers the old mode's dropdown selection, sets `livePlot_activeMode` and the radio button, and then either fills the dropdown and redraws (if the new mode has data) or shows the placeholder. It also updates the status label.

#### _on_mode_toggle()

Radio-button callback. Calls `_set_livePlot_mode(livePlot_modeVar.get())`.

#### _format_dataset_label(t)

Returns `f"{t} ({round(t - 273.15)})"`, for example `298.15 (25)` or `262.65 (-10)`. A non-numeric `t` is returned as `str(t)`.

#### _get_selected_dataset_temp()

Parses the Kelvin part of the dropdown text back to `int`, or to `float` if that fails. Returns `None` if the text is empty or unparsable.

#### _update_dataset_dropdown(temps, preferred=None)

Sets the dropdown values from `temps`. It selects `preferred` if that label is present, otherwise the last entry.

#### _on_dataset_selected(*_args)

`<<ComboboxSelected>>` handler. Calls `_redraw_auto_plots()`.

#### _schedule_live_poll(token)

The Live file watcher, run on the Tk thread once a second through `root.after(1000, ...)`. It stops if `token` no longer equals `livePlot_liveRunToken`. When no ingest is busy, it passes the files that exist and are not yet in `livePlot_processedFiles` to `_ingest_files_async`. It stops, and sets the status `Run complete: N temperature(s) loaded.` in Live mode, once every name in `run_dataFileNames` has been processed. Each step file is checked with `os.path.exists`, so a `*.h5.tmp` file that is still being written is not picked up.

#### _ingest_files_async(paths, token)

Sets `livePlot_liveIngestBusy` and starts a daemon thread. The thread loads `paths` into the Live `impdData`: `read_data()` for the first file, `append_data()` afterwards. It then runs `cleanup_data()`, sets `dataEmissionClusterParams = None` to force re-clustering, and calls `selected_emissions(emissionIndex=0)`, `filter_emissions(method, emissionIndex=0, recalculate=True, interactivePlot=False)`, and `selected_emissions(emissionIndex=-1)`, taking a snapshot after each. `apply()` runs on the Tk thread. It clears the busy flag, drops the result if the token is stale, logs any errors as `Live plot: ...`, stores the impdData, the processed paths, and the snapshots, and redraws if Live is shown. A file that fails to load is not marked processed, so the next tick tries it again.

#### _recompute_denoise_and_redraw(*_args)

`trace_add('write')` callback of the denoise variable. It does nothing if the active mode has no data or is busy. Otherwise it runs `selected_emissions(0)` and `filter_emissions(method, ...)` on a background thread, replaces the active mode's emission-0 snapshot if the token still matches, and redraws if that mode is still shown. The all-emissions snapshot is not recomputed, because it is raw data.

#### _redraw_auto_plots(*_args)

Draws both axes from the active mode's snapshots for the selected temperature, as described under "Plot area". If the selection has no emission-0 snapshot, it switches to the highest temperature that has one and updates the dropdown. With no data it shows the placeholder. It only reads cached results, so it is cheap enough for the Tk thread.

#### _load_offline_run()

**Load Existing Run (Offline)** handler. After the file dialog it resets the Offline state (switching the view to Offline), sets `livePlot_offlineIngestBusy`, and starts a daemon thread running the pipeline below. `apply()` stores the result if the offline token still matches, and fills the dropdown and redraws if Offline is shown. The busy flag is cleared through `root.after` in a `finally` block. Errors are logged as `Live plot: failed to load the selected offline files.` or `Live plot: error processing offline data: ...`.

The underlying `impedanceAnalysis_Tools` pipeline can be run without the GUI. This is the same sequence the tests use (`tests/test_hdf5_analysis.py::run_offline_pipeline`):

```python
import glob
import impedanceAnalysis_Tools as iaT

files = sorted(glob.glob(r'D:\data\092826\141503\p*.txt'))   # or *.h5; both may be mixed
impd = iaT.impdData(fName=files)
assert impd.read_data() == 0            # 0 on success
impd.cleanup_data()
impd.selected_emissions(emissionIndex=0)
impd.filter_emissions(method='pca', emissionIndex=0, recalculate=True, interactivePlot=False)
emission0 = {T: dict(rec) for T, rec in impd.dataEmissions.items()}     # keys: K (float)
impd.selected_emissions(emissionIndex=-1)
allEmissions = {T: dict(rec) for T, rec in impd.dataEmissions.items()}
print(impd.dataTemps)                   # e.g. [263.15, 298.15, 323.65] for -10, 25, 50.5 °C
```

#### _build_autoPlotFrame(parent)

Seeds the Live and Offline globals that `dltsConfig.init()` would normally set (mode `'live'`, tokens `0`, empty sets and dicts, busy flags `False`). It then builds the header row, calls `_build_runControlPanel`, and creates the two-axes figure, canvas, and toolbar.

#### _build_runControlPanel(parent)

Builds the **Run Control** frame: **Pause**, **Resume**, **Redo Selected**, and **Remove & Retake Selected** (all disabled at start), and the step listbox with its scrollbar.

### Qualitative Analysis: GUI and scanning

#### _set_manual_buttons_state(state)

Sets `state` (`'normal'` or `'disabled'`) on **Select Source Folder**, **Append Source Folder**, and **Extract & Average Transients**.

#### _describe_folder_contents(dir_path, max_entries=12)

Returns a one-line preview string: `"N item(s): a, b, ... (M more)  —  <guess>"`. The guess is `looks like ZI single-file format ...`, `looks like ZI subfolder-per-temperature format`, `looks like legacy per-temperature files`, or `format not recognized from filenames ...`. It returns `folder is empty` or `cannot list folder: <error>` when appropriate. It only lists the folder and reads no files. The Detailed Analysis tab also uses it.

#### _browse_manual_folder()

**Select Source Folder** handler: dialog, log preview, then `_scan_manual_directory_async(dir_path, isAppend=False)`. It does nothing while a scan or an extraction is busy.

#### _append_manual_folder()

**Append Source Folder** handler. It falls back to `_browse_manual_folder()` when the registry is empty; otherwise it runs a dialog, logs the preview, and calls `_scan_manual_directory_async(dir_path, isAppend=True)`.

#### _registry_format_label(registry)

Returns `'ZI'`, `'Legacy'`, or `'Mixed'` according to the tags present in the registry. This is the value stored in `dltsc.manual_ziMode` and shown in the status as `[ZI]`, `[Legacy]`, or `[Mixed]`.

#### _scan_manual_directory_async(dir_path, isAppend)

Sets `manual_loadingBusy`, disables the buttons, and starts a daemon thread. The thread detects the format (ZI single CSV, then ZI subfolders, then legacy with `_legacy_run_timing`) and builds the registry. `apply()` on the Tk thread:

- replaces or merges `manual_datasetRegistry` and `manual_sourceFolders`;
- stores the ZI grid parameters in `manual_ziParamsByFile` and the `manual_zi*` globals;
- fills the Timing Boundaries (not on append);
- refills and selects all entries in the temperature listbox;
- logs errors and sets the status `[<format>] N temperature step(s) from S source(s).`

A replacing scan also clears `manual_ziParamsByFile` and sets `manual_dataDirectory`.

#### _select_all_manual_temps()

Selects every entry in the temperature listbox.

#### _clear_manual_temps()

Clears the temperature listbox selection.

### Qualitative Analysis: dataset builders (pure computation)

All three return a **registry**, a dict mapping a temperature in °C (`float`) to its data source:

| Registry value | Produced by | Meaning |
|---|---|---|
| `('zi', dataFile, chunkId)` | `_compute_zi_dataset` | One chunk of a combined ZI CSV. |
| `('zi_subfolder', dataFile, None)` | `_compute_zi_subfolder_dataset` | This temperature's own ZI CSV. |
| `('legacy_chunk', filePath, chunkId or None)` | `_compute_legacy_dataset` | A semicolon CSV, optionally filtered by its first column. |
| `filePath` (str) | `_compute_legacy_dataset` | A `.txt` (JSON), `.h5`, or plain two-column `.csv` step file. |

`errorMsgs` is a list that each builder appends human-readable problems to. The builders never raise for a bad individual file.

#### _compute_zi_dataset(dir_path, header_filename, errorMsgs)

Reads `header_filename` (semicolon CSV with the columns `chunk_number`, `history_name`, `grid_col_offset`, `grid_col_delta`, `chunk_size`) and finds the first data CSV matching `imps_0_sample_param1_avg_<digits>.csv`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `dir_path` | str | none | Folder that holds the ZI export. |
| `header_filename` | str | none | Name of the header CSV inside `dir_path`. |
| `errorMsgs` | list | none | Receives error strings. |

**Returns** `(registry, ziInfo)`. `ziInfo` is `{'dataFile', 'gridColOffset', 'gridColDelta', 'chunkSize', 'fpMs', 'rbMs', 'sliceEnd'}`. The grid values come from the first header row, with the ZI defaults as fallback. `fpMs`, `rbMs`, and `sliceEnd` are strings parsed from the folder name, or `None`. On a read failure it returns `(registry, None)`. Temperatures come only from `history_name` values that start with `<digits>C_`.

**Side effects** Reads files only.

**Called by** `_scan_manual_directory_async` and `detailedAnalysisTab`.

#### _compute_zi_subfolder_dataset(dir_path, errorMsgs)

Scans the subfolders of `dir_path` that match `_ZI_SUBFOLDER_PATTERN`. For each, it takes the first `imps_0_sample_param1_avg_<n>.csv` and reads `grid_col_offset`, `grid_col_delta`, and `chunk_size` from that subfolder's header CSV, with defaults if the header is missing or unreadable.

**Returns** `(registry, ziParamsByFile)`, where `ziParamsByFile[dataFile] = {'gridColOffset', 'gridColDelta', 'chunkSize'}`.

**Called by** `_scan_manual_directory_async` and `detailedAnalysisTab`.

**Example**

```python
import liveDataTab as ldT
errors = []
registry, params = ldT._compute_zi_subfolder_dataset(r'D:\zi_export', errors)
# registry -> {-10.0: ('zi_subfolder', r'D:\zi_export\n10C\dev..._avg_00000.csv', None),
#              25.0:  ('zi_subfolder', r'D:\zi_export\25C_000\dev..._avg_00000.csv', None)}
# params   -> {r'D:\zi_export\n10C\dev..._avg_00000.csv': {'gridColOffset': -0.001,
#              'gridColDelta': 1e-05, 'chunkSize': 1000}, ...}
```

#### _compute_legacy_dataset(dir_path, errorMsgs)

Lists the files in `dir_path`, without recursing:

- A `.csv` whose first line contains `;`:
  - if the line also contains `chunk`: it reads the first column. With more than one distinct chunk, or with `p120C-p160C` in the file name, it maps chunks 0 to 8 to 120, 125, ..., 160 °C as `('legacy_chunk', path, chunk)`. Other chunk numbers are dropped. With a single chunk, the temperature comes from the file name.
  - else if it contains `smoothed_value` or `timestamp`: the temperature comes from the file name, as `('legacy_chunk', path, None)`.
- Any other file whose name matches `_LEGACY_FILENAME_PATTERN` is registered as a plain path. The temperature is sign × (integer + `0.<decimals>`).

**Returns** `registry` (dict).

**Called by** `_scan_manual_directory_async`, `detailedAnalysisTab`, the tests, and the benchmarks.

**Example** (see the full pipeline example under `_compute_legacy_transients`)

```python
errors = []
registry = ldT._compute_legacy_dataset(r'D:\data\092826\141503', errors)
# {-10.0: 'D:\\...\\n10p0.txt', 25.0: 'D:\\...\\p25p0.txt', 50.5: 'D:\\...\\p50p5.txt'}
```

#### _legacy_run_timing(dir_path)

Reads `runParams.txt` (JSON) in `dir_path`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `dir_path` | str | none | Run folder. |

**Returns** `(fpMs, rbMs)` as floats, with `fpMs = State Disable Time × 1000` and `rbMs = State Enable Time × 1000`. It returns `None` if the file or either key is missing or unreadable, or if either value is not positive.

**Side effects** None.

**Called by** `_scan_manual_directory_async`, and the benchmarks in `benchmarks/hardware/hw_analyze.py`.

**Example**

```python
ldT._legacy_run_timing(r'D:\data\092826\141503')   # runParams.txt with 0.006 / 0.003
# -> (3.0, 6.0)
```

### Qualitative Analysis: extraction (pure computation)

All extractors return `(processedTransients, executionErrors)`:

```python
processedTransients = {
    25.0: {                        # temperature in °C (the registry key)
        'time_ms':    ndarray,     # time axis, ms from reverse-bias start
        'avg_cap_pf': ndarray,     # averaged capacitance, pF
        'C_infinity': float,       # avg_cap_pf at the sample nearest cInfTargetMs
    },
    ...
}
executionErrors = ['30.0°C: no fill pulses found: ...', ...]   # one string per skipped temperature
```

They take only plain Python and numpy data, so they can run in a child process. This shape is what `dltsc.manual_processedTransients` holds, and what `dataAnalysisTab` and `detailedAnalysisTab` consume.

#### _compute_zi_transients(selectedTemps, cInfTargetMs, datasetRegistry, ziParamsByFile)

For the `'zi'` entries: it groups temperatures by data file and reads each file once (`pd.read_csv(sep=';')`). For each temperature it takes the `value` column where `chunk == chunkId`, truncated to `chunkSize`. The time axis is `(gridColOffset + arange(n) * gridColDelta) * 1000` ms, so it starts at the offset (−1 ms by default), before the trigger. Values below 1e-3 in magnitude are taken as farads and multiplied by 1e12.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `selectedTemps` | list of float | none | Temperatures to extract. Each must map to a `'zi'` tuple. |
| `cInfTargetMs` | float | none | Time for `C_infinity`, in ms. |
| `datasetRegistry` | dict | none | Registry from `_compute_zi_dataset`. |
| `ziParamsByFile` | dict | none | `dataFile -> {'gridColOffset', 'gridColDelta', 'chunkSize'}`. Missing entries use the defaults. |

**Returns** `(processedTransients, executionErrors)`.

**Called by** `_compute_mixed_transients`.

#### _compute_zi_subfolder_transients(selectedTemps, cInfTargetMs, datasetRegistry, ziParamsByFile)

For the `'zi_subfolder'` entries: it reads each file with the column names forced to `chunk;timestamp;value` and keeps the `chunk == 0` rows (at least 2 are required). The truncation, time axis, and unit conversion are the same as in `_compute_zi_transients`. The parameters are the same too.

**Returns** `(processedTransients, executionErrors)`.

**Called by** `_compute_mixed_transients`.

#### _compute_mixed_transients(ziTemps, legacyTemps, cInfTargetMs, datasetRegistry, ziParamsByFile, rbDurationMs, samplingRateS, ziSubfolderTemps=None)

Runs the three extractors on their subsets and merges the results. This is the function submitted to the process pool.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `ziTemps` | list | none | Temperatures tagged `'zi'`. |
| `legacyTemps` | list | none | Temperatures with a plain path or `'legacy_chunk'`. |
| `cInfTargetMs` | float | none | Time for `C_infinity`, in ms (the GUI passes 0.9 × Reverse Bias). |
| `datasetRegistry` | dict | none | Combined registry. |
| `ziParamsByFile` | dict | none | ZI grid parameters per data file. |
| `rbDurationMs` | float | none | Reverse-bias window length for legacy pulse averaging, in ms. |
| `samplingRateS` | float | none | Sample **period** in seconds, despite the name. |
| `ziSubfolderTemps` | list or None | `None` | Temperatures tagged `'zi_subfolder'`. |

**Returns** `(processedTransients, executionErrors)`.

**Called by** `_process_raw_transients` (in the child process) and `detailedAnalysisTab`.

#### _compute_legacy_transients(selectedTemps, rbDurationMs, cInfTargetMs, datasetRegistry, samplingRateS)

Extracts and averages transients from legacy entries:

- `('legacy_chunk', path, chunk)`: it reads the semicolon CSV and filters on the first column when `chunk` is not `None`. It drops rows with any NaN and uses the last column whose name contains `value`, `smoothed`, `cap`, or `impedance` (otherwise the last column). F values are converted to pF. The time axis is `arange(n) * samplingRateS * 1000` ms.
- `.txt` (JSON) or `.h5`: it reads `AuxInput1` (excitation, V) and `ImpedanceIm` (F). For `.h5` it reads only these two channels, through `iaT.read_h5_record`. It converts to float32 and multiplies `ImpedanceIm` by 1e12 (pF). It finds the reverse-bias starts with `_find_reverse_bias_starts` and cuts `int(rbDurationMs * 1e-3 / samplingRateS)` samples after each start, keeping only full windows. The windows are averaged. Time is `arange(len) * samplingRateS * 1000` ms, with t = 0 at the last fill sample.
- `.csv` (plain): column 0 is taken as `time_ms` and column 1 as `avg_cap_pf`, both as they are.
- Any other extension: logged as `unsupported file type`.

The skip reasons appended to `executionErrors` include `no excitation (AuxInput1) samples ...`, `no fill pulses found: the excitation (AuxInput1) stays between L and H V.`, `... never falls through X V.`, and `found N fill pulse(s), but none is followed by a full R ms reverse-bias window before the data ends (T ms recorded); lower Reverse Bias (ms).` Any exception becomes `T°C: <exception>`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `selectedTemps` | list of float | none | Temperatures to extract (keys of `datasetRegistry`). |
| `rbDurationMs` | float | none | Reverse-bias window, in ms. |
| `cInfTargetMs` | float | none | Time for `C_infinity`, in ms. |
| `datasetRegistry` | dict | none | Registry from `_compute_legacy_dataset`. |
| `samplingRateS` | float | none | Sample period, in s (the GUI uses 1.8666666666666665e-05). |

**Returns** `(processedTransients, executionErrors)`.

**Called by** `_compute_mixed_transients`, the tests, and the benchmarks.

**Example** (checked by running it: a synthetic 3 ms fill / 6 ms reverse-bias file)

```python
import json, os, tempfile
import numpy as np
import liveDataTab as ldT

dt = 1.8666666666666665e-05                       # s per sample
fillN, rbN = int(3e-3 / dt), int(6e-3 / dt)        # 160, 321
k = np.arange(20000) % (fillN + rbN)
aux = np.where(k < fillN, -0.5, -1.5)              # fill -0.5 V, reverse bias -1.5 V
cap = 1e-10 + 2e-12 * np.exp(-np.maximum(k - fillN, 0) * dt / 1e-3)   # F

folder = tempfile.mkdtemp()
with open(os.path.join(folder, 'p25p0.txt'), 'w') as f:
    json.dump({'AuxInput1': aux.tolist(), 'ImpedanceIm': cap.tolist()}, f)
with open(os.path.join(folder, 'runParams.txt'), 'w') as f:
    json.dump({'State Enable Time': 0.006, 'State Disable Time': 0.003}, f)

errors = []
registry = ldT._compute_legacy_dataset(folder, errors)          # {25.0: '...p25p0.txt'}
fpMs, rbMs = ldT._legacy_run_timing(folder)                     # (3.0, 6.0)
transients, extractErrors = ldT._compute_legacy_transients(
    sorted(registry), rbMs, 0.9 * rbMs, registry, dt)
rec = transients[25.0]
len(rec['time_ms'])        # 321
rec['time_ms'][-1]         # 5.9733 ms
rec['avg_cap_pf'][:2]      # [102., 102.]
rec['C_infinity']          # 100.009
extractErrors              # []
```

#### _find_reverse_bias_starts(auxV)

Finds where the excitation drops from the fill level to the reverse-bias level. It estimates the two levels from the finite samples only, but searches the full array (a NaN counts as not-forward), so the returned indices line up with `ImpedanceIm`. It takes the two levels as the 0.01th and 99.99th percentiles, which still catch a fill pulse that is 0.2 % of the samples. If the levels differ by less than `_MIN_PULSE_HEIGHT_V`, it reports no pulses. Otherwise the threshold is the midpoint `(low + high) / 2`. It returns the indices `i` where sample `i` is above the threshold and sample `i + 1` is not, that is, the last fill sample of each pulse.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `auxV` | array-like | none | Excitation voltage (AuxInput1), V. |

**Returns** `(indices, message)`. `indices` is an int array. `message` is `None` on success, otherwise a sentence starting `no excitation ...` or `no fill pulses found: ...`.

**Called by** `_compute_legacy_transients`.

**Example**

```python
ldT._find_reverse_bias_starts(np.array([0, 0, -5, -5, -5, 0, -5, -5.]))
# -> (array([1, 5]), None)      threshold -2.5 V
ldT._find_reverse_bias_starts(np.full(100, -1.0))
# -> (array([]), 'no fill pulses found: the excitation (AuxInput1) stays between -1.000 and -1.000 V.')
```

#### _capacitance_axis_units(curves)

Picks a display unit for curves stored in pF, from the largest finite absolute value `peak` across all curves: `peak >= 1e9` gives `(1e-9, 'mF')`, `>= 1e6` gives `(1e-6, 'µF')`, `>= 1e3` gives `(1e-3, 'nF')`, and anything smaller, or no finite data, gives `(1.0, 'pF')`. Multiply the pF values by `scale` to plot them.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `curves` | iterable of arrays | none | Curves in pF. Empty and all-NaN curves are skipped. |

**Returns** `(scale, unit)`.

**Called by** `_process_raw_transients`.

**Example**

```python
ldT._capacitance_axis_units([np.array([150.0])])    # (1.0, 'pF')
ldT._capacitance_axis_units([np.array([4.5e3])])    # (0.001, 'nF')
ldT._capacitance_axis_units([np.array([4.5e6])])    # (1e-06, 'µF')
ldT._capacitance_axis_units([])                     # (1.0, 'pF')
```

### Qualitative Analysis: extraction driver and plot

#### _plot_slice_ms()

Returns `(start, end)` in ms from **Analysis Slice Start/End (ms)**, each `None` when the field is empty, not a number, or the Timing Boundaries fields do not exist yet. `_process_raw_transients` uses it to window the Qualitative plot.

```python
lo, hi = ldT._plot_slice_ms()   # (2.0, 490.0) with the default fields
```

#### _downsample_for_plot(x, y, maxPoints=_MAX_PLOT_POINTS)

Returns `(x, y)` unchanged if `len(x) <= maxPoints`. Otherwise it returns every `ceil(n / maxPoints)`-th sample, for example 7000 points become 2334. It is used only for drawing; the stored data keeps full resolution.

#### _get_transient_executor()

Returns `dltsc.manual_transientExecutor`, creating a `ProcessPoolExecutor(max_workers=1)` on first use. The pool is reused, so only the first extraction pays the child's import start-up time. `DLTSGUI_MainWindow._finish_close` shuts it down.

#### _process_raw_transients()

**Extract & Average Transients** handler. It returns silently if the registry is empty or a worker is busy. It logs an error if no temperature is selected or **Reverse Bias (ms)** is not numeric. Otherwise it sets `manual_processingBusy`, disables the buttons, and splits the selection into `ziTemps`, `ziSubfolderTemps`, and `legacyTemps` by registry tag. A daemon thread submits `_compute_mixed_transients(...)` to the process pool and blocks on `future.result()`. `apply()` on the Tk thread stores `manual_processedTransients`, draws the plot, logs each error, and sets the status. A crash in the child process is reported as `extraction process failed: <error>`.

#### _build_manualPlotFrame(parent)

Seeds `manual_processedTransients`, `manual_processingBusy`, and `manual_loadingBusy`, then builds the whole **Qualitative Analysis** pane: the scrollable left column (with a mouse-wheel binding active while the pointer is over it), the four group boxes, the figure, the canvas, and the toolbar.

## Threading model

- **Tk main thread**: every widget update, every matplotlib draw, the button callbacks, `_schedule_live_poll`, `_poll_step_listbox_while_busy`, `_handle_run_status`, and `finish_experiment()` (which writes `runParams.txt`).
- **Run threads** (daemon `threading.Thread`): `start_dlts` for **Run DLTS**, and the `_run_control_thread` worker for Resume, Redo, and Retake. They drive the hardware through `runDlts_Tools`. `dltsc.run_busy` allows only one at a time: every launcher returns early while it is set, and `_return_to_room_temp_async` keeps it set during the ramp back. Pausing sets `run_pauseRequested`, and the loop in `run_experiment()` returns `'paused'` before the next step.
- **Room-return thread**: `_return_to_room_temp_async` runs `return_to_room_temp()`, which can block for many minutes.
- **Plot worker threads**: `_ingest_files_async`, `_load_offline_run`, and `_recompute_denoise_and_redraw` do `impdData` loading, clustering, and denoising. `livePlot_liveIngestBusy` and `livePlot_offlineIngestBusy` stop a second worker on the same mode.
- **Qualitative threads**: `_scan_manual_directory_async` (folder scan) and the waiter thread in `_process_raw_transients`. `manual_loadingBusy` and `manual_processingBusy` gate them, and the three buttons are disabled meanwhile.
- **Process pool**: one worker process (`dltsc.manual_transientExecutor`) runs `_compute_mixed_transients`. It has its own interpreter and GIL, so long extractions do not slow the Tk thread. This is why `DLTSGUI_MainWindow` guards GUI construction with `__name__ == '__main__'` and calls `multiprocessing.freeze_support()`.
- **Marshaling**: workers hand results back with `dltsc.root.after(0, callback)`, and Tk calls happen only in those callbacks. The exception is `dltsc.log_to_textbox`, which the run threads (inside `runDlts_Tools`) and `start_dlts` call directly from their background threads.
- **Run tokens**: `livePlot_liveRunToken` and `livePlot_offlineRunToken` are incremented on each reset. Pollers and workers carry the token they started with and discard their results if it has changed, so a stale watcher or loader from an earlier run cannot overwrite newer data.

## Notes and limitations

- **NaNs in `AuxInput1`** no longer shift the pulse windows: `[nan, 0, 0, -5, -5, -5, 0, -5, -5]` gives `[2, 6]` (fixed after this page was first written; covered by `tests/test_transient_extraction.py`).
- **Sample period.** Legacy `.txt`/`.h5` extraction takes the sample period from each file's `timeStampImps` (median spacing, `_sample_interval_s`), so a run at another **Data Transfer Rate** gets the right window length and time axis. Only files without usable time stamps, and chunked CSVs, fall back to 1.8666666666666665e-05 s (about 53.57 kSa/s).
- **Timing Boundaries.** Only **Reverse Bias (ms)** affects extraction. **Analysis Slice Start/End (ms)** window the Qualitative plot only; **Filling Duration (ms)** is display only.
- `runParams.txt` is written only when a main sequence completes. A paused, failed, or closed-early run folder has none, so the Timing Boundaries keep their previous values for it.
- **Folder-name timing regex.** The ZI `FP`/`RB` patterns need at least one character between `FP`/`RB` and the number. `FP_1ms_RB_500ms` gives 1 and 500 ms. `FP1ms_RB500ms` gives FP = 500 and RB = 00. `FP10ms` gives FP = 0.
- ZI single-CSV temperatures must be non-negative whole degrees (`^(\d+)C_` on `history_name`).
- Multi-chunk legacy CSVs use a hard-coded chunk map from 120 to 160 °C in 5 °C steps. Chunks above 8 are dropped.
- `_LEGACY_FILENAME_PATTERN` needs a leading `p`/`n` and a lower-case extension. `p25.TXT`, `25C.txt`, and `p25p0.json` are not recognized. **Load Existing Run (Offline)** does offer `*.json` in its filter.
- Plain two-column legacy `.csv` files are taken as they are: column 0 must already be in ms and column 1 in pF.
- **Possible Live-view mix-up on a second run.** `start_thread` starts the watcher before `init_experiment()` publishes the new `dltsc.run_dataFileNames`. On a second **Run DLTS** in the same session, the first ticks can still see the previous run's file list. Those files exist, so they are ingested into the new Live view. If they finish ingesting before the new list is published, the watcher decides that all files are done and stops, and the new run's files are never shown. This is inferred from the code and was not observed in the GUI.
- The Live watcher is started only by **Run DLTS**. Files rewritten by **Redo Selected** or **Remove & Retake Selected** are already marked processed and are not reloaded. Use **Load Existing Run (Offline)** to view them.
- A step file that always fails to load is retried every second for as long as the watcher runs, and each failure is logged.
- If `init_experiment()`, `run_experiment()`, or `return_to_room_temp()` raises an exception instead of returning a status, the `root.after` callback is never scheduled. `run_busy` then stays `True` and the buttons stay in `running` or `returning` until restart. `run_experiment()` catches step errors itself, so this needs an error outside its `try`.
- `dltsc.log_to_textbox` is called from background threads (the run threads and `start_dlts`), which updates a Tk widget off the main thread.
- The ZI transients' time axis starts at `grid_col_offset` (−1 ms by default), so ZI curves include pre-trigger samples. Legacy curves start at the last fill sample.
- The y label of the Live plots is **Impedance Im (F)**. The values are whatever `impdData` stores; no unit conversion is done here.
- `_recompute_denoise_and_redraw` leaves `impd.dataEmissions` holding the emission-0 selection, whereas after an ingest it holds the all-emissions selection. Other tabs that read `livePlot_*ImpdData.dataEmissions` directly can therefore see either one.

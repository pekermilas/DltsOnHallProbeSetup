# dltsConfig

`dltsConfig.py` is the shared state of the application. Every tab module, the run code and the instrument classes import it and read or write its module-level globals: the Tk root and tabs, the two connected instruments, the Input Parameters tab's variables, the run-control flags, and each analysis tab's widgets and results. It also provides the shared log function `log_to_textbox()` and `recast_param_type()`, which turns the Input Parameters tab's display strings into the numbers sent to the instruments.

Every module in the GUI uses it: `DLTSGUI_MainWindow`, `runParamsTab` (Input Parameters), `liveDataTab` (Live Tools), `dataAnalysisTab`, `detailedAnalysisTab`, plus `runDlts_Tools` and `zurichInstruments_Control`. The benchmark scripts in `benchmarks/hardware/` fill it by hand to run without the GUI.

## Import

```python
import dltsConfig as dltsc
```

Importing it calls `sys.setswitchinterval(0.001)` (the interpreter default is 5 ms), so a CPU-heavy background thread hands the GIL back to the Tk main thread more often. This applies to the whole process.

## Module constants and globals

All globals are listed below, grouped by the section comments in the file. Abbreviations in the "Set by" and "Read by" columns:

| Abbreviation | Module |
|---|---|
| `main` | `DLTSGUI_MainWindow.py` (`main` alone = its `if __name__ == '__main__':` block) |
| `rpT` | `runParamsTab.py` |
| `ldT` | `liveDataTab.py` |
| `daT` | `dataAnalysisTab.py` |
| `deT` | `detailedAnalysisTab.py` |
| `rdT` | `runDlts_Tools.py` |
| `ziC` | `zurichInstruments_Control.py` |
| `hw` | `benchmarks/hardware/hw_common.py`, `hw_run.py`, `hw_preflight.py` |

A function name followed by "(callback)" means a nested function inside it (usually a `worker` thread or the `apply` it schedules on the Tk thread with `root.after`). The "Initial / `init()`" column gives the value at import, then the value `init()` assigns, if it assigns one. The GUI never calls `init()` (see below), so in the GUI the import value is the starting value.

"Set by" and "Read by" were found by parsing every `.py` file in the repository root and `benchmarks/hardware/` for `dltsc.<name>`, `getattr/hasattr/setattr(dltsc, '<name>')`. Tests are not listed.

### GUI

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `root` | `None` | `main` (`tk.Tk()`) | `main`, `main._finish_close`, `main._show_close_dialog`, `main._wait_for_room_temp`; `ldT` (`start_dlts`, `start_thread`, `_run_control_thread`, `_poll_step_listbox_while_busy`, `_reset_live_plot_state`, `_schedule_live_poll`, `construct_livePlotTab` and several worker callbacks); `deT._detailed_open_label_editor` and worker callbacks; `rpT.construct_runParamsTab`, `rpT.export_h5_file` (callback) | Tk root window. Worker threads use `root.after(0, ...)` to run GUI updates on the Tk thread. |
| `tabControl` | `None` | `main` (`ttk.Notebook`) | `main`, `rpT.construct_runParamsTab`, `ldT.construct_livePlotTab`, `daT.construct_dataAnalysisTab`, `deT.construct_detailedAnalysisTab` | The notebook that holds the tabs. |
| `textbox` | `None` | `rpT.construct_runParamsTab` | `rpT.construct_runParamsTab`, `log_to_textbox` | The log `tk.Text` at the bottom of the Input Parameters tab. |
| `textboxes` | `None` | `main` (`[]`), `rpT.construct_runParamsTab` (appends `textbox`) | `rpT.construct_runParamsTab`, `log_to_textbox` | Every log text box. Only `textbox` is ever added. |
| `textlinecount` | `None` | `main` (`0`), `log_to_textbox` | `log_to_textbox` | Lines currently in the log. |
| `maxTextLineCount` | `None` | `main` (`10`) | `log_to_textbox` | Lines kept in the log; older lines are deleted. |
| `runParamsTab` | `None` | `main` (`ttk.Frame`) | `rpT.construct_runParamsTab` | Frame of the **Input Parameters** tab. |
| `livePlotTab` | `None` | `main` | `ldT.construct_livePlotTab` | Frame of the **Live Tools** tab. |
| `dataAnalysisTab` | `None` | `main` | `daT.construct_dataAnalysisTab` | Frame of the rate-window / Arrhenius tab. |
| `detailedAnalysisTab` | `None` | `main` | `deT.construct_detailedAnalysisTab` | Frame of the **Detailed Analysis** tab. |
| `postprocessingTab` | `None` | `main` | nothing | Frame created but never added to the notebook. |

### Devices (RUNTIME)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `tempDev` | `None` | `rpT.connect_and_get_params('temperature')`, `hw.connect_temperature` | `rdT.check_device_connections`, `rdT.init_experiment`, `rpT.apply_and_push_params`, `rpT.connect_and_get_params`, `main._send_room_ramp`, `main._wait_for_room_temp`, `main._finish_close`, `hw` | The connected `instecTempStage_Control.mK2000B`. |
| `impDev` | `None` | `rpT.connect_and_get_params('impedance')`, `hw.connect_impedance` | `rdT.check_device_connections`, `rpT.apply_and_push_params`, `rpT.connect_and_get_params`, `main._finish_close`, `hw` | The connected `zurichInstruments_Control.ziDevice`. |

### Parameter variables (section "TEST" in the file)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `sourcePrefixSelection` | `None` | nothing | nothing | Unused. |
| `z_params_vars` | `{}` / `{}` | `rpT.construct_runParamsTab` (one `tk.StringVar` per MFIA parameter), `hw.setup_gui_state` | `rpT._sync_param_values_to_device` (via `recast_param_type`), `rpT.connect_and_get_params`, `rpT.apply_and_push_params`, `rpT._capture_current_param_set`, `rpT._load_selected_param_set`, `rdT.check_device_parameters`, `ziC.ziDevice.set_param_value`, `recast_param_type`, `hw.connect_impedance` | MFIA parameter name → variable holding the GUI string, for example `'1 - On'` or `'0.300'`. |
| `z_params_for_push` | `{}` / `{}` | `rpT.connect_and_get_params`, `rpT.apply_and_push_params`, `hw.connect_impedance` | `ziC.ziDevice.set_param_value`, `rdT.check_device_parameters`, `rpT.apply_and_push_params`, `hw.connect_impedance` | MFIA parameter name → numeric value (output of `recast_param_type`). `set_param_value()` and `reload_params()` take values from here first. |
| `z_param_inputField` | `None` | `rpT.construct_runParamsTab` | `rpT.construct_runParamsTab` | MFIA parameter name → its `ttk.Combobox` or `ttk.Entry`. |
| `t_params_vars` | `{}` / `{}` | `rpT.construct_runParamsTab`, `hw.setup_gui_state` | `rpT._sync_param_values_to_device` (via `recast_param_type`), `rpT.connect_and_get_params`, `rpT.apply_and_push_params`, `rpT._capture_current_param_set`, `rpT._load_selected_param_set`, `rdT.check_device_parameters`, `recast_param_type`, `hw.connect_temperature` | Temperature parameter name → `tk.StringVar`. |
| `t_params_for_push` | `{}` / `{}` | `rpT.connect_and_get_params`, `rpT.apply_and_push_params`, `hw.connect_temperature` | `rdT.check_device_parameters`, `rpT.apply_and_push_params` (passed to `tempDev.load_params`), `hw.connect_temperature` | Temperature parameter name → number. |
| `t_param_inputField` | `None` | `rpT.construct_runParamsTab` | `rpT.construct_runParamsTab` | Temperature parameter name → `ttk.Entry`. |
| `d_params_vars` | `{}` / `{}` | `rpT.construct_runParamsTab`, `hw.setup_gui_state` | `rdT.check_device_parameters`, `recast_param_type`, `rpT.apply_and_push_params`, `rpT.browse_root_folder`, `rpT.export_h5_file`, `rpT._capture_current_param_set`, `rpT._load_selected_param_set` | Output parameters: `Number of Points (power of 2)` (GUI default 16), `Number of Reps` (500), `Data File Format` (`'TXT'` or `'HDF5'`), `Data Root Folder` (`''`, set by **Browse...**). |
| `d_params_for_push` | `{}` (not touched by `init()`) | nothing | nothing | Unused. |
| `d_param_inputField` | `None` | `rpT.construct_runParamsTab` | `rpT.construct_runParamsTab` | Output parameter name → widget (Entry, format Combobox, or the Browse button). |
| `root_data_folder` | `None` | nothing | nothing | Unused; the folder is `d_params_vars['Data Root Folder']`. |
| `param_history` | `None` | `rpT._ensure_param_history_state` (`[]`), `rpT._save_current_param_set` | `rpT._ensure_param_history_state`, `rpT._save_current_param_set`, `rpT._load_selected_param_set`, `rpT._update_param_history_field` | Up to 5 saved parameter sets, newest first. |
| `param_history_labels` | `None` | `rpT._ensure_param_history_state`, `rpT._update_param_history_field` | `rpT._ensure_param_history_state`, `rpT._load_selected_param_set`, `rpT._update_param_history_field` | Display labels of `param_history`. |
| `param_history_selection` | `None` | `rpT._ensure_param_history_state` (`tk.StringVar`) | `rpT._ensure_param_history_state`, `rpT._load_selected_param_set`, `rpT._update_param_history_field`, `rpT.construct_runParamsTab` | Selected history label. |
| `param_history_inputField` | `None` | `rpT.construct_runParamsTab` | `rpT._update_param_history_field`, `rpT.construct_runParamsTab` | History `ttk.Combobox`. |
| `run_button` | `None` | `ldT.construct_livePlotTab` | `ldT._set_run_control_buttons`, `ldT.construct_livePlotTab` | The **Run DLTS** button. |

### Run control (pause / resume / redo / retake)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `run_dltsInstance` | `None` | `ldT.start_dlts`, `hw` (`hw_run.py`) | `ldT._handle_run_status`, `ldT._resume_run`, `ldT._redo_selected_steps`, `ldT._retake_selected_steps`, `ldT._run_control_thread`, `ldT._return_to_room_temp_async`, `ldT._refresh_step_listbox`, `ldT._set_run_control_buttons` | The `runDlts_Tools.dltsRun` of the current or paused run. Resume, Redo and Retake reuse it. |
| `run_busy` | `None` / `False` | `ldT.start_thread` (`True`), `ldT._run_control_thread` (`True`), `ldT._return_to_room_temp_async` (`True`, then `False` in its callback), `ldT._handle_run_status` (`False`), `ldT.start_dlts` (callback, `False` on init failure) | `ldT.start_thread`, `ldT._run_control_thread`, `ldT._pause_run`, `ldT._resume_run`, `ldT._redo_selected_steps`, `ldT._retake_selected_steps`, `ldT._poll_step_listbox_while_busy` | `True` while a run thread or the room-temperature return is using the hardware. |
| `run_pauseRequested` | `None` / `False` | `ldT._pause_run` (`True`), `ldT.start_thread` and `ldT._run_control_thread` (`False`) | `rdT.run_experiment` | Pause button flag; checked between main-sequence steps. |
| `run_paused` | `None` / `False` | `ldT._handle_run_status`, `ldT.start_thread` | nothing | `True` once the run has stopped at a pause point. |
| `run_stepStatus` | `None` / `{}` | nothing | nothing | Unused. The step status is `run_dltsInstance.stepStatus`. |
| `run_stepListbox` | `None` | `ldT._build_runControlPanel` | `ldT._refresh_step_listbox`, `ldT._get_selected_step_indices` | `tk.Listbox` of grid steps and their status. |
| `run_pauseButton` | `None` | `ldT._build_runControlPanel` | `ldT._set_run_control_buttons`, `ldT._pause_run` | **Pause** button. |
| `run_resumeButton` | `None` | `ldT._build_runControlPanel` | `ldT._set_run_control_buttons` | **Resume** button. |
| `run_redoButton` | `None` | `ldT._build_runControlPanel` | `ldT._set_run_control_buttons` | **Redo** button. |
| `run_retakeButton` | `None` | `ldT._build_runControlPanel` | `ldT._set_run_control_buttons` | **Remove & Retake** button. |
| `run_abortRequested` | `None` / `False` | `main._send_room_ramp` (`True` on window close), `hw` (`hw_run.watchdog`) | `rdT.run_experiment`, `rdT._run_single_step`, `hw` | Stop the run at the next check and discard a step whose acquisition overlapped the close. Never reset in the GUI. |

### App close (return to room temperature)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `app_closing` | `None` / `False` | `main.on_closing` | `main.on_closing`, `ldT._handle_run_status`, `ldT._return_to_room_temp_async` (callback) | `True` once the window close was requested; blocks repeat clicks and new runs. |
| `app_roomReturnSent` | `None` / `False` | `main._send_room_ramp` | `main._emergency_room_return` | `True` once the room-temperature ramp was commanded on the way out, so the exit backstop does not send it again. |
| `app_closeDialog` | `None` | `main._show_close_dialog` | `main.on_closing` | The "returning to room temperature" `Toplevel`. |
| `app_closeStatusLabel` | `None` | `main._show_close_dialog` | `main._show_close_dialog`, `main._wait_for_room_temp` | Its live "Stage at X °C → room temperature Y °C" label. |
| `app_closeNowRequested` | `None` / `False` | `main._close_now` | `main._close_now`, `main._wait_for_room_temp` | "Close now" was clicked: stop waiting and leave the controller ramping. |

### Run file watch

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `run_dataFolder` | `None` | `rdT.init_experiment` | `ldT._qualitative_live_update` | Folder of the current run (ends with `\`); the Qualitative Analysis frame adopts it. |
| `run_startTime` | `None` | `rdT.init_experiment` | `ldT._process_raw_transients` | `datetime` the current run started (the time in its folder name); left end of the Temperature Trace time axis. |
| `run_dataFileNames` | `None` / `[]` | `rdT.init_experiment` | `ldT._schedule_live_poll`, `hw` (`hw_run.live_worker`) | One file path per grid step; the live watcher waits for each to exist. |
| `run_outputFileType` | `None` | `rdT.init_experiment` | nothing | Lower-cased Data File Format of the current run. |

### Live plot (automated)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `livePlot_activeMode` | `None` / `'live'` | `ldT._build_autoPlotFrame`, `ldT._set_livePlot_mode` | `ldT._active_impd`, `ldT._active_emission0Data`, `ldT._active_allEmissionsData`, `ldT._ingest_files_async`, `ldT._load_offline_run` (callback), `ldT._recompute_denoise_and_redraw`, `ldT._schedule_live_poll`, `ldT._set_livePlot_mode` | `'live'` or `'offline'`: which dataset is drawn. |
| `livePlot_modeVar` | `None` | `ldT._build_autoPlotFrame` | `ldT._on_mode_toggle`, `ldT._set_livePlot_mode` | `tk.StringVar` of the Live/Offline radio buttons. |
| `livePlot_denoiseMethodVar` | `None` | `ldT._build_autoPlotFrame` | `ldT._ingest_files_async`, `ldT._load_offline_run`, `ldT._recompute_denoise_and_redraw`, `ldT._redraw_auto_plots` | `tk.StringVar` of the denoise dropdown. |
| `livePlot_datasetVar` | `None` | `ldT._build_autoPlotFrame` | `ldT._get_selected_dataset_temp`, `ldT._redraw_auto_plots`, `ldT._reset_auto_plot_placeholder`, `ldT._set_livePlot_mode`, `ldT._update_dataset_dropdown` | `tk.StringVar` of the dataset (temperature) dropdown. |
| `livePlot_datasetCombo` | `None` | `ldT._build_autoPlotFrame` | `ldT._reset_auto_plot_placeholder`, `ldT._update_dataset_dropdown` | The dataset dropdown widget. |
| `livePlot_figure` | `None` | `ldT._build_autoPlotFrame` | `ldT._redraw_auto_plots` | Matplotlib figure of the automated plots. |
| `livePlot_axEmission0` | `None` | `ldT._build_autoPlotFrame` | `ldT._redraw_auto_plots`, `ldT._reset_auto_plot_placeholder` | "Emission 0" axes. |
| `livePlot_axAllEmissions` | `None` | `ldT._build_autoPlotFrame` | `ldT._redraw_auto_plots`, `ldT._reset_auto_plot_placeholder` | "All Emissions Aligned" axes. |
| `livePlot_canvas` | `None` | `ldT._build_autoPlotFrame` | `ldT._redraw_auto_plots`, `ldT._reset_auto_plot_placeholder` | Tk canvas of the figure. |
| `livePlot_statusLabel` | `None` | `ldT._build_autoPlotFrame` | `ldT._ingest_files_async`, `ldT._load_offline_run`, `ldT._schedule_live_poll`, `ldT._set_livePlot_mode` | Status text under the plots. |
| `livePlot_liveImpdData` | `None` | `ldT._reset_live_plot_state`, `ldT._ingest_files_async` (callback) | `ldT._active_impd`, `ldT._ingest_files_async` (worker), `daT._calculate_rate_windows`, `daT._resolve_impd_for_source` | The accumulating `impedanceAnalysis_Tools.impdData` of the current run. |
| `livePlot_liveEmission0Data` | `None` / `{}` | `ldT._reset_live_plot_state`, `ldT._ingest_files_async` (callback), `ldT._recompute_denoise_and_redraw` (callback) | `ldT._active_emission0Data` | Temperature → emission-0 block `{x, y/ymean, yFiltered}`. |
| `livePlot_liveAllEmissionsData` | `None` / `{}` | `ldT._reset_live_plot_state`, `ldT._ingest_files_async` (callback) | `ldT._active_allEmissionsData`, `daT._calculate_rate_windows`, `daT._processed_transients_from_automated` | Temperature → all emission blocks `{x, y (2-D, one column per block)}`. |
| `livePlot_liveDatasetSel` | `None` | `ldT._reset_live_plot_state`, `ldT._set_livePlot_mode` | `ldT._set_livePlot_mode` | Last dataset selected in Live mode. |
| `livePlot_liveRunToken` | `None` / `0` | `ldT._build_autoPlotFrame`, `ldT._reset_live_plot_state` (increments) | `ldT.start_thread`, `ldT._schedule_live_poll`, `ldT._ingest_files_async` (callback), `ldT._recompute_denoise_and_redraw` | Run counter; a watcher or worker with an older token stops. |
| `livePlot_pollAfterId` | `None` / `None` | `ldT._reset_live_plot_state`, `ldT._schedule_live_poll` | `ldT._reset_live_plot_state` | `root.after` id of the live file poll, for cancellation. |
| `livePlot_processedFiles` | `None` / `set()` | `ldT._build_autoPlotFrame`, `ldT._reset_live_plot_state`; added to in `ldT._ingest_files_async` (callback) | `ldT._schedule_live_poll`, `ldT._ingest_files_async` | Data files already ingested into the live `impdData`. |
| `livePlot_liveIngestBusy` | `None` / `False` | `ldT._build_autoPlotFrame`, `ldT._ingest_files_async`, `ldT._recompute_denoise_and_redraw`, `ldT._reset_live_plot_state` | `ldT._schedule_live_poll`, `ldT._recompute_denoise_and_redraw`, `daT._calculate_rate_windows` | `True` while a live-ingest worker runs. |
| `livePlot_offlineImpdData` | `None` | `ldT._reset_live_plot_state`, `ldT._load_offline_run` (callback) | `ldT._active_impd`, `daT._calculate_rate_windows`, `daT._resolve_impd_for_source` | `impdData` loaded by **Load Existing Run (Offline)**. |
| `livePlot_offlineEmission0Data` | `None` / `{}` | `ldT._reset_live_plot_state`, `ldT._load_offline_run` (callback), `ldT._recompute_denoise_and_redraw` (callback) | `ldT._active_emission0Data` | Offline counterpart of `livePlot_liveEmission0Data`. |
| `livePlot_offlineAllEmissionsData` | `None` / `{}` | `ldT._reset_live_plot_state`, `ldT._load_offline_run` (callback) | `ldT._active_allEmissionsData`, `daT._calculate_rate_windows`, `daT._processed_transients_from_automated` | Offline counterpart of `livePlot_liveAllEmissionsData`. |
| `livePlot_offlineDatasetSel` | `None` | `ldT._reset_live_plot_state`, `ldT._set_livePlot_mode` | `ldT._set_livePlot_mode` | Last dataset selected in Offline mode. |
| `livePlot_offlineRunToken` | `None` / `0` | `ldT._build_autoPlotFrame`, `ldT._reset_live_plot_state` | `ldT._load_offline_run`, `ldT._recompute_denoise_and_redraw` | Offline load counter, as `livePlot_liveRunToken`. |
| `livePlot_offlineIngestBusy` | `None` / `False` | `ldT._build_autoPlotFrame`, `ldT._load_offline_run`, `ldT._recompute_denoise_and_redraw`, `ldT._reset_live_plot_state` | `ldT._recompute_denoise_and_redraw`, `daT._calculate_rate_windows` | `True` while an offline load worker runs. |

### Manual / qualitative analysis (Live Tools, live run only)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `manual_datasetRegistry` | `None` / `{}` | `ldT._adopt_live_run_folder`, `ldT._qualitative_live_update` (adds new steps) | `ldT._process_raw_transients`, `ldT._qualitative_live_update` | Temperature (°C) → step file path of the run folder being followed (legacy per-temperature entries only; see `quickData_datasetRegistry` for every format a saved folder can hold). |
| `manual_samplingRate` | `None` | nothing | `ldT._extract_transients_async` | Always `None`; the reader falls back to `1.8666666666666665e-05` (a sample interval in s, despite the name) for files without usable time stamps. |
| `manual_processedTransients` | `None` / `{}` | `ldT._build_manualPlotFrame`, `ldT._process_raw_transients` (callback) | `daT._calculate_rate_windows`, `daT._get_processed_transients_for_source` | Temperature → `{time_ms, avg_cap_pf, C_infinity, setpoint_C, stage_C, acquired_at}` of the live run: the `Live Run (Qualitative Analysis)` Data Source. |
| `manual_paramVars` | `None` / `{}` | `ldT._build_manualPlotFrame` | `ldT._process_raw_transients`, `ldT._adopt_live_run_folder`, `ldT._plot_slice_ms`, `ldT._sync_slice_end_to_rb`, `daT._rb_ms_for_source` | `tk.StringVar`s `fp_ms` (Filling Duration, default `'1.0'`), `rb_ms` (Reverse Bias, `'500.0'`), `slice_start` (`'2.0'`), `slice_end` (`'490.0'`). |
| `manual_autoSliceEnd` | `None` (`490.0` after `init()`) | `ldT._build_manualPlotFrame`, `ldT._set_auto_slice_end` | `ldT._sync_slice_end_to_rb` | Last Analysis Slice End (ms) set automatically from Reverse Bias; while `slice_end` still holds it, it follows `rb_ms` edits (98 %). |
| `manual_tempListbox` | `None` | `ldT._build_manualPlotFrame` | `ldT._process_raw_transients`, `ldT._clear_manual_temps`, `ldT._select_all_manual_temps`, `ldT._adopt_live_run_folder`, `ldT._qualitative_live_update` | Temperature list box. |
| `manual_folderLabel` | `None` | `ldT._build_manualPlotFrame` | `ldT._adopt_live_run_folder` | `Run folder: ...` label of the Live Run group. |
| `manual_extractButton` | `None` | `ldT._build_manualPlotFrame` | `ldT._set_manual_buttons_state` | **Extract & Average Transients** button, disabled while a worker is running. |
| `manual_processingBusy` | `None` | `ldT._build_manualPlotFrame`, `ldT._process_raw_transients` | `ldT._process_raw_transients`, `ldT._qualitative_live_update` | `True` while `_process_raw_transients`' background worker runs. |
| `manual_transientExecutor` | `None` | `ldT._get_transient_executor` | `ldT._get_transient_executor`, `main._finish_close` (shutdown) | Persistent `ProcessPoolExecutor` for transient extraction (Qualitative frame and Quick Analysis Offline Data), so repeat extractions skip the child process's one-time import cold start. |
| `manual_figure` | `None` | `ldT._build_manualPlotFrame` | `ldT._process_raw_transients` (callback) | Qualitative Analysis figure. |
| `manual_ax` | `None` | `ldT._build_manualPlotFrame`, `ldT._process_raw_transients` (callback) | `ldT._process_raw_transients` (callback) | Left axes: Averaged Capacitance Transients Profile. |
| `manual_axTemps` | `None` | `ldT._build_manualPlotFrame`, `ldT._process_raw_transients` (callback) | `ldT._process_raw_transients` (callback) | Right axes: Temperature Trace (°C vs time of measurement), one point per extracted step, last point labeled as the latest. |
| `manual_canvas` | `None` | `ldT._build_manualPlotFrame` | `ldT._process_raw_transients` (callback) | Its Tk canvas. |
| `manual_statusLabel` | `None` | `ldT._build_manualPlotFrame` | `ldT._process_raw_transients` | Status label. |
| `manual_liveFollowVar` | `None` | `ldT._build_manualPlotFrame` | `ldT._qualitative_live_update` | `tk.BooleanVar` of **Follow live run (auto-update)**: re-extract as run files are written. |
| `manual_liveRunFolder` | `None` | `ldT.start_thread` (clears), `ldT._adopt_live_run_folder` | `ldT._qualitative_live_update` | Run folder the Qualitative frame adopted as its source while following. |
| `manual_liveFileMtimes` | `None` / `{}` | `ldT._build_manualPlotFrame`, `ldT.start_thread` (clears), `ldT._qualitative_live_update` | `ldT._changed_run_files` | Run data file → modification time it was last extracted at (new or rewritten = changed). |
| `manual_livePollActive` | `None` / `False` | `ldT._build_manualPlotFrame`, `ldT._start_qualitative_live_follow`, `ldT._qualitative_live_tick` | `ldT._start_qualitative_live_follow` | `True` while the follow loop (`_qualitative_live_tick`) is scheduled. |

### Quick Analysis: Offline Data (saved folder loader)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `quickData_dataDirectory` | `None` | `daT._scan_quick_folder_async` (callback) | `daT._browse_quick_folder` | Most recently selected (not appended) folder; the folder dialogs start there. |
| `quickData_datasetRegistry` | `None` / `{}` | `daT._build_offlineDataFrame`, `daT._scan_quick_folder_async` (callback) | `daT._browse_quick_folder`, `daT._extract_quick_transients` | Temperature (°C) → a file path (plain legacy file), `('legacy_chunk', file_path, chunk_id)` (chunk_id may be `None`), `('zi', data_file, chunk_id)`, or `('zi_subfolder', data_file, None)`. Explicitly tagged so entries from different-format sources can coexist after an append. |
| `quickData_ziParamsByFile` | `None` / `{}` | `daT._build_offlineDataFrame`, `daT._scan_quick_folder_async` (callback) | `daT._extract_quick_transients` | ZI data file → `{'gridColOffset', 'gridColDelta', 'chunkSize'}`; keyed per file so appended ZI sources keep their own acquisition parameters. |
| `quickData_sourceFolders` | `None` / `[]` | `daT._build_offlineDataFrame`, `daT._scan_quick_folder_async` (callback) | the same callback | Folders combined into `quickData_datasetRegistry` so far. |
| `quickData_processedTransients` | `None` / `{}` | `daT._build_offlineDataFrame`, `daT._scan_quick_folder_async` (callback, clears), `daT._extract_quick_transients` (callback) | `daT._get_processed_transients_for_source`, `daT._calculate_rate_windows` | Temperature → `{time_ms, avg_cap_pf, C_infinity, ...}`: the `Loaded Folder (Offline Data)` Data Source of Rate Window Analysis. |
| `quickData_paramVars` | `None` / `{}` | `daT._build_offlineDataFrame` | `daT._scan_quick_folder_async` (callback), `daT._extract_quick_transients`, `daT._rb_ms_for_source` | `tk.StringVar`s `fp_ms` (Filling Duration, default `'1.0'`) and `rb_ms` (Reverse Bias, `'500.0'`). |
| `quickData_tempListbox` | `None` | `daT._build_offlineDataFrame` | `daT._scan_quick_folder_async` (callback), `daT._extract_quick_transients` | Temperature list box. |
| `quickData_folderLabel` | `None` | `daT._build_offlineDataFrame` | `daT._scan_quick_folder_async` (callback) | `Source: ...` label. |
| `quickData_selectFolderButton` | `None` | `daT._build_offlineDataFrame` | `daT._set_quick_buttons_state` | **Select Source Folder** button, disabled while a scan or extraction is running. |
| `quickData_appendFolderButton` | `None` | `daT._build_offlineDataFrame` | `daT._set_quick_buttons_state` | **Append Source Folder** button. |
| `quickData_extractButton` | `None` | `daT._build_offlineDataFrame` | `daT._set_quick_buttons_state` | **Extract & Average Transients** button. |
| `quickData_statusLabel` | `None` | `daT._build_offlineDataFrame` | `daT._scan_quick_folder_async`, `daT._extract_quick_transients` | Status label. |
| `quickData_loadingBusy` | `None` / `False` | `daT._build_offlineDataFrame`, `daT._scan_quick_folder_async` | `daT._quick_busy` | `True` while `_scan_quick_folder_async`' background worker runs. |
| `quickData_processingBusy` | `None` / `False` | `daT._build_offlineDataFrame`, `daT._extract_quick_transients` | `daT._quick_busy` | `True` while `_extract_quick_transients`' background worker runs. |

### Data analysis (rate window / Arrhenius)

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `rateWindow_dataSourceVar` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | `tk.StringVar`: Loaded Folder / Live Run Qualitative / Automated Live / Automated Offline / Auto. |
| `rateWindow_statusLabel` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Which data source was used and how many temperatures. |
| `rateWindow_signalMethodVar` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Measured C (default) / Smoothed C. |
| `rateWindow_denoiseVar` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | `'None (raw)'` (default) / pca / wavelet / sgolay / lowess. |
| `rateWindow_denoisedEmissions` | `None` | `daT._calculate_rate_windows` | nothing | Last denoised emission snapshot, T → `{'x','yRaw','yFiltered','yerr','filterMethod'}`. |
| `rateWindow_peakMethodVar` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | `'Smoothing Spline'` (default) or lmfit curve fit. |
| `rateWindow_windowVars` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | List of 5 `(t1Var, t2Var)` pairs. |
| `rateWindow_tpLoVar` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Peak-search lower bound, K (blank = none). |
| `rateWindow_tpHiVar` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Peak-search upper bound, K. |
| `rateWindow_signals` | `None` / `{}` | `daT._build_rateWindowFrame`, `daT._calculate_rate_windows` | `daT._calculate_rate_windows` | Window index → `{'T_k', 'Signal'}`. |
| `rateWindow_extractedPeaks` | `None` / `{}` | `daT._build_rateWindowFrame`, `daT._calculate_rate_windows` | `daT._calculate_rate_windows`, `daT._run_arrhenius_solver` | Window index → `{'T_peak', 'S_peak', 'e_n', 'T_peak_err', 't1', 't2'}`; skipped windows are left out. |
| `rateWindow_transients` | `None` | `daT._calculate_rate_windows` | `daT._run_arrhenius_solver` | `(records, temps, rb_ms)`: the averaged transients of the last Compute as Detailed Analysis records, for N_T; `None` when there are none. |
| `rateWindow_peakTable` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | `ttk.Treeview` of per-window results. |
| `rateWindow_figure` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Rate-window figure. |
| `rateWindow_ax` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Its axes. |
| `rateWindow_canvas` | `None` | `daT._build_rateWindowFrame` | `daT._calculate_rate_windows` | Its canvas. |
| `arrhenius_ndVar` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Background doping Nd, cm⁻³. |
| `arrhenius_gammaVar` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Emission pre-factor γ, cm⁻² s⁻¹ K⁻². |
| `arrhenius_energyLabel` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Activation energy result label. |
| `arrhenius_captureLabel` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Capture cross-section result label. |
| `arrhenius_densityLabel` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Trap density result label. |
| `arrhenius_figure` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Arrhenius figure. |
| `arrhenius_ax` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Its axes. |
| `arrhenius_canvas` | `None` | `daT._build_arrheniusFrame` | `daT._run_arrhenius_solver` | Its canvas. |

### Detailed analysis

State and results:

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `detailed_data` | `None` / `{}` | `deT._detailed_load_data` (callback) | `deT._detailed_run_analysis`, `deT._set_detailed_buttons_state` | Temperature (°C) → `(t_ms array, capacitance array in pF, C_infinity)`. |
| `detailed_temps` | `None` / `[]` | `deT._detailed_load_data` (callback) | `deT._detailed_run_analysis` | Sorted temperatures, °C. |
| `detailed_figure` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor`, `deT._detailed_plot_rate_window_map`, `deT._detailed_plot_transient_map`, `deT._detailed_save_figure` | Current figure, rebuilt each run. |
| `detailed_canvas` | `None` | `deT._detailed_plot` | `deT._detailed_plot`, `deT._detailed_open_label_editor` | Canvas embedding it. |
| `detailed_figFrame` | `None` | `deT.construct_detailedAnalysisTab` | `deT._detailed_plot` | Frame the canvas and toolbar go in. |
| `detailed_ax1` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | Arrhenius panel. |
| `detailed_ax2` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | DLTS spectra panel (optional). |
| `detailed_ax3` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | 2-D transient map (optional). |
| `detailed_ax4` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | Rate-window analysis map (optional). |
| `detailed_leg1` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | Legend. |
| `detailed_leg2` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | Legend. |
| `detailed_legM` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | Legend. |
| `detailed_legRW` | `None` | `deT._detailed_plot` | `deT._detailed_open_label_editor` | Legend of the rate-window map. |
| `detailed_annBox` | `None` | `deT._detailed_plot` | nothing through `dltsc` | Draggable Arrhenius results annotation. |
| `detailed_lastResMw` | `None` | `deT._detailed_run_analysis` (callback) | nothing | Last multi-window `compute_arrhenius()` result. |
| `detailed_lastResStd` | `None` | `deT._detailed_run_analysis` (callback) | nothing | Last standard-window result. |
| `detailed_lastNt` | `None` | `deT._detailed_run_analysis` (callback) | nothing | Last trap density. |
| `detailed_loadingBusy` | `None` / `False` | `deT._detailed_load_data` (and callback) | `deT._detailed_load_data`, `deT._detailed_run_analysis` | `True` while the load worker runs. |
| `detailedProcessingBusy` | `None` / `False` | `deT._detailed_run_analysis` (and callback) | `deT._detailed_load_data`, `deT._detailed_run_analysis` | `True` while the analysis worker runs. The name has no underscore after `detailed`. |
| `detailed_executor` | `None` / `None` | `deT._get_detailed_executor`, `deT._run_in_detailed_process` | `deT._get_detailed_executor`, `main._finish_close` (shutdown) | Single-worker `ProcessPoolExecutor` of this tab. |
| `detailed_hitTestStale` | `None` / `True` | `deT._detailed_plot` (and its inner `_mark_fresh`, `_mark_stale`) | `deT._detailed_install_drag` (inner `_on_press`) | `True` between a canvas resize and its redraw; the drag handler redraws only then. |

Control variables, all created in `deT.construct_detailedAnalysisTab` and read by `deT._detailed_run_analysis` unless stated:

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `detailed_baseVar` | `None` | construct (`StringVar('')`) | `deT._detailed_browse_folder`, `deT._detailed_load_data` | Data folder. |
| `detailed_gridOffVar` | `None` | construct (`DoubleVar(-0.001)`) | `deT._detailed_load_data` | ZI grid offset, s. |
| `detailed_gridDtVar` | `None` | construct (`DoubleVar(1.86667e-5)`) | `deT._detailed_load_data` | ZI grid dt, s. |
| `detailed_chunkSizeVar` | `None` | construct (`IntVar(32768)`) | `deT._detailed_load_data` | Samples per chunk. |
| `detailed_rbMsVar` | `None` | construct (`DoubleVar(500.0)`) | `deT._detailed_load_data`, `deT._detailed_run_analysis` | Reverse-bias duration, ms. |
| `detailed_cinfLoVar` | `None` | construct (`DoubleVar(0.40)`) | `deT._detailed_load_data` | C₀ window start, fraction of RB. |
| `detailed_cinfHiVar` | `None` | construct (`DoubleVar(0.90)`) | `deT._detailed_load_data` | C₀ window end, fraction of RB. |
| `detailed_gammaVar` | `None` | construct (`DoubleVar(1.66e21)`) | `deT._detailed_run_analysis` | γ, cm⁻² s⁻¹ K⁻² (4H-SiC). |
| `detailed_ndVar` | `None` | construct (`DoubleVar(3.2e14)`) | `deT._detailed_run_analysis` | Nd, cm⁻³. |
| `detailed_tpeakLoVar` | `None` | construct (`DoubleVar(250.0)`) | `deT._detailed_run_analysis` | Peak search T min, K. |
| `detailed_tpeakHiVar` | `None` | construct (`DoubleVar(400.0)`) | `deT._detailed_run_analysis` | Peak search T max, K. |
| `detailed_peakMethodVar` | `None` | construct (`'Smoothing Spline (bootstrap)'`) | `deT._detailed_run_analysis` | Per-window peak finder: lmfit parabola or smoothing spline. |
| `detailed_signalMethodVar` | `None` | construct (`'Measured C (nearest sample)'`) | `deT._detailed_run_analysis` | C(t) read-off: nearest sample or spline-interpolated. |
| `detailed_denoiseVar` | `None` | construct (`'None (raw)'`) | `deT._detailed_run_analysis` | Per-transient denoise method. |
| `detailed_nWinVar` | `None` | construct (`IntVar(16)`) | `deT._detailed_run_analysis` | Number of multi-windows. |
| `detailed_t1MinVar` | `None` | construct (`DoubleVar(5.0)`) | `deT._detailed_run_analysis` | t₁ min, ms. |
| `detailed_t1MaxVar` | `None` | construct (`DoubleVar(90.0)`) | `deT._detailed_run_analysis` | t₁ max, ms. |
| `detailed_ratioVar` | `None` | construct (`DoubleVar(5.0)`) | `deT._detailed_run_analysis` | Ratio t₂/t₁. |
| `detailed_stdWinsVar` | `None` | construct (`BooleanVar(True)`) | `deT._detailed_run_analysis` | Show the 5-window comparison. |
| `detailed_stdEntries` | `None` | construct (list) | `deT._detailed_run_analysis` | 5 `(t1Var, t2Var)` `DoubleVar` pairs, defaults (5, 25), (10, 50), (20, 100), (50, 250), (100, 490) ms. |
| `detailed_showSpectraVar` | `None` | construct (`BooleanVar(True)`) | `deT._detailed_run_analysis` | Show the DLTS spectra panel. |
| `detailed_nSpectraVar` | `None` | construct (`IntVar(5)`) | `deT._detailed_run_analysis` | Number of spectra drawn. |
| `detailed_showTmapVar` | `None` | construct (`BooleanVar(True)`) | `deT._detailed_run_analysis` | Show the 2-D transient map. |
| `detailed_showTauVar` | `None` | construct (`BooleanVar(True)`) | `deT._detailed_run_analysis` | Overlay τ(T) on the map. |
| `detailed_showRwmVar` | `None` | construct (`BooleanVar(True)`) | `deT._detailed_run_analysis` | Show the rate-window analysis map. |

Widgets referenced outside their constructor:

| Name | Initial / `init()` | Set by | Read by | Meaning |
|---|---|---|---|---|
| `detailed_loadButton` | `None` | `deT.construct_detailedAnalysisTab` | `deT._set_detailed_buttons_state` | **Load Data** button. |
| `detailed_runButton` | `None` | `deT.construct_detailedAnalysisTab` | `deT._set_detailed_buttons_state` | **Run Analysis** button. |
| `detailed_loadInfoLabel` | `None` | `deT.construct_detailedAnalysisTab` | `deT._detailed_load_data` (callback) | "No data loaded." / load summary. |
| `detailed_statusLabel` | `None` | `deT.construct_detailedAnalysisTab` | `deT._detailed_load_data`, `deT._detailed_run_analysis`, `deT._detailed_save_figure`, `deT._detailed_export_txt` | Status line. |
| `detailed_resultsText` | `None` | `deT.construct_detailedAnalysisTab` | `deT._detailed_write_results`, `deT._detailed_export_txt` | Results text box. |

## Module-level functions

### init()

Declares all globals except `d_params_for_push` as `global` and resets a subset of them to "empty" values:

| Global | Value set by `init()` |
|---|---|
| `z_params_vars`, `z_params_for_push`, `t_params_vars`, `t_params_for_push`, `d_params_vars` | `{}` |
| `run_busy`, `run_pauseRequested`, `run_paused`, `run_abortRequested` | `False` |
| `app_closing`, `app_roomReturnSent`, `app_closeNowRequested` | `False` |
| `run_stepStatus` | `{}` |
| `run_dataFileNames` | `[]` |
| `livePlot_activeMode` | `'live'` |
| `livePlot_liveRunToken`, `livePlot_offlineRunToken` | `0` |
| `livePlot_pollAfterId` | `None` |
| `livePlot_processedFiles` | `set()` |
| `livePlot_liveEmission0Data`, `livePlot_liveAllEmissionsData`, `livePlot_offlineEmission0Data`, `livePlot_offlineAllEmissionsData` | `{}` |
| `livePlot_liveIngestBusy`, `livePlot_offlineIngestBusy` | `False` |
| `manual_datasetRegistry`, `manual_processedTransients`, `manual_paramVars`, `manual_liveFileMtimes` | `{}` |
| `manual_autoSliceEnd` | `490.0` |
| `manual_livePollActive` | `False` |
| `quickData_datasetRegistry`, `quickData_ziParamsByFile`, `quickData_processedTransients`, `quickData_paramVars` | `{}` |
| `quickData_sourceFolders` | `[]` |
| `quickData_loadingBusy`, `quickData_processingBusy` | `False` |
| `rateWindow_signals`, `rateWindow_extractedPeaks` | `{}` |
| `detailed_data` | `{}` |
| `detailed_temps` | `[]` |
| `detailed_loadingBusy`, `detailedProcessingBusy` | `False` |
| `detailed_executor` | `None` |
| `detailed_hitTestStale` | `True` |

Every other global keeps its current value.

No parameters.

**Returns** `None`.

**Side effects** Rebinds the globals above. It replaces the parameter-variable dicts, so calling it after the tabs are built disconnects `dltsConfig` from the GUI's `StringVar`s. The GUI (`DLTSGUI_MainWindow`) never calls it; the tab modules instead guard against the `None` starting values. `benchmarks/hardware/hw_common.setup_gui_state` calls it before filling the parameter dicts.

**Example**

```python
import dltsConfig as dltsc
dltsc.init()                          # script use: clean flags and empty dicts
assert dltsc.run_abortRequested is False
```

### log_to_textbox(message)

Appends `message` and a newline to every text box in `textboxes` (or to `textbox` if `textboxes` is empty), and keeps at most `maxTextLineCount` lines by deleting the first line. When there is no text box (no GUI), it prints `message` to the console instead.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `message` | `str` | required | Text to log. |

**Returns** `None`.

**Side effects** Inserts into Tk text widgets, increments `textlinecount`, or prints. It does not marshal onto the Tk thread: callers in worker threads (`runDlts_Tools`, `zurichInstruments_Control.pull_data`) touch the widget directly from those threads. With text boxes present but `textlinecount` or `maxTextLineCount` still `None`, it raises `TypeError`. `hw_common.setup_gui_state` replaces the whole function with a logger that prints and appends to a file; every caller uses `dltsc.log_to_textbox(...)`, so the replacement takes effect everywhere.

**Example**

```python
dltsc.log_to_textbox('Stage at 25.0 C')   # prints when no GUI is running
```

### recast_param_type(device, pname)

Reads `<group>_params_vars[pname].get()` and converts the GUI string to the value sent to the instrument.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `device` | `str` | required | `'impDev'` (reads `z_params_vars`), `'tempDev'` (`t_params_vars`) or `'output'` (`d_params_vars`). |
| `pname` | `str` | required | Parameter name. |

**Returns** the converted value (`float` or `int`).

**Side effects** None. Raises `UnboundLocalError` when `device` is unknown, `pname` is not in the dict, or a dropdown string matches no label below (for example `'1'` instead of `'1 - On'`). Raises `ValueError` when `float()`/`int()` cannot parse the text. The entry must have a `.get()` method.

Numeric conversions:

| Group | Parameter | Conversion |
|---|---|---|
| `impDev` | `Oscillation Amplitude`, `Oscillation Frequency`, `Max bandwidth`, `Current Range`, `Voltage Range`, `Omega Suppression`, `State Enable Time`, `State Disable Time`, `Aux Output Scale`, `Aux Output Offset`, `Aux Output Lower Limit`, `Aux Output Upper Limit` | `float()` |
| `impDev` | `Filter Harmonic`, `Filter Bandwidth`, `Data Transfer Rate` | `int()` |
| `tempDev` | `Initial Temperature (C)`, `Final Temperature (C)`, `Temperature Step (C)`, `Temperature Ramp (C/min)`, `Room Temperature (C)`, `Room Ramp (C/min)` | `float()` |
| `tempDev` | `Stability Delay (s)` | `int()` (so `'0.5'` raises `ValueError`) |
| `output` | `Number of Points (power of 2)`, `Number of Reps` | `int()` |

`output` entries `Data File Format` and `Data Root Folder` have no conversion and raise `UnboundLocalError` if passed.

Label → value mappings (`impDev`):

| Parameter | Label | Value |
|---|---|---|
| `Oscillation ON/OFF` | `1 - On` | 1 |
| | `0 - Off` | 0 |
| `Input Control` | `0 - Manual` | 0 |
| | `1 - Auto` | 1 |
| | `2 - Current Zone` | 2 |
| `Equivalent Circuit Mode` | `0 - 4-Terminal` | 0 |
| | `1 - 2-Terminal` | 1 |
| `Threshold Input Signal` | `59 - TU Output Value` | 59 |
| | `58 - Aux Output Overload` | 58 |
| | `56 - Aux Input Overload` | 56 |
| | `55 - Output Overload` | 55 |
| | `54 - Input(I) Overload` | 54 |
| | `53 - Input(V) Overload` | 53 |
| | `52 - Trigger Out` | 52 |
| | `51 - Trigger In` | 51 |
| | `50 - DIO` | 50 |
| | `3 - Demod Theta` | 3 |
| | `2 - Demod R` | 2 |
| | `1 - Demod Y` | 1 |
| | `0 - Demod X` | 0 |
| `Logic Unit Not` | `0 - Off` | 0 |
| | `1 - On` | 1 |
| `Aux Output Signal` | `0 - Demod X` | 0 |
| | `1 - Demod Y` | 1 |
| | `2 - Demod R` | 2 |
| | `3 - Demod Theta` | 3 |
| | `11 - TU Filtered Value` | 11 |
| | `12 - Manual` | 12 |
| | `13 - TU Output Value` | 13 |
| `Signal Output Add` | `1 - True` | 1 |
| | `0 - False` | 0 |
| `Trigger Source Signal` | `0 - Off` | 0 |
| | `1 - Osc Phi Demod 2` | 1 |
| | `36 - Threshold 1` | 36 |
| | `37 - Threshold 2` | 37 |
| | `38 - Threshold 3` | 38 |
| | `39 - Threshold 4` | 39 |
| | `52 - MDS Sync Out` | 52 |

These labels are exactly the dropdown options in `runParamsTab.construct_runParamsTab()`. The `Filter Harmonic` (1–16) and `Filter Bandwidth` (1–8) dropdowns hold plain digits and go through `int()`.

Callers: `runParamsTab._sync_param_values_to_device` (every MFIA and temperature parameter, on **Connect + Get Params** and **Apply + Push Params**) and `runDlts_Tools.dltsRun._run_single_step` (`Number of Points (power of 2)`, `Number of Reps`).

**Example**

```python
class Var:
    def __init__(self, v): self.v = v
    def get(self): return self.v

dltsc.z_params_vars = {'Trigger Source Signal': Var('36 - Threshold 1')}
dltsc.recast_param_type('impDev', 'Trigger Source Signal')   # 36
dltsc.d_params_vars = {'Number of Reps': Var('100')}
dltsc.recast_param_type('output', 'Number of Reps')          # 100
```

## Internal helpers

The module has no `_name` functions.

## Notes and limitations

- The GUI never calls `init()`. Flags such as `run_busy`, `run_abortRequested` and `app_closing` start as `None` and work only because `None` is falsy; `livePlot_liveRunToken` and similar are guarded with `or 0` in `liveDataTab`.
- `init()` does not declare `d_params_for_push` as `global` and does not reset it (it is unused anyway).
- Unused globals: `sourcePrefixSelection`, `d_params_for_push`, `root_data_folder`, `run_stepStatus`. Written but never read: `run_outputFileType`, `run_paused`, `rateWindow_denoisedEmissions`, `detailed_lastResMw`, `detailed_lastResStd`, `detailed_lastNt`, `postprocessingTab`.
- `manual_samplingRate` is read but never set, so `liveDataTab` uses its fallback of 1.8666666666666665e-05 s whenever a step file has no usable `timeStampImps`.
- `detailedProcessingBusy` breaks the `detailed_` naming pattern.
- `log_to_textbox()` updates Tk widgets from worker threads, which Tkinter does not guarantee to be safe.
- The log keeps only 10 lines in the GUI (`maxTextLineCount = 10`).
- `recast_param_type()` has no `else` branches: unknown names or labels raise `UnboundLocalError` instead of a clear error. `Stability Delay (s)` accepts only whole seconds, while the instrument class stores it as a float.
- `sys.setswitchinterval(0.001)` runs on import and affects every thread of the process, including scripts that only use the instrument classes.

# runParamsTab

## What it's for

`runParamsTab.py` builds the **Input Parameters** tab. On this tab you enter the settings for the Zurich Instruments MFIA impedance analyzer, the Instec temperature controller, and the output files. You connect to each instrument and push the settings to it. The tab also keeps a short history of parameter sets, has a button to export one HDF5 step file to readable text, and holds the application's only log text box.

## What the user sees

The tab has two framed areas. The top frame is 860 × 770 px with a fixed size (`grid_propagate(False)`) and holds all the parameter groups. The bottom frame holds the log text box and grows with the window.

### Impedance analyzer parameters (blue, left columns)

Each row is a label and a field. Fields listed with options are read-only dropdowns (`ttk.Combobox`). All other fields are free-text entries. Every value is stored as a string in `dltsc.z_params_vars[name]` (a `tk.StringVar`).

| Label | Default | Widget / options |
|---|---|---|
| Oscillation Amplitude | `0.300` | Entry |
| Oscillation Frequency | `501000` | Entry |
| Oscillation ON/OFF | `1 - On` | `0 - Off`, `1 - On` |
| Max bandwidth | `10000` | Entry |
| Input Control | `0 - Manual` | `0 - Manual`, `1 - Auto`, `2 - Current Zone` |
| Current Range | `0.010` | Entry |
| Voltage Range | `3` | Entry |
| Omega Suppression | `80` | Entry |
| Filter Harmonic | `1` | `1` to `16` |
| Filter Bandwidth | `2` | `1` to `8` |
| Data Transfer Rate | `60000` | Entry |
| Equivalent Circuit Mode | `0 - 4-Terminal` | `0 - 4-Terminal`, `1 - 2-Terminal` |
| Threshold Input Signal | `59 - TU Output Value` | `59 - TU Output Value`, `58 - Aux Output Overload`, `56 - Aux Input Overload`, `55 - Output Overload`, `54 - Input(I) Overload`, `53 - Input(V) Overload`, `52 - Trigger Out`, `51 - Trigger In`, `50 - DIO`, `3 - Demod Theta`, `2 - Demod R`, `1 - Demod Y`, `0 - Demod X` |
| State Enable Time | `0.006` | Entry |
| State Disable Time | `0.003` | Entry |
| Logic Unit Not | `1 - On` | `0 - Off`, `1 - On` |
| Aux Output Signal | `13 - TU Output Value` | `0 - Demod X`, `1 - Demod Y`, `2 - Demod R`, `3 - Demod Theta`, `11 - TU Filtered Value`, `12 - Manual`, `13 - TU Output Value` |
| Aux Output Scale | `-1` | Entry |
| Aux Output Offset | `-0.5` | Entry |
| Aux Output Lower Limit | `-10` | Entry |
| Aux Output Upper Limit | `0` | Entry |
| Signal Output Add | `1 - True` | `0 - False`, `1 - True` |
| Trigger Source Signal | `36 - Threshold 1` | `0 - Off`, `1 - Osc Phi Demod 2`, `36 - Threshold 1`, `37 - Threshold 2`, `38 - Threshold 3`, `39 - Threshold 4`, `52 - MDS Sync Out` |

`dltsConfig.recast_param_type('impDev', name)` converts each value before it is sent. Dropdown values become the integer before the dash. Filter Harmonic, Filter Bandwidth, and Data Transfer Rate become `int`. All other entries become `float`. The units follow the terminal prompts in `zurichInstruments_Control.ziDevice.set_param_value`: amplitude in V, frequency in Hz, bandwidth in Hz, current range in A, voltage range in V, omega suppression in dB, data transfer rate in Sa/s, State Enable/Disable Time in s, aux output values in V.

**State Enable Time** is the reverse-bias duration and **State Disable Time** is the fill-pulse duration of the MFIA threshold unit. This follows the docstring of `liveDataTab._legacy_run_timing`. The defaults give a 6 ms reverse bias and a 3 ms fill pulse.

Buttons under the group:

- **Connect + Get Params** calls `connect_and_get_params(devType='impedance')`.
- **Apply + Push Params** calls `apply_and_push_params(devType='impedance')`.

### Temperature controller parameters (red, right columns, top)

All seven are free-text entries stored in `dltsc.t_params_vars`.

| Label | Default | Converted to |
|---|---|---|
| Initial Temperature (C) | `25` | float |
| Final Temperature (C) | `25` | float |
| Temperature Step (C) | `5` | float |
| Temperature Ramp (C/min) | `5` | float |
| Stability Delay (s) | `0` | int (a value such as `0.5` raises `ValueError`) |
| Room Temperature (C) | `25` | float |
| Room Ramp (C/min) | `10` | float |

The run uses Initial, Final, and Step to build the temperature grid (`instecTempStage_Control.mK2000B.build_temp_grid`, inclusive of both ends). **Room Temperature (C)** and **Room Ramp (C/min)** set where, and how fast, the stage returns after a run, after a failed step, and when the GUI closes.

Buttons:

- **Connect + Get Params** calls `connect_and_get_params(devType='temperature')`.
- **Apply + Push Params** calls `apply_and_push_params(devType='temperature')`.

### Output parameters (green, right columns, middle)

Stored in `dltsc.d_params_vars`.

| Label | Default | Widget | Meaning |
|---|---|---|---|
| Number of Points (power of 2) | `16` | Entry | Exponent. The run acquires `2 ** value` points per step (`runDlts_Tools._run_single_step`). |
| Number of Reps | `500` | Entry | Passed to `pull_data(numReps=...)`. |
| Data File Format | `TXT` | Read-only dropdown: `TXT`, `HDF5` | `TXT` writes `.txt` files whose content is JSON. `HDF5` writes `.h5` files. |
| Data Root Folder | `''` | **Browse...** button | Root folder for run output. The tab does not display the chosen path; only the log shows it. |

The run writes each step to `<Data Root Folder>\MMDDYY\HHMMSS\` with names such as `p25p0.txt` or `n10p0.h5` (`p`/`n` for the sign, `p` for the decimal point). It writes `runParams.txt` there when the main sequence completes (`runDlts_Tools.dltsRun.init_experiment` and `finish_experiment`).

Buttons:

- **Apply + Push Params** calls `apply_and_push_params(devType='output')`. It sends nothing to any device (see below).
- **Export HDF5 File...** calls `export_h5_file()`.

### Parameter History (purple)

- **Parameter History** label, then a read-only dropdown (`dltsc.param_history_inputField`) listing saved sets as `HH:MM:SS | <source>`, newest first. After each save the newest entry is selected.
- **Save Current** saves the current values of all three groups under the source `Manual Save` and writes `Saved parameter set to history [Manual Save]` to the log.
- **Load Selected** restores the selected set into all three groups and logs `Reloaded parameter set from history [<source>]`. It only changes the GUI fields. It does not push anything to a device.

Connect and Apply actions also save an entry automatically, with sources `Connect/Get impedance`, `Connect/Get temperature`, `Apply/Push impedance`, `Apply/Push temperature`, or `Apply/Push output`. At most 5 entries are kept. History lives in memory only and is lost when the program exits.

### Log

A `tk.Text` box (`dltsc.textbox`, `wrap='none'`, 10 lines high) fills the bottom frame. It is appended to `dltsc.textboxes`, so every `dltsc.log_to_textbox()` call from any module writes here. `DLTSGUI_MainWindow` sets `maxTextLineCount = 10`, so only the 10 most recent lines are kept. The box has no scrollbar.

## Import

```python
import runParamsTab as rpT
```

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `_exportButton` | `ttk.Button` or `None` | The **Export HDF5 File...** button. Set by `construct_runParamsTab()`. `export_h5_file()` disables it during an export. |

Parameter lists (`z_param_list`, `param_options`, `t_param_list`, `d_param_list`) are local variables inside `construct_runParamsTab()`, not module constants. Their contents are the tables above.

`dltsConfig` globals this module reads or writes:

| Name | Access | Meaning |
|---|---|---|
| `root`, `runParamsTab`, `tabControl` | read | Tk root, this tab's frame, the notebook. |
| `z_params_vars`, `t_params_vars`, `d_params_vars` | write | `dict[str, tk.StringVar]` for each group. The keys are the labels. |
| `z_param_inputField`, `t_param_inputField`, `d_param_inputField` | write | `dict[str, widget]` of the entry, combobox, or button for each parameter. |
| `z_params_for_push`, `t_params_for_push` | write | Typed values last synced to the device. `runDlts_Tools` prefers these over the live GUI fields. |
| `impDev` | write | `zurichInstruments_Control.ziDevice` instance. |
| `tempDev` | write | `instecTempStage_Control.mK2000B` instance. |
| `param_history`, `param_history_labels`, `param_history_selection`, `param_history_inputField` | write | Parameter history state and widget. |
| `textbox`, `textboxes` | write | The log text box, and the list `log_to_textbox` writes to. |

## Functions

### connect_and_get_params(devType='impedance')

Creates a device object, connects it, and copies the current GUI values into the device's `params` dict. Despite the button label, it does **not** read any settings from the instrument.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `devType` | str | `'impedance'` | `'impedance'` or `'temperature'`. Any other value does nothing. |

**Returns** `0`.

**Side effects**
- `'impedance'`: `dltsc.impDev = ziC.ziDevice()` (serial `dev32271` by default), then `connect_device()`, which opens a zhinst-toolkit session. Then `time.sleep(1)` and `_sync_param_values_to_device(...)`. The result goes into `dltsc.z_params_for_push`. A history entry `Connect/Get impedance` is saved and the log shows `Connect + Get Params [impedance]: name=value, ...`.
- `'temperature'`: `dltsc.tempDev = tsC.mK2000B()` (port `COM7`), then `connect_temp_controller()`, which opens the serial port. Then `time.sleep(1)` and the sync into `dltsc.t_params_for_push`. The sync also sets `tRamp`, `tStableDelay`, `Troom`, and `roomRamp` on the device. A history entry `Connect/Get temperature` is saved and the log line is written.
- Runs on the Tk thread, so the GUI freezes for the connection time plus 1 s.
- Each click replaces the previous device object without disconnecting it first.

**Called by** the two **Connect + Get Params** buttons.

### apply_and_push_params(devType='impedance')

Copies the current GUI values to the connected device and sends them to the instrument.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `devType` | str | `'impedance'` | `'impedance'`, `'temperature'`, or `'output'`. |

**Returns** `0` for `'output'`, otherwise `None`.

**Side effects**
- `'impedance'`: requires `dltsc.impDev` and `dltsc.impDev.device`. It syncs the values into `impDev.params` and `dltsc.z_params_for_push`. Then it calls `impDev.push_param_to_device(name)` for every parameter, which writes the MFIA nodes through `session.daq_server.set`. It saves history `Apply/Push impedance` and logs the values. Without a device it logs `Apply + Push Params [impedance]: No device connected. ...`.
- `'temperature'`: requires `dltsc.tempDev` and `dltsc.tempDev.dev`. It syncs, then calls `tempDev.load_params(dltsc.t_params_for_push)`. This stores the values, rebuilds `params['Temperature Grid (C)']`, and updates `tRamp`, `tStableDelay`, `Troom`, and `roomRamp`. No serial command is sent here. The controller is commanded only when a run or the close handler moves the stage. It saves history `Apply/Push temperature` and logs the values.
- `'output'`: if **Data Root Folder** is set, it saves history `Apply/Push output` and logs the values. Otherwise it logs `... No data folder selected.` Nothing is sent to any device. The run reads the output fields straight from `dltsc.d_params_vars`.
- The message `Set ... parameters first by Connect + Get Params!` appears only if the sync returns an empty dict.

**Called by** the three **Apply + Push Params** buttons.

### browse_root_folder()

Opens a folder picker (`filedialog.askdirectory()`) and stores the chosen path in `dltsc.d_params_vars['Data Root Folder']`. It then logs a preview of the folder's contents: `Data Root Folder: selected <path> -- already contains N item(s): a, b, ...` (at most 12 names, then `... (M more)`). An empty folder logs `-- empty folder.` and an unreadable one logs `-- cannot list contents: <error>`. Cancelling the dialog changes nothing.

**Returns** `0`.

**Side effects** Opens a Tk dialog, writes the StringVar, and writes to the log.

**Called by** the **Browse...** button in the output group.

### export_h5_file()

Exports one HDF5 step file to a readable tab-separated `.txt` table or to `.json`, using `convert_h5_to_text.export_h5`.

1. An open dialog, **Select an HDF5 step file to export**, filtered to `*.h5`. It starts in the Data Root Folder.
2. A save dialog, **Save readable copy as**. It starts in the `.h5` file's folder with the default name `<stem>_export.txt`. The file types are `.txt` and `.json`. The output format follows the chosen extension: `.json` gives JSON, anything else gives the text table.
3. The button is disabled and the log shows `Exporting <file> to <out>...`.
4. A daemon thread runs `h5txt.export_h5(h5Path, outPath)`. It then uses `root.after(0, ...)` to re-enable the button and log either `Exported <file> -> <output> (TXT, R rows x C channels, S MB).` or `Export of <file> failed: <error>`.

Cancelling either dialog returns without exporting.

**Returns** `0`.

**Side effects** Tk dialogs, one background thread, and one output file. Per `convert_h5_to_text`, a failed export leaves no partial file.

**Called by** the **Export HDF5 File...** button.

### construct_runParamsTab()

Builds the whole tab. It adds `dltsc.runParamsTab` to the notebook as **Input Parameters**, creates the namespaced ttk styles (`Dlts.Blue.TLabel`, `Dlts.Blue.TButton`, and the same for Red, Green, and Purple), creates every widget and Tk variable listed above, initializes the history, and registers the log text box.

**Returns** `0`.

**Side effects** Writes the `dltsConfig` globals listed above and the module global `_exportButton`.

**Called by** `DLTSGUI_MainWindow` at startup.

## Internal helpers

### _format_param_snapshot(param_vars)

Returns `"name=value, name=value, ..."` for a dict of Tk variables. A value without a `.get()` is used as it is. Used in log messages.

### _get_param_values(param_vars)

Returns a plain `{name: value}` dict read from a dict of Tk variables. A value without a `.get()` is copied as it is.

### _apply_param_values(param_vars, values)

Calls `.set(value)` on each Tk variable whose name appears in `values`. Unknown names and `set` errors are ignored.

### _ensure_param_history_state()

Creates `dltsc.param_history` (list), `dltsc.param_history_labels` (list), and `dltsc.param_history_selection` (`tk.StringVar`) if any of them is missing or `None`.

### _capture_current_param_set(source='Manual Save')

Returns one history entry: `{'timestamp': 'HH:MM:SS', 'source': source, 'z_params': {...}, 't_params': {...}, 'd_params': {...}}`, with plain values from the three groups.

### _update_param_history_field()

Rebuilds `dltsc.param_history_labels` as `"<timestamp> | <source>"`, loads the labels into the history dropdown, and selects the first (newest) entry, or clears the selection if the history is empty.

### _save_current_param_set(source='Manual Save', should_log=False)

Inserts a new entry at the front of `dltsc.param_history`, trims the list to 5 entries, and refreshes the dropdown. When `should_log` is true, it writes `Saved parameter set to history [<source>]`.

### _load_selected_param_set()

Finds the selected label in `dltsc.param_history_labels` and writes that entry's values back into all three groups. If nothing is selected, it logs `No parameter history entry selected.` Returns `0`. If two entries have the same label (same second, same source), `list.index` picks the newer one.

### _sync_param_values_to_device(device, param_vars, device_type)

Builds typed values and stores them in `device.params`. For `'impDev'` and `'tempDev'` each value comes from `dltsc.recast_param_type(device_type, name)`, which reads `dltsc.z_params_vars` or `dltsc.t_params_vars` directly rather than the `param_vars` argument. For each name in `device.params` that has a typed value, it calls `device.set_param_value(name, typed_values)`. Returns the typed dict, or `{}` if `device` or `param_vars` is `None`. A non-numeric entry raises `ValueError` from `recast_param_type`. Nothing catches it, so the button callback stops and Tk prints the traceback to the console.

## Notes and limitations

- **Connect + Get Params** does not read settings from either instrument. It pushes the GUI values into the Python device object.
- Connection failures are printed to the console, not written to the log. `ziDevice.connect_device()` and `mK2000B.connect_temp_controller()` catch their own errors with `print(...)`. The tab still logs `Connect + Get Params [...]` and saves a history entry, so a failed connection looks successful in the GUI. `ziDevice.connect_device()` calls `ziDiscovery.find/get` outside its `try`, so an exception there reaches Tk's callback handler and nothing is logged.
- After connecting, a run uses the values from the last **Connect + Get Params** or **Apply + Push Params**. `runDlts_Tools._get_runtime_param_value` prefers `z_params_for_push` and `t_params_for_push`, and the temperature grid comes from `tempDev.params`. Edits made after that without **Apply + Push Params** are ignored for impedance and temperature. The output group is always read live from the GUI.
- The output group's **Apply + Push Params** only logs and saves history. `dltsc.d_params_for_push` is never written.
- **Stability Delay (s)** must be an integer.
- `dltsc.maxTextLineCount = 10`: the log keeps 10 lines and has no scrollbar, so long messages and bursts of messages scroll out quickly.
- The top frame has a fixed 860 × 770 px size. On a smaller window its lower rows are clipped rather than scrolled.
- The chosen Data Root Folder is shown only in the log, not next to the **Browse...** button.
- **Data Root Folder** starts empty. **Run DLTS** with it empty (or relative) stops before anything is created: the log shows `Error: Data Root Folder is not set`, `Choose it with Browse... on the Input Parameters tab, then Apply + Push Params.` and `Error: Failed to initialize the experiment.` (checked in `runDlts_Tools.dltsRun.init_experiment`). Earlier versions wrote such a run to the root of the current drive.
- Device identifiers are fixed in the device classes: MFIA serial `dev32271`, temperature controller on `COM7`.

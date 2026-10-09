# runDlts_Tools

`runDlts_Tools.py` runs a DLTS temperature scan. Its class, `dltsRun`, checks that both instruments are connected and all parameters are set, builds the temperature grid and the output file names, then, for each set-point, ramps the stage, waits for it to stabilize, acquires one triggered MFIA record and writes it to its own file. The same object handles Pause/Resume, Redo and Remove & Retake of selected steps, and the return to room temperature after a run.

GUI callers (all in `liveDataTab.py`, **Live Tools** tab):

- **Run DLTS** (`start_thread` → `start_dlts`): creates `dltsRun()`, stores it in `dltsc.run_dltsInstance`, calls `init_experiment()`, sets every `stepStatus[i] = 'pending'`, then `run_experiment()` on a background thread.
- **Pause** sets `dltsc.run_pauseRequested = True`; **Resume** calls `run_experiment()` again on the same instance.
- **Redo** calls `run_experiment(indices=selected, deleteFirst=False)`; **Remove & Retake** calls `run_experiment(indices=selected, deleteFirst=True)`.
- `_handle_run_status` calls `finish_experiment()` after a completed main sequence, then `_return_to_room_temp_async()` runs `return_to_room_temp()` on a background thread after any completed or failed run (not after a pause or an abort).
- `_refresh_step_listbox` shows `stepStatus` in the step list.
- The window close handler (`DLTSGUI_MainWindow._send_room_ramp`) sets `dltsc.run_abortRequested = True`, which this module checks.

## Import

```python
import runDlts_Tools as rdT
```

The module imports `dltsConfig as dltsc` and works entirely through its globals: `dltsc.impDev`, `dltsc.tempDev`, `dltsc.z_params_vars`, `dltsc.z_params_for_push`, `dltsc.t_params_vars`, `dltsc.t_params_for_push`, `dltsc.d_params_vars`, `dltsc.run_pauseRequested`, `dltsc.run_abortRequested`, `dltsc.recast_param_type`, `dltsc.log_to_textbox`. It writes `dltsc.run_dataFolder`, `dltsc.run_startTime`, `dltsc.run_dataFileNames` and `dltsc.run_outputFileType`.

On import it also calls `warnings.filterwarnings("ignore", category=FutureWarning, module="uncertainties")`.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| (none) | | The module defines no constants. It has one module-level helper, `_get_runtime_param_value` (see Internal helpers). |

## Data folder and file naming

`init_experiment()` builds the paths from **Data Root Folder** and the current local time:

```text
<Data Root Folder>\MMDDYY\HHMMSS\<prefix><|T|>.<ext>
```

- **Data Root Folder** must be set and be a full path (for example `C:\Users\spencer\Desktop\DATA\DLTS`). Otherwise `init_experiment()` logs `Error: Data Root Folder is not set` (or `... is not a full path`) and returns `-1` before creating anything, and the GUI reports `Error: Failed to initialize the experiment.`
- `MMDDYY`: month, day, two-digit year. `HHMMSS`: 24-hour time, both from one `datetime.now()` call. Paths are joined with `os.path.join`, for example `C:\DATA\DLTS\092826\143015\p25p0.h5`.
- `<prefix>`: `n` if `str(T)` contains `-`, otherwise `p`.
- `<|T|>`: `str(abs(T))` with `.` replaced by `p`. Grid values are floats, so 25 °C gives `p25p0`, 27.5 °C gives `p27p5`, -10 °C gives `n10p0`.
- `<ext>` from **Data File Format** (lower-cased): `json` → `.json`, `hdf5` → `.h5`, `txt` → `.txt`, anything else → `.json`.
- Run parameters go to `<dataFolder>\runParams.txt` (JSON content).

The GUI offers only `TXT` and `HDF5`. `TXT` files contain JSON (written by `writeDataJson`), not a text table.

## Step status values

`stepStatus` maps a `tempGrid` index to one of:

| Value | Set by | Meaning |
|---|---|---|
| `'pending'` | the caller (`liveDataTab.start_dlts`, `hw_run.py`) after `init_experiment()` | Not yet run. `dltsRun` never sets it. |
| `'running'` | `_run_single_step` | Ramping, stabilizing or acquiring. |
| `'done'` | `_run_single_step` | File written. |
| `'failed'` | `run_experiment` | An exception occurred during this step. |
| `'paused'` | `run_experiment` | The main sequence paused before this step; Resume starts here. |
| `'aborted'` | `_run_single_step` | `dltsc.run_abortRequested` was set after the ramp or during acquisition; no file written. |

The unused global `dltsc.run_stepStatus` is not this dict; the GUI reads `dltsc.run_dltsInstance.stepStatus`.

## class dltsRun

### Attributes

| Name | Type | Default | Meaning |
|---|---|---|---|
| `impDevice` | `ziC.ziDevice` or `None` | `None` | Set from `dltsc.impDev` by `check_device_connections()` when both instruments are connected. |
| `tempDevice` | `tsC.mK2000B` or `None` | `None` | Set from `dltsc.tempDev` at the same time. |
| `impDeviceParams` | `dict` or `None` | `None` | MFIA parameter values found by `check_device_parameters('impDev')`. |
| `tempDeviceParams` | `dict` or `None` | `None` | Temperature parameter values. |
| `outputParams` | `dict` or `None` | `None` | Output parameters (`Number of Points (power of 2)`, `Number of Reps`, `Data File Format`, `Data Root Folder`). |
| `dataFolder` | `str` or `None` | `None` | Run folder, ends with `\`. |
| `runOutputFileType` | `str` or `None` | `None` | Lower-cased Data File Format. |
| `dataFileNames` | `list[str]` or `None` | `None` | One path per `tempGrid` index. |
| `paramsFileName` | `str` or `None` | `None` | `dataFolder + 'runParams.txt'`. |
| `currentStepIndex` | `int` | `0` | Next index the main sequence runs; the resume point. |
| `stepStatus` | `dict[int, str]` | `{}` | See "Step status values". |
| `_everPulled` | `bool` | `False` | `True` after the first acquisition on this instance. Before every later acquisition the MFIA gets a factory reset. |

### __init__(self, fName=None)

Creates an empty run object. `fName` is accepted and ignored.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `fName` | any | `None` | Unused. |

**Returns** a new `dltsRun`.

**Side effects** None.

**Example**

```python
run = rdT.dltsRun()
```

### check_device_connections(self)

Reports which instruments exist in `dltsConfig`. When both `dltsc.impDev` and `dltsc.tempDev` are not `None`, it copies them into `impDevice` and `tempDevice`.

No parameters.

**Returns** `[imp, temp]`: for each, `1` connected (not `None`), `0` `None`, `-1` attribute missing from `dltsConfig` (cannot happen with the current `dltsConfig`, which defines both).

**Side effects** Prints one status line with `print()` (not the GUI log). Sets `impDevice`/`tempDevice` only when both are present. It checks for `None` only; it does not check that the connections work.

**Example**

```python
print(run.check_device_connections())   # [1, 1]
```

### check_device_parameters(self, device='impDev')

Collects the parameter values for one group and counts the missing ones.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `device` | `str` | `'impDev'` | `'impDev'`: keys of `dltsc.z_params_vars`, values preferring `dltsc.z_params_for_push`. `'tempDev'`: keys of `dltsc.t_params_vars`, values preferring `dltsc.t_params_for_push`. `'output'`: keys and values of `dltsc.d_params_vars`. |

A value is "missing" when it is `None`. An empty string (for example no Data Root Folder) counts as set here; `init_experiment()` then rejects an empty or relative Data Root Folder.

**Returns** the number of missing values (`int`), or `None` for any other `device` string.

**Side effects** Sets `impDeviceParams`, `tempDeviceParams` or `outputParams`. Logs `Error: Parameter <name> does not exist.` for each missing value.

**Example**

```python
missing = run.check_device_parameters('output')
```

### check_setup(self)

Runs `check_device_connections()` and the three `check_device_parameters()` calls.

No parameters.

**Returns** `2` when both instruments are present and no value is missing; `0` or `-2` otherwise (+1/-1 for devices, +1/-1 for parameters).

**Side effects** Logs `All devices are connected.` or `Error: One or more devices are not connected.`, and `All device parameters are set.` or `Error: One or more device parameters are not set.`. Sets the `*Params` attributes and the device references.

**Example**

```python
if run.check_setup() < 2:
    raise RuntimeError('setup incomplete')
```

### init_experiment(self)

Prepares a new run: checks the setup, builds the temperature grid, creates the data folders and fixes every file name.

No parameters.

**Returns** `0` on success; `-1` if `check_setup()` returned less than 2, if **Data Root Folder** is empty or not an absolute path, or if the run folder cannot be created.

**Side effects**

- Calls `tempDevice.set_temp_grid()`, which rebuilds `tempGrid` from `tempDevice.params` (needs `tempDevice.dev` set).
- Checks **Data Root Folder** (stripped of spaces): empty or relative logs an error plus `Choose it with Browse... on the Input Parameters tab, then Apply + Push Params.` and returns `-1` without creating anything.
- Creates `<root>\MMDDYY\HHMMSS\` with `os.makedirs(exist_ok=True)`; an `OSError` (no permission, missing drive) logs `Error: cannot create the run folder ...` and returns `-1`.
- Sets `runOutputFileType`, `dataFolder`, `dataFileNames`, `paramsFileName`.
- Publishes `dltsc.run_dataFolder`, `dltsc.run_startTime`, `dltsc.run_dataFileNames` (a copy of the list) and `dltsc.run_outputFileType`; the live-data watcher polls `run_dataFileNames`.
- Logs `1. Hardware initialized.`, `2. Temperature grid set.`, `3. Output file names set.`
- Does not reset `currentStepIndex`, `stepStatus` or `_everPulled`; use a new `dltsRun` for a new run (the GUI does).

**Example**

```python
if run.init_experiment() < 0:
    raise RuntimeError('init_experiment failed')
print(run.dataFolder, run.dataFileNames)
```

### run_experiment(self, indices=None, deleteFirst=False)

Runs temperature steps and returns why it stopped.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `indices` | iterable of `int` or `None` | `None` | `None`: main sequence, from `currentStepIndex` to the end of `tempGrid`. A list: only those indices, sorted ascending (fewer thermal cycles), without touching `currentStepIndex` (Redo / Remove & Retake). |
| `deleteFirst` | `bool` | `False` | `True` ("Remove & Retake"): delete each step's existing file before re-acquiring. `False` ("Redo"): overwrite in place. |

Before each step it checks `dltsc.run_abortRequested` (returns `'aborted'`). In the main sequence only, it then checks `dltsc.run_pauseRequested`: if set, it stores the index in `currentStepIndex`, marks it `'paused'`, logs `Run paused before T = ... C (step i/N).` and returns `'paused'`. Devices stay connected and the grid is untouched, so calling `run_experiment()` again resumes. After each completed main-sequence step, `currentStepIndex = i + 1`.

**Returns** `'completed'`, `'paused'`, `'aborted'` or `'error'`. An exception from any step marks that step `'failed'`, logs `Error during step T = ... C: <exception>` and returns `'error'`.

**Side effects** Everything `_run_single_step` does, for each step. Blocks for the whole run; the GUI runs it on a daemon thread. It does not clear `dltsc.run_pauseRequested`; the caller must set it back to `False` before resuming (the GUI does). It does not return the stage to room temperature.

**Example**

```python
# Stage heats/cools and the sample is biased for every step.
status = run.run_experiment()                               # main sequence
status = run.run_experiment(indices=[4], deleteFirst=False) # Redo step 5
status = run.run_experiment(indices=[3], deleteFirst=True)  # Remove & Retake step 4
```

### finish_experiment(self)

Writes the run parameters and logs the end of the run.

No parameters.

**Returns** `0`.

**Side effects** Writes `runParams.txt` (JSON: MFIA, temperature and output parameters merged) with `impDevice.writeDataJson()`, if `impDevice` and `paramsFileName` are set. Logs `Run complete: devices remain connected for the next run until the GUI is closed.` It does not move the stage or disconnect anything.

**Example**

```python
if run.run_experiment() == 'completed':
    run.finish_experiment()
```

### return_to_room_temp(self)

Ramps the stage to `tempDevice.Troom` at `tempDevice.roomRamp` and waits (`go_to_room_temp(Tr, ramp)`, 0.5 °C tolerance, deadline = expected ramp time + 900 s).

No parameters.

**Returns** `0` reached, `1` gave up waiting (stage still ramping or holding at room temperature), `-1` not connected, no `tempDevice`, or an exception.

**Side effects** One ramp command, then a `read_temp()` every 5 s. Blocks for minutes; call it from a background thread in a GUI. Logs `Returning stage to room temperature: ...` and the outcome.

**Example**

```python
# The stage heats or cools to Room Temperature (C).
status = run.return_to_room_temp()
```

## Internal helpers

- `_get_runtime_param_value(param_vars, param_name, fallback_bucket=None)` (module level): returns `fallback_bucket[param_name]` if present; else `param_vars[param_name].get()`, or the raw entry if it has no `.get()`; else `None` if the name is missing.
- `dltsRun._read_stage_temp(self)`: `tempDevice.read_temp()`, or `None` on any exception. Used only for the HDF5 `stage_temperature_C` attribute.
- `dltsRun._current_run_params(self)`: `{**impDeviceParams, **tempDeviceParams, **outputParams}` when all three are set, otherwise `{}`. Written to `runParams.txt` and to each HDF5 file's `run_params` attribute.
- `dltsRun._run_single_step(self, i, deleteFirst=False)`: acquires and writes step `i`. In order: if `deleteFirst`, deletes `dataFileNames[i]` (logs a warning if that fails); marks `'running'`; `tempDevice.go_to_temp(tempGrid[i], tRamp, tStableDelay)`; returns `'aborted'` if `dltsc.run_abortRequested`; sleeps 1 s; calls `impDevice.device.factory_reset()` if `_everPulled`; `impDevice.reload_params()`; reads `numPoints = 2 ** recast_param_type('output', 'Number of Points (power of 2)')` and `numReps = recast_param_type('output', 'Number of Reps')`; for `txt`/`json`/`hdf5` reads the stage temperature, runs `pull_data(plot=False, trigger=True, numPoints, numReps)`, reads the stage temperature again and averages the readings that succeeded; returns `'aborted'` (and discards the data) if `dltsc.run_abortRequested` was set during acquisition; writes with `writeDataH5(data, fName, setpoint_C=tempGrid[i], stage_temperature_C=avg, runParams=_current_run_params())` for `hdf5` or `writeDataJson(data, fName)` otherwise; sets `_everPulled = True`, marks `'done'`, returns `0`.

## Standalone use

Safety: this script heats and cools the stage and biases the mounted sample for every step. Only run it when the sample and temperature range are safe.

The working pattern is `benchmarks/hardware/hw_common.py` and `hw_run.py`. `dltsRun` reads its inputs from `dltsConfig`, so a script must fill the same globals the Input Parameters tab fills:

- `dltsc.z_params_vars`, `dltsc.t_params_vars`, `dltsc.d_params_vars`: dicts of objects with `.get()` holding the GUI's **string labels** (`'1 - On'`, `'36 - Threshold 1'`, ...). `recast_param_type()` calls `.get()` on them, so plain values do not work for `d_params_vars`.
- `dltsc.z_params_for_push`, `dltsc.t_params_for_push`: the numeric values, built by `runParamsTab._sync_param_values_to_device()` exactly as the **Connect + Get Params** / **Apply + Push Params** buttons do.

```python
import sys, os
REPO = r'C:\Users\spencer\Documents\GitHub\DltsOnHallProbeSetup'
sys.path.insert(0, REPO)
import matplotlib; matplotlib.use('Agg')
import dltsConfig as dltsc
import runParamsTab as rpT
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import runDlts_Tools as rdT


class Var:
    """tk.StringVar stand-in."""
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


# Input Parameters tab defaults, as the tab stores them (runParamsTab.construct_runParamsTab).
Z = [('Oscillation Amplitude', '0.300'), ('Oscillation Frequency', '501000'),
     ('Oscillation ON/OFF', '1 - On'), ('Max bandwidth', '10000'), ('Input Control', '0 - Manual'),
     ('Current Range', '0.010'), ('Voltage Range', '3'), ('Omega Suppression', '80'),
     ('Filter Harmonic', '1'), ('Filter Bandwidth', '2'), ('Data Transfer Rate', '60000'),
     ('Equivalent Circuit Mode', '0 - 4-Terminal'), ('Threshold Input Signal', '59 - TU Output Value'),
     ('State Enable Time', '0.006'), ('State Disable Time', '0.003'), ('Logic Unit Not', '1 - On'),
     ('Aux Output Signal', '13 - TU Output Value'), ('Aux Output Scale', '-1'),
     ('Aux Output Offset', '-0.5'), ('Aux Output Lower Limit', '-10'), ('Aux Output Upper Limit', '0'),
     ('Signal Output Add', '1 - True'), ('Trigger Source Signal', '36 - Threshold 1')]
T = [('Initial Temperature (C)', '25'), ('Final Temperature (C)', '40'),
     ('Temperature Step (C)', '5'), ('Temperature Ramp (C/min)', '5'),
     ('Stability Delay (s)', '0'), ('Room Temperature (C)', '25'), ('Room Ramp (C/min)', '10')]
D = [('Number of Points (power of 2)', 16), ('Number of Reps', 100),
     ('Data File Format', 'HDF5'), ('Data Root Folder', r'C:\DATA\DLTS')]

dltsc.init()                     # run-control flags False, empty dicts; call it before filling the dicts
                                 # (no GUI textbox, so log_to_textbox() prints to the console)
dltsc.z_params_vars = {k: Var(v) for k, v in Z}
dltsc.t_params_vars = {k: Var(v) for k, v in T}
dltsc.d_params_vars = {k: Var(v) for k, v in D}

# Connect + push, as the Input Parameters buttons do.
dltsc.tempDev = tsC.mK2000B()
dltsc.tempDev.connect_temp_controller()
if not dltsc.tempDev.state:
    raise SystemExit('temperature controller connection failed')
dltsc.t_params_for_push = rpT._sync_param_values_to_device(dltsc.tempDev, dltsc.t_params_vars, 'tempDev')
dltsc.tempDev.load_params(dltsc.t_params_for_push)

dltsc.impDev = ziC.ziDevice()
dltsc.impDev.connect_device()
if dltsc.impDev.device is None:
    dltsc.tempDev.disconnect_temp_controller(stopControl=False)
    raise SystemExit('MFIA connection failed')
dltsc.z_params_for_push = rpT._sync_param_values_to_device(dltsc.impDev, dltsc.z_params_vars, 'impDev')
for pName in dltsc.impDev.params:
    dltsc.impDev.push_param_to_device(pName)

roomStatus = None
try:
    run = rdT.dltsRun()
    dltsc.run_dltsInstance = run
    if run.init_experiment() < 0:
        raise RuntimeError('init_experiment failed')
    for i in range(len(run.tempDevice.tempGrid)):
        run.stepStatus[i] = 'pending'

    status = run.run_experiment()          # 'completed' / 'paused' / 'error' / 'aborted'
    print('main sequence:', status, run.stepStatus)
    if status == 'completed':
        run.finish_experiment()            # writes runParams.txt
        # Optional: redo the second step in place.
        # run.run_experiment(indices=[1], deleteFirst=False)
    roomStatus = run.return_to_room_temp() # 0 arrived, 1 gave up, -1 failed
finally:
    # Send TEMPerature:STOP only if the stage is at room temperature;
    # otherwise the controller keeps ramping there on its own.
    dltsc.tempDev.disconnect_temp_controller(stopControl=(roomStatus == 0))
    dltsc.impDev.disconnect_device()
```

Pause, resume and abort from another thread:

```python
dltsc.run_pauseRequested = True       # run_experiment() returns 'paused' before the next step
# ... later, in the run thread:
dltsc.run_pauseRequested = False
status = run.run_experiment()         # continues from run.currentStepIndex

# Abort (what the GUI close handler does): set both flags.
dltsc.run_abortRequested = True
dltsc.tempDev.abort()                 # ends a go_to_temp() wait
# Before any further motion with the same objects:
dltsc.tempDev._aborted = False
dltsc.run_abortRequested = False
```

`hw_run.py` adds a watchdog thread that sets both abort flags when one step exceeds a time limit, because `go_to_temp()` has no overall time limit on stabilizing. (A silent controller is a separate case: `read_temp()` raises `TimeoutError` after about 4 s, and the step fails.)

## Notes and limitations

- **Data File Format** `TXT` writes JSON into `.txt` files. A format string other than `txt`, `json` or `hdf5` (not reachable from the GUI) gets a `.json` extension in `init_experiment()`, but `_run_single_step` then acquires nothing, writes nothing and still marks the step `'done'`.
- An empty or relative **Data Root Folder** stops the run in `init_experiment()` (earlier versions wrote the run to `\MMDDYY\HHMMSS\` at the root of the current drive, with a doubled backslash in the path). `check_setup()` itself still accepts an empty value. Tested in `tests/test_run_folder_and_serial.py`.
- `check_device_connections()` prints with `print()`, not `log_to_textbox()`, so its messages do not reach the GUI log.
- `check_device_parameters()` takes the MFIA and temperature keys from `*_params_vars`, not from `*_params_for_push`. With empty `*_params_vars` the check passes and the MFIA/temperature parameters are missing from `runParams.txt` and the HDF5 `run_params` attribute.
- `_run_single_step` ignores `go_to_temp()`'s return value and checks only `dltsc.run_abortRequested`. `tempDev.abort()` alone does not stop a run; the step acquires at the current stage temperature.
- `_run_single_step` factory-resets the MFIA before every acquisition except the first on the instance, then `reload_params()` re-sends parameters from `dltsc.z_params_for_push`. Parameters not in that dict (for example `imps/0/model`) return to factory values.
- `run_experiment()` catches `Exception` only. `KeyboardInterrupt` leaves the step marked `'running'`.
- An out-of-range index in `indices` raises `IndexError` inside the `except` handler itself (the log line indexes `tempGrid[i]`), so `run_experiment()` raises instead of returning `'error'`.
- `run_experiment(indices=[])` returns `'completed'` without doing anything.
- `init_experiment()` does not reset `currentStepIndex`, `stepStatus` or `_everPulled`. `run_experiment()` on a completed instance runs nothing and returns `'completed'`, even after a new `init_experiment()`.
- `finish_experiment()` writes `runParams.txt` with JSON content; `Temperature Grid (C)` is not included because it is not a `t_params_vars` key.
- `__init__`'s `fName` argument is unused.

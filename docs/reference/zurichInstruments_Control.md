# zurichInstruments_Control

`zurichInstruments_Control.py` drives the Zurich Instruments MFIA impedance analyzer (serial `dev32271`) through the `zhinst.core` and `zhinst.toolkit` packages. Its single class, `ziDevice`, connects to the LabOne data server, pushes the 23 MFIA settings shown on the **Input Parameters** tab, acquires one capacitance transient record per temperature step, and writes that record to disk as HDF5 or JSON. It also works without the GUI: `DEFAULT_PARAMS` and `ziDevice.configure()` set and push every setting from a script.

GUI callers:

- **Input Parameters** tab (`runParamsTab.connect_and_get_params`, `runParamsTab.apply_and_push_params`): creates `dltsc.impDev = ziDevice()`, calls `connect_device()`, `set_param_value()` and `push_param_to_device()`.
- **Live Tools** tab, Run DLTS (`runDlts_Tools.dltsRun._run_single_step`): calls `reload_params()`, `pull_data(plot=False, trigger=True, ...)`, `writeDataH5()` or `writeDataJson()` for each temperature step, and `device.factory_reset()` before every step except the first.
- `runDlts_Tools.dltsRun.finish_experiment` calls `writeDataJson()` to write `runParams.txt`.
- Window close (`DLTSGUI_MainWindow._finish_close`): calls `disconnect_device()`.
- `convert_json_to_h5.py` calls `writeDataH5()` with `acquired_at` and `extraAttrs` to convert older files.

## Import

```python
import zurichInstruments_Control as ziC
```

The module imports `dltsConfig as dltsc` itself. It reads `dltsc.z_params_for_push`, `dltsc.z_params_vars` and `dltsc.log_to_textbox`.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `DEFAULT_PARAMS` | `dict`, 23 entries (table below) | The Input Parameters tab's MFIA defaults, as the numeric values pushed to the device. `ziDevice.configure()` starts from these. |
| `ziDevice.H5_FORMAT_VERSION` | `int`, `1` (class attribute of `ziDevice`, not a module global) | Written to the `format_version` root attribute of every HDF5 file. Bumped when the on-disk layout of `writeDataH5()` changes. |

### MFIA parameters

Every key of `ziDevice.params` and `DEFAULT_PARAMS`, in push order. All node paths are hard-coded with the serial `dev32271`. "Allowed values" come from the terminal prompts in `set_param_value()` and the dropdown lists in `runParamsTab.construct_runParamsTab()`. The GUI label is the string the Input Parameters tab stores; `dltsConfig.recast_param_type()` turns it into the number in the "Default" column.

| Parameter | Device node it is pushed to | Default (`DEFAULT_PARAMS`) | Allowed values / meaning |
|---|---|---|---|
| `Oscillation Amplitude` | `/dev32271/imps/0/output/amplitude` | `0.3` | Test-signal amplitude in V (free entry). |
| `Oscillation Frequency` | `/dev32271/imps/0/freq` | `501000.0` | Test-signal frequency in Hz (free entry). |
| `Oscillation ON/OFF` | `/dev32271/imps/0/auto/output` | `1` | `0` Off, `1` On (GUI: `0 - Off`, `1 - On`). The node is the impedance module's `auto/output` switch, not `imps/0/output/on`; the code never writes `output/on`. Check the LabOne node documentation for what `auto/output` controls on your firmware. |
| `Max bandwidth` | `/dev32271/imps/0/maxbandwidth` | `10000.0` | Maximum demodulator bandwidth in Hz (free entry). |
| `Input Control` | `/dev32271/imps/0/auto/inputrange` | `0` | `0` Manual, `1` Auto, `2` Current Zone (GUI: `0 - Manual`, `1 - Auto`, `2 - Current Zone`). |
| `Current Range` | `/dev32271/imps/0/current/range` | `0.01` | Current input range in A (free entry). Used when Input Control is Manual. |
| `Voltage Range` | `/dev32271/imps/0/voltage/range` | `3.0` | Voltage input range in V (free entry). |
| `Omega Suppression` | `/dev32271/imps/0/omegasuppression` | `80.0` | Omega suppression in dB (free entry). |
| `Filter Harmonic` | `/dev32271/imps/0/demod/harmonic` | `1` | Demodulator harmonic. GUI dropdown `1` to `16`. |
| `Filter Bandwidth` | `/dev32271/imps/0/demod/order` | `2` | Demodulator filter **order**, not a bandwidth (the prompt says "Filter Order Bandwidth"). GUI dropdown `1` to `8`. |
| `Data Transfer Rate` | `/dev32271/imps/0/demod/rate` | `60000` | Demodulator sample rate in Sa/s (free entry). |
| `Equivalent Circuit Mode` | `/dev32271/imps/0/mode` | `0` | `0` 4-Terminal, `1` 2-Terminal (GUI: `0 - 4-Terminal`, `1 - 2-Terminal`). |
| `Threshold Input Signal` | `/dev32271/tu/thresholds/0/input` | `59` | Input of threshold unit 0: `59` TU Output Value, `58` Aux Output Overload, `56` Aux Input Overload, `55` Output Overload, `54` Input(I) Overload, `53` Input(V) Overload, `52` Trigger Out, `51` Trigger In, `50` DIO, `3` Demod Theta, `2` Demod R, `1` Demod Y, `0` Demod X. |
| `State Enable Time` | `/dev32271/tu/thresholds/0/activationtime` | `0.006` | Threshold activation time in s (free entry). |
| `State Disable Time` | `/dev32271/tu/thresholds/0/deactivationtime` | `0.003` | Threshold deactivation time in s (free entry). |
| `Logic Unit Not` | `/dev32271/tu/logicunits/0/inputs/0/not` | `1` | Invert input 0 of logic unit 0: `0` Off, `1` On (GUI: `0 - Off`, `1 - On`). |
| `Aux Output Signal` | `/dev32271/auxouts/0/outputselect` | `13` | Signal on Aux Output 1: `0` Demod X, `1` Demod Y, `2` Demod R, `3` Demod Theta, `11` TU Filtered Value, `12` Manual, `13` TU Output Value. |
| `Aux Output Scale` | `/dev32271/auxouts/0/scale` | `-1.0` | Aux output scale (prompt unit: V). |
| `Aux Output Offset` | `/dev32271/auxouts/0/offset` | `-0.5` | Aux output offset in V. |
| `Aux Output Lower Limit` | `/dev32271/auxouts/0/limitlower` | `-10.0` | Aux output lower limit in V. |
| `Aux Output Upper Limit` | `/dev32271/auxouts/0/limitupper` | `0.0` | Aux output upper limit in V. |
| `Signal Output Add` | `/dev32271/sigouts/0/add` | `1` | Add the Aux output to Signal Output 1: `0` False, `1` True (GUI: `0 - False`, `1 - True`). |
| `Trigger Source Signal` | `/dev32271/triggers/out/0/source` | `36` | Source of Trigger Out 1: `0` Off, `1` Osc Phi Demod 2, `36` Threshold 1, `37` Threshold 2, `38` Threshold 3, `39` Threshold 4, `52` MDS Sync Out. |

With the defaults, threshold unit 0 watches its own output (59), the logic unit inverts it, and the TU output (13) drives Aux Output 1 with scale -1 and offset -0.5 V, limited to -10 V ... 0 V. `Signal Output Add = 1` adds that aux voltage to the signal output, so the sample sees a pulsed DC bias. Trigger Out 1 follows Threshold 1, and `pull_data(trigger=True)` triggers on it. The enable/disable times set the two pulse durations. This reading of the defaults follows from the node names; the code has no comment that states it.

## class ziDevice

One MFIA connection plus the parameter values last set for it.

### Attributes

| Name | Type | Default | Meaning |
|---|---|---|---|
| `devSerial` | `str` | `'dev32271'` | Serial used by `connect_device()` and `disconnect_device()`. Every other method uses the hard-coded `/dev32271/` path instead. |
| `session` | `zhinst.toolkit.Session` or `None` | `None` | Connection to the LabOne data server. |
| `device` | toolkit device object or `None` | `None` | The connected MFIA. `None` means not connected. |
| `rm` | `None` | `None` | Unused. |
| `params` | `dict` | the 23 names above, all `0` | Values the next `push_param_to_device()` will write. |
| `configuredParams` | `dict` or `None` | `None` | The full parameter set of the last `configure()` call; `set_param_value()` falls back to it when there is no GUI. |
| `H5_FORMAT_VERSION` | `int` (class attribute) | `1` | See above. |

### __init__(self, devSerial = None)

Creates an unconnected device object. No hardware is contacted.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `devSerial` | `str` or `None` | `None` | Device serial; `None` means `'dev32271'`. |

**Returns** a new `ziDevice`.

**Side effects** None.

**Example**

```python
mfia = ziC.ziDevice()          # dev32271
```

### connect_device(self)

Finds the device with `zhinst.core.ziDiscovery().find(devSerial)`, reads its data-server address and port, opens a `zhinst.toolkit.Session(..., allow_version_mismatch=True)` and calls `session.connect_device(devSerial)`.

No parameters.

**Returns** `0` in every case. Check `self.device is not None` to know whether it worked.

**Side effects** Opens a network session to the LabOne data server. If the session or device connection fails, it prints `Error connecting to device: ...` and leaves `session` and `device` at `None`. The discovery calls are outside the `try` block, so a device that discovery cannot find raises an exception from `zhinst.core` instead of printing. No settings are changed on the instrument.

**Example**

```python
mfia = ziC.ziDevice()
mfia.connect_device()
if mfia.device is None:
    raise RuntimeError('MFIA connection failed')
```

### disconnect_device(self)

Drops the device object, calls `session.disconnect_device(devSerial)`, and calls `session.close()` if the session has one (toolkit 1.3.0 sessions do not). Every step is wrapped in `try/except: pass`.

No parameters.

**Returns** `0`.

**Side effects** Sets `session` and `device` to `None`. It does not change any instrument setting: the test signal, the aux output and the added bias stay as last configured.

**Example**

```python
mfia.disconnect_device()
```

### set_param_value(self, pName='Oscillation Frequency', valueDict=None)

Stores one parameter value in `self.params`. It does not talk to the device.

The value source, in order:

1. `valueDict`, if given: `self.params[pName] = valueDict.get(pName)` (a missing key stores `None`).
2. If `valueDict` is `None` and `pName` is in `dltsc.z_params_for_push`: that dict.
3. Otherwise, if `dltsc.z_params_vars` is non-empty: a dict of `var.get()` (or the raw value) for each entry. These are the GUI's label strings such as `'1 - On'`, not numbers.
4. Otherwise, if `configure()` has been called: `self.configuredParams` (the values it set).
5. Otherwise: an interactive `input()` prompt on the console for `pName`. An empty answer stores the prompt's default (the same values as `DEFAULT_PARAMS`). The typed text is converted with `float()` or `int()`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `pName` | `str` | `'Oscillation Frequency'` | Parameter name from the table above. |
| `valueDict` | `dict` or `None` | `None` | `{name: value}` source. |

**Returns** `0`.

**Side effects** Writes `self.params[pName]`. Unknown names print `Unknown Parameter <name>!!!` (prompt path) or `Parameter <name> not found!` (dict path). Path 4 blocks on console input.

**Example**

```python
mfia.set_param_value('State Enable Time', {'State Enable Time': 0.5})
```

### push_param_to_device(self, pName='Oscillation Frequency')

Writes `self.params[pName]` to its node (table above) with `session.daq_server.set(path, value)`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `pName` | `str` | `'Oscillation Frequency'` | Parameter to push. |

**Returns** `0`.

**Side effects** One `set` on the instrument. Needs a connected `session`; with `session = None` it raises `AttributeError`. Unknown names print `Unknown Parameter!!!`. A value of `None` is passed to `set` unchanged.

**Example**

```python
mfia.params['Oscillation Frequency'] = 1.0e6
mfia.push_param_to_device('Oscillation Frequency')
```

### check_param(self, pName='Oscillation Frequency')

Reads the whole node tree with `session.daq_server.get('*')` and compares the parameter's node value with `self.params[pName]` using `np.isclose(..., rtol=1e-03)`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `pName` | `str` | `'Oscillation Frequency'` | Parameter to check. |

**Returns** `numpy.bool_` (`True` when the device value is within 0.1 % of the stored value), or `False` for an unknown name.

**Side effects** One full-tree `get('*')` per call. Prints `Unknown Parameter!!!` for an unknown name.

**Example**

```python
ok = mfia.check_param('Data Transfer Rate')
```

### configure(self, values=None, push=True)

Sets every parameter without the GUI. It starts from `DEFAULT_PARAMS`, overrides it with `values`, stores all 23 values with `set_param_value(pName, merged)`, and, when `push` is true, pushes all 23 to the device in the order of the table.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `values` | `dict` or `None` | `None` | `{parameter name: number}` overrides. Use numbers, not GUI label strings. |
| `push` | `bool` | `True` | Push to the device after setting. `False` only fills `self.params`. |

**Returns** a copy of `self.params` (`dict`), the values now in effect.

**Side effects**

- Raises `KeyError('unknown MFIA parameter(s): [...]')` before changing anything if `values` holds a name not in `self.params`.
- With `push=True` and no session, raises `RuntimeError("MFIA not connected: call connect_device() first")`. `self.params` is already updated at that point.
- With `push=True`: 23 `daq_server.set` calls.
- Stores the merged values in `self.configuredParams`, so a later `reload_params()` (for example after `device.factory_reset()`) re-sends these values instead of prompting on the console when there is no GUI. It does not write `dltsc.z_params_for_push`; GUI values, when present, still take priority.

**Example**

```python
mfia.connect_device()
params = mfia.configure({'State Enable Time': 0.5, 'State Disable Time': 0.001})
offline = ziC.ziDevice().configure(push=False)   # no hardware needed
```

### load_params(self)

Calls `set_param_value(pName)` with no dict, then `push_param_to_device(pName)`, for every parameter.

No parameters.

**Returns** `0`.

**Side effects** 23 `set` calls. Values come from `dltsc.z_params_for_push`, else `dltsc.z_params_vars`, else console prompts (see `set_param_value`). Nothing in the codebase calls it.

**Example**

```python
import dltsConfig as dltsc
dltsc.z_params_for_push = dict(ziC.DEFAULT_PARAMS)
mfia.load_params()
```

### reload_params(self)

For every parameter, calls `check_param(pName)`. When the device value differs, it calls `set_param_value(pName)` with no dict and pushes the result.

No parameters.

**Returns** `0`.

**Side effects** 23 full-tree reads plus one `set` per mismatch. A mismatched value is re-read from `dltsc.z_params_for_push` (or `z_params_vars`, or a console prompt), not from `self.params`. `dltsRun._run_single_step` calls it before every acquisition, right after `device.factory_reset()`, so after a factory reset every parameter that differs from the factory value is re-sent.

**Example**

```python
mfia.device.factory_reset()
mfia.reload_params()
```

### pull_data(self, plot=True, trigger=False, numPoints=1024, numReps=1)

Acquires one record from the MFIA and returns it as a dict of NumPy arrays.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `plot` | `bool` | `True` | Show a 2×2 matplotlib figure of the channels (`plt.show()`). |
| `trigger` | `bool` | `False` | `True`: triggered, averaged acquisition with the DAQ module (the path used by DLTS runs). `False`: short untriggered poll. |
| `numPoints` | `int` | `1024` | Triggered path only: grid columns (samples per record). The run uses `2**N` from the Input Parameters tab. |
| `numReps` | `int` | `1` | Triggered path only: grid repetitions averaged into the record. |

#### Triggered path (`trigger=True`)

The managed DAQ module (`session.modules.daq`, one instance reused for the whole session) is configured as:

| Setting | Value | Meaning |
|---|---|---|
| `type` | `6` | Hardware trigger. |
| `triggernode` | `/dev32271/demods/0/sample.TrigOut1` | Trigger on Trigger Out 1 (set by `Trigger Source Signal`). |
| `clearhistory` | `1` | Clear previous records. |
| `bandwidth` | `0` | DAQ module low-pass bandwidth; the code gives no comment on this value. |
| `grid.mode` | `4` | Exact (on-grid) sampling. |
| `grid.cols` | `numPoints` | Samples per record. |
| `grid.repetitions` | `numReps` | Records averaged. |
| `endless` | `0` | Single acquisition. |

It enables `imps[0]`, subscribes to `demods/0/sample.AuxIn0.avg`, `demods/0/sample.R.avg`, `imps/0/sample.Param0.avg` and `imps/0/sample.Param1.avg`, calls `daq_module.forcetrigger()`, waits 1 s, calls `execute()`, waits 0.5 s, then polls `progress()` every 0.05 s until it reaches 1.0. After 60 s it logs `Warning: DAQ acquisition did not complete within 60s; proceeding with whatever data is available.` through `dltsc.log_to_textbox` and continues. It then waits 1 s, calls `read()`, waits 5 s and unsubscribes everything.

Fixed sleeps: 1 + 0.5 + 1 + 5 = 7.5 s per call, on top of the acquisition itself (about `numReps` trigger periods). The `sample.R.avg` subscription is read back but not returned.

Channels returned (each a 1-D array of `numPoints` values, the averaged grid row `value[0]` of the first burst):

| Key | Content | Units |
|---|---|---|
| `tickStampImps` | Time axis of the `param1` record (`DAQResult.time`: grid timestamps minus the first, divided by 60 MHz). Floats, despite the name. | s |
| `tickStampDemods` | Same array as `tickStampImps` (also taken from `param1`, not from the demodulator node). | s |
| `timeStampImps` | Copy of `tickStampImps`. | s |
| `timeStampDemods` | Copy of `tickStampDemods`. | s |
| `ImpedanceRe` | `imps/0/sample.param0`, averaged. | Depends on the impedance module's representation (`imps/0/model`, not set by this code). The analysis code treats it as a resistance in Ω. |
| `ImpedanceIm` | `imps/0/sample.param1`, averaged. | Same dependency. The analysis code (`impedanceAnalysis_Tools`, `liveDataTab`) treats it as capacitance in F and multiplies by 1e12 for pF. |
| `AuxInput1` | `demods/0/sample.auxin0`, averaged. The fill-pulse (excitation) waveform used to locate transients. | V |
| `AbsZ` | `sqrt(ImpedanceRe**2 + ImpedanceIm**2)` computed in Python. Only a true \|Z\| when param0/param1 are the real and imaginary parts. | as the params |

#### Untriggered path (`trigger=False`)

Enables `demods[0]`, waits 2 s, enables `imps[0]`, waits 2 s, subscribes `demods[0].sample`, calls `session.poll()` (toolkit default: 0.1 s recording time, 0.5 s timeout), unsubscribes, waits 2 s, does the same for `imps[0].sample`, waits 2 s. Fixed sleeps: 8 s. `numPoints` and `numReps` are ignored; the record length is whatever arrived during the poll.

| Key | Content | Units |
|---|---|---|
| `tickStampImps` | Raw `imps` sample timestamps. | 60 MHz clock ticks (integers) |
| `tickStampDemods` | Raw `demods` sample timestamps. | clock ticks |
| `timeStampImps` | `tickStampImps / 60e6`, minus its first value. | s |
| `timeStampDemods` | `tickStampDemods / 60e6`, minus its first value. | s |
| `ImpedanceRe` | `imps` sample `param0`. | per `imps/0/model` |
| `ImpedanceIm` | `imps` sample `param1`. | per `imps/0/model` |
| `AbsZ` | `abs(z)` of the complex impedance sample. | Ω |
| `AuxInput1` | `demods` sample `auxin0`. | V |

**Returns** `dict` of the 8 keys above.

**Side effects** Enables the impedance module (and, untriggered, demodulator 0). Blocks for at least 7.5 s (triggered) or 8 s (untriggered). With `plot=True`, opens a matplotlib window; `plt.show()` blocks in a non-interactive backend.

**Example**

```python
# The stage and bias must be safe: the sample is pulsed during acquisition.
data = mfia.pull_data(plot=False, trigger=True, numPoints=2**16, numReps=100)
print(data['ImpedanceIm'].size, data['timeStampImps'][-1])
```

### defaultJsonConverter(self, obj)

`default=` hook for `json.dump`: converts a NumPy array to a list and raises `TypeError` for anything else.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `obj` | any | required | Object `json` cannot serialize. |

**Returns** `obj.tolist()` for an `np.ndarray`. The trailing `return 0` is unreachable.

**Side effects** None.

**Example**

```python
import json, numpy as np
json.dumps({'a': np.arange(3)}, default=mfia.defaultJsonConverter)
```

### writeDataJson(self, data, fName)

Writes `data` as indented JSON (`indent=4`) to `fName`, creating missing parent folders.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `data` | `dict` | required | Usually a `pull_data()` result or the run parameters. |
| `fName` | `str` or path | required | Output file. The extension is not checked. |

**Returns** `0`.

**Side effects** Creates folders and overwrites `fName` directly (no temporary file, so a crash can leave a truncated file). NumPy arrays become lists; NumPy integer scalars raise `TypeError`. DLTS runs with Data File Format **TXT** use this method, so their `.txt` step files contain JSON. `finish_experiment()` also writes `runParams.txt` with it.

**Example**

```python
mfia.writeDataJson(data, r'C:\DATA\test\p25p0.txt')
```

### writeDataH5(self, data, fName, setpoint_C=None, stage_temperature_C=None, runParams=None, acquired_at=None, extraAttrs=None)

Writes one temperature step's `pull_data()` output to its own HDF5 file. One file per step means Redo / Remove & Retake overwrites only that step, and a crash can only cost the step being written.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `data` | `dict` | required | `{channel name: array-like}`. |
| `fName` | `str` or path | required | Final file path, usually `...\p25p0.h5`. |
| `setpoint_C` | number or `None` | `None` | Temperature set-point in °C. |
| `stage_temperature_C` | number or `None` | `None` | Measured stage temperature in °C (the run averages the readings before and after acquisition). |
| `runParams` | `dict` or `None` | `None` | Run parameters, stored as a JSON string. |
| `acquired_at` | `datetime` or `None` | `None` | Acquisition time; `None` means now. |
| `extraAttrs` | `dict` or `None` | `None` | More root attributes (used by `convert_json_to_h5.py`). |

File layout:

| Item | Kind | Content |
|---|---|---|
| `format_version` | root attribute | `H5_FORMAT_VERSION` (1). |
| `acquired_at` | root attribute | ISO 8601 string, seconds precision. |
| `setpoint_C` | root attribute | `float`, `NaN` if not given. |
| `stage_temperature_C` | root attribute | `float`, `NaN` if not given. |
| `run_params` | root attribute | `json.dumps(runParams, default=str)`; absent if `runParams` is `None`. |
| any `extraAttrs` key | root attribute | as given. |
| one dataset per `data` key | 1-D dataset | Keys starting with `tickStamp` whose array has an integer dtype are stored as `uint64`; everything else is cast to `float64`. Non-empty datasets use gzip level 4 with shuffle. Empty arrays are stored uncompressed. |

Triggered `pull_data()` output has float `tickStamp*` arrays, so those are stored as `float64` seconds.

**Returns** `0`.

**Side effects** Creates parent folders. Writes to `<fName>.tmp`, then renames it onto `fName` with `os.replace`, so the live-data watcher never sees a half-written file. On `PermissionError` (another process has `fName` open) it retries up to 10 times, 0.5 s apart, then re-raises. If writing fails (for example a non-numeric channel), the exception propagates, `fName` is untouched, and the `.tmp` file is left on disk.

**Example**

```python
mfia.writeDataH5(data, r'C:\DATA\test\p25p0.h5', setpoint_C=25.0,
                 stage_temperature_C=25.02, runParams=params)
```

### runSweep(self, sweepType='freq')

Runs a LabOne sweeper measurement. Not used by the GUI.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `sweepType` | `str` | `'freq'` | `'freq'`: sweep `/dev32271/oscs/0/freq` from 10 Hz to 510 kHz. `'cv'`: sweep `/dev32271/auxouts/0/offset` from 0 to 1 V. Any other value leaves the grid node unset. |

Fixed sweeper settings: 200 points, linear x mapping (`xmapping 0`), `filtermode 0`, `endless 0`, settling inaccuracy 0.01, averaging 20 samples / 15 TC / 0.1 s, `bandwidth 10`, `maxbandwidth 100`, `bandwidthoverlap 1`, `omegasuppression 80`, `order 8`.

**Returns** a tuple `(allData, d)`: the full `sweep_module.read()` result and `allData['/dev32271/imps/0/sample'][0][0]`.

**Side effects** Enables `imps[0]`, subscribes three nodes, runs the sweep, prints `progress()` once per second until done (no timeout), unsubscribes. The `'cv'` sweep changes the DC offset on the aux output, which biases the sample, and leaves it at the last swept value.

**Example**

```python
# Biases the sample (cv) or drives it across 10 Hz-510 kHz (freq).
allData, d = mfia.runSweep('freq')
```

## Internal helpers

The module has no `_name` functions. `set_param_value`'s interactive prompt path and `defaultJsonConverter` act as helpers but are public.

## Standalone use

Safety: these scripts bias the mounted sample (aux output added to the signal output) and, in the second script, heat or cool the stage.

### MFIA only

```python
import sys
sys.path.insert(0, r'C:\Users\spencer\Documents\GitHub\DltsOnHallProbeSetup')
import matplotlib; matplotlib.use('Agg')
import dltsConfig as dltsc
import zurichInstruments_Control as ziC

mfia = ziC.ziDevice()
mfia.connect_device()
if mfia.device is None:
    raise SystemExit('MFIA connection failed')
try:
    params = mfia.configure({'State Enable Time': 0.5, 'State Disable Time': 0.001})

    data = mfia.pull_data(plot=False, trigger=True, numPoints=2**16, numReps=100)
    mfia.writeDataH5(data, r'C:\DATA\standalone\p25p0.h5', setpoint_C=None, runParams=params)
finally:
    mfia.disconnect_device()     # instrument settings stay as configured
```

### MFIA plus temperature stage, one step

```python
import sys
sys.path.insert(0, r'C:\Users\spencer\Documents\GitHub\DltsOnHallProbeSetup')
import matplotlib; matplotlib.use('Agg')
import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC

stage = tsC.mK2000B()                 # COM7
stage.connect_temp_controller()
if not stage.state:
    raise SystemExit('temperature controller connection failed')
mfia = ziC.ziDevice()
mfia.connect_device()
if mfia.device is None:
    stage.disconnect_temp_controller(stopControl=False)
    raise SystemExit('MFIA connection failed')

roomStatus = None
try:
    tParams = stage.configure({'Temperature Ramp (C/min)': 5, 'Room Temperature (C)': 25})
    tParams.pop('Temperature Grid (C)')          # numpy array; not needed in the metadata
    params = mfia.configure()

    T = 30.0
    stage.go_to_temp(T)                          # blocks until stable (no overall time limit)
    before = stage.read_temp()
    data = mfia.pull_data(plot=False, trigger=True, numPoints=2**16, numReps=100)
    after = stage.read_temp()
    mfia.writeDataH5(data, r'C:\DATA\standalone\p30p0.h5', setpoint_C=T,
                     stage_temperature_C=(before + after) / 2,
                     runParams={**params, **tParams})
    roomStatus = stage.go_to_room_temp()         # 0 arrived, 1 gave up, -1 not connected
finally:
    # Send TEMPerature:STOP only if the stage reached room temperature;
    # otherwise leave the controller ramping there on its own.
    stage.disconnect_temp_controller(stopControl=(roomStatus == 0))
    mfia.disconnect_device()
```

`stage.configure()` sends nothing to the controller; `go_to_temp()` sends the ramp command.

## Notes and limitations

- Every node path is hard-coded to `/dev32271/`. `devSerial` only affects `connect_device()` and `disconnect_device()`; a different MFIA would connect but every set, get and subscribe would address `dev32271`.
- `connect_device()` always returns `0`. Discovery errors are raised, session errors are printed.
- `reload_params()` (called by every run step) re-reads mismatched values from `dltsc.z_params_for_push`, then `dltsc.z_params_vars`, then `self.configuredParams` (set by `configure()`), and only then `input()` prompts. A script that calls `configure()` first never reaches the prompts (covered by `tests/test_standalone_helpers.py`).
- If `dltsc.z_params_vars` holds GUI label strings and `z_params_for_push` lacks a name, `set_param_value(pName)` stores the label string (for example `'1 - On'`) and the push fails.
- `check_param()` reads the entire node tree (`get('*')`) once per parameter; `reload_params()` does this 23 times.
- `Oscillation ON/OFF` is pushed to `imps/0/auto/output`, not an output on/off node. `Filter Bandwidth` sets the filter order.
- Triggered `pull_data()`: `tickStampDemods` is the `param1` time axis, not the demodulator's own; `tickStamp*` hold seconds, not clock ticks; `AbsZ` is `sqrt(param0² + param1²)`, which is not \|Z\| when the representation is Rp‖Cp; the `R.avg` subscription is unused.
- `daq_module.forcetrigger()` is called with no argument. In zhinst-toolkit, calling a node without an argument reads it, so this line most likely does not force a trigger.
- After the 60 s timeout, `pull_data()` still calls `read()` and indexes `[0]` of each node's result. If no burst arrived, that raises an exception, which the run records as a failed step.
- `pull_data()` never calls `daq_module.finish()`; the managed module is reused between calls. The 0.5 s settle after `execute()` exists because `progress()` can report the previous run's 1.0.
- The code never sets `imps/0/model`, so the meaning of `param0`/`param1` depends on the instrument's current or factory setting.
- `disconnect_device()` leaves the bias and test signal running.
- `H5_FORMAT_VERSION` is a class attribute (`ziC.ziDevice.H5_FORMAT_VERSION`), not a module constant.
- `writeDataH5()` leaves `<fName>.tmp` behind when writing fails.
- `runSweep()` has no timeout and the `'cv'` sweep leaves the aux offset at its last value.

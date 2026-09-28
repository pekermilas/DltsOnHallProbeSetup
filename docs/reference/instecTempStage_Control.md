# instecTempStage_Control

`instecTempStage_Control.py` controls the Instec mK2000B temperature controller of the Hall-probe stage over a serial port (`COM7` by default). Its class, `mK2000B`, opens the port, commands temperature ramps, reads the stage temperature, waits for the stage to stabilize at each set-point of the DLTS temperature grid, and returns the stage to room temperature after a run. It also works without the GUI: `DEFAULT_PARAMS` and `mK2000B.configure()` set every temperature parameter from a script.

GUI callers:

- **Input Parameters** tab: `runParamsTab.connect_and_get_params('temperature')` creates `dltsc.tempDev = mK2000B()` and calls `connect_temp_controller()` and `set_param_value()`; `apply_and_push_params('temperature')` calls `load_params()`.
- **Live Tools** tab, Run DLTS (`runDlts_Tools.dltsRun`): `set_temp_grid()`, `go_to_temp()`, `read_temp()` (HDF5 metadata), `go_to_room_temp()`, and the attributes `tempGrid`, `tRamp`, `tStableDelay`, `Troom`, `roomRamp`.
- Window close (`DLTSGUI_MainWindow`): `abort()`, `start_ramp(..., lockTimeout=...)`, `read_temp()` while waiting, and `disconnect_temp_controller(stopControl=...)`.

## Import

```python
import instecTempStage_Control as tsC
```

The module does not import `dltsConfig`.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `SERIAL_TIMEOUT_S` | `2.0` (s) | Read and write timeout set on the port by `connect_temp_controller()`. The longest `read_temp()` waits for one reply. |
| `READ_RETRIES` | `1` | Extra queries `read_temp()` sends after a missed or unreadable reply before raising `TimeoutError`. |
| `DEFAULT_PARAMS` | `dict`, 7 entries (below) | The Input Parameters tab's temperature defaults. `mK2000B.configure()` starts from these. |
| `mK2000B._PARAM_ATTRS` | `dict` (class attribute) | Maps parameter names to the attributes the motion methods read: `'Temperature Ramp (C/min)'` → `tRamp`, `'Stability Delay (s)'` → `tStableDelay`, `'Room Temperature (C)'` → `Troom`, `'Room Ramp (C/min)'` → `roomRamp`. |

`DEFAULT_PARAMS`:

| Key | Value | Meaning |
|---|---|---|
| `Initial Temperature (C)` | `25.0` | First grid set-point, °C. |
| `Final Temperature (C)` | `25.0` | Last grid set-point, °C. |
| `Temperature Step (C)` | `5.0` | Grid step, °C (sign ignored). |
| `Temperature Ramp (C/min)` | `5.0` | Ramp rate between set-points. |
| `Stability Delay (s)` | `0.0` | Extra wait after the stage is stable. |
| `Room Temperature (C)` | `25.0` | Where the stage goes after a run. |
| `Room Ramp (C/min)` | `10.0` | Ramp rate for that return. |

`params` also has an eighth key, `Temperature Grid (C)`, which is always computed from the first three; it is not in `DEFAULT_PARAMS` and `configure()` rejects it.

## Serial commands

The port uses pyserial defaults for the line settings (9600 baud, 8 data bits, no parity, 1 stop bit). `connect_temp_controller()` sets a read and a write timeout of `SERIAL_TIMEOUT_S` (2 s); the controller normally answers in 10–15 ms. Every command ends with `\n`.

| Command sent | Sent by | Reply | Effect |
|---|---|---|---|
| `TEMPerature:RAMP <T>,<ramp>` | `start_ramp()` (so `go_to_temp()`, `go_to_room_temp()`, GUI close) | none read | Ramp to `<T>` °C at `<ramp>` °C/min. The controller carries the ramp out by itself. `<T>` and `<ramp>` are Python `str()` of the values, for example `TEMPerature:RAMP 30.0,5.0`. No leading colon. |
| `:TEMPerature:CTEMperature?` | `read_temp()` | one line, parsed with `float()` | Current stage temperature, °C. Sent again (up to `READ_RETRIES` times) if no readable reply arrives within 2 s. |
| `:TEMPerature:STOP` | `disconnect_temp_controller(stopControl=True)` | none read | Ends temperature control and cancels any ramp in progress. |

## Stabilization logic

`go_to_temp(Tf)` sends the ramp, waits 0.5 s, then compares the measured deviation `|Tf - T_stage|` with a tolerance from `expected_del_t(Tf)`:

1. Take one reading. If the deviation is at or below the tolerance, the wait ends right away (no confirmation reading).
2. Otherwise loop: take a reading. If it is below the tolerance, wait 10 s and take a confirmation reading; the loop ends only if that reading is also within tolerance. If it is not below the tolerance, wait 5 s.
3. After the loop, sleep `tStableDelay` seconds.

There is no overall time limit on stabilizing: the loop ends only on stabilization, `abort()`, or an exception. If the controller stops answering, `read_temp()` raises `TimeoutError` after about 4 s (2 tries × 2 s), which ends the wait with that exception instead of hanging.

`expected_del_t(T)` builds the tolerance from a sensor calibration table: set-points `[19.648, 100, 199.99, 300, 400, 500, 600]` °C and measured `[19.648, 99.679, 199.633, 299.235, 398.98, 498.725, 598.47]` °C, so `delT = [0, 0.321, 0.357, 0.765, 1.02, 1.275, 1.53]` °C. Then:

| Range of `T` | Tolerance formula |
|---|---|
| `T < 19.648` | Straight line from 0 at 19.648 °C to `2 × 1.53 = 3.06` at -190 °C: `-0.0145959·T + 0.286780` |
| `19.648 ≤ T ≤ 25` | `0.1` |
| `T > 25` | Straight line from 0 at 19.648 °C to 1.53 at 600 °C: `0.00263633·T - 0.0517986` |

It also runs an lmfit linear fit of `delT` on every call (about 1 ms) and discards the result.

Tolerances computed offline with the function itself:

| Set-point (°C) | Tolerance (°C) |
|---|---|
| -190 | 3.060 |
| -100 | 1.746 |
| -50 | 1.017 |
| 0 | 0.287 |
| 10 | 0.141 |
| 19 | 0.0095 |
| 19.648 to 25 | 0.100 |
| 25.01 | 0.0141 |
| 30 | 0.0273 |
| 40 | 0.0537 |
| 50 | 0.0800 |
| 75 | 0.1459 |
| 100 | 0.2118 |
| 150 | 0.3437 |
| 200 | 0.4755 |
| 300 | 0.7391 |
| 400 | 1.0027 |
| 500 | 1.2664 |
| 600 | 1.5300 |

The tolerance jumps from 0.1 °C at 25 °C to 0.014 °C just above it, and falls to nearly 0 just below 19.648 °C. Set-points slightly above 25 °C or slightly below 19.6 °C need the stage to hold within a few hundredths of a degree for two readings 10 s apart.

`go_to_room_temp()` does not use this tolerance. It uses a plain `tolerance` argument (0.5 °C by default) and a deadline.

## Thread safety

`_ioLock` is a `threading.RLock`. `start_ramp()`, `read_temp()` and `disconnect_temp_controller()` hold it for each command (and, for `read_temp()`, the command plus its reply), so the run thread, the GUI close handler and any monitor thread never interleave bytes on the port. `go_to_temp()` and `go_to_room_temp()` do not hold the lock between polls. `write()`, `read()` and `query()` do not use the lock.

## class mK2000B

### Attributes

| Name | Type | Default | Meaning |
|---|---|---|---|
| `port` | `str` | `'COM7'` | Serial port name. |
| `dev` | `serial.Serial` or `None` | `None` | Open port. Not reset to `None` by `disconnect_temp_controller()`. |
| `rm` | `None` | `None` | Unused. |
| `state` | `bool` | `False` | `True` while the port is open. |
| `Tinitial` | number | `25` | First set-point, updated by `set_temp_grid()` and `configure()`. |
| `Tfinal` | number | `25` | Last set-point. |
| `tempStep` | number | `5` | Grid step. |
| `numTemps` | `int` | `1` | Number of grid points. |
| `tRamp` | `float` | `5` | Ramp rate `go_to_temp()` uses, °C/min. |
| `tStableDelay` | `float` | `0` | Wait after stabilization, s. |
| `tempGrid` | `numpy.ndarray` | `25` (an `int` until a grid is built) | Set-points, °C. |
| `Troom` | `float` | `25` | Room-temperature target, °C. |
| `roomRamp` | `float` | `10` | Room-return ramp rate, °C/min. |
| `_ioLock` | `threading.RLock` | new lock | Serial I/O lock. |
| `_aborted` | `bool` | `False` | Set by `abort()`. Never cleared by the class. |
| `params` | `dict` | 8 keys, all `None` | The seven `DEFAULT_PARAMS` names plus `Temperature Grid (C)`. |

### __init__(self, port = None)

Creates an unconnected controller object.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `port` | `str` or `None` | `None` | Serial port; `None` means `'COM7'`. |

**Returns** a new `mK2000B`.

**Side effects** None. The port is not opened.

**Example**

```python
stage = tsC.mK2000B()          # COM7
stage3 = tsC.mK2000B('COM3')
```

### build_temp_grid(Tinit, Tfin, step)

Static method. Builds the set-point grid from `Tinit` to `Tfin` inclusive, stepping by `|step|`. The number of intervals is `round(|Tfin - Tinit| / step)` (at least 1), and the last point is forced to `Tfin`, so the last interval can be shorter or longer than `step`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `Tinit` | number or numeric string | required | First set-point, °C. |
| `Tfin` | number or numeric string | required | Last set-point, °C. Can be below `Tinit` (cooling grid). |
| `step` | number or numeric string | required | Step, °C; sign ignored. |

**Returns** `numpy.ndarray` of floats. `Tinit == Tfin` gives `[Tinit]`; `step == 0` gives `[Tinit, Tfin]`.

**Side effects** None.

**Example**

```python
tsC.mK2000B.build_temp_grid(25, 50, 5)   # [25. 30. 35. 40. 45. 50.]
tsC.mK2000B.build_temp_grid(25, 52, 5)   # [25. 30. 35. 40. 45. 52.]
tsC.mK2000B.build_temp_grid(50, 25, 5)   # [50. 45. 40. 35. 30. 25.]
```

### read(self)

Returns `self.dev.read()`: one byte from the port (pyserial reads 1 byte by default).

No parameters.

**Returns** `bytes`. Raises `AttributeError` if `dev` is `None`.

**Side effects** Waits up to `SERIAL_TIMEOUT_S` for a byte; returns `b''` on timeout. Not locked. Not used by the codebase.

**Example**

```python
b = stage.read()
```

### write(self, writeStr = None)

Writes `writeStr` to the port if `dev` is set.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `writeStr` | `bytes` | `None` | Raw bytes to send, including `\n`. A `str` raises `TypeError` in pyserial. |

**Returns** `0` if written, `-1` if `dev` is `None`.

**Side effects** Sends bytes. Not locked. Not used by the codebase.

**Example**

```python
stage.write(b':TEMPerature:CTEMperature?\n')
```

### query(self, queryStr = None)

Calls `self.dev.query(queryStr)`. `serial.Serial` has no `query` method, so this raises `AttributeError` when connected, and returns `None` when `dev` is `None`. It is a leftover from a VISA-based version.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `queryStr` | any | `None` | Unused in practice. |

**Returns** `None` (or raises).

**Side effects** None.

**Example**

```python
# Do not use; call read_temp() instead.
```

### connect_temp_controller(self)

Opens `self.port` with `serial.Serial()`, with `timeout` and `write_timeout` set to `SERIAL_TIMEOUT_S`, waits 0.2 s and sets `state = True`. If the controller is already connected it prints `Temperature controller is already connected!`.

No parameters.

**Returns** `0` in every case. Check `self.state`.

**Side effects** Opens the serial port. On failure prints `Error connecting to device: ...` and resets `state`, `dev`, `rm`. It sends no command, so any device on the port "connects".

**Example**

```python
stage.connect_temp_controller()
if not stage.state:
    raise RuntimeError('temperature controller connection failed')
```

### disconnect_temp_controller(self, stopControl=True, lockTimeout=5.0)

Closes the serial port. With `stopControl=True` it first sends `:TEMPerature:STOP` and waits 0.5 s.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `stopControl` | `bool` | `True` | `True`: end temperature control (and cancel any ramp) before closing. `False`: leave the controller running on its own, for example still ramping to room temperature after the program exits. |
| `lockTimeout` | `float` | `5.0` | Seconds to wait for `_ioLock`. If it expires, the method closes the port anyway. |

**Returns** `0`.

**Side effects** Optional STOP command; closes the port; `state = False`. `dev` keeps the closed port object. Prints `Already disconnected!` if `state` is already `False`, or `Nothing to do!` if `dev` is `None`. The GUI passes `stopControl=True` only when the stage reached room temperature (or no ramp was needed); "Close now" passes `False`.

**Example**

```python
stage.disconnect_temp_controller(stopControl=False)   # stage keeps ramping
```

### abort(self)

Sets `self._aborted = True`. `go_to_temp()` then refuses to send a new set-point and its wait loop exits; `go_to_room_temp()` stops waiting (the ramp it already sent keeps going).

No parameters.

**Returns** `None`.

**Side effects** Sets the flag only. Nothing clears it; set `stage._aborted = False` before using the object again (as `benchmarks/hardware/hw_run.py` does). In a `dltsRun`, also set `dltsc.run_abortRequested = True`, or the run will acquire at whatever temperature the stage has.

**Example**

```python
import threading
threading.Timer(40 * 60, stage.abort).start()    # watchdog for go_to_temp()
```

### start_ramp(self, T, ramp, lockTimeout=None)

Sends `TEMPerature:RAMP <T>,<ramp>` and returns without waiting.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `T` | number | required | Target, °C. |
| `ramp` | number | required | Rate, °C/min. |
| `lockTimeout` | `float` or `None` | `None` | `None`: wait for the lock indefinitely. A number: wait that long, then send anyway. The GUI close handler uses 5 s (2 s for the exit backstop): reaching room temperature matters more than a garbled concurrent reply. |

**Returns** `None`.

**Side effects** One serial command. Does not check `state` or `_aborted`. Raises `AttributeError` if `dev` is `None`, and `serial.SerialTimeoutException` if the write cannot complete within `SERIAL_TIMEOUT_S`.

**Example**

```python
# The stage starts heating or cooling immediately.
stage.start_ramp(30.0, 5.0)
```

### read_temp(self, retries=READ_RETRIES)

Clears any unread bytes from the port, sends `:TEMPerature:CTEMperature?` and reads one reply line, all under the lock. A missing (timed out) or non-numeric reply is retried.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `retries` | `int` | `READ_RETRIES` (1) | Extra attempts after the first. Each waits at most `SERIAL_TIMEOUT_S` (2 s). |

**Returns** `float`, stage temperature in °C.

**Side effects** One to `retries + 1` command/response pairs. Clearing the input buffer first means a late reply to an earlier query is never taken for this one. When no attempt gives a number, it raises `TimeoutError("temperature controller on COM7 did not answer the temperature query (2 tries, 2 s each; last reply b'')")`, about 4 s after the call, and releases the lock. Callers handle it: a run marks the step failed and returns to room temperature, `dltsRun._read_stage_temp()` records the stage temperature as missing, and the GUI close dialog keeps polling until its deadline.

**Example**

```python
try:
    print(stage.read_temp())
except TimeoutError as exc:
    print('controller not answering:', exc)
```

### expected_del_t(self, T=25)

Returns the stabilization tolerance for set-point `T` (see "Stabilization logic").

| Name | Type | Default | Meaning |
|---|---|---|---|
| `T` | number | `25` | Set-point, °C. |

**Returns** `float`, tolerance in °C.

**Side effects** None (runs an unused lmfit fit). Works offline.

**Example**

```python
tsC.mK2000B().expected_del_t(50)   # 0.0800...
```

### go_to_temp(self, Tf=25, ramp=5, delayTime = 0)

Ramps to `Tf` and blocks until the stage is stable, then sleeps the stability delay.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `Tf` | number | `25` | Target set-point, °C. |
| `ramp` | number | `5` | **Ignored** when `dev` is set: replaced by `self.tRamp`. |
| `delayTime` | number | `0` | **Ignored** when `dev` is set: replaced by `self.tStableDelay`. Used only on the `dev is None` path. |

**Returns** `0` when done. `-1` if `_aborted` was set before the call, during the wait, or during the stability delay. Also `0` when `dev` is `None` (prints `Nothing to do!`) or `state` is `False` (prints `T-Controller is disconnected!`), without moving the stage.

**Side effects** Sends one ramp command, then `read_temp()` every 5 s (plus confirmation readings 10 s apart). Prints `Wait for T = <Tf> stabilization!`. Has no overall time limit; other than stabilizing, it ends on `abort()` from another thread, or with `TimeoutError` from `read_temp()` if the controller stops answering.

**Example**

```python
# The stage heats or cools to 30 C.
stage.configure({'Temperature Ramp (C/min)': 5, 'Stability Delay (s)': 60})
status = stage.go_to_temp(30.0)
```

### go_to_room_temp(self, Tr=None, ramp=None, tolerance=0.5, extraWaitS=900)

Ramps to room temperature and waits until the stage is within `tolerance` of it, or a deadline passes.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `Tr` | number or `None` | `None` | Target, °C; `None` means `self.Troom`. |
| `ramp` | number or `None` | `None` | Rate, °C/min; `None` means `self.roomRamp`. |
| `tolerance` | `float` | `0.5` | Arrival band, °C. |
| `extraWaitS` | `float` | `900` | Deadline = `|Tr - T_first| / ramp × 60 s + extraWaitS`, from the first reading. |

**Returns** `0` once within tolerance (after a final 10 s sleep); `1` if aborted or the deadline passed (prints `Gave up waiting for room temperature ...` on timeout); `-1` if `dev` is `None` or `state` is `False`.

**Side effects** Sends the ramp command even if `_aborted` is set, then polls `read_temp()` every 5 s. Returning `1` leaves the controller ramping or holding at `Tr`. A `TimeoutError` from `read_temp()` propagates (`dltsRun.return_to_room_temp()` catches it and returns `-1`).

**Example**

```python
# The stage heats or cools to 25 C.
status = stage.go_to_room_temp(Tr=25, ramp=10)
```

### set_temp_grid(self, userInput = False)

Builds `tempGrid` from the initial/final/step values and stores `Tinitial`, `Tfinal`, `tempStep`, `numTemps`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `userInput` | `bool` | `False` | `False`: read the values from `self.params`. `True`: prompt on the console with `input()`; an empty answer keeps the current attribute. |

**Returns** `0`.

**Side effects** Updates the grid attributes. Does nothing but print `Nothing to do!` when `dev` is `None`, so it needs a connected (or at least constructed) port. `dltsRun.init_experiment()` calls it.

**Example**

```python
stage.set_temp_grid()
print(stage.tempGrid)
```

### set_param_value(self, pName='Initial Temperature (C)', valueDict=None)

Stores one parameter in `self.params`, then copies the ramp, delay and room values into the motion attributes (`_sync_attrs_from_params()`).

| Name | Type | Default | Meaning |
|---|---|---|---|
| `pName` | `str` | `'Initial Temperature (C)'` | One of the 8 `params` keys. |
| `valueDict` | `dict` or `None` | `None` | `{name: value}`. `None`: prompt on the console (empty answer = the `DEFAULT_PARAMS` value). |

For `Temperature Grid (C)` the value is always `build_temp_grid()` of the dict's (or `params`') initial, final and step values. Any other name takes `valueDict.get(pName)` (a missing key stores `None`, which `_sync_attrs_from_params()` then skips).

**Returns** `0`.

**Side effects** Writes `params` and possibly `tRamp`, `tStableDelay`, `Troom`, `roomRamp` (cast to `float`). Unknown names print `Unknown Parameter <name>!!!`. No serial traffic.

**Example**

```python
stage.set_param_value('Room Temperature (C)', {'Room Temperature (C)': 22})
```

### configure(self, values=None)

Sets every parameter without the GUI: `DEFAULT_PARAMS` overridden by `values`, then `load_params()`, then `Tinitial`, `Tfinal`, `tempStep`, `tempGrid` and `numTemps`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `values` | `dict` or `None` | `None` | `{parameter name: number}` overrides. Names must be `DEFAULT_PARAMS` keys. |

**Returns** a copy of `self.params` (`dict`), including the `Temperature Grid (C)` array.

**Side effects** Raises `KeyError('unknown temperature parameter(s): [...]')` for unknown names before changing anything. Updates `params`, the motion attributes and the grid. Needs no connection and sends nothing to the controller.

**Example**

```python
stage = tsC.mK2000B()
p = stage.configure({'Initial Temperature (C)': 25, 'Final Temperature (C)': 50})
stage.tempGrid      # array([25., 30., 35., 40., 45., 50.])
```

### load_params(self, valueDict)

Calls `set_param_value(pName, valueDict)` for all 8 parameters.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `valueDict` | `dict` | required | Must contain the initial, final and step values (the grid is built from them). |

**Returns** `0`.

**Side effects** As `set_param_value`. The **Apply + Push Params** button calls it with `dltsc.t_params_for_push`.

**Example**

```python
stage.load_params(dict(tsC.DEFAULT_PARAMS))
```

### measure_proxy_temp(self, Tf)

Reads the stage once and returns the deviation and the tolerance.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `Tf` | number | required | Set-point, °C. |

**Returns** tuple `(abs(Tf - T_stage), expected_del_t(Tf))`, both °C.

**Side effects** One `read_temp()`. With `dev = None` it prints `Nothing to do!` and then raises `UnboundLocalError`.

**Example**

```python
dev, tol = stage.measure_proxy_temp(30.0)
```

## Internal helpers

- `_sync_attrs_from_params(self)`: for each entry of `_PARAM_ATTRS`, copies `float(params[name])` into the attribute if the value is not `None`. Without it, `go_to_temp()` would keep the constructor's 5 °C/min and 0 s.

## Standalone use

Safety: these scripts heat and cool the stage; the last one also biases the sample.

### Read the temperature

```python
import sys
sys.path.insert(0, r'C:\Users\spencer\Documents\GitHub\DltsOnHallProbeSetup')
import instecTempStage_Control as tsC

stage = tsC.mK2000B()
stage.connect_temp_controller()
if not stage.state:
    raise SystemExit('connection failed')
try:
    print('stage at', stage.read_temp(), 'C')
finally:
    stage.disconnect_temp_controller(stopControl=False)   # do not change control state
```

### Ramp through a grid with a watchdog

```python
import sys, threading
sys.path.insert(0, r'C:\Users\spencer\Documents\GitHub\DltsOnHallProbeSetup')
import instecTempStage_Control as tsC

stage = tsC.mK2000B()
stage.configure({'Initial Temperature (C)': 25, 'Final Temperature (C)': 40,
                 'Temperature Step (C)': 5, 'Temperature Ramp (C/min)': 5,
                 'Stability Delay (s)': 30, 'Room Temperature (C)': 25})
stage.connect_temp_controller()
if not stage.state:
    raise SystemExit('connection failed')

roomStatus = None
try:
    for T in stage.tempGrid:
        watchdog = threading.Timer(30 * 60, stage.abort)      # go_to_temp has no overall time limit
        watchdog.start()
        status = stage.go_to_temp(T)
        watchdog.cancel()
        if status == -1:
            print(f'gave up stabilizing at {T} C')
            break
        print(f'{T} C reached, stage reads {stage.read_temp()} C')
finally:
    stage._aborted = False                  # abort() is sticky
    roomStatus = stage.go_to_room_temp()    # 0 arrived, 1 gave up, -1 not connected
    stage.disconnect_temp_controller(stopControl=(roomStatus == 0))
```

`stopControl=(roomStatus == 0)` follows the GUI: send STOP only when the stage is at room temperature, otherwise leave the controller ramping there.

### One DLTS step with the MFIA

```python
import sys
sys.path.insert(0, r'C:\Users\spencer\Documents\GitHub\DltsOnHallProbeSetup')
import matplotlib; matplotlib.use('Agg')
import dltsConfig as dltsc
import instecTempStage_Control as tsC
import zurichInstruments_Control as ziC

stage, mfia = tsC.mK2000B(), ziC.ziDevice()
stage.configure({'Room Temperature (C)': 25})
stage.connect_temp_controller()
mfia.connect_device()
if not stage.state or mfia.device is None:
    raise SystemExit('connection failed')

roomStatus = None
try:
    params = mfia.configure()                  # also what reload_params() falls back to
    T = 30.0
    stage.go_to_temp(T)
    tBefore = stage.read_temp()
    data = mfia.pull_data(plot=False, trigger=True, numPoints=2**16, numReps=100)
    tAfter = stage.read_temp()
    mfia.writeDataH5(data, r'C:\DATA\standalone\p30p0.h5', setpoint_C=T,
                     stage_temperature_C=(tBefore + tAfter) / 2, runParams=params)
    roomStatus = stage.go_to_room_temp()
finally:
    stage.disconnect_temp_controller(stopControl=(roomStatus == 0))
    mfia.disconnect_device()
```

## Notes and limitations

- A controller that stops answering no longer hangs anything: reads time out after 2 s, `read_temp()` retries once and then raises `TimeoutError` (earlier versions set no serial timeout and blocked forever). Tested in `tests/test_run_folder_and_serial.py`.
- `go_to_temp()` still has no overall time limit. A set-point the stage cannot hold within tolerance, while the controller keeps answering, waits until another thread calls `abort()`.
- `go_to_temp()` ignores its `ramp` and `delayTime` arguments when connected and uses `tRamp` and `tStableDelay`.
- `go_to_temp()` returns `0` without moving the stage when the port is closed (`state == False`) or `dev` is `None`, so callers cannot tell "done" from "not connected".
- If the stage is already within tolerance at the first reading, `go_to_temp()` skips the 10 s confirmation reading.
- `expected_del_t()` is discontinuous: 0.1 °C at 25 °C, 0.014 °C at 25.01 °C, and it drops to about 0 just below 19.648 °C. At 30 °C the tolerance is 0.027 °C. The lmfit fit it runs is unused.
- `abort()` is permanent for the object; reset `_aborted` by hand to reuse it. `go_to_room_temp()` sends its ramp even when aborted.
- `dltsRun` checks `dltsc.run_abortRequested`, not `go_to_temp()`'s return value. Calling only `stage.abort()` during a run makes the step acquire at the current temperature.
- `connect_temp_controller()` does not verify that the device on the port is an mK2000B.
- `read()`, `write()` and `query()` are unlocked leftovers; `query()` always fails on a `serial.Serial`.
- `measure_proxy_temp()` raises `UnboundLocalError` when not connected.
- `set_temp_grid()` does nothing without an open port object, but `configure()` builds the same grid offline.
- `tempGrid` is the integer `25` until a grid is built.
- `disconnect_temp_controller()` leaves `dev` pointing at the closed port.
- The header comment's example (`temperatureTools`, `connectTempController`, `goToTemp`, `disconnTController`) names functions that do not exist in this module.
- The module imports `matplotlib.pyplot` and `from lmfit.models import *` without using them beyond `lmfit.models.LinearModel`.

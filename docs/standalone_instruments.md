# Standalone instruments

Both instrument classes work without the GUI. Use them to test the hardware, take
single measurements, or write your own measurement scripts. Ready-made scripts are in
`examples/`.

**Safety.** Ramping heats or cools the sample. The MFIA applies the pulse bias (Aux
output added to the signal output) as soon as its parameters are pushed.

## Temperature controller: `instecTempStage_Control.mK2000B`

```python
import instecTempStage_Control as tsC

stage = tsC.mK2000B()                      # port 'COM7'; mK2000B(port='COM5') for another
stage.configure({'Temperature Ramp (C/min)': 5, 'Room Temperature (C)': 25})
stage.connect_temp_controller()            # opens the serial port; stage.state is True on success
print(stage.read_temp())                   # current stage temperature, C

stage.go_to_temp(30, stage.tRamp, stage.tStableDelay)   # ramp and wait until stable (no overall time limit)
stage.go_to_room_temp()                    # ramp to Room Temperature and wait (gives up after the ramp time + 15 min)
stage.disconnect_temp_controller(stopControl=True)      # True: send STOP first; False: leave it holding/ramping
```

- `configure(values)` sets every parameter from `DEFAULT_PARAMS` plus your overrides,
  including the temperature grid (`stage.tempGrid`), with no connection needed.
- `go_to_temp()` blocks until the reading is within `expected_del_t(T)` of the setpoint
  (0.1 °C at 25 °C, 0.027 °C at 30 °C, 0.21 °C at 100 °C) and stays there 10 s later.
  From another thread, `stage.abort()` makes it return −1.
- Every serial exchange holds `stage._ioLock`, so a monitoring thread can call
  `read_temp()` while another thread ramps.
- Serial reads and writes time out after `tsC.SERIAL_TIMEOUT_S` (2 s). `read_temp()`
  asks once more, then raises `TimeoutError`, so a controller that stops answering
  fails your script within about 4 s instead of hanging it.

Full reference: [instecTempStage_Control](reference/instecTempStage_Control.md).
Script: `python examples/standalone_temperature.py --goto 30`.

## Impedance analyzer: `zurichInstruments_Control.ziDevice`

```python
import zurichInstruments_Control as ziC

dev = ziC.ziDevice()                       # device 'dev32271'
dev.connect_device()                       # dev.device is None if the connection failed
dev.configure({'State Enable Time': 0.5, 'State Disable Time': 0.001,
               'Aux Output Scale': -5.0, 'Aux Output Offset': 0.0, 'Aux Output Upper Limit': 5.0})
data = dev.pull_data(plot=False, trigger=True, numPoints=2**16, numReps=100)
dev.writeDataH5(data, r'C:\temp\p25p0.h5', setpoint_C=25.0, runParams=dev.params)
dev.disconnect_device()
```

- `configure(values, push=True)` sets all 23 parameters from `DEFAULT_PARAMS` (the GUI
  defaults) plus your overrides and pushes them. `push=False` only fills `dev.params`.
  Unknown names raise `KeyError`. Later `reload_params()` calls fall back to these
  values, so a script never hits the console prompts in `set_param_value()`.
- `pull_data(trigger=True, ...)` is what a run uses: the DAQ module records `numPoints`
  samples after each pulse trigger and averages `numReps` repetitions. It returns a dict
  of 8 NumPy arrays: `AuxInput1` (excitation, V), `ImpedanceIm`, `ImpedanceRe`, `AbsZ`,
  and four time channels in seconds. It takes about 7.5 s of fixed waits plus the data
  time, and gives up waiting after 60 s (a warning is printed).
- `writeDataH5()` writes the GUI's HDF5 step format; `writeDataJson()` the TXT format.
- All device node paths are hard-coded to `/dev32271/`. For another MFIA, change them in
  `push_param_to_device()`, `check_param()` and `pull_data()`.

Full reference: [zurichInstruments_Control](reference/zurichInstruments_Control.md).
Script: `python examples/standalone_impedance.py --out C:\temp\test.h5`.

## Both together

`examples/standalone_scan.py` is a complete minimal scan: configure both instruments,
write `runParams.txt`, then for every setpoint ramp, acquire, and write `p25p0.h5` etc.,
and finally return to room temperature. Its files load in every analysis tab.

```
python examples/standalone_scan.py --folder C:\temp\scan1 --start 25 --stop 50 --step 5 --room 30 --points 16 --reps 100
```

It does not provide Pause, Redo or Remove & Retake. For those without the GUI, drive
`runDlts_Tools.dltsRun` itself; `benchmarks/hardware/hw_run.py` shows the complete
pattern (see [runDlts_Tools](reference/runDlts_Tools.md#standalone-use)).

## Analysis without instruments

```
python examples/analyze_run.py RUN_FOLDER --t1-min 0.5 --t1-max 5 --tp 300 400 --png summary.png
```

It runs the Detailed Analysis computation on a run folder and saves a figure of the
transients, DLTS spectra and Arrhenius fit ([Quick run case A](quick_run.md#a-analyze-a-finished-run-no-instruments)).
For your own analysis code, start from `impedanceAnalysis_Tools.impdData`
([reference](reference/impedanceAnalysis_Tools.md#typical-workflows)).

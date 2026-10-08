# DLTSGUI_MainWindow

## What it's for

`DLTSGUI_MainWindow.py` is the entry point of the DLTS Control GUI. It creates the Tk root window, builds the notebook tabs by calling each tab module's `construct_*` function, and installs the close handler. Closing the window always tries to send the temperature stage back to the room temperature set on the **Input Parameters** tab before the program exits. It also registers backstop handlers that command the same ramp when the program ends without going through the window's close button.

Start the GUI from the repository folder:

```powershell
python DLTSGUI_MainWindow.py
```

## What the user sees

### Main window

- Title: **DLTS Control GUI**.
- The window opens maximized (`root.state('zoomed')`). If that fails, the code sets the geometry to the full screen size.
- Minimum size: 860 px wide. The minimum height is `min(780, max(760, screen_height - 180))`, so it is always between 760 and 780 px.
- Notebook tab font: Arial 11, padding 6.

### Tabs, in order

| Tab label | Frame (`dltsConfig` global) | Built by |
|---|---|---|
| Input Parameters | `dltsc.runParamsTab` | `runParamsTab.construct_runParamsTab()` |
| Live Tools | `dltsc.livePlotTab` | `liveDataTab.construct_livePlotTab()` |
| Quick Analysis | `dltsc.dataAnalysisTab` | `dataAnalysisTab.construct_dataAnalysisTab()` |
| Detailed Analysis | `dltsc.detailedAnalysisTab` | `detailedAnalysisTab.construct_detailedAnalysisTab()` |

Each tab module adds its own frame to `dltsc.tabControl` and sets its label.

A fifth frame, `dltsc.postprocessingTab`, is created but never added to the notebook. The call to `ppT.construct_postprocessingTab()` is commented out, and `postprocessingTab.py` is an empty file.

The only log in the application is the text box at the bottom of the **Input Parameters** tab. This module sets `dltsc.maxTextLineCount = 10`, so the log keeps only the 10 most recent lines (see `dltsConfig.log_to_textbox`).

### Closing the window

Clicking the window's close button calls `on_closing()`:

1. Every run-control button on the **Live Tools** tab is disabled (`ldT._set_run_control_buttons('returning')`).
2. `dltsc.run_abortRequested` is set to `True`. The run loop in `runDlts_Tools.dltsRun.run_experiment()` checks this flag before each step, and `_run_single_step()` checks it again after the stage move and after the acquisition. Data acquired while the flag is set is discarded.
3. If a temperature controller is connected (`dltsc.tempDev.state` is true), the code calls `tempDev.abort()`. It then commands a ramp to `tempDev.Troom` at `tempDev.roomRamp` °C/min. These two values come from **Room Temperature (C)** and **Room Ramp (C/min)** on the Input Parameters tab. They reach the device only when you click **Connect + Get Params** or **Apply + Push Params** in the temperature group. Until then the constructor defaults apply: 25 °C and 10 °C/min.
4. A small dialog opens, titled **Closing: returning to room temperature**. It shows:
   - "Returning the stage to room temperature (*Tr* °C at *ramp* °C/min). The program will close automatically when it arrives."
   - A bold status line, updated about every 2 s: `Stage at X °C → room temperature Y °C (R °C/min)`, or `Waiting for stage reading... (target Y °C)` if the controller cannot be read.
   - A button, **Close now (controller keeps ramping to *Tr* °C)**.
5. A background thread polls the stage temperature every 2 s:
   - **Arrived** (within `ROOM_TOLERANCE_C` = 0.5 °C of the target): the controller is disconnected **with** `:TEMPerature:STOP`, the impedance analyzer is disconnected, the process pools are shut down, and the window is destroyed.
   - **Timed out**: the program exits the same way, but **without** STOP, so the controller keeps ramping on its own. The time limit is `|Tr − T| / ramp × 60 s + ROOM_EXTRA_WAIT_S` (900 s), computed from the first successful reading. If no reading ever succeeds, the limit is 900 s from the start of the wait.
   - **Close now** (the button, or closing the dialog window): the program exits at once without STOP. The controller keeps ramping.
6. If no temperature controller is connected, or commanding the ramp raises an exception, the program skips the dialog. It disconnects the devices and closes at once, with `stopControl=True`. On an exception, the log first shows `Warning: could not command the room-temperature ramp on close: <error>`.

Clicking the main window's close button again while the dialog is open only raises the dialog.

### Exits that bypass the close button

- `atexit.register(_emergency_room_return)` runs on a normal interpreter exit. This includes Ctrl+C in the console and an unhandled exception that ends `mainloop()`.
- `SIGBREAK` and `SIGTERM` are mapped to `_on_console_close` when the platform defines them. On Windows, closing the console window or pressing Ctrl+Break delivers `SIGBREAK`.

Both paths command the room-temperature ramp once, if the close handler has not already done so (`dltsc.app_roomReturnSent`). They do not wait and do not send STOP.

## Import

The module is an entry point. The codebase does not import it and has no alias for it. Importing it is safe because all GUI construction sits behind `if __name__ == '__main__':`. Importing it still runs `matplotlib.use('TkAgg')` and imports every tab module.

```python
import DLTSGUI_MainWindow            # no GUI is built on import
```

The module imports the other parts of the application with these aliases, which the other reference pages also use:

```python
import dltsConfig as dltsc
import runParamsTab as rpT
import liveDataTab as ldT
import dataAnalysisTab as daT
import detailedAnalysisTab as deT
```

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `ROOM_TOLERANCE_C` | `0.5` (float, °C) | The close dialog treats the stage as arrived when `abs(Troom - T) <= 0.5`. |
| `ROOM_EXTRA_WAIT_S` | `900` (int, s) | Extra time allowed beyond the expected ramp time before the close dialog gives up waiting. |

`dltsConfig` globals this module reads or writes:

| Name | Access | Meaning |
|---|---|---|
| `root`, `tabControl` | write | Tk root and the `ttk.Notebook`. |
| `runParamsTab`, `livePlotTab`, `dataAnalysisTab`, `detailedAnalysisTab`, `postprocessingTab` | write | One `ttk.Frame` per tab. |
| `maxTextLineCount`, `textlinecount`, `textboxes` | write | Log setup: 10 lines, counter 0, empty list of text boxes. |
| `tempDev`, `impDev` | read | Connected devices, created on the Input Parameters tab. |
| `manual_transientExecutor`, `detailed_executor` | read | Process pools that are shut down on close. |
| `run_abortRequested` | write | Set to `True` when the room-temperature ramp is commanded. |
| `app_closing` | read/write | `True` once `on_closing()` has run. It prevents a second close sequence. |
| `app_roomReturnSent` | read/write | `True` once the room ramp has been sent. The emergency handlers skip their ramp when it is set. |
| `app_closeNowRequested` | read/write | `True` after **Close now**. It stops the wait thread. |
| `app_closeDialog`, `app_closeStatusLabel` | write | The close dialog and its status label. |

`dltsConfig.init()` is never called, so these flags start as `None`. The code only tests them for truthiness, so `None` works the same as `False`.

## Functions

### on_closing()

The window's `WM_DELETE_WINDOW` handler. It starts the close sequence described under "Closing the window".

**Returns** `None`.

**Side effects**
- Sets `dltsc.app_closing = True`. A repeat call only lifts `dltsc.app_closeDialog`, if it exists.
- Disables all Live Tools run buttons through `ldT._set_run_control_buttons('returning')`.
- Calls `_send_room_ramp(lockTimeout=5.0)`, which sets `dltsc.run_abortRequested` and sends a serial command to the temperature controller.
- Writes to the log.
- Either calls `_finish_close(stopControl=True)` at once (no controller connected), or opens the close dialog and starts a daemon thread running `_wait_for_room_temp`.

**Called by** the main window's close button (`dltsc.root.protocol("WM_DELETE_WINDOW", on_closing)`).

## Internal helpers

### _send_room_ramp(lockTimeout)

Sets `dltsc.run_abortRequested = True`. If `dltsc.tempDev` exists and its `state` is true, it calls `tempDev.abort()` and `tempDev.start_ramp(tempDev.Troom, tempDev.roomRamp, lockTimeout=lockTimeout)`, sets `dltsc.app_roomReturnSent = True`, and returns `(Troom, roomRamp)`. It returns `None` when no controller is connected. `lockTimeout` is how long, in seconds, to wait for the controller's serial lock. If the wait expires, `start_ramp` sends the command anyway.

### _emergency_room_return(*_)

The backstop registered with `atexit`, also called from `_on_console_close`. It does nothing if `dltsc.app_roomReturnSent` is already set. Otherwise it calls `_send_room_ramp(lockTimeout=2.0)` and ignores any exception. It does not wait for the ramp or send STOP.

### _on_console_close(signum, frame)

Signal handler for `SIGBREAK` and `SIGTERM`. It calls `_emergency_room_return()` and then `os._exit(1)`. Windows kills the process a few seconds after `SIGBREAK`, and `atexit` handlers do not run on that path.

### _finish_close(stopControl)

Disconnects the temperature controller with `disconnect_temp_controller(stopControl=stopControl)`, if it is connected. Then it disconnects the impedance analyzer (`disconnect_device()`). It calls `shutdown(wait=False, cancel_futures=True)` on `dltsc.manual_transientExecutor` and `dltsc.detailed_executor`, then runs `dltsc.root.destroy()`. Each device and executor step ignores its own exceptions. With `stopControl=False` the controller keeps ramping after the program exits.

### _close_now()

Handler for the **Close now** button and for closing the dialog window. It sets `dltsc.app_closeNowRequested = True` and calls `_finish_close(stopControl=False)`. A second call does nothing.

### _wait_for_room_temp(Tr, ramp)

Runs on a daemon thread. Every 2 s it reads `dltsc.tempDev.read_temp()`, compares the reading with `Tr`, and pushes the status text to `dltsc.app_closeStatusLabel` through `root.after(0, ...)`. It stops when the stage is within `ROOM_TOLERANCE_C`, when the deadline passes, or when **Close now** is requested. It then schedules `_finish_close(stopControl=(result == 'arrived'))` on the Tk thread. After **Close now** it returns without scheduling anything.

### _show_close_dialog(Tr, ramp)

Builds the `tk.Toplevel` close dialog described above. The dialog is transient to the root window and cannot be resized. It stores the dialog in `dltsc.app_closeDialog` and the status label in `dltsc.app_closeStatusLabel`.

## Startup sequence (`__main__` block)

1. `multiprocessing.freeze_support()`. The transient extraction (`liveDataTab._extract_transients_async`, used by Qualitative Analysis and by the Quick Analysis Offline Data column) and the Detailed Analysis tab use `ProcessPoolExecutor`. On Windows the `spawn` start method re-imports this script in each child process. The `__main__` guard stops a child from opening another GUI, and `freeze_support()` covers frozen executables.
2. Log setup, root window, window size, and notebook style.
3. `dltsc.tabControl = ttk.Notebook(dltsc.root, padding=0)`, then each tab frame is created and its `construct_*` function is called, in the order shown in the table above.
4. `root.protocol("WM_DELETE_WINDOW", on_closing)`, `atexit.register(_emergency_room_return)`, and the signal handlers.
5. `dltsc.root.mainloop()`.

## Notes and limitations

- The room-temperature target is whatever `tempDev.Troom` and `tempDev.roomRamp` hold at close time. If you edit **Room Temperature (C)** or **Room Ramp (C/min)** after connecting and do not click **Apply + Push Params**, the close sequence uses the older values.
- If no temperature controller is connected, closing destroys the window at once, even while a run thread is active. The run thread is a daemon and ends with the process.
- On a timeout, the program exits without STOP, so the controller keeps ramping. It stops the controller only when the stage actually reached room temperature.
- The wait thread calls `read_temp()` while a run thread may still be finishing a step. Both calls go through the controller's `_ioLock`, so their serial commands do not interleave.
- `_finish_close` shuts down the process pools with `wait=False`. A child process busy with an extraction is not waited for.
- `dltsConfig.init()` is not called. The tab modules seed the globals they need themselves.
- The log shows only the last 10 lines (`maxTextLineCount = 10`). Earlier messages are deleted from the text box.

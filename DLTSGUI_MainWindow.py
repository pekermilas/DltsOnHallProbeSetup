import tkinter as tk
import atexit
import multiprocessing
import os
import signal
import threading
import time
import matplotlib
matplotlib.use('TkAgg')

from tkinter import ttk

import dltsConfig as dltsc
import runParamsTab as rpT
import liveDataTab as ldT
import dataAnalysisTab as daT
import detailedAnalysisTab as deT


#---------------------CLOSE: RETURN STAGE TO ROOM TEMPERATURE-------------------------#
# Closing the window -- including in the middle of a run -- always sends the
# stage back to the Room Temperature / Room Ramp set on the Input Parameters
# tab: the run is aborted, the ramp is commanded right away, and a small
# dialog shows the stage temperature until it arrives (then the controller is
# stopped and the app exits). "Close now" exits without waiting and WITHOUT
# sending TEMPerature:STOP, so the controller keeps ramping to room
# temperature on its own. Exits that bypass the window (Ctrl+C, closing the
# console window) are covered by _emergency_room_return(), registered below.
ROOM_TOLERANCE_C = 0.5      # "arrived" when within this of Room Temperature
ROOM_EXTRA_WAIT_S = 900     # wait at most the expected ramp time plus this

def _send_room_ramp(lockTimeout):
    """Abort any run and command the room-temperature ramp. Returns
    (Troom, roomRamp), or None if no temperature controller is connected."""
    dltsc.run_abortRequested = True
    tempDev = dltsc.tempDev
    if tempDev is None or not getattr(tempDev, 'state', False):
        return None
    tempDev.abort()
    tempDev.start_ramp(tempDev.Troom, tempDev.roomRamp, lockTimeout=lockTimeout)
    dltsc.app_roomReturnSent = True
    return tempDev.Troom, tempDev.roomRamp

def _emergency_room_return(*_):
    """Backstop for exits that never reach on_closing() (Ctrl+C in the
    console, an unhandled exception ending mainloop, the console window being
    closed): command the ramp, if the close handler hasn't already. Doesn't
    wait or send STOP, so the controller carries the ramp out on its own."""
    if dltsc.app_roomReturnSent:
        return
    try:
        _send_room_ramp(lockTimeout=2.0)
    except Exception:
        pass

def _on_console_close(signum, frame):
    # Windows delivers the console window's close button / Ctrl+Break as
    # SIGBREAK and kills the process a few seconds later; atexit handlers
    # don't get to run on that path, so send the ramp here and exit.
    _emergency_room_return()
    os._exit(1)

def _finish_close(stopControl):
    """Disconnect everything and destroy the window. stopControl=False leaves
    the temperature controller running (still ramping to room temperature)."""
    try:
        if dltsc.tempDev is not None and getattr(dltsc.tempDev, 'state', False):
            dltsc.tempDev.disconnect_temp_controller(stopControl=stopControl)
    except Exception:
        pass
    try:
        if dltsc.impDev is not None and hasattr(dltsc.impDev, 'disconnect_device'):
            dltsc.impDev.disconnect_device()
    except Exception:
        pass
    for executor in (dltsc.manual_transientExecutor, dltsc.detailed_executor):
        try:
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
    dltsc.root.destroy()

def _close_now():
    """'Close now' in the waiting dialog: exit immediately, leaving the
    controller ramping to room temperature (no STOP)."""
    if dltsc.app_closeNowRequested:
        return
    dltsc.app_closeNowRequested = True
    _finish_close(stopControl=False)

def _wait_for_room_temp(Tr, ramp):
    """Background thread: poll the stage until it's at room temperature (or
    the wait times out), updating the dialog; then finish closing on the main
    thread -- stopping the controller only if the stage actually arrived."""
    deadline = time.time() + ROOM_EXTRA_WAIT_S
    deadlineFromRamp = False
    result = 'timeout'
    while not dltsc.app_closeNowRequested:
        try:
            T = dltsc.tempDev.read_temp()
        except Exception:
            T = None
        if T is not None and not deadlineFromRamp:
            deadline = time.time() + abs(Tr - T) / max(float(ramp), 1e-6) * 60.0 + ROOM_EXTRA_WAIT_S
            deadlineFromRamp = True
        if T is not None and abs(Tr - T) <= ROOM_TOLERANCE_C:
            result = 'arrived'
            break
        if time.time() > deadline:
            break
        text = (f'Stage at {T:.1f} °C  →  room temperature {Tr:g} °C  ({ramp:g} °C/min)'
                if T is not None else f'Waiting for stage reading...  (target {Tr:g} °C)')
        try:
            dltsc.root.after(0, lambda t=text: dltsc.app_closeStatusLabel.config(text=t))
        except Exception:
            return   # window already gone (Close now)
        time.sleep(2)

    if dltsc.app_closeNowRequested:
        return
    try:
        dltsc.root.after(0, lambda: _finish_close(stopControl=(result == 'arrived')))
    except Exception:
        pass

def _show_close_dialog(Tr, ramp):
    dlg = tk.Toplevel(dltsc.root)
    dlg.title('Closing: returning to room temperature')
    dlg.transient(dltsc.root)
    dlg.resizable(False, False)
    dlg.protocol('WM_DELETE_WINDOW', _close_now)
    frm = ttk.Frame(dlg, padding=14)
    frm.pack(fill='both', expand=True)
    ttk.Label(frm, text=f'Returning the stage to room temperature ({Tr:g} °C at {ramp:g} °C/min).\n'
                        'The program will close automatically when it arrives.',
              justify='left').pack(anchor='w')
    dltsc.app_closeStatusLabel = ttk.Label(frm, text='Reading stage temperature...', font=('Segoe UI', 10, 'bold'))
    dltsc.app_closeStatusLabel.pack(anchor='w', pady=(10, 10))
    ttk.Button(frm, text=f'Close now (controller keeps ramping to {Tr:g} °C)', command=_close_now).pack(fill='x')
    dltsc.app_closeDialog = dlg
    dlg.lift()

def on_closing():
    if dltsc.app_closing:
        if dltsc.app_closeDialog is not None:
            dltsc.app_closeDialog.lift()
        return
    dltsc.app_closing = True
    ldT._set_run_control_buttons('returning')   # nothing may start while closing
    try:
        target = _send_room_ramp(lockTimeout=5.0)
    except Exception as exc:
        dltsc.log_to_textbox(f"Warning: could not command the room-temperature ramp on close: {exc}")
        target = None
    if target is None:   # no connected temperature controller (or it failed): just close
        _finish_close(stopControl=True)
        return
    dltsc.log_to_textbox(f"Closing: stage returning to room temperature ({target[0]:g} °C).")
    _show_close_dialog(*target)
    threading.Thread(target=_wait_for_room_temp, args=target, daemon=True).start()


# Qualitative Analysis' transient extraction runs in a separate process (see
# liveDataTab._compute_zi_transients/_compute_legacy_transients) so it never
# contends with the Tk main thread for the GIL, keeping tab switches and
# redraws responsive no matter how long that extraction takes. Windows'
# 'spawn' start method re-imports this script in the child process, so
# everything that builds/runs the GUI must be guarded behind __name__ ==
# '__main__' -- otherwise the child would open a second GUI (and that one a
# third, ...) instead of just running the extraction function it was asked for.
if __name__ == '__main__':
    multiprocessing.freeze_support()

    dltsc.maxTextLineCount = 10
    dltsc.textlinecount = 0
    dltsc.textboxes = []
    dltsc.root = tk.Tk()
    dltsc.root.title('DLTS Control GUI')
    try:
        # Start maximized: the Live Tools tab is dense enough that the extra room
        # keeps it from feeling crowded on typical displays.
        dltsc.root.state('zoomed')
    except Exception:
        try:
            screen_w = dltsc.root.winfo_screenwidth()
            screen_h = dltsc.root.winfo_screenheight()
            dltsc.root.geometry(f'{screen_w}x{screen_h}+0+0')
        except Exception:
            pass
    try:
        screen_h = dltsc.root.winfo_screenheight()
        min_h = min(780, max(760, screen_h - 180))
        dltsc.root.minsize(860, min_h)
    except Exception:
        pass

    s = ttk.Style()
    s.configure('TNotebook.Tab', font=('Arial', 11), padding=6)

    dltsc.tabControl = ttk.Notebook(dltsc.root, padding=0)


    dltsc.runParamsTab = ttk.Frame(dltsc.tabControl)
    rpT.construct_runParamsTab()

    dltsc.livePlotTab = ttk.Frame(dltsc.tabControl)
    ldT.construct_livePlotTab()

    dltsc.dataAnalysisTab = ttk.Frame(dltsc.tabControl)
    daT.construct_dataAnalysisTab()

    dltsc.detailedAnalysisTab = ttk.Frame(dltsc.tabControl)
    deT.construct_detailedAnalysisTab()

    dltsc.postprocessingTab = ttk.Frame(dltsc.tabControl)
    # ppT.construct_postprocessingTab()

    dltsc.root.protocol("WM_DELETE_WINDOW", on_closing)
    # Backstops for exits that bypass the window's close button (see
    # _emergency_room_return): normal interpreter exit / Ctrl+C, and the
    # console window being closed (SIGBREAK on Windows).
    atexit.register(_emergency_room_return)
    for sigName in ('SIGBREAK', 'SIGTERM'):
        if hasattr(signal, sigName):
            signal.signal(getattr(signal, sigName), _on_console_close)
    dltsc.root.mainloop()
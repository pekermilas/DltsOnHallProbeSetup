import tkinter as tk
import threading
import os
import time
import re
import json
from concurrent.futures import ProcessPoolExecutor

from tkinter import ttk
from tkinter import filedialog

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import dltsConfig as dltsc
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT

# Denoising methods exposed by impedanceAnalysis_Tools.impdData.filter_emissions().
DENOISE_METHODS = ['pca', 'wavelet', 'sgolay', 'lowess']

# Legacy per-temperature filename pattern, ported from DrKayisScript.py's Tab 1 loader.
_LEGACY_FILENAME_PATTERN = re.compile(r'^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt|csv)$')


#---------------------DLTS RUN CONTROL (PAUSE / RESUME / REDO / RETAKE)-------------------------#
# dltsc.run_busy gates hardware access: only one of the main sequence, a resume,
# a redo, or a retake may be driving the connected devices at a time. Pausing
# does NOT tear the run down -- the same dltsc.run_dltsInstance, with devices
# still connected and dltsRun.currentStepIndex remembering where it stopped,
# is reused by Resume/Redo/Retake, so pausing and resuming (or redoing/retaking
# specific steps in between) never re-runs init_experiment() or reconnects.
def start_dlts():
    dltsc.log_to_textbox("DLTS run started...")
    dlts = rdT.dltsRun()
    dltsc.run_dltsInstance = dlts
    run = dlts.init_experiment()
    if run < 0:
        dltsc.log_to_textbox("Error: Failed to initialize the experiment.")

        def applyInitFailure():
            dltsc.run_busy = False
            _set_run_control_buttons('idle')
        dltsc.root.after(0, applyInitFailure)
        return

    dltsc.log_to_textbox("Experiment initialized successfully.")
    for i in range(len(dlts.tempDevice.tempGrid)):
        dlts.stepStatus[i] = 'pending'
    dltsc.root.after(0, _refresh_step_listbox)

    status = dlts.run_experiment()

    def apply():
        _handle_run_status(status, isMainSequence=True)
    dltsc.root.after(0, apply)

def start_thread():
    if dltsc.run_busy:
        return
    # Reset the live-mode plot state, switch the display to Live, and start
    # watching for output files. This runs on the Tk main thread (the button
    # callback), so the poll loop that follows never has to touch Tkinter from
    # the background run thread. Any Offline data already loaded is untouched.
    dltsc.run_busy = True
    dltsc.run_pauseRequested = False
    dltsc.run_paused = False
    _set_run_control_buttons('running')
    _reset_live_plot_state('live')
    _schedule_live_poll(dltsc.livePlot_liveRunToken)

    taskThread = threading.Thread(target=start_dlts)
    taskThread.daemon = True
    taskThread.start()
    dltsc.root.after(200, _poll_step_listbox_while_busy)

def _pause_run():
    if not dltsc.run_busy:
        return
    dltsc.run_pauseRequested = True
    if dltsc.run_pauseButton is not None:
        dltsc.run_pauseButton.config(state="disabled")
    dltsc.log_to_textbox("Pause requested; the run will stop after the current temperature step completes.")

def _run_control_thread(indices=None, deleteFirst=False, isMainSequence=False):
    """Common launcher for resuming the main sequence (indices=None) and for
    redo/retake (indices=[...]); start_thread() launches the very first run of
    a session separately since it also resets the live-plot watch state.
    """
    if dltsc.run_dltsInstance is None or dltsc.run_busy:
        return
    dltsc.run_busy = True
    dltsc.run_pauseRequested = False
    _set_run_control_buttons('running')

    def worker():
        status = dltsc.run_dltsInstance.run_experiment(indices=indices, deleteFirst=deleteFirst)

        def apply():
            _handle_run_status(status, isMainSequence)
        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()
    dltsc.root.after(200, _poll_step_listbox_while_busy)

def _resume_run():
    if dltsc.run_dltsInstance is None or dltsc.run_busy:
        return
    dltsc.log_to_textbox("Resuming run...")
    _run_control_thread(indices=None, isMainSequence=True)

def _get_selected_step_indices():
    if dltsc.run_stepListbox is None:
        return []
    return list(dltsc.run_stepListbox.curselection())

def _redo_selected_steps():
    indices = _get_selected_step_indices()
    if not indices:
        dltsc.log_to_textbox("Redo: select at least one step from the list first.")
        return
    if dltsc.run_dltsInstance is None or dltsc.run_busy:
        return
    dltsc.log_to_textbox(f"Redoing {len(indices)} step(s)...")
    _run_control_thread(indices=indices, deleteFirst=False, isMainSequence=False)

def _retake_selected_steps():
    indices = _get_selected_step_indices()
    if not indices:
        dltsc.log_to_textbox("Remove & Retake: select at least one step from the list first.")
        return
    if dltsc.run_dltsInstance is None or dltsc.run_busy:
        return
    dltsc.log_to_textbox(f"Removing and retaking {len(indices)} step(s)...")
    _run_control_thread(indices=indices, deleteFirst=True, isMainSequence=False)

def _set_run_control_buttons(mode):
    """mode: 'idle' (nothing has ever run) / 'running' / 'paused' /
    'idle_with_instance' (completed or errored, but the run instance and its
    connected devices are still there for Resume/Redo/Retake).
    """
    hasInstance = dltsc.run_dltsInstance is not None
    tempGrid = getattr(getattr(dltsc.run_dltsInstance, 'tempDevice', None), 'tempGrid', None) if hasInstance else None
    canResume = hasInstance and tempGrid is not None and dltsc.run_dltsInstance.currentStepIndex < len(tempGrid)

    if mode == 'running':
        buttonStates = dict(run=False, pause=True, resume=False, redo=False, retake=False)
    elif mode == 'paused':
        buttonStates = dict(run=False, pause=False, resume=True, redo=True, retake=True)
    elif mode == 'idle_with_instance':
        buttonStates = dict(run=True, pause=False, resume=canResume, redo=True, retake=True)
    else:
        buttonStates = dict(run=True, pause=False, resume=False, redo=False, retake=False)

    widgets = dict(run=dltsc.run_button, pause=dltsc.run_pauseButton, resume=dltsc.run_resumeButton,
                   redo=dltsc.run_redoButton, retake=dltsc.run_retakeButton)
    for key, enabled in buttonStates.items():
        widget = widgets.get(key)
        if widget is not None:
            widget.config(state="normal" if enabled else "disabled")

def _handle_run_status(status, isMainSequence):
    dltsc.run_busy = False
    _refresh_step_listbox()
    if status == 'completed':
        if isMainSequence:
            dltsc.run_dltsInstance.finish_experiment()
            dltsc.log_to_textbox("DLTS run completed!")
        else:
            dltsc.log_to_textbox("Redo/Retake completed.")
        dltsc.run_paused = False
        _set_run_control_buttons('idle_with_instance')
    elif status == 'paused':
        dltsc.run_paused = True
        dltsc.log_to_textbox("Run paused. Click Resume to continue, or Redo/Remove & Retake specific steps below.")
        _set_run_control_buttons('paused')
    else:
        dltsc.log_to_textbox("Run stopped due to an error. Devices remain connected; Resume/Redo/Retake are available.")
        _set_run_control_buttons('idle_with_instance')

def _refresh_step_listbox():
    if dltsc.run_stepListbox is None or dltsc.run_dltsInstance is None:
        return
    tempGrid = getattr(dltsc.run_dltsInstance.tempDevice, 'tempGrid', None)
    if tempGrid is None:
        return
    stepStatus = dltsc.run_dltsInstance.stepStatus
    selected = set(dltsc.run_stepListbox.curselection())
    dltsc.run_stepListbox.delete(0, tk.END)
    for i, t in enumerate(tempGrid):
        status = stepStatus.get(i, 'pending')
        dltsc.run_stepListbox.insert(tk.END, f"{i + 1}. {t:.2f} °C — {status}")
    for i in selected:
        if i < dltsc.run_stepListbox.size():
            dltsc.run_stepListbox.select_set(i)

def _poll_step_listbox_while_busy():
    _refresh_step_listbox()
    if dltsc.run_busy:
        dltsc.root.after(500, _poll_step_listbox_while_busy)


#---------------------AUTOMATED / LIVE DATA VISUALIZATION-------------------------#
# Live and Offline each keep their own impdData instance + snapshots + dataset
# selection (dltsc.livePlot_live*/livePlot_offline*), so loading one never discards
# the other; dltsc.livePlot_activeMode picks which of the two is currently drawn.
def _active_impd():
    if dltsc.livePlot_activeMode == 'offline':
        return dltsc.livePlot_offlineImpdData
    return dltsc.livePlot_liveImpdData

def _active_emission0Data():
    data = (dltsc.livePlot_offlineEmission0Data if dltsc.livePlot_activeMode == 'offline'
            else dltsc.livePlot_liveEmission0Data)
    return data or {}

def _active_allEmissionsData():
    data = (dltsc.livePlot_offlineAllEmissionsData if dltsc.livePlot_activeMode == 'offline'
            else dltsc.livePlot_liveAllEmissionsData)
    return data or {}

def _mode_label(mode):
    return 'Live' if mode == 'live' else 'Offline'

def _reset_auto_plot_placeholder():
    """Clear both automated-plot axes and show a waiting-for-data placeholder."""
    if dltsc.livePlot_axEmission0 is None or dltsc.livePlot_axAllEmissions is None:
        return

    ax0 = dltsc.livePlot_axEmission0
    ax1 = dltsc.livePlot_axAllEmissions
    ax0.clear()
    ax1.clear()
    ax0.text(0.5, 0.5, 'Waiting for data...', ha='center', va='center', transform=ax0.transAxes)
    ax0.set_title('Emission 0')
    ax1.text(0.5, 0.5, 'Waiting for data...', ha='center', va='center', transform=ax1.transAxes)
    ax1.set_title('All Emissions Aligned')

    if dltsc.livePlot_canvas is not None:
        dltsc.livePlot_canvas.draw()

    if dltsc.livePlot_datasetCombo is not None:
        dltsc.livePlot_datasetCombo['values'] = []
    if dltsc.livePlot_datasetVar is not None:
        dltsc.livePlot_datasetVar.set('')

def _reset_live_plot_state(mode):
    """Clear one mode's ('live' or 'offline') plot state ahead of a (re)start, then
    switch the display to that mode. The other mode's data is left untouched so the
    user can still switch back to it.
    """
    if mode == 'live':
        dltsc.livePlot_liveRunToken = (dltsc.livePlot_liveRunToken or 0) + 1
        dltsc.livePlot_liveImpdData = None
        dltsc.livePlot_liveEmission0Data = {}
        dltsc.livePlot_liveAllEmissionsData = {}
        dltsc.livePlot_liveDatasetSel = None
        dltsc.livePlot_processedFiles = set()
        dltsc.livePlot_liveIngestBusy = False
        if dltsc.livePlot_pollAfterId is not None:
            try:
                dltsc.root.after_cancel(dltsc.livePlot_pollAfterId)
            except Exception:
                pass
            dltsc.livePlot_pollAfterId = None
    else:
        dltsc.livePlot_offlineRunToken = (dltsc.livePlot_offlineRunToken or 0) + 1
        dltsc.livePlot_offlineImpdData = None
        dltsc.livePlot_offlineEmission0Data = {}
        dltsc.livePlot_offlineAllEmissionsData = {}
        dltsc.livePlot_offlineDatasetSel = None
        dltsc.livePlot_offlineIngestBusy = False

    _set_livePlot_mode(mode)

def _set_livePlot_mode(newMode):
    """Switch which mode (Live/Offline) is currently drawn, preserving both sides'
    state and last-viewed dataset so the user can freely go back and forth.
    """
    oldMode = dltsc.livePlot_activeMode
    if oldMode == 'live' and dltsc.livePlot_datasetVar is not None:
        dltsc.livePlot_liveDatasetSel = dltsc.livePlot_datasetVar.get()
    elif oldMode == 'offline' and dltsc.livePlot_datasetVar is not None:
        dltsc.livePlot_offlineDatasetSel = dltsc.livePlot_datasetVar.get()

    dltsc.livePlot_activeMode = newMode
    if dltsc.livePlot_modeVar is not None and dltsc.livePlot_modeVar.get() != newMode:
        dltsc.livePlot_modeVar.set(newMode)

    impd = _active_impd()
    if impd is not None and impd.dataTemps:
        preferred = dltsc.livePlot_liveDatasetSel if newMode == 'live' else dltsc.livePlot_offlineDatasetSel
        _update_dataset_dropdown(impd.dataTemps, preferred=preferred)
        if dltsc.livePlot_statusLabel is not None:
            dltsc.livePlot_statusLabel.config(
                text=f'{_mode_label(newMode)}: {len(impd.dataTemps)} temperature(s) loaded.')
        _redraw_auto_plots()
    else:
        _reset_auto_plot_placeholder()
        if dltsc.livePlot_statusLabel is not None:
            dltsc.livePlot_statusLabel.config(text=f'{_mode_label(newMode)}: waiting for data...')

def _on_mode_toggle():
    """Live/Offline radio buttons changed: switch the displayed mode."""
    if dltsc.livePlot_modeVar is not None:
        _set_livePlot_mode(dltsc.livePlot_modeVar.get())

def _format_dataset_label(t):
    """Format a dataset's Kelvin temperature as 'K (C)', e.g. 273 (0) or 271 (-2)."""
    try:
        celsius = round(t - 273.15)
    except TypeError:
        return str(t)
    return f"{t} ({celsius})"

def _get_selected_dataset_temp():
    """Return the currently selected dataset's temperature key, or None."""
    var = dltsc.livePlot_datasetVar
    if var is None:
        return None
    raw = var.get()
    if not raw:
        return None
    kelvinPart = raw.split(' (')[0]
    try:
        return int(kelvinPart)
    except ValueError:
        try:
            return float(kelvinPart)
        except ValueError:
            return None

def _update_dataset_dropdown(temps, preferred=None):
    """Refresh the dataset dropdown's values.

    Each entry is labeled with its Kelvin value and the equivalent Celsius value
    in parentheses (e.g. '273 (0)'). Selects `preferred` (a previously-viewed
    dataset label, e.g. when switching modes back) if it is still available,
    otherwise the most recently added one.
    """
    if dltsc.livePlot_datasetCombo is None or dltsc.livePlot_datasetVar is None:
        return
    values = [_format_dataset_label(t) for t in temps]
    dltsc.livePlot_datasetCombo['values'] = values
    if not values:
        dltsc.livePlot_datasetVar.set('')
    elif preferred is not None and preferred in values:
        dltsc.livePlot_datasetVar.set(preferred)
    else:
        dltsc.livePlot_datasetVar.set(values[-1])

def _on_dataset_selected(*_args):
    """Dataset dropdown changed: just redraw from already-computed snapshots (cheap)."""
    _redraw_auto_plots()

def _schedule_live_poll(token):
    """Poll dltsc.run_dataFileNames on the Tk main loop for newly written temperature files.

    There is no write-completion callback from runDlts_Tools.dltsRun, so this is the
    only way to detect new files. `token` is compared against dltsc.livePlot_liveRunToken
    on every tick so a watcher from a previous run stops rescheduling itself once a
    new run has started; it runs independently of whatever _load_offline_run() does.
    """
    if token != dltsc.livePlot_liveRunToken:
        return

    if dltsc.run_outputFileType == 'hdf5':
        if dltsc.livePlot_activeMode == 'live' and dltsc.livePlot_statusLabel is not None:
            dltsc.livePlot_statusLabel.config(text='Live plotting is not yet supported for HDF5 output.')
        dltsc.livePlot_pollAfterId = None
        return

    fileNames = dltsc.run_dataFileNames or []
    allIngested = fileNames and len(dltsc.livePlot_processedFiles) >= len(fileNames)

    # Clustering cost grows with the number of ingested temperatures (confirmed against
    # a real 100+ temperature run), so a batch is processed on a background thread rather
    # than the Tk main thread; skip starting a new batch while one is still running.
    if not dltsc.livePlot_liveIngestBusy and not allIngested:
        newFiles = [f for f in fileNames if f not in dltsc.livePlot_processedFiles and os.path.exists(f)]
        if newFiles:
            _ingest_files_async(newFiles, token)

    if allIngested:
        if dltsc.livePlot_activeMode == 'live' and dltsc.livePlot_statusLabel is not None:
            dltsc.livePlot_statusLabel.config(text=f'Run complete: {len(fileNames)} temperature(s) loaded.')
        dltsc.livePlot_pollAfterId = None
        return

    dltsc.livePlot_pollAfterId = dltsc.root.after(1000, lambda: _schedule_live_poll(token))

def _ingest_files_async(paths, token):
    """Load newly-written temperature files on a background thread, then redraw.

    Only plain Python/impdData work happens on the worker thread; the resulting
    redraw and status-label update are marshaled back onto the Tk main thread via
    root.after(), since Tkinter/matplotlib calls are not safe off the main thread.
    Writes only to the Live-mode state; if the user is currently viewing Offline,
    the dropdown/plot are left alone and only refreshed next time Live is shown.
    """
    dltsc.livePlot_liveIngestBusy = True
    if dltsc.livePlot_activeMode == 'live' and dltsc.livePlot_statusLabel is not None:
        dltsc.livePlot_statusLabel.config(text=f'Processing {len(paths)} new file(s)...')
    method = dltsc.livePlot_denoiseMethodVar.get() if dltsc.livePlot_denoiseMethodVar is not None else DENOISE_METHODS[0]

    def worker():
        impd = dltsc.livePlot_liveImpdData
        processedOk = []
        errorMsgs = []
        try:
            for path in paths:
                try:
                    freshlyCreated = impd is None
                    if freshlyCreated:
                        impd = iaT.impdData(fName=[path])
                        result = impd.read_data()
                    else:
                        result = impd.append_data(fName=[path])

                    if result != 0:
                        errorMsgs.append(f"failed to load {os.path.basename(path)}.")
                        if freshlyCreated:
                            impd = None  # retry a fresh read_data() on the next file/tick
                        continue

                    processedOk.append(path)
                except Exception as exc:
                    errorMsgs.append(f"error processing {os.path.basename(path)}: {exc}")

            emission0Snapshot = None
            allEmissionsSnapshot = None
            if impd is not None and processedOk:
                impd.cleanup_data()
                # selected_emissions() only (re)computes clusters when
                # dataEmissionClusterParams is None, so force a recompute here to
                # pick up the newly appended temperature(s). This first call is the
                # only expensive one (GMM/KMeans clustering); the second call below
                # reuses the now-cached cluster params and is cheap.
                impd.dataEmissionClusterParams = None
                impd.selected_emissions(emissionIndex=0)
                # Denoising is also expensive across many temperatures (confirmed
                # against a real 100+ temperature run), so it runs here on the
                # worker thread too rather than in the main-thread redraw.
                try:
                    impd.filter_emissions(method=method, emissionIndex=0, recalculate=True, interactivePlot=False)
                except Exception as exc:
                    errorMsgs.append(f"denoise ({method}) failed: {exc}")
                emission0Snapshot = {T: dict(rec) for T, rec in impd.dataEmissions.items()}

                impd.selected_emissions(emissionIndex=-1)
                allEmissionsSnapshot = {T: dict(rec) for T, rec in impd.dataEmissions.items()}
        except Exception as exc:
            errorMsgs.append(f"error during clustering: {exc}")

        def apply():
            dltsc.livePlot_liveIngestBusy = False
            if token != dltsc.livePlot_liveRunToken:
                return  # a newer run has invalidated this batch

            for msg in errorMsgs:
                dltsc.log_to_textbox(f"Live plot: {msg}")

            if impd is not None and processedOk:
                dltsc.livePlot_liveImpdData = impd
                dltsc.livePlot_processedFiles.update(processedOk)
                if emission0Snapshot is not None:
                    dltsc.livePlot_liveEmission0Data = emission0Snapshot
                if allEmissionsSnapshot is not None:
                    dltsc.livePlot_liveAllEmissionsData = allEmissionsSnapshot
                if dltsc.livePlot_activeMode == 'live':
                    if dltsc.livePlot_statusLabel is not None:
                        nTemps = len(impd.dataTemps or [])
                        dltsc.livePlot_statusLabel.config(text=f'Live: {nTemps} temperature(s) loaded.')
                    _update_dataset_dropdown(impd.dataTemps)
                    _redraw_auto_plots()

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _recompute_denoise_and_redraw(*_args):
    """Recompute filter_emissions() for the newly selected method, then redraw.

    Bound to the denoise dropdown. Applies to whichever mode (Live/Offline) is
    currently displayed. Runs on a background thread for the same reason as the
    ingest worker above: filter_emissions() is expensive across many temperatures
    and must not block the Tk main thread.
    """
    mode = dltsc.livePlot_activeMode
    impd = _active_impd()
    if impd is None or not impd.dataTemps:
        return
    busy = dltsc.livePlot_liveIngestBusy if mode == 'live' else dltsc.livePlot_offlineIngestBusy
    if busy:
        return  # a load/ingest for this mode is already in flight and will apply this method itself

    method = dltsc.livePlot_denoiseMethodVar.get() if dltsc.livePlot_denoiseMethodVar is not None else DENOISE_METHODS[0]
    token = dltsc.livePlot_liveRunToken if mode == 'live' else dltsc.livePlot_offlineRunToken
    if mode == 'live':
        dltsc.livePlot_liveIngestBusy = True
    else:
        dltsc.livePlot_offlineIngestBusy = True

    def worker():
        emission0Snapshot = None
        try:
            # selected_emissions() is cheap here since dataEmissionClusterParams is
            # already cached; only filter_emissions() is expensive, and only for
            # the single emission-0 block (the all-emissions-aligned data is raw,
            # unaffected by the denoise method).
            impd.selected_emissions(emissionIndex=0)
            impd.filter_emissions(method=method, emissionIndex=0, recalculate=True, interactivePlot=False)
            emission0Snapshot = {T: dict(rec) for T, rec in impd.dataEmissions.items()}
        except Exception as exc:
            dltsc.root.after(0, lambda: dltsc.log_to_textbox(f"Live plot: denoise ({method}) failed: {exc}"))

        def finish():
            currentToken = dltsc.livePlot_liveRunToken if mode == 'live' else dltsc.livePlot_offlineRunToken
            if mode == 'live':
                dltsc.livePlot_liveIngestBusy = False
            else:
                dltsc.livePlot_offlineIngestBusy = False
            if currentToken == token and emission0Snapshot is not None:
                if mode == 'live':
                    dltsc.livePlot_liveEmission0Data = emission0Snapshot
                else:
                    dltsc.livePlot_offlineEmission0Data = emission0Snapshot
                if dltsc.livePlot_activeMode == mode:
                    _redraw_auto_plots()
        dltsc.root.after(0, finish)

    threading.Thread(target=worker, daemon=True).start()

def _redraw_auto_plots(*_args):
    """Draw the emission-0 (raw + denoised) and all-emissions-aligned subplots for
    the currently selected dataset (temperature) in the currently active mode.

    Only reads already-computed snapshots (filter_emissions() runs elsewhere, on a
    background thread) so this stays cheap enough to call directly on the main
    thread, including in response to the dataset dropdown changing selection.
    """
    ax0 = dltsc.livePlot_axEmission0
    ax1 = dltsc.livePlot_axAllEmissions
    emission0Data = _active_emission0Data()
    allEmissionsData = _active_allEmissionsData()
    if ax0 is None or ax1 is None or not emission0Data:
        _reset_auto_plot_placeholder()
        return

    selectedTemp = _get_selected_dataset_temp()
    if selectedTemp is None or selectedTemp not in emission0Data:
        # The dropdown's current selection doesn't resolve to a temperature
        # this mode actually has an emission-0 snapshot for -- e.g. the most
        # recently ingested temperature failed clustering and never got one.
        # Recover onto the latest temperature that DOES have data instead of
        # silently leaving whatever was drawn before (a previous run, or the
        # other mode) on screen, which is what made switching modes look like
        # it got permanently stuck.
        if not emission0Data:
            _reset_auto_plot_placeholder()
            return
        selectedTemp = sorted(emission0Data.keys())[-1]
        if dltsc.livePlot_datasetVar is not None:
            dltsc.livePlot_datasetVar.set(_format_dataset_label(selectedTemp))

    method = dltsc.livePlot_denoiseMethodVar.get() if dltsc.livePlot_denoiseMethodVar is not None else DENOISE_METHODS[0]

    ax0.clear()
    ax1.clear()

    sig0 = emission0Data.get(selectedTemp, {})
    x0 = np.asarray(sig0.get('xTimeStampImps', sig0.get('x', [])))
    yRaw0 = np.asarray(sig0.get('ymean', sig0.get('y', [])))
    if x0.size and yRaw0.size:
        ax0.plot(x0, yRaw0, color='0.5', linewidth=1, label='Raw')
    if 'yFiltered' in sig0:
        ax0.plot(x0, np.asarray(sig0['yFiltered']), color='C1', linewidth=1.5,
                  label=f'Denoised ({method})')
    ax0.set_title(f'Emission 0 (T = {selectedTemp} K)')
    ax0.set_xlabel('Time (s)')
    ax0.set_ylabel('Impedance Im (F)')
    ax0.legend(loc='best', fontsize=8)

    sigAll = allEmissionsData.get(selectedTemp, {})
    xAll = np.asarray(sigAll.get('xTimeStampImps', sigAll.get('x', [])))
    yAll = np.asarray(sigAll.get('y', []))
    if xAll.size and yAll.size:
        if yAll.ndim == 1:
            ax1.plot(xAll, yAll, color='C0', linewidth=1)
        else:
            cmap = plt.get_cmap('viridis')
            nRepeats = yAll.shape[1]
            for j in range(nRepeats):
                color = cmap(j / max(nRepeats - 1, 1))
                ax1.plot(xAll, yAll[:, j], color=color, linewidth=1, label=f'#{j + 1}')
            if nRepeats <= 12:
                ax1.legend(loc='best', fontsize=7, ncol=2)
    ax1.set_title(f'All Emissions Aligned (T = {selectedTemp} K)')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Impedance Im (F)')

    dltsc.livePlot_figure.tight_layout(pad=2.0, w_pad=3.0)
    dltsc.livePlot_canvas.draw()

def _load_offline_run():
    """Load a previously completed run's data files for offline automated-plot viewing.

    Runs on a background thread: confirmed against a real 100+ temperature run that
    read_data()/cleanup_data()/selected_emissions() can take well over a minute, which
    would otherwise freeze the whole GUI (not just this tab) for that entire time.
    This only ever touches the Offline-mode state, so a Live run being watched in
    the background keeps ingesting undisturbed.
    """
    files = filedialog.askopenfilenames(
        title="Select DLTS Data Files (Offline Run)",
        filetypes=[("Text/JSON files", "*.txt *.json"), ("CSV files", "*.csv"), ("All files", "*.*")]
    )
    if not files:
        return

    _reset_live_plot_state('offline')
    token = dltsc.livePlot_offlineRunToken
    dltsc.livePlot_offlineIngestBusy = True
    method = dltsc.livePlot_denoiseMethodVar.get() if dltsc.livePlot_denoiseMethodVar is not None else DENOISE_METHODS[0]
    if dltsc.livePlot_statusLabel is not None:
        dltsc.livePlot_statusLabel.config(
            text=f'Loading {len(files)} offline file(s) — this can take a while for many temperatures...')

    def worker():
        emission0Snapshot = None
        allEmissionsSnapshot = None
        impd = None
        try:
            impd = iaT.impdData(fName=list(files))
            result = impd.read_data()
            if result != 0:
                dltsc.root.after(0, lambda: dltsc.log_to_textbox(
                    "Live plot: failed to load the selected offline files."))
                return

            impd.cleanup_data()
            impd.selected_emissions(emissionIndex=0)
            try:
                impd.filter_emissions(method=method, emissionIndex=0, recalculate=True, interactivePlot=False)
            except Exception as exc:
                dltsc.root.after(0, lambda: dltsc.log_to_textbox(f"Live plot: denoise ({method}) failed: {exc}"))
            emission0Snapshot = {T: dict(rec) for T, rec in impd.dataEmissions.items()}

            impd.selected_emissions(emissionIndex=-1)
            allEmissionsSnapshot = {T: dict(rec) for T, rec in impd.dataEmissions.items()}
        except Exception as exc:
            dltsc.root.after(0, lambda: dltsc.log_to_textbox(
                f"Live plot: error processing offline data: {exc}"))
            return
        finally:
            def clearBusy():
                dltsc.livePlot_offlineIngestBusy = False
            dltsc.root.after(0, clearBusy)

        def apply():
            if token != dltsc.livePlot_offlineRunToken:
                return  # a newer offline load has invalidated this one
            dltsc.livePlot_offlineImpdData = impd
            dltsc.livePlot_offlineEmission0Data = emission0Snapshot
            dltsc.livePlot_offlineAllEmissionsData = allEmissionsSnapshot
            if dltsc.livePlot_activeMode == 'offline':
                if dltsc.livePlot_statusLabel is not None:
                    dltsc.livePlot_statusLabel.config(text=f'Offline: {len(impd.dataTemps)} temperature(s) loaded.')
                _update_dataset_dropdown(impd.dataTemps)
                _redraw_auto_plots()

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _build_autoPlotFrame(parent):
    # dltsConfig.init() (which would normally seed these) is not called by
    # DLTSGUI_MainWindow.py, so seed them here to be safe regardless of that wiring.
    if dltsc.livePlot_activeMode is None:
        dltsc.livePlot_activeMode = 'live'
    if dltsc.livePlot_liveRunToken is None:
        dltsc.livePlot_liveRunToken = 0
    if dltsc.livePlot_offlineRunToken is None:
        dltsc.livePlot_offlineRunToken = 0
    if dltsc.livePlot_processedFiles is None:
        dltsc.livePlot_processedFiles = set()
    if dltsc.livePlot_liveIngestBusy is None:
        dltsc.livePlot_liveIngestBusy = False
    if dltsc.livePlot_offlineIngestBusy is None:
        dltsc.livePlot_offlineIngestBusy = False
    for attr in ('livePlot_liveEmission0Data', 'livePlot_liveAllEmissionsData',
                 'livePlot_offlineEmission0Data', 'livePlot_offlineAllEmissionsData'):
        if getattr(dltsc, attr) is None:
            setattr(dltsc, attr, dict())

    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    controlsFrame = tk.Frame(parent)
    controlsFrame.grid(row=0, column=0, sticky='ew', padx=4, pady=4)

    ttk.Label(controlsFrame, text='Automated / Live Data', font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(0, 10))

    ttk.Label(controlsFrame, text='View:').pack(side='left', padx=(0, 2))
    dltsc.livePlot_modeVar = tk.StringVar(value=dltsc.livePlot_activeMode)
    ttk.Radiobutton(controlsFrame, text='Live', variable=dltsc.livePlot_modeVar, value='live',
                    command=_on_mode_toggle).pack(side='left')
    ttk.Radiobutton(controlsFrame, text='Offline', variable=dltsc.livePlot_modeVar, value='offline',
                    command=_on_mode_toggle).pack(side='left', padx=(0, 10))

    ttk.Button(controlsFrame, text='Load Existing Run (Offline)', command=_load_offline_run).pack(side='left', padx=4)

    ttk.Label(controlsFrame, text='Dataset:').pack(side='left', padx=(10, 2))
    dltsc.livePlot_datasetVar = tk.StringVar(value='')
    dltsc.livePlot_datasetCombo = ttk.Combobox(controlsFrame, textvariable=dltsc.livePlot_datasetVar,
                                               values=[], width=10, state='readonly')
    dltsc.livePlot_datasetCombo.pack(side='left', padx=4)
    dltsc.livePlot_datasetCombo.bind('<<ComboboxSelected>>', _on_dataset_selected)

    ttk.Label(controlsFrame, text='Denoise Method:').pack(side='left', padx=(10, 2))
    dltsc.livePlot_denoiseMethodVar = tk.StringVar(value=DENOISE_METHODS[0])
    denoiseCombo = ttk.Combobox(controlsFrame, textvariable=dltsc.livePlot_denoiseMethodVar,
                                 values=DENOISE_METHODS, width=10, state='readonly')
    denoiseCombo.pack(side='left', padx=4)
    dltsc.livePlot_denoiseMethodVar.trace_add('write', _recompute_denoise_and_redraw)

    dltsc.livePlot_statusLabel = ttk.Label(controlsFrame, text='Waiting for data...')
    dltsc.livePlot_statusLabel.pack(side='left', padx=(10, 4))

    plotHolder = tk.Frame(parent)
    plotHolder.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
    plotHolder.grid_rowconfigure(0, weight=0)
    plotHolder.grid_rowconfigure(1, weight=1)
    plotHolder.grid_columnconfigure(0, weight=1)

    # Side-by-side (1 row, 2 columns) rather than stacked, so each plot gets more
    # horizontal room to show a full transient without being squeezed vertically.
    dltsc.livePlot_figure = Figure(figsize=(10, 4), dpi=100)
    dltsc.livePlot_axEmission0 = dltsc.livePlot_figure.add_subplot(1, 2, 1)
    dltsc.livePlot_axAllEmissions = dltsc.livePlot_figure.add_subplot(1, 2, 2)
    dltsc.livePlot_figure.tight_layout(pad=2.0, w_pad=3.0)

    dltsc.livePlot_canvas = FigureCanvasTkAgg(dltsc.livePlot_figure, master=plotHolder)
    # Same pan/zoom/home/save toolbar as the Qualitative Analysis plot.
    toolbar = NavigationToolbar2Tk(dltsc.livePlot_canvas, plotHolder, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.livePlot_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')

    _reset_auto_plot_placeholder()


#---------------------MANUAL / QUALITATIVE ANALYSIS-------------------------#
# Ported from DrKayisScript.py's "1. Transient Extraction" tab (PyQt6) into tkinter,
# plotting into an embedded canvas here instead of that script's own window.
def _set_manual_buttons_state(state):
    """Enable/disable the Qualitative Analysis frame's action buttons.

    Mirrors the Run DLTS button's disabled-while-running pattern, giving visual
    feedback (instead of a silent no-op) while a background worker is in flight,
    and preventing a second worker from starting on top of it.
    """
    if dltsc.manual_selectFolderButton is not None:
        dltsc.manual_selectFolderButton.config(state=state)
    if dltsc.manual_appendFolderButton is not None:
        dltsc.manual_appendFolderButton.config(state=state)
    if dltsc.manual_extractButton is not None:
        dltsc.manual_extractButton.config(state=state)

def _describe_folder_contents(dir_path, max_entries=12):
    """One-line, synchronous preview of a folder someone just picked in a file
    dialog: entry count + first few names + a quick format guess (ZI single-
    file / ZI subfolder-per-temperature / legacy per-temperature /
    unrecognized). This app supports three different on-disk data layouts and
    the OS folder-picker dialog shows nothing about a folder's CONTENTS (only
    its name), so without this, picking the wrong one of several similarly-
    named data folders is only discovered after waiting on the full
    background scan. Cheap enough (one os.listdir(), no file reads) to run
    synchronously right when the dialog closes, logged immediately via
    dltsc.log_to_textbox() by every folder-browse call site.
    """
    try:
        entries = sorted(os.listdir(dir_path))
    except Exception as exc:
        return f"cannot list folder: {exc}"

    if not entries:
        return "folder is empty"

    shown = entries[:max_entries]
    listing = ", ".join(shown)
    if len(entries) > max_entries:
        listing += f", ... ({len(entries) - max_entries} more)"

    zi_headers = [f for f in entries
                 if re.search(r'imps_0_sample_param1_avg_header', f, re.IGNORECASE) and f.endswith('.csv')]
    if zi_headers:
        guess = "looks like ZI single-file format (one combined multi-chunk CSV)"
    elif any(_ZI_SUBFOLDER_PATTERN.match(e) and os.path.isdir(os.path.join(dir_path, e)) for e in entries):
        guess = "looks like ZI subfolder-per-temperature format"
    elif any(_LEGACY_FILENAME_PATTERN.search(e) for e in entries):
        guess = "looks like legacy per-temperature files"
    else:
        guess = "format not recognized from filenames -- will be reported after scanning"

    return f"{len(entries)} item(s): {listing}  —  {guess}"

def _browse_manual_folder():
    if dltsc.manual_loadingBusy or dltsc.manual_processingBusy:
        return
    dir_path = filedialog.askdirectory(
        title="Select DLTS Source Folder",
        initialdir=dltsc.manual_dataDirectory or os.getcwd()
    )
    if dir_path:
        dltsc.log_to_textbox(f"Manual analysis: selected {dir_path} -- {_describe_folder_contents(dir_path)}")
        _scan_manual_directory_async(dir_path, isAppend=False)

def _append_manual_folder():
    """Add another folder's temperatures to the current dataset instead of
    replacing it, so a run that was split into pieces or taken across
    different dates/sessions can still be analyzed together.
    """
    if dltsc.manual_loadingBusy or dltsc.manual_processingBusy:
        return
    if not dltsc.manual_datasetRegistry:
        # Nothing loaded yet -- append is just a first load in that case.
        _browse_manual_folder()
        return
    dir_path = filedialog.askdirectory(
        title="Select DLTS Source Folder to Append",
        initialdir=dltsc.manual_dataDirectory or os.getcwd()
    )
    if dir_path:
        dltsc.log_to_textbox(f"Manual analysis: selected {dir_path} -- {_describe_folder_contents(dir_path)}")
        _scan_manual_directory_async(dir_path, isAppend=True)

# Both are ZI MFIA CSV exports -- 'zi' is one combined multi-chunk file (a
# whole sweep in one CSV, temperatures told apart by chunk number), 'zi_subfolder'
# is one subfolder per temperature (the DLTS_APP.py / Detailed Analysis tab
# convention), each with its own single-chunk CSV.
_ZI_REGISTRY_TAGS = ('zi', 'zi_subfolder')

def _registry_format_label(registry):
    """'ZI' / 'Legacy' / 'Mixed', describing the formats present in registry --
    once appending is possible, a combined dataset can span both."""
    hasZi = any(isinstance(v, tuple) and v[0] in _ZI_REGISTRY_TAGS for v in registry.values())
    hasLegacy = any(not (isinstance(v, tuple) and v[0] in _ZI_REGISTRY_TAGS) for v in registry.values())
    if hasZi and hasLegacy:
        return "Mixed"
    return "ZI" if hasZi else "Legacy"

def _scan_manual_directory_async(dir_path, isAppend):
    """Auto-detect ZI vs. legacy format and index the available temperatures in
    dir_path, then merge (isAppend=True) into the current dataset or replace
    it (isAppend=False) with them.

    Runs the directory scan/parse on a background thread, like Run DLTS does for
    the experiment itself, so scanning a large folder never freezes the GUI. Only
    plain Python/pandas work happens on the worker thread; all Tk widget updates
    are marshaled back onto the main thread via root.after().
    """
    if dltsc.manual_loadingBusy or dltsc.manual_processingBusy:
        return
    dltsc.manual_loadingBusy = True
    _set_manual_buttons_state('disabled')
    action = "Appending" if isAppend else "Loading"
    if dltsc.manual_folderLabel is not None and not isAppend:
        dltsc.manual_folderLabel.config(text=f"Source: {os.path.basename(dir_path)} (scanning...)")
    if dltsc.manual_statusLabel is not None:
        dltsc.manual_statusLabel.config(text=f"{action} {os.path.basename(dir_path)}...")

    def worker():
        errorMsgs = []
        registry = {}
        ziDetected = False
        ziInfo = None
        ziSubfolderParams = None
        try:
            # Detect format, in order: a single combined ZI export (a header
            # CSV matching *imps_0_sample_param1_avg_header*.csv directly in
            # dir_path) -> a subfolder-per-temperature ZI export (the
            # DLTS_APP.py / Detailed Analysis tab convention: dir_path holds
            # one subdirectory per temperature, e.g. '0C'/'n10C'/'120C_000',
            # each with its own such CSV) -> legacy per-temperature files.
            zi_headers = [f for f in os.listdir(dir_path)
                          if re.search(r'imps_0_sample_param1_avg_header', f, re.IGNORECASE)
                          and f.endswith('.csv')]
            if zi_headers:
                ziDetected = True
                registry, ziInfo = _compute_zi_dataset(dir_path, zi_headers[0], errorMsgs)
            else:
                registry, ziSubfolderParams = _compute_zi_subfolder_dataset(dir_path, errorMsgs)
                if registry:
                    ziDetected = True
                else:
                    registry = _compute_legacy_dataset(dir_path, errorMsgs)
        except Exception as exc:
            errorMsgs.append(f"error scanning folder: {exc}")

        def apply():
            dltsc.manual_loadingBusy = False
            _set_manual_buttons_state('normal')

            if isAppend:
                if dltsc.manual_datasetRegistry is None:
                    dltsc.manual_datasetRegistry = {}
                skipped = sorted(t for t in registry if t in dltsc.manual_datasetRegistry)
                added = {t: v for t, v in registry.items() if t not in dltsc.manual_datasetRegistry}
                dltsc.manual_datasetRegistry.update(added)
                if dltsc.manual_sourceFolders is None:
                    dltsc.manual_sourceFolders = []
                dltsc.manual_sourceFolders.append(dir_path)
                if skipped:
                    dltsc.log_to_textbox(
                        f"Manual analysis: skipped {len(skipped)} temperature(s) already present "
                        f"from a previous source (kept the first-loaded copy): {skipped}")
            else:
                dltsc.manual_datasetRegistry = registry
                dltsc.manual_sourceFolders = [dir_path]
                dltsc.manual_dataDirectory = dir_path
                dltsc.manual_ziParamsByFile = {}
                if dltsc.manual_folderLabel is not None:
                    dltsc.manual_folderLabel.config(text=f"Source: {os.path.basename(dir_path)}")

            if ziInfo is not None:
                ziParams = {'gridColOffset': ziInfo['gridColOffset'], 'gridColDelta': ziInfo['gridColDelta'],
                            'chunkSize': ziInfo['chunkSize']}
                dltsc.manual_ziParamsByFile[ziInfo['dataFile']] = ziParams
                dltsc.manual_ziDataFile = ziInfo['dataFile']
                dltsc.manual_ziGridColOffset = ziParams['gridColOffset']
                dltsc.manual_ziGridColDelta = ziParams['gridColDelta']
                dltsc.manual_ziChunkSize = ziParams['chunkSize']
                if not isAppend:
                    if ziInfo.get('fpMs') is not None:
                        dltsc.manual_paramVars['fp_ms'].set(ziInfo['fpMs'])
                    if ziInfo.get('rbMs') is not None:
                        dltsc.manual_paramVars['rb_ms'].set(ziInfo['rbMs'])
                        dltsc.manual_paramVars['slice_end'].set(ziInfo['sliceEnd'])
            elif ziSubfolderParams:
                # One params entry per temperature's own file (each subfolder
                # carries its own header CSV) rather than a single shared one.
                dltsc.manual_ziParamsByFile.update(ziSubfolderParams)
                firstFile, firstParams = next(iter(ziSubfolderParams.items()))
                dltsc.manual_ziDataFile = firstFile
                dltsc.manual_ziGridColOffset = firstParams['gridColOffset']
                dltsc.manual_ziGridColDelta = firstParams['gridColDelta']
                dltsc.manual_ziChunkSize = firstParams['chunkSize']
                if not isAppend:
                    folder_name = os.path.basename(dir_path)
                    fp_match = re.search(r'FP\w+?(\d+(?:\.\d+)?)ms', folder_name, re.IGNORECASE)
                    rb_match = re.search(r'RB[\w\+\-]+?(\d+(?:\.\d+)?)ms', folder_name, re.IGNORECASE)
                    if fp_match:
                        dltsc.manual_paramVars['fp_ms'].set(fp_match.group(1))
                    if rb_match:
                        rb_ms = float(rb_match.group(1))
                        dltsc.manual_paramVars['rb_ms'].set(str(rb_ms))
                        dltsc.manual_paramVars['slice_end'].set(str(rb_ms * 0.98))

            dltsc.manual_ziMode = _registry_format_label(dltsc.manual_datasetRegistry)

            if isAppend and dltsc.manual_folderLabel is not None:
                nSources = len(dltsc.manual_sourceFolders)
                dltsc.manual_folderLabel.config(
                    text=f"Source: {nSources} folder(s) combined (latest: {os.path.basename(dir_path)})")

            dltsc.manual_tempListbox.delete(0, tk.END)
            for temp in sorted(dltsc.manual_datasetRegistry.keys()):
                dltsc.manual_tempListbox.insert(tk.END, f"{temp} °C")
            dltsc.manual_tempListbox.select_set(0, tk.END)

            for msg in errorMsgs:
                dltsc.log_to_textbox(f"Manual analysis: {msg}")

            if dltsc.manual_statusLabel is not None:
                dltsc.manual_statusLabel.config(
                    text=f"[{dltsc.manual_ziMode}] {len(dltsc.manual_datasetRegistry)} temperature step(s) "
                        f"from {len(dltsc.manual_sourceFolders)} source(s).")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _compute_zi_dataset(dir_path, header_filename, errorMsgs):
    """Parse the ZI averaged-data folder (pure computation, safe on a background thread).

    File layout (inside dir_path):
      dev*_imps_0_sample_param1_avg_header_*.csv  — metadata per chunk
      dev*_imps_0_sample_param1_avg_*.csv         — capacitance transients
    Header columns of interest:
      chunk_number, history_name, grid_col_offset, grid_col_delta, chunk_size

    Returns (registry, ziInfo) where ziInfo is a dict of the fields the caller
    needs to copy into dltsConfig globals, or (registry, None) on failure.
    """
    registry = {}
    header_path = os.path.join(dir_path, header_filename)
    try:
        hdr = pd.read_csv(header_path, sep=';')
    except Exception as exc:
        errorMsgs.append(f"cannot read ZI header file: {exc}")
        return registry, None

    data_candidates = [f for f in os.listdir(dir_path)
                       if re.search(r'imps_0_sample_param1_avg_\d+\.csv$', f, re.IGNORECASE)
                       and 'header' not in f.lower()]
    if not data_candidates:
        errorMsgs.append("cannot locate ZI capacitance data CSV (imps_0_sample_param1_avg_*.csv).")
        return registry, None

    ziInfo = {
        'dataFile': os.path.join(dir_path, data_candidates[0]),
        'gridColOffset': -0.001,
        'gridColDelta': 1.86667e-05,
        'chunkSize': 32768,
        'fpMs': None,
        'rbMs': None,
        'sliceEnd': None,
    }

    row0 = hdr.iloc[0]
    try:
        ziInfo['gridColOffset'] = float(row0.get('grid_col_offset', -0.001))
        ziInfo['gridColDelta'] = float(row0.get('grid_col_delta', 1.86667e-05))
        ziInfo['chunkSize'] = int(row0.get('chunk_size', 32768))
    except Exception:
        pass  # keep defaults

    temp_pattern = re.compile(r'^(\d+)C_', re.IGNORECASE)
    for _, row in hdr.iterrows():
        chunk_num = int(row['chunk_number'])
        name = str(row.get('history_name', ''))
        m = temp_pattern.match(name)
        if m:
            temp_c = float(m.group(1))
            # Explicitly tagged (not a bare chunk number) so entries from a
            # ZI source can coexist in the registry with legacy-format entries
            # appended from a different folder.
            registry[temp_c] = ('zi', ziInfo['dataFile'], chunk_num)

    # Update timing defaults if we can parse them from the folder name.
    folder_name = os.path.basename(dir_path)
    fp_match = re.search(r'FP\w+?(\d+(?:\.\d+)?)ms', folder_name, re.IGNORECASE)
    rb_match = re.search(r'RB[\w\+\-]+?(\d+(?:\.\d+)?)ms', folder_name, re.IGNORECASE)
    if fp_match:
        ziInfo['fpMs'] = fp_match.group(1)
    if rb_match:
        rb_ms = float(rb_match.group(1))
        ziInfo['rbMs'] = str(rb_ms)
        ziInfo['sliceEnd'] = str(rb_ms * 0.98)

    return registry, ziInfo

# Matches a per-temperature ZI export subfolder name: '0C', '100C', 'n10C'
# (n prefix = negative), '120C_000' (trailing run-id suffix). Same convention
# DLTS_APP.py / detailedAnalysisTab.py use for their own folder-per-temperature scan.
_ZI_SUBFOLDER_PATTERN = re.compile(r'^(n?)(\d+)C(?:_\d+)?$', re.IGNORECASE)

def _compute_zi_subfolder_dataset(dir_path, errorMsgs):
    """Parse a subfolder-per-temperature ZI export: dir_path holds one
    subdirectory per temperature step (matching _ZI_SUBFOLDER_PATTERN), each
    containing its own dev*_imps_0_sample_param1_avg_*.csv (+ a matching
    _header_*.csv for that temperature's own acquisition grid params) --
    the DLTS_APP.py / Detailed Analysis tab's own export convention, distinct
    from the single-combined-CSV 'zi' format _compute_zi_dataset() handles
    (which instead tells temperatures apart by chunk number within one file).

    Pure computation (no Tk calls), safe on a background thread. Returns
    (registry, ziParamsByFile): registry[tempC] = ('zi_subfolder', dataFile,
    None) (no chunk id -- each temperature already has its own file), and
    ziParamsByFile maps each such dataFile to its own {'gridColOffset',
    'gridColDelta', 'chunkSize'} (defaulted from the standard ZI MFIA grid if
    that subfolder's header CSV can't be read).
    """
    registry = {}
    ziParamsByFile = {}
    try:
        entries = sorted(os.listdir(dir_path))
    except Exception as exc:
        errorMsgs.append(f"cannot list folder: {exc}")
        return registry, ziParamsByFile

    for entry in entries:
        sub = os.path.join(dir_path, entry)
        if not os.path.isdir(sub):
            continue
        m = _ZI_SUBFOLDER_PATTERN.match(entry)
        if not m:
            continue
        tempC = float(m.group(2))
        if m.group(1).lower() == 'n':
            tempC = -tempC

        try:
            subFiles = os.listdir(sub)
        except Exception as exc:
            errorMsgs.append(f"{entry}: cannot list subfolder: {exc}")
            continue

        dataCandidates = [f for f in subFiles
                          if re.search(r'imps_0_sample_param1_avg_\d+\.csv$', f, re.IGNORECASE)
                          and 'header' not in f.lower()]
        if not dataCandidates:
            errorMsgs.append(f"{entry}: no ZI capacitance data CSV found")
            continue
        dataFile = os.path.join(sub, dataCandidates[0])

        params = {'gridColOffset': -0.001, 'gridColDelta': 1.86667e-05, 'chunkSize': 32768}
        headerCandidates = [f for f in subFiles
                            if re.search(r'imps_0_sample_param1_avg_header', f, re.IGNORECASE)
                            and f.endswith('.csv')]
        if headerCandidates:
            try:
                hdr = pd.read_csv(os.path.join(sub, headerCandidates[0]), sep=';')
                row0 = hdr.iloc[0]
                params['gridColOffset'] = float(row0.get('grid_col_offset', params['gridColOffset']))
                params['gridColDelta'] = float(row0.get('grid_col_delta', params['gridColDelta']))
                params['chunkSize'] = int(row0.get('chunk_size', params['chunkSize']))
            except Exception:
                pass  # keep defaults

        registry[tempC] = ('zi_subfolder', dataFile, None)
        ziParamsByFile[dataFile] = params

    return registry, ziParamsByFile

def _compute_legacy_dataset(dir_path, errorMsgs):
    """Legacy per-temperature file loader (original DrKayisScript.py logic, unchanged).

    Pure computation (no Tk calls) so it is safe to run on a background thread;
    returns the dataset registry dict for the caller to apply.
    """
    registry = {}
    for file in os.listdir(dir_path):
        file_path = os.path.join(dir_path, file)
        if not os.path.isfile(file_path):
            continue

        if file.lower().endswith('.csv'):
            try:
                with open(file_path, 'r') as f:
                    first_line = f.readline().strip().lower()

                is_semicolon = ';' in first_line
                has_chunk = 'chunk' in first_line
                has_smoothed = 'smoothed_value' in first_line or 'timestamp' in first_line

                if is_semicolon:
                    if has_chunk:
                        df_chunks = pd.read_csv(file_path, sep=';', usecols=[0])
                        unique_chunks = sorted(df_chunks.iloc[:, 0].unique())

                        if "p120C-p160C" in file or len(unique_chunks) > 1:
                            chunk_map = {0: 120.0, 1: 125.0, 2: 130.0, 3: 135.0,
                                         4: 140.0, 5: 145.0, 6: 150.0, 7: 155.0,
                                         8: 160.0}
                            for ch in unique_chunks:
                                if ch in chunk_map:
                                    registry[chunk_map[ch]] = ('legacy_chunk', file_path, ch)
                        else:
                            match = _LEGACY_FILENAME_PATTERN.search(file)
                            if match:
                                sign, int_part, frac_part, ext = match.groups()
                                t_val = float(int_part) + (float(f"0.{frac_part}")
                                                           if frac_part else 0.0)
                                if sign.lower() == 'n':
                                    t_val = -t_val
                                registry[t_val] = ('legacy_chunk', file_path, unique_chunks[0])
                        continue
                    elif has_smoothed:
                        match = _LEGACY_FILENAME_PATTERN.search(file)
                        if match:
                            sign, int_part, frac_part, ext = match.groups()
                            t_val = float(int_part) + (float(f"0.{frac_part}")
                                                       if frac_part else 0.0)
                            if sign.lower() == 'n':
                                t_val = -t_val
                            registry[t_val] = ('legacy_chunk', file_path, None)
                        continue
            except Exception as exc:
                errorMsgs.append(f"skipping CSV pre-scan on {file}: {exc}")

        match = _LEGACY_FILENAME_PATTERN.search(file)
        if match:
            sign, integer_part, frac_part, ext = match.groups()
            frac = f"0.{frac_part}" if frac_part else "0.0"
            temp = float(integer_part) + float(frac)
            if sign.lower() == 'n':
                temp = -temp
            registry[temp] = file_path

    return registry

def _select_all_manual_temps():
    dltsc.manual_tempListbox.select_set(0, tk.END)

def _clear_manual_temps():
    dltsc.manual_tempListbox.select_clear(0, tk.END)

_MAX_PLOT_POINTS = 3000

def _downsample_for_plot(x, y, maxPoints=_MAX_PLOT_POINTS):
    """Stride a transient down to at most maxPoints before handing it to
    matplotlib. canvas.draw() cost scales with vertex count, and a raw
    ~27,000-point transient (real reverse-bias sampling rate x duration) makes
    the post-extraction plot redraw itself visibly stall the main thread for a
    beat -- the one remaining rendering cost once the extraction itself runs
    fully off-process. Striding is visually lossless for a smooth decay curve
    at typical plot/screen resolution; the full-resolution data is untouched in
    dltsc.manual_processedTransients for anything else that needs it.
    """
    n = len(x)
    if n <= maxPoints:
        return x, y
    stride = -(-n // maxPoints)  # ceil division
    return x[::stride], y[::stride]

def _get_transient_executor():
    """Return the shared ProcessPoolExecutor for _process_raw_transients, creating
    it on first use. Reused across extractions so only the very first click pays
    the child process's one-time import cold-start (matplotlib/pandas/etc.);
    later clicks reuse the already-running worker process.
    """
    if dltsc.manual_transientExecutor is None:
        dltsc.manual_transientExecutor = ProcessPoolExecutor(max_workers=1)
    return dltsc.manual_transientExecutor

def _process_raw_transients():
    """Extract & average transients for the checked temperatures (ZI or legacy format).

    Dispatches the per-temperature file I/O and math to a separate OS process
    (via ProcessPoolExecutor), not just a background thread: confirmed against a
    real 101-temperature legacy dataset that this can take ~20s of CPU-heavy
    work (large JSON parses, list->ndarray conversions), and even off the main
    thread that still holds Python's GIL for long, uninterrupted stretches
    within a single temperature's processing -- enough to make tab switches and
    redraws visibly lag behind a click. A genuinely separate process has its own
    GIL, so it can never contend with the Tk main thread no matter how long any
    single temperature takes to process. The calling background thread just
    blocks on the process's result, which is a cheap OS-level wait.
    Only the resulting matplotlib plotting happens back on the main thread.
    """
    if not dltsc.manual_datasetRegistry:
        return
    if dltsc.manual_processingBusy or dltsc.manual_loadingBusy:
        return

    sortedTemps = sorted(dltsc.manual_datasetRegistry.keys())
    selectedIndices = dltsc.manual_tempListbox.curselection()
    selectedTemps = [sortedTemps[i] for i in selectedIndices]

    if not selectedTemps:
        dltsc.log_to_textbox("Manual analysis: select at least one temperature trace.")
        return

    try:
        rbDurationMs = float(dltsc.manual_paramVars['rb_ms'].get())
    except ValueError:
        dltsc.log_to_textbox("Manual analysis: Reverse Bias (ms) must be numeric.")
        return
    cInfTargetMs = 0.90 * rbDurationMs

    dltsc.manual_processingBusy = True
    _set_manual_buttons_state('disabled')
    dltsc.manual_statusLabel.config(text=f"Processing {len(selectedTemps)} temperature(s)...")

    # Snapshot everything the worker needs so it never touches Tk widgets/variables.
    # Selected temperatures are split by their OWN registry entry's format tag
    # (not a single global mode) so a combined dataset -- some temperatures
    # from an appended ZI source, others from an appended legacy source -- is
    # routed correctly instead of forcing every selection through one format.
    datasetRegistry = dict(dltsc.manual_datasetRegistry)
    ziTemps = [t for t in selectedTemps
              if isinstance(datasetRegistry.get(t), tuple) and datasetRegistry[t][0] == 'zi']
    ziSubfolderTemps = [t for t in selectedTemps
                        if isinstance(datasetRegistry.get(t), tuple) and datasetRegistry[t][0] == 'zi_subfolder']
    legacyTemps = [t for t in selectedTemps if t not in ziTemps and t not in ziSubfolderTemps]
    ziParamsByFile = dict(dltsc.manual_ziParamsByFile or {})
    samplingRateS = dltsc.manual_samplingRate or 1.8666666666666665e-05

    def worker():
        try:
            executor = _get_transient_executor()
            future = executor.submit(_compute_mixed_transients, ziTemps, legacyTemps, cInfTargetMs,
                                     datasetRegistry, ziParamsByFile, rbDurationMs, samplingRateS,
                                     ziSubfolderTemps=ziSubfolderTemps)
            processedTransients, executionErrors = future.result()
        except Exception as exc:
            processedTransients, executionErrors = {}, [f"extraction process failed: {exc}"]

        def apply():
            dltsc.manual_processingBusy = False
            _set_manual_buttons_state('normal')
            dltsc.manual_processedTransients = processedTransients

            dltsc.manual_ax.clear()
            for temp in sorted(processedTransients.keys()):
                rec = processedTransients[temp]
                x, y = _downsample_for_plot(rec['time_ms'], rec['avg_cap_pf'])
                dltsc.manual_ax.plot(x, y, label=f"{temp}°C")
            dltsc.manual_ax.set_xlabel("Time from Reverse Bias Start (ms)")
            dltsc.manual_ax.set_ylabel("Capacitance (pF)")
            dltsc.manual_ax.set_title("Averaged Capacitance Transients Profile")
            dltsc.manual_ax.grid(True, linestyle=":")
            handles, labels = dltsc.manual_ax.get_legend_handles_labels()
            if labels:
                # A fixed corner instead of loc='best' skips matplotlib's
                # overlap-search over every plotted point, which is otherwise a
                # further main-thread rendering cost right when results land.
                dltsc.manual_ax.legend(loc='upper right')
            dltsc.manual_figure.tight_layout(pad=2.0)
            dltsc.manual_canvas.draw()

            if executionErrors:
                for err in executionErrors:
                    dltsc.log_to_textbox(f"Manual analysis: {err}")
                dltsc.manual_statusLabel.config(text="Completed with processing errors.")
            else:
                dltsc.manual_statusLabel.config(
                    text=f"Transients ensembled completely — {len(processedTransients)} traces.")

        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()

def _compute_zi_transients(selectedTemps, cInfTargetMs, datasetRegistry, ziParamsByFile):
    """Read each distinct ZI data CSV once, then extract every selected chunk
    from it. datasetRegistry[temp] is ('zi', dataFile, chunkId); appended ZI
    sources can contribute different dataFiles (each with its own acquisition
    params in ziParamsByFile), so temps are grouped by dataFile first and each
    file is only read from disk once regardless of how many temps use it.

    Pure computation (no Tk/matplotlib calls), run in a separate OS process (see
    _process_raw_transients) so it can never contend with the Tk main thread for
    the GIL. Returns (processedTransients, executionErrors) since a separate
    process can't mutate the caller's objects by reference.
    """
    processedTransients = {}
    executionErrors = []

    byFile = {}
    for temp in selectedTemps:
        _, dataFile, chunkId = datasetRegistry[temp]
        byFile.setdefault(dataFile, []).append((temp, chunkId))

    for dataFile, entries in byFile.items():
        params = ziParamsByFile.get(dataFile, {})
        ziGridColOffset = params.get('gridColOffset', -0.001)
        ziGridColDelta = params.get('gridColDelta', 1.86667e-05)
        ziChunkSize = params.get('chunkSize', 32768)

        try:
            dfAll = pd.read_csv(dataFile, sep=';')
        except Exception as exc:
            executionErrors.append(f"failed to read ZI data CSV {os.path.basename(dataFile)}: {exc}")
            continue

        # Time axis (relative to reverse-bias start at t = 0 ms).
        timeAxisMs = (ziGridColOffset + np.arange(ziChunkSize) * ziGridColDelta) * 1000.0

        for temp, chunkId in sorted(entries):
            try:
                chunkRows = dfAll[dfAll['chunk'] == chunkId]['value'].to_numpy()

                if len(chunkRows) == 0:
                    executionErrors.append(f"{temp}°C: No data for chunk {chunkId}")
                    continue

                n = min(len(chunkRows), ziChunkSize)
                avgCurve = chunkRows[:n].astype(np.float64)
                tAxis = timeAxisMs[:n]

                # Unit conversion: Farads -> pF.
                if np.nanmax(np.abs(avgCurve)) < 1e-3:
                    avgCurve = avgCurve * 1e12

                cInfIdx = np.argmin(np.abs(tAxis - cInfTargetMs))
                cInfinity = avgCurve[cInfIdx]

                processedTransients[temp] = {
                    'time_ms': tAxis,
                    'avg_cap_pf': avgCurve,
                    'C_infinity': cInfinity
                }

            except Exception as exc:
                executionErrors.append(f"{temp}°C: {exc}")

    return processedTransients, executionErrors

def _compute_zi_subfolder_transients(selectedTemps, cInfTargetMs, datasetRegistry, ziParamsByFile):
    """Read each selected temperature's own per-subfolder ZI CSV directly (one
    file per temp, filtered to chunk==0) -- for the 'zi_subfolder' registry tag,
    the DLTS_APP.py / Detailed Analysis tab's own per-temperature-folder ZI
    export convention, distinct from the single-combined-CSV 'zi' format
    _compute_zi_transients() handles.

    Pure computation (no Tk/matplotlib calls), run in a separate OS process
    (see _process_raw_transients) so it can never contend with the Tk main
    thread for the GIL. Returns (processedTransients, executionErrors) since a
    separate process can't mutate the caller's objects by reference.
    """
    processedTransients = {}
    executionErrors = []
    for temp in sorted(selectedTemps):
        _, dataFile, _ = datasetRegistry[temp]
        params = ziParamsByFile.get(dataFile, {})
        gridColOffset = params.get('gridColOffset', -0.001)
        gridColDelta = params.get('gridColDelta', 1.86667e-05)
        chunkSize = params.get('chunkSize', 32768)

        try:
            df = pd.read_csv(dataFile, sep=';', header=0, names=['chunk', 'timestamp', 'value'])
            rows = df[df['chunk'] == 0]
            if len(rows) < 2:
                executionErrors.append(f"{temp}°C: no chunk-0 rows in {os.path.basename(dataFile)}")
                continue

            avgCurve = rows['value'].to_numpy(dtype=np.float64)
            n = min(len(avgCurve), chunkSize)
            avgCurve = avgCurve[:n]
            timeAxisMs = (gridColOffset + np.arange(n) * gridColDelta) * 1000.0

            # Unit conversion: Farads -> pF.
            if np.nanmax(np.abs(avgCurve)) < 1e-3:
                avgCurve = avgCurve * 1e12

            cInfIdx = np.argmin(np.abs(timeAxisMs - cInfTargetMs))
            cInfinity = avgCurve[cInfIdx]

            processedTransients[temp] = {
                'time_ms': timeAxisMs,
                'avg_cap_pf': avgCurve,
                'C_infinity': cInfinity
            }

        except Exception as exc:
            executionErrors.append(f"{temp}°C: {exc}")

    return processedTransients, executionErrors

def _compute_mixed_transients(ziTemps, legacyTemps, cInfTargetMs, datasetRegistry,
                              ziParamsByFile, rbDurationMs, samplingRateS, ziSubfolderTemps=None):
    """Dispatch each selected temperature to the ZI, ZI-subfolder, or legacy
    extractor depending on how its own registry entry is tagged, then merge
    the results. Needed because appending sources of different formats can
    leave a single selection spanning several -- a single global "ziMode"
    flag can no longer decide the whole batch's format.
    """
    processedTransients = {}
    executionErrors = []
    if ziTemps:
        p, e = _compute_zi_transients(ziTemps, cInfTargetMs, datasetRegistry, ziParamsByFile)
        processedTransients.update(p)
        executionErrors.extend(e)
    if ziSubfolderTemps:
        p, e = _compute_zi_subfolder_transients(ziSubfolderTemps, cInfTargetMs, datasetRegistry, ziParamsByFile)
        processedTransients.update(p)
        executionErrors.extend(e)
    if legacyTemps:
        p, e = _compute_legacy_transients(legacyTemps, rbDurationMs, cInfTargetMs, datasetRegistry, samplingRateS)
        processedTransients.update(p)
        executionErrors.extend(e)
    return processedTransients, executionErrors

def _compute_legacy_transients(selectedTemps, rbDurationMs, cInfTargetMs, datasetRegistry,
                               samplingRateS):
    """Legacy transient extraction, ported from DrKayisScript.py's original logic.

    Pure computation (no Tk/matplotlib calls), run in a separate OS process (see
    _process_raw_transients) so it can never contend with the Tk main thread for
    the GIL -- a single large JSON parse/list-to-ndarray conversion here can hold
    the GIL far longer than any inter-iteration yield could paper over. Returns
    (processedTransients, executionErrors) since a separate process can't mutate
    the caller's objects by reference.
    """
    processedTransients = {}
    executionErrors = []
    for temp in sorted(selectedTemps):
        targetSource = datasetRegistry[temp]
        try:
            if isinstance(targetSource, tuple) and targetSource[0] == 'legacy_chunk':
                _, filePath, chunkId = targetSource
                df = pd.read_csv(filePath, sep=';')

                if chunkId is not None:
                    dfTarget = df[df.iloc[:, 0] == chunkId].dropna()
                else:
                    dfTarget = df.dropna()

                valCols = [c for c in dfTarget.columns
                          if any(k in c.lower() for k in ['value', 'smoothed', 'cap', 'impedance'])]
                targetCol = valCols[-1] if valCols else dfTarget.columns[-1]
                avgCurve = dfTarget[targetCol].to_numpy()

                if np.nanmax(np.abs(avgCurve)) < 1e-3:
                    avgCurve = avgCurve * 1e12

                timeAxisMs = np.arange(len(avgCurve)) * samplingRateS * 1000

            else:
                filePath = targetSource
                ext = os.path.splitext(filePath)[1].lower()

                if ext == '.txt':
                    with open(filePath, 'r') as f:
                        data = json.load(f)
                    auxV = np.array(data['AuxInput1'], dtype=np.float32)
                    rawCap = np.array(data['ImpedanceIm'], dtype=np.float32) * 1e12

                    isForward = auxV > -2.5
                    transitions = np.diff(isForward.astype(int))
                    fallingTriggers = np.where(transitions == -1)[0]

                    cycleLen = int((rbDurationMs * 1e-3) / samplingRateS)
                    validBlocks = [rawCap[trig:trig + cycleLen]
                                  for trig in fallingTriggers
                                  if trig + cycleLen <= len(rawCap)]
                    if not validBlocks:
                        continue
                    avgCurve = np.mean(np.array(validBlocks), axis=0)
                    timeAxisMs = np.arange(len(avgCurve)) * samplingRateS * 1000

                elif ext == '.csv':
                    df = pd.read_csv(filePath)
                    timeAxisMs = df.iloc[:, 0].to_numpy()
                    avgCurve = df.iloc[:, 1].to_numpy()

                else:
                    executionErrors.append(f"{temp}°C: unsupported file type '{ext}'")
                    continue

            cInfIdx = np.argmin(np.abs(timeAxisMs - cInfTargetMs))
            cInfinity = avgCurve[cInfIdx]

            processedTransients[temp] = {
                'time_ms': timeAxisMs,
                'avg_cap_pf': avgCurve,
                'C_infinity': cInfinity
            }

        except Exception as exc:
            executionErrors.append(f"{temp}°C: {exc}")

    return processedTransients, executionErrors

def _build_manualPlotFrame(parent):
    # dltsConfig.init() (which would normally seed these as dicts/False) is not called
    # by DLTSGUI_MainWindow.py, so seed them here to be safe regardless of that wiring.
    if dltsc.manual_processedTransients is None:
        dltsc.manual_processedTransients = dict()
    if dltsc.manual_processingBusy is None:
        dltsc.manual_processingBusy = False
    if dltsc.manual_loadingBusy is None:
        dltsc.manual_loadingBusy = False

    parent.grid_rowconfigure(0, weight=0)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=0)
    parent.grid_columnconfigure(1, weight=1)

    headerFrame = tk.Frame(parent)
    headerFrame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=4, pady=4)
    ttk.Label(headerFrame, text='Qualitative Analysis', font=('Segoe UI', 10, 'bold')).pack(side='left')

    # The left column (loader config + temperature list + timing fields + execution
    # action) can be taller than the available screen height on smaller windows, so
    # it is wrapped in a scrollable canvas rather than a plain fixed frame.
    leftContainer = tk.Frame(parent)
    leftContainer.grid(row=1, column=0, sticky='ns', padx=4, pady=4)

    leftCanvas = tk.Canvas(leftContainer, width=230, highlightthickness=0)
    leftScroll = ttk.Scrollbar(leftContainer, orient='vertical', command=leftCanvas.yview)
    leftCanvas.configure(yscrollcommand=leftScroll.set)
    leftCanvas.pack(side='left', fill='both', expand=True)
    leftScroll.pack(side='right', fill='y')

    leftPanel = tk.Frame(leftCanvas)
    leftPanelWindow = leftCanvas.create_window((0, 0), window=leftPanel, anchor='nw')
    leftPanel.bind('<Configure>', lambda e: leftCanvas.configure(scrollregion=leftCanvas.bbox('all')))
    leftCanvas.bind('<Configure>', lambda e: leftCanvas.itemconfigure(leftPanelWindow, width=e.width))

    def _on_mousewheel(event):
        leftCanvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    leftCanvas.bind('<Enter>', lambda e: leftCanvas.bind_all('<MouseWheel>', _on_mousewheel))
    leftCanvas.bind('<Leave>', lambda e: leftCanvas.unbind_all('<MouseWheel>'))

    rightPanel = tk.Frame(parent)
    rightPanel.grid(row=1, column=1, sticky='nsew', padx=4, pady=4)
    rightPanel.grid_rowconfigure(1, weight=1)
    rightPanel.grid_columnconfigure(0, weight=1)

    # --- Directory Loader Config ---
    ioGroup = tk.LabelFrame(leftPanel, text='Directory Loader Config')
    ioGroup.pack(fill='x', pady=(0, 4))
    dltsc.manual_selectFolderButton = ttk.Button(ioGroup, text='Select Source Folder', command=_browse_manual_folder)
    dltsc.manual_selectFolderButton.pack(fill='x', padx=4, pady=(4, 2))
    dltsc.manual_appendFolderButton = ttk.Button(ioGroup, text='Append Source Folder', command=_append_manual_folder)
    dltsc.manual_appendFolderButton.pack(fill='x', padx=4, pady=(0, 2))
    dltsc.manual_folderLabel = ttk.Label(ioGroup, text='Source: (none selected)', wraplength=220, justify='left')
    dltsc.manual_folderLabel.pack(fill='x', padx=4, pady=(0, 4))

    # --- Available Temperatures Filter ---
    # Kept short (height=3) so Timing Boundaries and Execution Action below stay
    # visible without scrolling; the listbox itself still scrolls internally.
    tempGroup = tk.LabelFrame(leftPanel, text='Available Temperatures Filter')
    tempGroup.pack(fill='x', pady=(0, 4))
    listFrame = tk.Frame(tempGroup)
    listFrame.pack(fill='both', expand=True, padx=4, pady=(4, 2))
    listScroll = ttk.Scrollbar(listFrame, orient='vertical')
    dltsc.manual_tempListbox = tk.Listbox(listFrame, selectmode=tk.MULTIPLE, exportselection=False,
                                          height=3, yscrollcommand=listScroll.set)
    listScroll.config(command=dltsc.manual_tempListbox.yview)
    dltsc.manual_tempListbox.pack(side='left', fill='both', expand=True)
    listScroll.pack(side='right', fill='y')

    utilFrame = tk.Frame(tempGroup)
    utilFrame.pack(fill='x', padx=4, pady=(0, 4))
    ttk.Button(utilFrame, text='Select All', command=_select_all_manual_temps).pack(
        side='left', fill='x', expand=True, padx=(0, 2))
    ttk.Button(utilFrame, text='Clear All', command=_clear_manual_temps).pack(
        side='left', fill='x', expand=True, padx=(2, 0))

    # --- Timing Boundaries ---
    paramGroup = tk.LabelFrame(leftPanel, text='Timing Boundaries')
    paramGroup.pack(fill='x', pady=(0, 4))
    dltsc.manual_paramVars = {
        'fp_ms': tk.StringVar(value='1.0'),
        'rb_ms': tk.StringVar(value='500.0'),
        'slice_start': tk.StringVar(value='2.0'),
        'slice_end': tk.StringVar(value='490.0'),
    }
    paramLabels = [
        ('fp_ms', 'Filling Duration (ms):'),
        ('rb_ms', 'Reverse Bias (ms):'),
        ('slice_start', 'Analysis Slice Start (ms):'),
        ('slice_end', 'Analysis Slice End (ms):'),
    ]
    for row, (key, label) in enumerate(paramLabels):
        ttk.Label(paramGroup, text=label).grid(row=row, column=0, sticky='w', padx=4, pady=1)
        ttk.Entry(paramGroup, textvariable=dltsc.manual_paramVars[key], width=10).grid(
            row=row, column=1, sticky='ew', padx=4, pady=1)
    paramGroup.grid_columnconfigure(1, weight=1)

    # --- Execution Action ---
    execGroup = tk.LabelFrame(leftPanel, text='Execution Action')
    execGroup.pack(fill='x')
    dltsc.manual_extractButton = tk.Button(execGroup, text='Extract & Average Transients', font=('Segoe UI', 9, 'bold'),
                           bg='#e8f5e9', command=_process_raw_transients)
    dltsc.manual_extractButton.pack(fill='x', padx=4, pady=(4, 2))
    dltsc.manual_statusLabel = ttk.Label(execGroup, text='Status: Idle')
    dltsc.manual_statusLabel.pack(fill='x', padx=4, pady=(0, 4))

    # --- Plot area (embedded, no popup window) ---
    dltsc.manual_figure = Figure(figsize=(6, 5), dpi=100)
    dltsc.manual_ax = dltsc.manual_figure.add_subplot(1, 1, 1)
    dltsc.manual_ax.set_title('Averaged Capacitance Transients Profile')
    dltsc.manual_ax.set_xlabel('Time from Reverse Bias Start (ms)')
    dltsc.manual_ax.set_ylabel('Capacitance (pF)')
    # Without this, the default subplot margins leave too little room for the
    # x-axis label on a short canvas and it gets clipped at the bottom.
    dltsc.manual_figure.tight_layout(pad=2.0)

    dltsc.manual_canvas = FigureCanvasTkAgg(dltsc.manual_figure, master=rightPanel)
    toolbar = NavigationToolbar2Tk(dltsc.manual_canvas, rightPanel, pack_toolbar=False)
    toolbar.update()
    toolbar.grid(row=0, column=0, sticky='ew')
    dltsc.manual_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')
    dltsc.manual_canvas.draw()


#---------------------TAB CONSTRUCTION-------------------------#
def construct_livePlotTab():
    root = dltsc.root
    livePlotTab = dltsc.livePlotTab
    tabControl = dltsc.tabControl

    tabControl.add(livePlotTab, text='Live Tools')
    tabControl.pack(expand=1, fill="both")

    # Allow tab content to expand with the notebook window. The analysis panes get
    # the expanding row; the run button, run control, and the log textbox are
    # fixed-height rows pinned to the top and bottom respectively.
    dltsc.livePlotTab.grid_rowconfigure(0, weight=0)
    dltsc.livePlotTab.grid_rowconfigure(1, weight=0)
    dltsc.livePlotTab.grid_rowconfigure(2, weight=1)
    dltsc.livePlotTab.grid_rowconfigure(3, weight=0)
    dltsc.livePlotTab.grid_columnconfigure(0, weight=1)



    runButtonFrame = tk.Frame(dltsc.livePlotTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=52)

    runButtonFrame.grid(row=0, column=0, padx=10, pady=(0, 2), sticky='nsew')
    runButtonFrame.grid_propagate(False)
    runButtonFrame.grid_columnconfigure(0, weight=1)
    runButtonFrame.grid_columnconfigure(1, weight=1)
    runButtonFrame.grid_columnconfigure(2, weight=0)
    runButtonFrame.grid_columnconfigure(3, weight=1)
    runButtonFrame.config()

    dltsc.run_button = tk.Button(runButtonFrame, text="Run DLTS", command=start_thread,
                                 font=('Segoe UI', 14, 'bold'))
    dltsc.run_button.pack(fill='both', expand=True, padx=4, pady=0)

    # --- Run Control: pause/resume the main sequence, or redo/remove & retake
    # specific already-scanned temperature steps by selecting them below. ---
    runControlFrame = tk.Frame(dltsc.livePlotTab, highlightbackground="gray",
                               highlightthickness=1, highlightcolor='gray',
                               width=860, height=150)
    runControlFrame.grid(row=1, column=0, padx=10, pady=(0, 2), sticky='nsew')
    runControlFrame.grid_propagate(False)
    runControlFrame.grid_columnconfigure(0, weight=0)
    runControlFrame.grid_columnconfigure(1, weight=1)
    runControlFrame.grid_rowconfigure(0, weight=1)

    runControlButtons = tk.Frame(runControlFrame)
    runControlButtons.grid(row=0, column=0, sticky='ns', padx=4, pady=4)
    dltsc.run_pauseButton = tk.Button(runControlButtons, text="Pause", command=_pause_run, state="disabled")
    dltsc.run_pauseButton.pack(fill='x', pady=2)
    dltsc.run_resumeButton = tk.Button(runControlButtons, text="Resume", command=_resume_run, state="disabled")
    dltsc.run_resumeButton.pack(fill='x', pady=2)
    dltsc.run_redoButton = tk.Button(runControlButtons, text="Redo Selected", command=_redo_selected_steps,
                                     state="disabled")
    dltsc.run_redoButton.pack(fill='x', pady=2)
    dltsc.run_retakeButton = tk.Button(runControlButtons, text="Remove & Retake Selected",
                                       command=_retake_selected_steps, state="disabled")
    dltsc.run_retakeButton.pack(fill='x', pady=2)

    stepListFrame = tk.Frame(runControlFrame)
    stepListFrame.grid(row=0, column=1, sticky='nsew', padx=4, pady=4)
    stepListFrame.grid_rowconfigure(0, weight=1)
    stepListFrame.grid_columnconfigure(0, weight=1)
    stepListScroll = ttk.Scrollbar(stepListFrame, orient='vertical')
    dltsc.run_stepListbox = tk.Listbox(stepListFrame, selectmode=tk.MULTIPLE, exportselection=False,
                                       yscrollcommand=stepListScroll.set)
    stepListScroll.config(command=dltsc.run_stepListbox.yview)
    dltsc.run_stepListbox.grid(row=0, column=0, sticky='nsew')
    stepListScroll.grid(row=0, column=1, sticky='ns')

    # Automated/live plot (top) and manual/qualitative analysis (bottom), stacked in
    # a resizable pane so both stay reachable without crowding the tab. The manual
    # pane starts taller since its control column has more to show.
    analysisPanes = tk.PanedWindow(dltsc.livePlotTab, orient=tk.VERTICAL, sashrelief='raised', sashwidth=6)
    analysisPanes.grid(row=2, column=0, padx=10, pady=(0, 2), sticky='nsew')

    autoPlotFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                             highlightthickness=1, highlightcolor='gray')
    manualPlotFrame = tk.Frame(analysisPanes, highlightbackground="gray",
                               highlightthickness=1, highlightcolor='gray')
    analysisPanes.add(autoPlotFrame, height=460, stretch='always')
    analysisPanes.add(manualPlotFrame, height=460, stretch='always')

    _build_autoPlotFrame(autoPlotFrame)
    _build_manualPlotFrame(manualPlotFrame)

    reportLivesFrame = tk.Frame(dltsc.livePlotTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=90)

    reportLivesFrame.grid(row=3, column=0, padx=10, pady=(0, 10), sticky='ew')
    reportLivesFrame.grid_propagate(False)
    reportLivesFrame.grid_columnconfigure(0, weight=1)
    reportLivesFrame.grid_rowconfigure(0, weight=1)
    reportLivesFrame.config()

    dltsc.textbox = tk.Text(reportLivesFrame, wrap='none', width=1, height=5)
    dltsc.textbox.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
    if not hasattr(dltsc, 'textboxes') or dltsc.textboxes is None:
        dltsc.textboxes = []
    if dltsc.textbox not in dltsc.textboxes:
        dltsc.textboxes.append(dltsc.textbox)

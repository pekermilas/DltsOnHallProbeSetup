import tkinter as tk
import os
import re
import sys
import time
import copy
import threading

from tkinter import *
from tkinter import ttk
from tkinter import font
from tkinter import filedialog
from PIL import Image, ImageTk
from datetime import datetime
from pathlib import Path

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import agilent33220A_Control as awgC
import excitationTools as exT
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT
import convert_h5_to_text as h5txt


def _format_param_snapshot(param_vars):
    """Return a compact name=value snapshot for a dict of Tk variables."""
    snapshot = []
    for pname, pvar in param_vars.items():
        try:
            pvalue = pvar.get()
        except Exception:
            pvalue = pvar
        snapshot.append(f"{pname}={pvalue}")
    return ', '.join(snapshot)

def _get_param_values(param_vars):
    """Return a plain dict of current values from a dict of Tk variables."""
    values = {}
    for pname, pvar in param_vars.items():
        try:
            values[pname] = pvar.get()
        except Exception:
            values[pname] = pvar
    return values

def _apply_param_values(param_vars, values):
    """Restore plain values into a dict of Tk variables."""
    for pname, pvalue in values.items():
        if pname in param_vars:
            try:
                param_vars[pname].set(pvalue)
            except Exception:
                pass

def _ensure_param_history_state():
    """Initialize parameter history state stored in dltsConfig."""
    if not hasattr(dltsc, 'param_history') or dltsc.param_history is None:
        dltsc.param_history = []
    if not hasattr(dltsc, 'param_history_labels') or dltsc.param_history_labels is None:
        dltsc.param_history_labels = []
    if not hasattr(dltsc, 'param_history_selection') or dltsc.param_history_selection is None:
        dltsc.param_history_selection = tk.StringVar(value='')

def _capture_current_param_set(source='Manual Save'):
    """Capture all current parameter groups into one history entry."""
    return {
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'source': source,
        'z_params': _get_param_values(getattr(dltsc, 'z_params_vars', {})),
        't_params': _get_param_values(getattr(dltsc, 't_params_vars', {})),
        'd_params': _get_param_values(getattr(dltsc, 'd_params_vars', {})),
        'l_params': _get_param_values(getattr(dltsc, 'l_params_vars', {})),
    }

def _update_param_history_field():
    """Refresh the history combobox labels from stored entries."""
    _ensure_param_history_state()
    dltsc.param_history_labels = [
        f"{entry['timestamp']} | {entry['source']}"
        for entry in dltsc.param_history
    ]
    if hasattr(dltsc, 'param_history_inputField') and dltsc.param_history_inputField is not None:
        dltsc.param_history_inputField['values'] = dltsc.param_history_labels
        if dltsc.param_history_labels:
            dltsc.param_history_selection.set(dltsc.param_history_labels[0])
        else:
            dltsc.param_history_selection.set('')

def _save_current_param_set(source='Manual Save', should_log=False):
    """Store the current parameter set in a fixed-length history."""
    _ensure_param_history_state()
    entry = _capture_current_param_set(source=source)
    dltsc.param_history.insert(0, entry)
    dltsc.param_history = dltsc.param_history[:5]
    _update_param_history_field()
    if should_log:
        dltsc.log_to_textbox(f"Saved parameter set to history [{source}]")

def _load_selected_param_set():
    """Restore the currently selected parameter set from history."""
    _ensure_param_history_state()
    selected_label = dltsc.param_history_selection.get()
    if not selected_label or selected_label not in dltsc.param_history_labels:
        dltsc.log_to_textbox('No parameter history entry selected.')
        return 0

    selected_idx = dltsc.param_history_labels.index(selected_label)
    selected_entry = dltsc.param_history[selected_idx]
    _apply_param_values(getattr(dltsc, 'z_params_vars', {}), selected_entry['z_params'])
    _apply_param_values(getattr(dltsc, 't_params_vars', {}), selected_entry['t_params'])
    _apply_param_values(getattr(dltsc, 'd_params_vars', {}), selected_entry['d_params'])
    _apply_param_values(getattr(dltsc, 'l_params_vars', {}), selected_entry.get('l_params', {}))
    dltsc.log_to_textbox(f"Reloaded parameter set from history [{selected_entry['source']}]")
    return 0

def _sync_param_values_to_device(device, param_vars, device_type):
    """Flatten current UI state into a plain dict and push it into the device's params dict."""
    if device is None or param_vars is None:
        return {}

    values = {}
    for pname in list(param_vars):
        try:
            values[pname] = param_vars[pname].get()
        except Exception:
            values[pname] = param_vars[pname]

    typed_values = {}
    for pname in list(values):
        if device_type == 'impDev':
            typed_values[pname] = dltsc.recast_param_type('impDev', pname)
        elif device_type == 'tempDev':
            typed_values[pname] = dltsc.recast_param_type('tempDev', pname)
        else:
            typed_values[pname] = values[pname]

    for pName in list(device.params):
        if pName in typed_values:
            device.set_param_value(pName, typed_values)

    return typed_values

def _typed_param_values(device_type, param_vars):
    """{name: typed value} of a parameter group, skipping values that don't parse."""
    typed = {}
    for pname in list(param_vars or {}):
        try:
            typed[pname] = dltsc.recast_param_type(device_type, pname)
        except Exception:
            continue
    return typed

def _refresh_effective_mfia_params(z_typed):
    """MFIA values adjusted for the selected excitation method (an optical fill
    holds the bias at its reverse level); stored in dltsc.z_params_effective,
    which the MFIA prefers on every push / reload."""
    dltsc.z_params_effective = exT.mfia_override(z_typed, rdT.current_light_params())
    return dltsc.z_params_effective or z_typed

def _push_mfia_values(values):
    for pName in list(dltsc.impDev.params):
        if pName in values:
            dltsc.impDev.set_param_value(pName, values)
            dltsc.impDev.push_param_to_device(pName)

def _light_connected():
    return dltsc.lightDev is not None and getattr(dltsc.lightDev, 'state', False)

def _set_light_status(text):
    if dltsc.l_statusLabel is not None:
        dltsc.l_statusLabel.config(text=text)

def refresh_visa_resources():
    """Fill the AWG VISA Resource dropdown with the instruments VISA can see."""
    resources = awgC.list_resources()
    field = (dltsc.l_param_inputField or {}).get('AWG VISA Resource')
    if field is not None:
        field['values'] = resources
        current = dltsc.l_params_vars['AWG VISA Resource'].get()
        if not current and resources:
            preferred = [r for r in resources if r.upper().startswith('USB')] or resources
            dltsc.l_params_vars['AWG VISA Resource'].set(preferred[0])
    dltsc.log_to_textbox('Light source: VISA resources: ' + (', '.join(resources) if resources else 'none found'))
    return resources

def led_off_now():
    """The panel's LED OFF button: switch the 33220A output off immediately."""
    if dltsc.lightDev is not None and dltsc.lightDev.led_off():
        dltsc.log_to_textbox('Light source: output OFF.')
    else:
        dltsc.log_to_textbox('Light source: not connected (the LED driver arming switch is the hardware OFF).')

def disconnect_light_source():
    if dltsc.lightDev is not None:
        dltsc.lightDev.disconnect_device()
    dltsc.lightDev = None
    _set_light_status('Not connected')
    dltsc.log_to_textbox('Light source: disconnected (output OFF).')


def _temperature_port():
    """The port in the Serial Port box, or the driver's default."""
    var = getattr(dltsc, 't_portVar', None)
    port = var.get().strip() if var is not None else ''
    return port or tsC.DEFAULT_PORT


def refresh_serial_ports():
    """Fill the Serial Port dropdown with the ports Windows reports."""
    field = (dltsc.t_param_inputField or {}).get('Serial Port')
    ports = tsC.list_serial_ports()
    if field is not None:
        field['values'] = ports
    return ports


def connect_temperature_controller():
    """Connect dltsc.tempDev on the port in the Serial Port box.

    An already-open connection on the same port is kept. One on another port is
    closed first, without STOP, so a ramp the controller is running is not
    cancelled; earlier a new mK2000B was made each time while the old one still
    held the port, so reconnecting failed with "port in use". Refused while a
    run uses the controller. Returns 0 when connected, -1 otherwise (the reason
    is in the log)."""
    port = _temperature_port()
    old = dltsc.tempDev
    if old is not None and getattr(old, 'state', False):
        if old.port == port:
            dltsc.log_to_textbox(f'Temperature controller: already connected on {port}.')
            return 0
        if dltsc.run_busy:
            dltsc.log_to_textbox(f'Temperature controller: a run is using {old.port}; '
                                 f'not switching to {port} until it ends.')
            return -1
        old.disconnect_temp_controller(stopControl=False)
        dltsc.log_to_textbox(f'Temperature controller: closed {old.port} (control left running).')
    dev = tsC.mK2000B(port=port)
    if dev.connect_temp_controller() != 0:
        dltsc.tempDev = None
        dltsc.log_to_textbox(f'Temperature controller: NOT connected -- {dev.lastError}. '
                             'Check the Serial Port, the cable, and that no other program '
                             '(e.g. the Hall probe software) has the port open.')
        return -1
    dltsc.tempDev = dev
    dltsc.log_to_textbox(f'Temperature controller: connected on {port}.')
    return 0


def connect_and_get_params(devType='impedance'):
    if devType=='impedance':
        dltsc.impDev = ziC.ziDevice()
        dltsc.impDev.connect_device()
        time.sleep(1)

        dltsc.z_params_for_push = _sync_param_values_to_device(
            dltsc.impDev, getattr(dltsc, 'z_params_vars', {}), 'impDev'
        )
        _save_current_param_set(source='Connect/Get impedance')
        dltsc.log_to_textbox('Connect + Get Params [impedance]: ' +
                        _format_param_snapshot(dltsc.z_params_vars))

    if devType=='temperature':
        if connect_temperature_controller() != 0:
            return -1

        dltsc.t_params_for_push = _sync_param_values_to_device(
            dltsc.tempDev, getattr(dltsc, 't_params_vars', {}), 'tempDev'
        )
        _save_current_param_set(source='Connect/Get temperature')
        dltsc.log_to_textbox('Connect + Get Params [temperature]: ' +
                        _format_param_snapshot(dltsc.t_params_vars))

    if devType=='light':
        if dltsc.lightDev is not None:
            dltsc.lightDev.disconnect_device()
        resource = dltsc.l_params_vars['AWG VISA Resource'].get().strip()
        dltsc.lightDev = awgC.awgDevice()
        if dltsc.lightDev.connect_device(resource) != 0:
            dltsc.lightDev = None
            _set_light_status('Not connected')
            return -1
        dltsc.l_params_for_push = _typed_param_values('light', dltsc.l_params_vars)
        _set_light_status(f'Connected: {dltsc.lightDev.idn}  (output OFF)')
        _save_current_param_set(source='Connect/Get light')
        dltsc.log_to_textbox(f'Connect + Get Params [light]: {dltsc.lightDev.idn}; output OFF. ' +
                             _format_param_snapshot(dltsc.l_params_vars))

    return  0


def apply_and_push_params(devType='impedance'):
    if devType=='impedance':
        if dltsc.impDev is not None:
            if dltsc.impDev.device is not None:
                dltsc.z_params_for_push = _sync_param_values_to_device(
                    dltsc.impDev, getattr(dltsc, 'z_params_vars', {}), 'impDev'
                )
                if dltsc.z_params_for_push:
                    # Pushed as the selected excitation method needs them (an
                    # optical fill holds the bias constant); the GUI keeps the
                    # electrical values.
                    _push_mfia_values(_refresh_effective_mfia_params(dltsc.z_params_for_push))
                    _save_current_param_set(source='Apply/Push impedance')
                    dltsc.log_to_textbox('Apply + Push Params [impedance]: ' +
                                         _format_param_snapshot(dltsc.z_params_vars))
                else:
                    dltsc.log_to_textbox('Set impedance parameters first by Connect + Get Params!')
            else:
                dltsc.log_to_textbox('Apply + Push Params [impedance]: No device connected. ' +
                                _format_param_snapshot(dltsc.z_params_vars))
        else:
            dltsc.log_to_textbox('Apply + Push Params [impedance]: No device connected. ' +
                            _format_param_snapshot(dltsc.z_params_vars))
    if devType=='temperature':
        if dltsc.tempDev is not None:
            if dltsc.tempDev.dev is not None:
                dltsc.t_params_for_push = _sync_param_values_to_device(
                    dltsc.tempDev, getattr(dltsc, 't_params_vars', {}), 'tempDev'
                )
                if dltsc.t_params_for_push:
                    dltsc.tempDev.load_params(dltsc.t_params_for_push)
                    _save_current_param_set(source='Apply/Push temperature')
                    dltsc.log_to_textbox('Apply + Push Params [temperature]: ' +
                                    _format_param_snapshot(dltsc.t_params_vars))
                else:
                    dltsc.log_to_textbox('Set temperature parameters first by Connect + Get Params!')
            else:
                dltsc.log_to_textbox('Apply + Push Params [temperature]: No device connected. ' +
                                _format_param_snapshot(dltsc.t_params_vars))
        else:
            dltsc.log_to_textbox('Apply + Push Params [temperature]: No device connected. ' +
                            _format_param_snapshot(dltsc.t_params_vars))
    if devType=='light':
        typed = _typed_param_values('light', dltsc.l_params_vars)
        z_typed = _typed_param_values('impDev', dltsc.z_params_vars)
        errors = exT.validate({**exT.DEFAULT_LIGHT_PARAMS, **typed}, z_typed)
        if errors:
            for err in errors:
                dltsc.log_to_textbox(f'Apply + Push Params [light]: {err}')
            dltsc.log_to_textbox('Apply + Push Params [light]: not applied.')
            return -1
        dltsc.l_params_for_push = typed
        method = exT.method_info(typed)
        if _light_connected():
            dltsc.lightDev.led_off()     # configured and switched on only during acquisitions
        # The MFIA follows the method at once (an optical fill holds the bias constant).
        if dltsc.impDev is not None and getattr(dltsc.impDev, 'device', None) is not None:
            _push_mfia_values(_refresh_effective_mfia_params(z_typed))
        else:
            _refresh_effective_mfia_params(z_typed)
        _save_current_param_set(source='Apply/Push light')
        settings = exT.awg_settings(typed)
        detail = {'off': 'LED not used',
                  'pulse': f"LED pulse {settings.get('highV', 0):.3g} V at CTRL IN",
                  'dc': f"LED steady {settings.get('dcV', 0):.3g} V at CTRL IN"}[settings['mode']]
        dltsc.log_to_textbox(f"Apply + Push Params [light]: {method['name']}; {detail}. " +
                             _format_param_snapshot(dltsc.l_params_vars))
        if method['awg'] is not None and not _light_connected():
            dltsc.log_to_textbox('Apply + Push Params [light]: connect the 33220A before running.')
        return 0
    if devType=='output':
        selected_root = dltsc.d_params_vars['Data Root Folder'].get()
        if selected_root:
            _save_current_param_set(source='Apply/Push output')
            dltsc.log_to_textbox('Apply + Push Params [output]: ' +
                            _format_param_snapshot(dltsc.d_params_vars))
        else:
            dltsc.log_to_textbox('Apply + Push Params [output]: No data folder selected. ' +
                            _format_param_snapshot(dltsc.d_params_vars))
        return 0

def browse_root_folder():
    """Open a folder selection dialog and update Data Root Folder variable."""
    if hasattr(dltsc, 'd_params_vars') and 'Data Root Folder' in dltsc.d_params_vars:
        selected_path = filedialog.askdirectory()
        if selected_path:
            dltsc.d_params_vars['Data Root Folder'].set(selected_path)
            # The OS folder picker only shows folder NAMES, not what's already
            # inside one -- log a quick contents preview so picking the wrong
            # (possibly non-empty, about-to-be-overwritten) folder is obvious
            # right away instead of only surfacing once the run starts.
            try:
                entries = sorted(os.listdir(selected_path))
            except Exception as exc:
                entries = None
                dltsc.log_to_textbox(f"Data Root Folder: selected {selected_path} -- cannot list contents: {exc}")
            if entries is not None:
                if entries:
                    shown = ", ".join(entries[:12])
                    if len(entries) > 12:
                        shown += f", ... ({len(entries) - 12} more)"
                    dltsc.log_to_textbox(
                        f"Data Root Folder: selected {selected_path} -- already contains {len(entries)} "
                        f"item(s): {shown}")
                else:
                    dltsc.log_to_textbox(f"Data Root Folder: selected {selected_path} -- empty folder.")
        else:
            pass

    return 0

_exportButton = None

def export_h5_file():
    """'Export HDF5 File...': pick a .h5 step file, then where to save it as a
    readable tab-separated .txt table or .json (convert_h5_to_text.py). The
    export runs on a background thread; a 2^18-point step takes a few seconds."""
    initialDir = ''
    if 'Data Root Folder' in getattr(dltsc, 'd_params_vars', {}):
        initialDir = dltsc.d_params_vars['Data Root Folder'].get() or ''
    h5Path = filedialog.askopenfilename(title='Select an HDF5 step file to export',
                                        initialdir=initialDir or None,
                                        filetypes=[('HDF5 step files', '*.h5'), ('All files', '*.*')])
    if not h5Path:
        return 0
    outPath = filedialog.asksaveasfilename(
        title='Save readable copy as', initialdir=os.path.dirname(h5Path),
        initialfile=os.path.basename(h5txt.default_output_path(h5Path, 'txt')), defaultextension='.txt',
        filetypes=[('Text table, tab-separated (*.txt)', '*.txt'), ('JSON (*.json)', '*.json')])
    if not outPath:
        return 0

    if _exportButton is not None:
        _exportButton.config(state='disabled')
    dltsc.log_to_textbox(f"Exporting {os.path.basename(h5Path)} to {os.path.basename(outPath)}...")

    def worker():
        try:
            result = h5txt.export_h5(h5Path, outPath)
            msg = (f"Exported {os.path.basename(h5Path)} -> {result['output']} ({result['format'].upper()}, "
                   f"{result['rows']} rows x {result['channels']} channels, {result['bytes'] / 1024 ** 2:.1f} MB).")
        except Exception as exc:
            msg = f"Export of {os.path.basename(h5Path)} failed: {exc}"

        def apply():
            if _exportButton is not None:
                _exportButton.config(state='normal')
            dltsc.log_to_textbox(msg)
        dltsc.root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()
    return 0

def _construct_lightSourceFrame(style_names):
    """Light Source group (365 nm LED head driven by an Agilent 33220A), in
    its own panel to the right of the instrument parameters. See
    excitationTools.py for the methods and docs/optical_dlts_light_source.md
    for the wiring."""
    lightFrame = tk.Frame(dltsc.runParamsTab, highlightbackground="gray",
                          highlightthickness=1, highlightcolor='gray', width=430, height=770)
    lightFrame.grid(row=0, column=1, padx=(0, 10), pady=(2, 10), sticky='nw')
    lightFrame.grid_propagate(False)
    lightFrame.grid_columnconfigure(1, weight=1)

    ttk.Label(lightFrame, text='Light Source (Agilent 33220A + LED driver)', style=style_names['purple']['label'],
              font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', padx=4, pady=(4, 6))

    defaults = exT.DEFAULT_LIGHT_PARAMS
    method_options = [f"{k} - {v['name']}" for k, v in exT.METHODS.items()]
    l_param_list = [
        ('Excitation Method', method_options, method_options[defaults['Excitation Method']]),
        ('LED Driver Range', ['0 - 1 A (1 Ohm)', '1 - 100 mA (10 Ohm)'], None),
        ('LED Pulse Current (mA)', None, defaults['LED Pulse Current']),
        ('LED Pulse Width (s)', None, defaults['LED Pulse Width']),
        ('LED Pulse Delay (s)', None, defaults['LED Pulse Delay']),
        ('LED Steady Current (mA)', None, defaults['LED Steady Current']),
        ('Optical Timing Reference', ['0 - I_MON (Aux In 2)', '1 - Commanded Timing'], None),
        ('Commanded Timing Offset (s)', None, defaults['Commanded Timing Offset']),
        ('Record I_MON', ['0 - No', '1 - Yes'], None),
        ('AWG VISA Resource', 'editable', ''),
    ]
    dltsc.l_params_vars = {}
    dltsc.l_param_inputField = {}
    for idx, (plabel, options, pdef) in enumerate(l_param_list):
        pname = re.sub(r'\s*\([^)]*\)$', '', plabel)
        if isinstance(options, list) and pdef is None:
            pdef = next(o for o in options if int(o.split(' - ')[0]) == int(defaults[pname]))
        r = idx + 1
        ttk.Label(lightFrame, text=plabel, style=style_names['purple']['label']).grid(
            row=r, column=0, sticky='w', padx=4, pady=2)
        var = tk.StringVar(value=str(pdef))
        if isinstance(options, list):
            field = ttk.Combobox(lightFrame, textvariable=var, values=options, width=28, state='readonly')
        elif options == 'editable':
            field = ttk.Combobox(lightFrame, textvariable=var, values=[], width=28)
        else:
            field = ttk.Entry(lightFrame, textvariable=var, width=12)
        field.grid(row=r, column=1, sticky='ew', padx=4, pady=2)
        dltsc.l_param_inputField[pname] = field
        dltsc.l_params_vars[pname] = var

    row = len(l_param_list) + 1
    bframe = ttk.Frame(lightFrame)
    bframe.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(8, 2))
    for c in range(2):
        bframe.grid_columnconfigure(c, weight=1)
    ttk.Button(bframe, text='Refresh VISA List', style=style_names['purple']['button'],
               command=refresh_visa_resources).grid(row=0, column=0, padx=4, pady=2, sticky='ew')
    ttk.Button(bframe, text='Disconnect', style=style_names['purple']['button'],
               command=disconnect_light_source).grid(row=0, column=1, padx=4, pady=2, sticky='ew')
    ttk.Button(bframe, text='Connect + Get Params', style=style_names['purple']['button'],
               command=lambda: connect_and_get_params(devType='light')).grid(
        row=1, column=0, padx=4, pady=2, sticky='ew')
    ttk.Button(bframe, text='Apply + Push Params', style=style_names['purple']['button'],
               command=lambda: apply_and_push_params(devType='light')).grid(
        row=1, column=1, padx=4, pady=2, sticky='ew')
    tk.Button(bframe, text='LED OFF', fg='white', bg='#c62828', activebackground='#8e0000',
              font=('Segoe UI', 10, 'bold'), command=led_off_now).grid(
        row=2, column=0, columnspan=2, padx=4, pady=(6, 2), sticky='ew')

    dltsc.l_statusLabel = ttk.Label(lightFrame, text='Not connected', wraplength=400, justify='left')
    dltsc.l_statusLabel.grid(row=row + 1, column=0, columnspan=2, sticky='w', padx=4, pady=(4, 2))
    ttk.Label(lightFrame, wraplength=400, justify='left', foreground='gray', text=(
        "The LED runs only while data is being taken; the driver's arming switch is the hardware "
        "interlock. Optical Fill holds the bias at the reverse level (Aux Output Offset + Scale) and "
        "fires the LED instead of the fill pulse. Delay is from the MFIA Trigger Out 2 rising edge. "
        "Wiring: 33220A Output -> CTRL IN; MFIA Trigger Out 2 -> 33220A Trig In; I_MON -> MFIA Aux In 2.")
              ).grid(row=row + 2, column=0, columnspan=2, sticky='w', padx=4, pady=(4, 2))


def construct_runParamsTab():
    global _exportButton
    root = dltsc.root
    runParamsTab = dltsc.runParamsTab
    tabControl = dltsc.tabControl

    tabControl.add(runParamsTab, text='Input Parameters')
    tabControl.pack(expand=1, fill="both")

    style = ttk.Style()
    # Use namespaced ttk styles so repeated builds or other tabs do not clobber colors.
    style_names = {
        "blue": {"label": "Dlts.Blue.TLabel", "button": "Dlts.Blue.TButton"},
        "red": {"label": "Dlts.Red.TLabel", "button": "Dlts.Red.TButton"},
        "green": {"label": "Dlts.Green.TLabel", "button": "Dlts.Green.TButton"},
        "purple": {"label": "Dlts.Purple.TLabel", "button": "Dlts.Purple.TButton"},
    }
    for color_name, names in style_names.items():
        style.configure(names["label"], foreground=color_name)
        style.configure(names["button"], foreground=color_name)
        # Keep custom foreground on common button states across reruns/theme refreshes.
        style.map(names["button"],
                  foreground=[('!disabled', color_name), ('active', color_name), ('pressed', color_name)])

    # Allow tab content to expand with the notebook window.
    dltsc.runParamsTab.grid_rowconfigure(0, weight=0)
    dltsc.runParamsTab.grid_rowconfigure(1, weight=1)
    dltsc.runParamsTab.grid_columnconfigure(0, weight=1)

    # Construct Impedance Analyzer Parameters Frame
    # -------------------------------------------------------------------------
    runParamsFrame = tk.Frame(dltsc.runParamsTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=770)

    runParamsFrame.grid(row=0, column=0, padx=10, pady=(2, 10), sticky='ew')
    runParamsFrame.grid_propagate(False)
    runParamsFrame.grid_columnconfigure(0, weight=1)
    runParamsFrame.grid_columnconfigure(1, weight=1)
    runParamsFrame.grid_columnconfigure(2, weight=0)
    runParamsFrame.grid_columnconfigure(3, weight=1)
    runParamsFrame.config()

    # Construct Impedance Analyzer Parameters
    # -------------------------------------------------------------------------
    z_param_list = [
        ('Oscillation Amplitude (V)', '0.300'),
        ('Oscillation Frequency (Hz)', '501000'),
        ('Oscillation ON/OFF', '1 - On'),
        ('Max bandwidth (Hz)', '10000'),
        ('Input Control', '0 - Manual'),
        ('Current Range (A)', '0.010'),
        ('Voltage Range (V)', '3'),
        ('Omega Suppression (dB)', '80'),
        ('Filter Harmonic', '1'),
        ('Filter Bandwidth (Hz)', '2'),
        ('Data Transfer Rate (Sa/s)', '60000'),
        ('Equivalent Circuit Mode', '0 - 4-Terminal'),
        ('Threshold Input Signal', '59 - TU Output Value'),
        ('State Enable Time (s)', '0.006'),
        ('State Disable Time (s)', '0.003'),
        ('Logic Unit Not', '1 - On'),
        ('Aux Output Signal', '13 - TU Output Value'),
        ('Aux Output Scale (V)', '-1'),
        ('Aux Output Offset (V)', '-0.5'),
        ('Aux Output Lower Limit (V)', '-10'),
        ('Aux Output Upper Limit (V)', '0'),
        ('Signal Output Add', '1 - True'),
        ('Trigger Source Signal', '36 - Threshold 1'),
        # Trigger Out 2 -> the light source's 33220A Trig In (Light Source panel)
        ('Trigger 2 Source Signal', '36 - Threshold 1')
    ]

    # define parameters that should be dropdowns (multiple-choice) with human-readable labels
    param_options = {
        'Oscillation ON/OFF': [
            '0 - Off',
            '1 - On'
        ],
        'Input Control': [
            '0 - Manual',
            '1 - Auto',
            '2 - Current Zone'
        ],
        'Filter Harmonic': [
            '1', '2', '3', '4', '5', '6', '7', '8',
            '9', '10', '11', '12', '13', '14', '15', '16'
        ],
        'Filter Bandwidth': [
            '1', '2', '3', '4', '5', '6', '7', '8'
        ],
        'Equivalent Circuit Mode': [
            '0 - 4-Terminal',
            '1 - 2-Terminal'
        ],
        'Threshold Input Signal': [
            '59 - TU Output Value',
            '58 - Aux Output Overload',
            '56 - Aux Input Overload',
            '55 - Output Overload',
            '54 - Input(I) Overload',
            '53 - Input(V) Overload',
            '52 - Trigger Out',
            '51 - Trigger In',
            '50 - DIO',
            '3 - Demod Theta',
            '2 - Demod R',
            '1 - Demod Y',
            '0 - Demod X'
        ],
        'Logic Unit Not': [
            '0 - Off',
            '1 - On'
        ],
        'Aux Output Signal': [
            '0 - Demod X',
            '1 - Demod Y',
            '2 - Demod R',
            '3 - Demod Theta',
            '11 - TU Filtered Value',
            '12 - Manual',
            '13 - TU Output Value'
        ],
        'Signal Output Add': [
            '0 - False',
            '1 - True'
        ],
        'Trigger Source Signal': [
            '0 - Off',
            '1 - Osc Phi Demod 2',
            '36 - Threshold 1',
            '37 - Threshold 2',
            '38 - Threshold 3',
            '39 - Threshold 4',
            '52 - MDS Sync Out'
        ]
    }
    param_options['Trigger 2 Source Signal'] = list(param_options['Trigger Source Signal'])

    dltsc.z_params_vars = {}
    # lay out parameters starting at row 2 below impedance inputs

    dltsc.z_param_inputField = dict()

    for idx, (plabel, pdef) in enumerate(z_param_list):
        # Labels carry units for display only; ziDevice.params, recast_param_type
        # and param_options are keyed by the bare name, e.g. 'Oscillation Amplitude'.
        pname = re.sub(r'\s*\([^)]*\)$', '', plabel)
        r = idx
        c = 0
        lbl = ttk.Label(runParamsFrame, text=plabel, style=style_names['blue']['label'])
        lbl.grid(row=r, column=c, sticky='w', padx=4, pady=2)
        var = tk.StringVar(value=pdef)
        # if parameter has a set of known options, use a Combobox dropdown
        if pname in param_options:
            dltsc.z_param_inputField[pname] = ttk.Combobox(runParamsFrame, textvariable=var,
                                                           values=param_options[pname], width=16,
                                                           state='readonly')
            dltsc.z_param_inputField[pname].set(pdef)
            dltsc.z_param_inputField[pname].grid(row=r, column=c + 1, sticky='ew', padx=4, pady=2)
        else:
            dltsc.z_param_inputField[pname] = ttk.Entry(runParamsFrame, textvariable=var, width=16)
            dltsc.z_param_inputField[pname].grid(row=r, column=c + 1, sticky='ew', padx=4, pady=2)
        dltsc.z_params_vars[pname] = var

    # Device / control buttons at the bottom of the impedance panel
    cframe = ttk.Frame(runParamsFrame)
    button_row = len(z_param_list)
    cframe.grid(row=button_row, column=0, columnspan=4, sticky='ew', pady=(8, 2))

    connect_btn1 = ttk.Button(cframe, text='Connect + Get Params', style=style_names['blue']['button'],
                               command=lambda: connect_and_get_params(devType='impedance'))
    connect_btn1.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    apply_btn1 = ttk.Button(cframe, text='Apply + Push Params', style=style_names['blue']['button'],
                             command=lambda: apply_and_push_params(devType='impedance'))
    apply_btn1.grid(row=0, column=1, padx=4, pady=0, sticky='ew')


    # Construct Temperature Controller Params
    # -------------------------------------------------------------------------
    dltsc.t_params_vars = dict()
    # Room Temperature / Room Ramp: where (and how fast) the stage is returned
    # to once a run finishes or stops on an error (runDlts_Tools.return_to_room_temp).
    t_param_list = [('Initial Temperature (C)', '25'), ('Final Temperature (C)', '25'),
                    ('Temperature Step (C)', '5'), ('Temperature Ramp (C/min)', '5'),
                    ('Stability Delay (s)', '0'), ('Room Temperature (C)', '25'),
                    ('Room Ramp (C/min)', '10')]
    dltsc.t_param_inputField = dict(t_param_list)

    for idx, (pname, pdef) in enumerate(t_param_list):
        var = tk.StringVar(value=pdef)
        lbl = ttk.Label(runParamsFrame, text=pname, style=style_names['red']['label'])
        lbl.grid(row=idx, column=2, sticky='w', padx=4, pady=2)
        dltsc.t_param_inputField[pname] = ttk.Entry(runParamsFrame, width=8, textvariable=var)
        dltsc.t_param_inputField[pname].grid(row=idx, column=3, sticky='ew', padx=4, pady=2)
        dltsc.t_params_vars[pname] = var

    # Device / control buttons at the bottom of the temperature panel
    tframe = ttk.Frame(runParamsFrame)
    tframe.grid(row=len(t_param_list), column=2, columnspan=4, sticky='ew', pady=(8, 2))

    # spacer1 = ttk.Label(runParamsFrame, text="")
    # spacer1.grid(row=6, column=2)
    # spacer2 = ttk.Label(runParamsFrame, text="")
    # spacer2.grid(row=6, column=3)

    connect_btn2 = ttk.Button(tframe, text='Connect + Get Params', style=style_names['red']['button'],
                               command=lambda: connect_and_get_params(devType='temperature'))
    connect_btn2.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    apply_btn2 = ttk.Button(tframe, text='Apply + Push Params', style=style_names['red']['button'],
                             command=lambda: apply_and_push_params(devType='temperature'))
    apply_btn2.grid(row=0, column=1, padx=4, pady=0, sticky='ew')

    # Serial port of the mK2000B (used by Connect + Get Params). Editable, so a
    # port Windows does not list yet can still be typed in.
    ttk.Label(tframe, text='Serial Port', style=style_names['red']['label']).grid(
        row=1, column=0, padx=4, pady=(4, 0), sticky='e')
    dltsc.t_portVar = tk.StringVar(value=tsC.DEFAULT_PORT)
    portBox = ttk.Combobox(tframe, textvariable=dltsc.t_portVar, width=10,
                           values=tsC.list_serial_ports(), postcommand=refresh_serial_ports)
    portBox.grid(row=1, column=1, padx=4, pady=(4, 0), sticky='w')
    dltsc.t_param_inputField['Serial Port'] = portBox

    # Construct Data Params
    # -------------------------------------------------------------------------
    dltsc.d_params_vars = dict()
    # 'TXT' is the correct default here: the on-disk content is always JSON
    # (runDlts_Tools.run_experiment() writes it via writeDataJson() for both
    # the 'txt' and 'json' Data File Format selections -- the content format
    # never changes), but files are meant to carry a .txt extension per
    # impedanceAnalysis_Tools.impdData.read_data()'s expected convention. A
    # 'JSON' default here previously made the file extension come out as
    # .json instead.
    d_param_list = [('Number of Points (power of 2)', 16), ('Number of Reps', 500),
                    ('Data File Format', 'TXT'), ('Data Root Folder', '')]
    dltsc.d_param_inputField = dict(d_param_list)

    idx_offset = len(t_param_list)+2
    for idx, (pname, pdef) in enumerate(d_param_list):
        var = tk.StringVar(value=pdef)
        lbl = ttk.Label(runParamsFrame, text=pname, style=style_names['green']['label'])
        lbl.grid(row=idx+idx_offset, column=2, sticky='w', padx=4, pady=2)
        if pname == 'Data File Format':
            dltsc.d_param_inputField[pname] = ttk.Combobox(runParamsFrame, width=16, textvariable=var,
                                                           values=["TXT", "HDF5"], state='readonly')
            dltsc.d_param_inputField[pname].grid(row=idx+idx_offset, column=3, sticky='ew', padx=4, pady=0)

        elif pname == 'Data Root Folder':
            dltsc.d_param_inputField[pname] = ttk.Button(runParamsFrame, text='Browse...',
                                                         style=style_names['green']['button'], command=browse_root_folder)
            dltsc.d_param_inputField[pname].grid(row=idx+idx_offset, column=3, sticky='ew', padx=4, pady=0)
        else:
            dltsc.d_param_inputField[pname] = ttk.Entry(runParamsFrame, width=8, textvariable=var)
            dltsc.d_param_inputField[pname].grid(row=idx+idx_offset, column=3, sticky='ew', padx=4, pady=2)
        dltsc.d_params_vars[pname] = var

    # Device / control buttons at the bottom of the temperature panel
    oframe = ttk.Frame(runParamsFrame)
    oframe_row = idx_offset + len(d_param_list)
    oframe.grid(row=oframe_row, column=2, columnspan=4, sticky='ew', pady=(8, 2))

    apply_btn4 = ttk.Button(oframe, text='Apply + Push Params', style=style_names['green']['button'],
                             command=lambda: apply_and_push_params(devType='output'))
    apply_btn4.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    # Readable .txt/.json copy of one HDF5 step file, for inspection.
    _exportButton = ttk.Button(oframe, text='Export HDF5 File...', style=style_names['green']['button'],
                               command=export_h5_file)
    _exportButton.grid(row=0, column=1, padx=4, pady=0, sticky='ew')

    history_frame = ttk.Frame(runParamsFrame)
    # Place history controls below the existing parameter rows to avoid altering row heights above.
    history_frame.grid(row=max(len(dltsc.z_param_inputField)//2+1, oframe_row+1), column=2, columnspan=4,
                       sticky='ew', pady=(8, 2))
    history_frame.grid_columnconfigure(0, weight=1)

    history_lbl = ttk.Label(history_frame, text='Parameter History', style=style_names['purple']['label'])
    history_lbl.grid(row=0, column=0, sticky='w', padx=4, pady=(0, 2))

    _ensure_param_history_state()
    dltsc.param_history_inputField = ttk.Combobox(history_frame, width=34,
                                                  textvariable=dltsc.param_history_selection,
                                                  values=[], state='readonly')
    dltsc.param_history_inputField.grid(row=1, column=0, columnspan=2, sticky='ew', padx=4, pady=0)

    save_history_btn = ttk.Button(history_frame, text='Save Current', style=style_names['purple']['button'],
                                  command=lambda: _save_current_param_set(source='Manual Save', should_log=True))
    save_history_btn.grid(row=2, column=0, padx=4, pady=(4, 0), sticky='ew')

    load_history_btn = ttk.Button(history_frame, text='Load Selected', style=style_names['purple']['button'],
                                  command=_load_selected_param_set)
    load_history_btn.grid(row=2, column=1, padx=4, pady=(4, 0), sticky='ew')

    spacer1 = ttk.Label(history_frame, text="")
    spacer1.grid(row=3, column=0)
    spacer2 = ttk.Label(history_frame, text="")
    spacer2.grid(row=3, column=1)

    _update_param_history_field()

    _construct_lightSourceFrame(style_names)

    reportParamsFrame = tk.Frame(dltsc.runParamsTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=220)

    reportParamsFrame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 2), sticky='nsew')
    reportParamsFrame.grid_rowconfigure(0, weight=1)
    reportParamsFrame.grid_columnconfigure(0, weight=1)
    reportParamsFrame.config()

    dltsc.textbox = tk.Text(reportParamsFrame, wrap='none', width=1, height=10)
    dltsc.textbox.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
    if not hasattr(dltsc, 'textboxes') or dltsc.textboxes is None:
        dltsc.textboxes = []
    if dltsc.textbox not in dltsc.textboxes:
        dltsc.textboxes.append(dltsc.textbox)

    return 0
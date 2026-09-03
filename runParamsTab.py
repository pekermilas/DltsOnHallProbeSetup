import tkinter as tk
import os
import sys
import time

from tkinter import *
from tkinter import ttk
from tkinter import font
from tkinter import filedialog
from PIL import Image, ImageTk
from datetime import datetime
from pathlib import Path

from bokeh.colors.groups import purple
from param.ipython import blue

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT


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
    dltsc.log_to_textbox(f"Reloaded parameter set from history [{selected_entry['source']}]")
    return 0

def connect_and_get_params(devType='impedance'):
    if devType=='impedance':
        dltsc.impDev = ziC.ziDevice()
        dltsc.impDev.connect_device()
        time.sleep(1)
        for pName in list(dltsc.impDev.params):
            dltsc.impDev.set_param_value(pName, dltsc.z_params_vars)
        _save_current_param_set(source='Connect/Get impedance')
        dltsc.log_to_textbox('Connect + Get Params [impedance]: ' +
                        _format_param_snapshot(dltsc.z_params_vars))

    if devType=='temperature':
        dltsc.tempDev = None
        dltsc.tempDev = tsC.mK2000B()
        dltsc.tempDev.connect_temp_controller()
        time.sleep(1)
        for pName in list(dltsc.tempDev.params):
            dltsc.tempDev.set_param_value(pName, dltsc.t_params_vars)
        _save_current_param_set(source='Connect/Get temperature')
        dltsc.log_to_textbox('Connect + Get Params [temperature]: ' +
                        _format_param_snapshot(dltsc.t_params_vars))

    return  0

def apply_and_push_params(devType='impedance'):
    if devType=='impedance':
        if dltsc.impDev.device is not None:
            for pName in list(dltsc.impDev.params):
                dltsc.impDev.push_param_to_device(pName)
            _save_current_param_set(source='Apply/Push impedance')
            dltsc.log_to_textbox('Apply + Push Params [impedance]: ' +
                            _format_param_snapshot(dltsc.z_params_vars))
        else:
            dltsc.log_to_textbox('Apply + Push Params [impedance]: No device connected. ' +
                            _format_param_snapshot(dltsc.z_params_vars))
    if devType=='temperature':
        if dltsc.tempDev.dev is not None:
            dltsc.tempDev.load_params(dltsc.t_params_vars)
            _save_current_param_set(source='Apply/Push temperature')
            dltsc.log_to_textbox('Apply + Push Params [temperature]: ' +
                            _format_param_snapshot(dltsc.t_params_vars))
        else:
            dltsc.log_to_textbox('Apply + Push Params [temperature]: No device connected. ' +
                            _format_param_snapshot(dltsc.t_params_vars))
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
        else:
            pass

    return 0

def construct_runParamsTab():
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
                              width=860, height=730)

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
        ('Oscillation Amplitude', '0.300'),
        ('Oscillation Frequency', '501000'),
        ('Oscillation ON/OFF', '1 - On'),
        ('Max bandwidth', '10000'),
        ('Input Control', '0 - Manual'),
        ('Current Range', '0.010'),
        ('Voltage Range', '3'),
        ('Omega Suppression', '80'),
        ('Filter Harmonic', '1'),
        ('Filter Bandwidth', '2'),
        ('Data Transfer Rate', '60000'),
        ('Equivalent Circuit Mode', '0 - 4-Terminal'),
        ('Threshold Input Signal', '59 - TU Output Value'),
        ('State Enable Time', '0.006'),
        ('State Disable Time', '0.003'),
        ('Logic Unit Not', '1 - On'),
        ('Aux Output Signal', '13 - TU Output Value'),
        ('Aux Output Scale', '-1'),
        ('Aux Output Offset', '-0.5'),
        ('Aux Output Lower Limit', '-10'),
        ('Aux Output Upper Limit', '0'),
        ('Signal Output Add', '1 - True'),
        ('Trigger Source Signal', '36 - Threshold 1')
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

    dltsc.z_params_vars = {}
    # Legacy dynamic device-param editor is not rendered; keep dict for push/load helpers.
    device_param_vars = {}
    # lay out parameters starting at row 2 below impedance inputs

    dltsc.z_param_inputField = dict()
    for i in range(len(z_param_list)):
        variable_name = list(z_param_list)[i]
        dltsc.z_param_inputField[variable_name] = None

    for idx, (pname, pdef) in enumerate(z_param_list):
        r = idx
        c = 0
        lbl = ttk.Label(runParamsFrame, text=pname, style=style_names['blue']['label'])
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
    t_param_list = [('Initial Temperature (C)', '25'), ('Final Temperature (C)', '25'),
                    ('Number of Temperatures', '1'), ('Temperature Ramp (C/min)', '5'),
                    ('Stability Delay (s)', '0')]
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
    tframe.grid(row=5, column=2, columnspan=4, sticky='ew', pady=(8, 2))

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

    # Construct Data Frame
    # -------------------------------------------------------------------------
    dltsc.d_params_vars = dict()
    d_param_list = [('Number of Points (power of 2)', 16), ('Number of Reps', 500),
                    ('Data File Format', 'JSON'), ('Data Root Folder', '')]
    dltsc.d_param_inputField = dict(d_param_list)

    idx_offset = len(t_param_list)+2
    for idx, (pname, pdef) in enumerate(d_param_list):
        var = tk.StringVar(value=pdef)
        lbl = ttk.Label(runParamsFrame, text=pname, style=style_names['green']['label'])
        lbl.grid(row=idx+idx_offset, column=2, sticky='w', padx=4, pady=2)
        if pname == 'Data File Format':
            dltsc.d_param_inputField[pname] = ttk.Combobox(runParamsFrame, width=16, textvariable=var,
                                                           values=["JSON", "HDF5"], state='readonly')
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
    oframe.grid(row=11, column=2, columnspan=4, sticky='ew', pady=(8, 2))

    apply_btn4 = ttk.Button(oframe, text='Apply + Push Params', style=style_names['green']['button'],
                             command=lambda: apply_and_push_params(devType='output'))
    apply_btn4.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    history_frame = ttk.Frame(runParamsFrame)
    # Place history controls below the existing parameter rows to avoid altering row heights above.
    history_frame.grid(row=len(dltsc.z_param_inputField)//2+1, column=2, columnspan=4, sticky='ew', pady=(8, 2))
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

    _update_param_history_field()

    reportParamsFrame = tk.Frame(dltsc.runParamsTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=220)

    reportParamsFrame.grid(row=1, column=0, padx=10, pady=(0, 2), sticky='nsew')
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
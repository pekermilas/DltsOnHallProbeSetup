import tkinter as tk
import os
import sys

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

def connect_devices(devType='impedance'):
    if devType=='impedance':
        dltsc.impDev = None
        dltsc.impDev = ziC.ziDevice()
        dltsc.impDev.connectDevice()

    if devType=='temperature':
        dltsc.tempDev = None
        dltsc.tempDev = tsC.mK2000B()
        dltsc.tempDev.connectTempController()

    return  0

def apply_and_push_params(devType='impedance'):
    if devType=='impedance':
        if dltsc.impDev.device is not None:
            dltsc.impDev.applyParams()
            for pName in list(self.params):
                dltsc.impDev.setParam(pName)

    if devType=='temperature':
        if dltsc.tempDev.dev is not None:
            dltsc.tempDev.applyParams()
    if devType=='output':
        return 0


def browse_root_folder():
    """Open a folder selection dialog and set the Root Folder entry."""
    dltsc.d_param_inputField['Data Root Folder'] = None
    dltsc.d_param_inputField['Data Root Folder'] = filedialog.askdirectory()

    if dltsc.d_param_inputField['Data Root Folder'] is None:
        print('Folder selection canceled.')
    else:
        print(f'Selected folder: {dltsc.d_param_inputField["Data Root Folder"]}')
    return 0

def construct_runParamsTab():
    root = dltsc.root
    runParamsTab = dltsc.runParamsTab
    tabControl = dltsc.tabControl

    tabControl.add(runParamsTab, text='Run Parameters')
    tabControl.pack(expand=1, fill="both")

    style = ttk.Style()
    # 2. Configure a custom style name (e.g., "Red.TLabel")
    # The name must end with the widget's default class name ".TLabel"
    colors = ["blue", "red", "green", "purple"]
    for c in colors:
        style.configure(c + '.TLabel', foreground=c)
        style.configure(c + '.TButton', foreground=c)


    # Construct Impedance Analyzer Parameters Frame
    # -------------------------------------------------------------------------
    runParamsLabel = tk.Label(dltsc.runParamsTab, text="Run Parameters",
                              font=("Segoe UI", 14), fg='black')
    runParamsLabel.grid(row=0, column=0, padx=70, pady=2)

    runParamsFrame = tk.Frame(dltsc.runParamsTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=700)

    runParamsFrame.grid(row=1, column=0, padx=10, pady=2)
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
        # r = (idx // 2) + 2
        # c = (idx % 2) * 2
        r = idx
        c = 0
        # lbl = ttk.Label(runParamsFrame, text=pname, foreground='blue')
        lbl = ttk.Label(runParamsFrame, text=pname, style='blue.TLabel')
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

    connect_btn1 = ttk.Button(cframe, text='Connect Device', style='blue.TButton', command=lambda: connect_devices(devType='impedance'))
    connect_btn1.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    apply_btn1 = ttk.Button(cframe, text='Apply + Push Params', style='blue.TButton', command=lambda: apply_and_push_params(devType='impedance'))
    apply_btn1.grid(row=0, column=1, padx=4, pady=0, sticky='ew')


    # Construct Temperature Controller Frame
    # -------------------------------------------------------------------------
    dltsc.t_param_inputField = dict()
    t_param_list = ['Initial Temperature (C)', 'Final Temperature (C)',
                    'Number of Temperatures', 'Temperature Ramp (C/min)',
                    'Stability Delay (s)']
    for i in range(len(t_param_list)):
        variable_name = list(t_param_list)[i]
        dltsc.t_param_inputField[variable_name] = None

    for i in range(len(t_param_list)):
        pname = list(t_param_list)[i]
        lbl = ttk.Label(runParamsFrame, text=pname, style='red.TLabel')
        lbl.grid(row=i, column=2, sticky='w', padx=4, pady=2)
        dltsc.t_param_inputField[pname] = ttk.Entry(runParamsFrame, width=8)
        dltsc.t_param_inputField[pname].insert(0, '25')
        dltsc.t_param_inputField[pname].grid(row=i, column=3, sticky='ew', padx=4, pady=2)

    # Device / control buttons at the bottom of the temperature panel
    tframe = ttk.Frame(runParamsFrame)
    tframe.grid(row=5, column=2, columnspan=4, sticky='ew', pady=(8, 2))

    connect_btn2 = ttk.Button(tframe, text='Connect Device', style='red.TButton', command=lambda: connect_devices(devType='temperature'))
    connect_btn2.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    apply_btn2 = ttk.Button(tframe, text='Apply + Push Params', style='red.TButton', command=lambda: apply_and_push_params(devType='temperature'))
    apply_btn2.grid(row=0, column=1, padx=4, pady=0, sticky='ew')

    spacer1 = ttk.Label(runParamsFrame, text="")
    spacer1.grid(row=6, column=2)
    spacer2 = ttk.Label(runParamsFrame, text="")
    spacer2.grid(row=6, column=3)
    # -----------------------------------------------------------------------------------------------------------
    dltsc.d_param_inputField = dict()
    d_param_list = ['Number of Points (power of 2)', 'Number of Reps',
                    'Data File Format', 'Data Root Folder']
    for i in range(len(d_param_list)):
        variable_name = list(d_param_list)[i]
        dltsc.d_param_inputField[variable_name] = None

    idx_offset = len(t_param_list)+2
    for i in range(len(d_param_list)):
        pname = list(d_param_list)[i]
        lbl = ttk.Label(runParamsFrame, text=pname, style='green.TLabel')
        lbl.grid(row=i+idx_offset, column=2, sticky='w', padx=4, pady=2)
        if pname == 'Data File Format':
            dltsc.d_param_inputField[pname] = ttk.Combobox(runParamsFrame, width=16,
                                                           values=["JSON", "HDF5"], state='readonly')
            dltsc.d_param_inputField[pname].set("JSON")
            dltsc.d_param_inputField[pname].grid(row=i+idx_offset, column=3, sticky='ew', padx=4, pady=0)

        elif pname == 'Data Root Folder':
            dltsc.d_param_inputField[pname] = ttk.Button(runParamsFrame, text='Browse...',
                                                         style='green.TButton', command=browse_root_folder)
            dltsc.d_param_inputField[pname].grid(row=i+idx_offset, column=3, sticky='ew', padx=4, pady=2)
        else:
            dltsc.d_param_inputField[pname] = ttk.Entry(runParamsFrame, width=8)
            dltsc.d_param_inputField[pname].insert(0, '25')
            dltsc.d_param_inputField[pname].grid(row=i+idx_offset, column=3, sticky='ew', padx=4, pady=2)

    # Device / control buttons at the bottom of the temperature panel
    oframe = ttk.Frame(runParamsFrame)
    oframe.grid(row=13, column=2, columnspan=4, sticky='ew', pady=(8, 2))

    apply_btn4 = ttk.Button(oframe, text='Apply + Push Params', style='purple.TButton', command=lambda: apply_and_push_params(devType='output'))
    apply_btn4.grid(row=0, column=0, padx=4, pady=0, sticky='ew')





    return 0
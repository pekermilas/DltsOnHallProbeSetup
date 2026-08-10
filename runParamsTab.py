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
        dltsc.impDev = ziC.ziDevice()
        dltsc.impDev.connectDevice()

    if devType=='temperature':
        dltsc.tempDev = tsC.mK2000B()
        dltsc.tempDev.connectTempController()

    return 0

def apply_and_push_params(devType='impedance'):
    if devType=='impedance':
        return 0
    if devType=='temperature':
        return 0
    if devType=='output':
        return 0


def browse_root_folder():
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

    zprms = dict()
    for i in range(len(z_param_list)):
        variable_name = f"prms_{i}"
        zprms[variable_name] = None

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
            cb = ttk.Combobox(runParamsFrame, textvariable=var, values=param_options[pname], width=16, state='readonly')
            cb.set(pdef)
            cb.grid(row=r, column=c + 1, sticky='ew', padx=4, pady=2)
        else:
            ent = ttk.Entry(runParamsFrame, textvariable=var, width=16)
            ent.grid(row=r, column=c + 1, sticky='ew', padx=4, pady=2)
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
    lblt1 = ttk.Label(runParamsFrame, text='Initial Temperature (C)', style='red.TLabel')
    lblt1.grid(row=0, column=2, sticky='w', padx=4, pady=2)
    tinit_e = ttk.Entry(runParamsFrame, width=8)
    tinit_e.insert(0, '25')
    tinit_e.grid(row=0, column=3, sticky='ew', padx=4, pady=2)

    lblt2 = ttk.Label(runParamsFrame, text='Final Temperature (C)', style='red.TLabel')
    lblt2.grid(row=1, column=2, sticky='w', padx=4, pady=2)
    tfin_e = ttk.Entry(runParamsFrame, width=8)
    tfin_e.insert(0, '25')
    tfin_e.grid(row=1, column=3, sticky='ew', padx=4, pady=2)

    lblt3 = ttk.Label(runParamsFrame, text='Number of Temperatures', style='red.TLabel')
    lblt3.grid(row=2, column=2, sticky='w', padx=4, pady=2)
    ntemp_e = ttk.Entry(runParamsFrame, width=8)
    ntemp_e.insert(0, '1')
    ntemp_e.grid(row=2, column=3, sticky='ew', padx=4, pady=2)

    lblt4 = ttk.Label(runParamsFrame, text='Temperature Ramp (C/min)', style='red.TLabel')
    lblt4.grid(row=3, column=2, sticky='w', padx=4, pady=2)
    tramp_e = ttk.Entry(runParamsFrame, width=8)
    tramp_e.insert(0, '5')
    tramp_e.grid(row=3, column=3, sticky='ew', padx=4, pady=2)

    lblt5 = ttk.Label(runParamsFrame, text='Stability Delay (s)', style='red.TLabel')
    lblt5.grid(row=4, column=2, sticky='w', padx=4, pady=2)
    tdelay_e = ttk.Entry(runParamsFrame, width=8)
    tdelay_e.insert(0, '0')
    tdelay_e.grid(row=4, column=3, sticky='ew', padx=4, pady=2)

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

    lblti1 = ttk.Label(runParamsFrame, text='Number of Points (power of 2)', style='green.TLabel')
    lblti1.grid(row=7, column=2, sticky='w')
    npts_e = ttk.Entry(runParamsFrame, width=8)
    npts_e.insert(0, '13')
    npts_e.grid(row=7, column=3, sticky='ew')

    lblti2 = ttk.Label(runParamsFrame, text='Number of Reps', style='green.TLabel')
    lblti2.grid(row=8, column=2, sticky='w')
    nreps_e = ttk.Entry(runParamsFrame, width=8)
    nreps_e.insert(0, '1')
    nreps_e.grid(row=8, column=3, sticky='ew')

    # Device / control buttons at the bottom of the temperature panel
    aframe = ttk.Frame(runParamsFrame)
    aframe.grid(row=9, column=2, columnspan=4, sticky='ew', pady=(8, 2))

    apply_btn3 = ttk.Button(aframe, text='Apply + Push Params', style='green.TButton', command=lambda: apply_and_push_params(devType='temperature'))
    apply_btn3.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    spacer3 = ttk.Label(runParamsFrame, text="")
    spacer3.grid(row=10, column=2)
    spacer4 = ttk.Label(runParamsFrame, text="")
    spacer4.grid(row=10, column=3)

    lblti3 = ttk.Label(runParamsFrame, text='Data File Format', style='purple.TLabel')
    lblti3.grid(row=11, column=2, sticky='w')
    cb = ttk.Combobox(runParamsFrame, width=16, state='readonly')
    cb["values"] = ["JSON", "HDF5"]
    cb.current(0)
    cb.grid(row=11, column=3, sticky='ew', padx=4, pady=0)

    lblti4 = ttk.Label(runParamsFrame, text='Data Root Folder', style='purple.TLabel')
    lblti4.grid(row=12, column=2, sticky='w')
    browse_btn = ttk.Button(runParamsFrame, text='Browse...', style='purple.TButton', command=browse_root_folder)
    browse_btn.grid(row=12, column=3, padx=4, pady=0, sticky='ew')

    # Device / control buttons at the bottom of the temperature panel
    oframe = ttk.Frame(runParamsFrame)
    oframe.grid(row=13, column=2, columnspan=4, sticky='ew', pady=(8, 2))

    apply_btn4 = ttk.Button(oframe, text='Apply + Push Params', style='purple.TButton', command=lambda: apply_and_push_params(devType='output'))
    apply_btn4.grid(row=0, column=0, padx=4, pady=0, sticky='ew')





    return 0
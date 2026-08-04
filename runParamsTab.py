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

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT

def getSourPrefix():
    return 0
def connect_devices():
    return 0
def apply_and_push_params():
    return 0

def construct_runParamsTab():
    root = dltsc.root
    runParamsTab = dltsc.runParamsTab
    tabControl = dltsc.tabControl

    tabControl.add(runParamsTab, text='Run Parameters')
    tabControl.pack(expand=1, fill="both")

    dltsc.tempDev = tsC.mK2000B()
    # button is to be added dltsc.tempDev.connectTempController()
    dltsc.impDev = ziC.ziDevice()
    # button is to be added dltsc.impDev.connectDevice()

    # Construct Impedance Analyzer Parameters Frame
    # -------------------------------------------------------------------------
    impParamsLabel = tk.Label(dltsc.runParamsTab, text="Impedance Analyzer Parameters",
                              font=("Segoe UI", 14), fg='blue')
    impParamsLabel.grid(row=0, column=0, padx=70, pady=2)

    impParamsFrame = tk.Frame(dltsc.runParamsTab, highlightbackground="blue",
                              highlightthickness=1, highlightcolor='blue',
                              width=300, height=300)
    impParamsFrame.grid(row=1, column=0, padx=70, pady=2)
    impParamsFrame.config()


    # Construct GUI Fields for Setting Impedance Analyzer Parameters
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
    for idx, (pname, pdef) in enumerate(z_param_list):
        r = (idx // 2) + 2
        c = (idx % 2) * 2
        lbl = ttk.Label(impParamsFrame, text=pname)
        lbl.grid(row=r, column=c, sticky='w', padx=4, pady=2)
        var = tk.StringVar(value=pdef)
        # if parameter has a set of known options, use a Combobox dropdown
        if pname in param_options:
            cb = ttk.Combobox(impParamsFrame, textvariable=var, values=param_options[pname], width=16, state='readonly')
            cb.set(pdef)
            cb.grid(row=r, column=c + 1, sticky='ew', padx=4, pady=2)
        else:
            ent = ttk.Entry(impParamsFrame, textvariable=var, width=16)
            ent.grid(row=r, column=c + 1, sticky='ew', padx=4, pady=2)
        dltsc.z_params_vars[pname] = var

    # Device / control buttons at the bottom of the impedance panel
    cframe = ttk.Frame(impParamsFrame)
    button_row = ((len(z_param_list) - 1) // 2) + 3
    cframe.grid(row=button_row, column=0, columnspan=4, sticky='ew', pady=(8, 2))

    connect_btn = ttk.Button(cframe, text='Connect Devices', command=connect_devices)
    connect_btn.grid(row=0, column=0, padx=4, pady=0, sticky='ew')

    apply_btn = ttk.Button(cframe, text='Apply + Push Params', command=apply_and_push_params)
    apply_btn.grid(row=0, column=1, padx=4, pady=0, sticky='ew')

    # dltsc.sourcePrefixSelection = tk.ttk.Combobox(impParamsFrame, width="15", font=("Segoe UI", 10))
    # dltsc.sourcePrefixSelection["values"] = ["base","(milli)m","(micro)\u03bc","(nano)n","(pico)p"]
    # dltsc.sourcePrefixSelection.current(0)
    # dltsc.sourcePrefixSelection.grid(row=1, column=1, padx=10, pady=10)
    # sourcePrefixSelectionButton = tk.Button(impParamsFrame, text='Source Prefix',
    #                                    font=("Segoe UI", 10), bd=1, command=getSourPrefix)
    # sourcePrefixSelectionButton.grid(row=0, column=1, padx=10, pady=10)







    # dltsc.tControllerOnOff = False
    # hpc.switchBoxOnOff = False
    # hpc.sourcemeterOnOff = False
    # hpc.magArduControllerOnOff = False
    # hpc.magGRBLControllerOnOff = False
    #
    # hpc.switchBox = None
    # hpc.tController = None
    # hpc.sourcemeter = None
    # hpc.magnetArduino = None
    # hpc.magnetGRBL = None
    #
    # hpc.hdwrConns = 0
    # hpc.sfwrConns = 0
    # hpc.runState = 0
    #
    # hpc.senseRange = 0
    #

    # # Set experiment type
    # # -------------------------------------------------------------------------
    # hpc.expTypeSelection = tk.ttk.Combobox(expParamsFrame, width="15", font=("Segoe UI", 10))
    # hpc.expTypeSelection["values"] = ["Sample Test", "Resistivity", "Hall Probe", "Resistivity Hall"]
    # hpc.expTypeSelection.current(0)
    # hpc.expTypeSelection.grid(row=1, column=0, padx=10, pady=10)
    # expTypeSelectionButton = tk.Button(expParamsFrame, text='Experiment Type',
    #                                    font=("Segoe UI", 10), bd=1, command=getExpType)
    # expTypeSelectionButton.grid(row=0, column=0, padx=10, pady=10)
    #
    # # Set source prefix
    # # -------------------------------------------------------------------------
    # hpc.sourcePrefixSelection = tk.ttk.Combobox(expParamsFrame, width="15", font=("Segoe UI", 10))
    # hpc.sourcePrefixSelection["values"] = ["base", "(milli)m", "(micro)\u03bc", "(nano)n", "(pico)p"]
    # hpc.sourcePrefixSelection.current(0)
    # hpc.sourcePrefixSelection.grid(row=1, column=1, padx=10, pady=10)
    # sourcePrefixSelectionButton = tk.Button(expParamsFrame, text='Source Prefix',
    #                                         font=("Segoe UI", 10), bd=1, command=getSourPrefix)
    # sourcePrefixSelectionButton.grid(row=0, column=1, padx=10, pady=10)
    #
    # # Source constants
    # # -------------------------------------------------------------------------
    # sourceInitButton = tk.Button(expParamsFrame, text='Initial Source', bd=1,
    #                              font=("Segoe UI", 10), command=getInitSource)
    # sourceInitButton.grid(row=0, column=2, padx=4, pady=10)
    # hpc.sourceInitEntry = tk.Entry(expParamsFrame, width=15)
    # hpc.sourceInitEntry.grid(row=1, column=2, padx=4, pady=10)
    #
    # sourceFinalButton = tk.Button(expParamsFrame, text='Final Source', bd=1,
    #                               font=("Segoe UI", 10), command=getFinalSource)
    # sourceFinalButton.grid(row=0, column=3, padx=4, pady=10)
    # hpc.sourceFinalEntry = tk.Entry(expParamsFrame, width=15)
    # hpc.sourceFinalEntry.grid(row=1, column=3, padx=4, pady=10)
    #
    # sourceNumButton = tk.Button(expParamsFrame, text='Number of Sources', bd=1,
    #                             font=("Segoe UI", 10), command=getNumSource)
    # sourceNumButton.grid(row=0, column=4, padx=4, pady=10)
    # hpc.sourceNumEntry = tk.Entry(expParamsFrame, width=20)
    # hpc.sourceNumEntry.grid(row=1, column=4, padx=4, pady=10)
    #
    # # Magnet constants
    # # -------------------------------------------------------------------------
    # hpc.magPosSelection = tk.ttk.Combobox(expParamsFrame, width="15", font=("Segoe UI", 10))
    # hpc.magPosSelection["values"] = ["Back(0)", "Front(1)"]
    # hpc.magPosSelection.current(0)
    # hpc.magPosSelection.grid(row=3, column=0, padx=10, pady=10)
    # magPosSelectionButton = tk.Button(expParamsFrame, text='Initial\nMagnet Position',
    #                                   font=("Segoe UI", 10), bd=1, command=getMagPos)
    # magPosSelectionButton.grid(row=2, column=0, padx=10, pady=10)
    #
    # hpc.magPolSelection = tk.ttk.Combobox(expParamsFrame, width="15", font=("Segoe UI", 10))
    # hpc.magPolSelection["values"] = ["N-Up(0)", "S-Up(1)"]
    # hpc.magPolSelection.current(0)
    # hpc.magPolSelection.grid(row=3, column=1, padx=10, pady=10)
    # magPolSelectionButton = tk.Button(expParamsFrame, text='Initial\nMagnet Polarity',
    #                                   font=("Segoe UI", 10), bd=1, command=getMagPol)
    # magPolSelectionButton.grid(row=2, column=1, padx=10, pady=10)
    #
    # # Tempreature constants
    # # -------------------------------------------------------------------------
    # temprInitButton = tk.Button(expParamsFrame, text='Initial\nTemperature', bd=1,
    #                             font=("Segoe UI", 10), command=getInitTempr)
    # temprInitButton.grid(row=2, column=2, padx=4, pady=10)
    # hpc.temprInitEntry = tk.Entry(expParamsFrame, width=15)
    # hpc.temprInitEntry.grid(row=3, column=2, padx=4, pady=10)
    #
    # temprFinalButton = tk.Button(expParamsFrame, text='Final\nTemperature', bd=1,
    #                              font=("Segoe UI", 10), command=getFinalTempr)
    # temprFinalButton.grid(row=2, column=3, padx=4, pady=10)
    # hpc.temprFinalEntry = tk.Entry(expParamsFrame, width=15)
    # hpc.temprFinalEntry.grid(row=3, column=3, padx=4, pady=10)
    #
    # temprNumButton = tk.Button(expParamsFrame, text='Number of\nTemperatures', bd=1,
    #                            font=("Segoe UI", 10), command=getNumTempr)
    # temprNumButton.grid(row=2, column=4, padx=4, pady=10)
    # hpc.temprNumEntry = tk.Entry(expParamsFrame, width=20)
    # hpc.temprNumEntry.grid(row=3, column=4, padx=4, pady=10)
    #
    # temprDelayTimeButton = tk.Button(expParamsFrame, text='Temperature\nDelay(s)', bd=1,
    #                                  font=("Segoe UI", 10), command=getDelayTempr)
    # temprDelayTimeButton.grid(row=4, column=1, padx=4, pady=10)
    # hpc.temprDelayTimeEntry = tk.Entry(expParamsFrame, width=15)
    # hpc.temprDelayTimeEntry.grid(row=5, column=1, padx=4, pady=10)
    #
    # # Set sense Voltage range
    # # -------------------------------------------------------------------------
    # hpc.senseRangeSelection = tk.ttk.Combobox(expParamsFrame, width="15", font=("Segoe UI", 10))
    # hpc.senseRangeSelection["values"] = ["AUTO", "20mV", "200mV", "2V", "20V", "200V", "1nA", \
    #                                      "10nA", "100nA", "1\u03bcA", "10\u03bcA", \
    #                                      "100\u03bcA", "1mA", "10mA", "100mA", "1A", "FULL AUTO"]
    # hpc.senseRangeSelection.current(0)
    # hpc.senseRangeSelection.grid(row=5, column=2, padx=10, pady=10)
    # senseRangeSelectionButton = tk.Button(expParamsFrame, text='Sense Range',
    #                                       font=("Segoe UI", 10), bd=1, command=getSenseRange)
    # senseRangeSelectionButton.grid(row=4, column=2, padx=10, pady=10)
    #
    # # Set data folder
    # # -------------------------------------------------------------------------
    # setDataFolderButton = tk.Button(expParamsFrame, text='Set data folder!', bd=1,
    #                                 font=("Segoe UI", 12), command=setDataFolder)
    # setDataFolderButton.grid(row=4, column=3, padx=4, pady=10)
    # # setDataFolderButton.config(height = 3, width = 15)
    #
    # # Construct Hardware Connections Frame
    # # -------------------------------------------------------------------------
    # hdwConnsLabel = tk.Label(hpc.expTab, text="Hardware Connections",
    #                          font=("Segoe UI", 14), fg='red')
    # hdwConnsLabel.grid(row=2, column=0, padx=70, pady=2)
    #
    # hdwConnsFrame = tk.Frame(hpc.expTab, highlightbackground="red",
    #                          highlightthickness=1, highlightcolor='red',
    #                          width=300, height=300)
    # hdwConnsFrame.grid(row=3, column=0, padx=70, pady=2)
    # hdwConnsFrame.config()
    #
    # # Set communication ports
    # # -------------------------------------------------------------------------
    # hpc.port_list = ["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    #                  "COM9", "COM10", "COM11", "COM12"]
    # hpc.tControllerPortSelection = tk.ttk.Combobox(hdwConnsFrame, values=hpc.port_list,
    #                                                width="15", font=("Segoe UI", 10))
    # hpc.tControllerPortSelection.current(6)
    # hpc.tControllerPortSelection.grid(row=1, column=0, padx=10, pady=10)
    # tControllerPortSelectionButton = tk.Button(hdwConnsFrame, text='Temperature\nController Port',
    #                                            font=("Segoe UI", 10), bd=1,
    #                                            command=lambda: getComPort('tController'))
    # tControllerPortSelectionButton.grid(row=0, column=0, padx=10, pady=10)
    #
    # hpc.arduinoSwitchBoxPortSelection = tk.ttk.Combobox(hdwConnsFrame, values=hpc.port_list,
    #                                                     width="15", font=("Segoe UI", 10))
    # hpc.arduinoSwitchBoxPortSelection.current(5)
    # hpc.arduinoSwitchBoxPortSelection.grid(row=1, column=1, padx=10, pady=10)
    # arduinoSwitchBoxPortSelectionButton = tk.Button(hdwConnsFrame, text='Switchbox\nPort',
    #                                                 font=("Segoe UI", 10), bd=1,
    #                                                 command=lambda: getComPort('arduinoSwitchBox'))
    # arduinoSwitchBoxPortSelectionButton.grid(row=0, column=1, padx=10, pady=10)
    #
    # hpc.arduinoMagnetPortSelection = tk.ttk.Combobox(hdwConnsFrame, values=hpc.port_list,
    #                                                  width="15", font=("Segoe UI", 10))
    # hpc.arduinoMagnetPortSelection.current(2)
    # hpc.arduinoMagnetPortSelection.grid(row=1, column=2, padx=10, pady=10)
    # arduinoMagnetPortSelectionButton = tk.Button(hdwConnsFrame, text='Arduino\nMagnet Port',
    #                                              font=("Segoe UI", 10), bd=1,
    #                                              command=lambda: getComPort('arduinoMagnet'))
    # arduinoMagnetPortSelectionButton.grid(row=0, column=2, padx=10, pady=10)
    #
    # hpc.GRBLMagnetPortSelection = tk.ttk.Combobox(hdwConnsFrame, values=hpc.port_list,
    #                                               width="15", font=("Segoe UI", 10))
    # hpc.GRBLMagnetPortSelection.current(3)
    # hpc.GRBLMagnetPortSelection.grid(row=1, column=3, padx=10, pady=10)
    # GRBLMagnetPortSelectionButton = tk.Button(hdwConnsFrame, text='GRBL\nMagnet Port',
    #                                           font=("Segoe UI", 10), bd=1,
    #                                           command=lambda: getComPort('GRBLMagnet'))
    # GRBLMagnetPortSelectionButton.grid(row=0, column=3, padx=10, pady=10)
    #
    # # # Connect hardware button
    # # # -------------------------------------------------------------------------
    # # connHrdwButton = tk.Button(hdwConnsFrame, text='Connect to all Hardwares', bd=1,
    # #                            font=("Segoe UI", 10), command=connHardware)
    # # connHrdwButton.grid(row=2, column=4, padx=4, pady=10)
    # # # setDataFolderButton.config(height = 3, width = 15)
    #
    # # Runtime Frame
    # # -------------------------------------------------------------------------
    # runTimeLabel = tk.Label(hpc.expTab, text="Run Experiment",
    #                         font=("Segoe UI", 14), fg='green')
    # runTimeLabel.grid(row=4, column=0, padx=70, pady=3)
    #
    # runTimeFrame = tk.Frame(hpc.expTab, highlightbackground="green",
    #                         highlightthickness=1, highlightcolor='green',
    #                         width=600, height=300)
    # runTimeFrame.grid(row=5, column=0, padx=70, pady=2)
    # runTimeFrame.config()
    #
    # # Connect Hardware button
    # # -------------------------------------------------------------------------
    # resizeOnImage = hpc.on.resize((150, 60))
    # resizeOffImage = hpc.off.resize((150, 60))
    # hpc.on = ImageTk.PhotoImage(resizeOnImage)
    # hpc.off = ImageTk.PhotoImage(resizeOffImage)
    # hwConnLabel = tk.Label(runTimeFrame, text="Check Hardware",
    #                        font=("Segoe UI", 14), fg='red')
    # hwConnLabel.grid(row=0, column=0, padx=20, pady=2)
    # hpc.hwConnButton = tk.Button(runTimeFrame, image=hpc.off, bd=0, command=chkHardware)
    # hpc.hwConnButton.grid(row=1, column=0, ipadx=10, ipady=20)
    #
    # # Run button
    # # -------------------------------------------------------------------------
    # swConnLabel = tk.Label(runTimeFrame, text="Check Parameters",
    #                        font=("Segoe UI", 14), fg='blue')
    # swConnLabel.grid(row=0, column=1, padx=20, pady=2)
    # hpc.swConnButton = tk.Button(runTimeFrame, image=hpc.off, bd=0, command=chkSoftware)
    # hpc.swConnButton.grid(row=1, column=1, ipadx=10, ipady=20)
    #
    # # # Run button
    # # # -------------------------------------------------------------------------
    # # expRunLabel = tk.Label(runTimeFrame, text = "Run",
    # #                           font=("Segoe UI", 14), fg='green')
    # # expRunLabel.grid(row=0, column=2, padx=20, pady=2)
    # # hpc.expRunButton = tk.Button(runTimeFrame, text='Start', font=("Segoe UI", 12),
    # #                              bd=1, width=20, height=2, command=runSwitch)
    # # hpc.expRunButton.grid(row=1, column=2, padx=5, pady=2)

    return 0
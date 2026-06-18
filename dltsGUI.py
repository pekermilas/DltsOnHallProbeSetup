# -*- coding: utf-8 -*-
"""
Lightweight Tkinter GUI wrapper for runDLTS.py (dltsRun)

This GUI acts as a thin layer on top of the existing runDlts_Tools / device
libraries and does not modify those modules. It provides three tabs:

- Parameters: configure temperature sweep, impedance and data storage options
- Live Plot: run the experiment and display simple live plots of the acquired data
- Post Processing: load saved data files and run a simple analysis routine

The GUI performs device connections by calling the existing device classes
in `instecTempStage_Control.py` and `zurichInstruments_Control.py` and then
runs the measurement loop in a background thread so the UI remains responsive.

Author: generated
"""

import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time
import os
import json

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt

import numpy as np
from pathlib import Path

import runDlts_Tools as rdT
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC


class DLTSGui:
    def __init__(self, root):
        self.root = root
        self.root.title('DLTS Control GUI')

        s = ttk.Style()
        s.configure('TNotebook.Tab', font=('Arial', 11), padding=6)

        self.tabControl = ttk.Notebook(self.root)

        # dlts run object
        self.run = rdT.dltsRun()
        self.run.runDevices = []

        # state
        self.connected = False
        self._stop_request = False
        self._run_thread = None

        # Live-plot runtime state (initialize before building tabs so controls can read defaults)
        # ordered list of seen data files (oldest first)
        self._live_file_order = []
        # mapping filename -> dict with arrays and matplotlib Line2D objects
        self._live_datasets = {}
        self._live_watcher_thread = None
        self._live_watcher_stop = threading.Event()
        self._live_poll_interval = 1.0  # seconds
        # maximum number of traces to keep visible in the live plot
        self._live_max_traces = 5
        # exponential fade strength (gamma) for alpha mapping
        self._live_fade_gamma = 3.0
        # filenames to ignore when scanning folder (e.g., runParams file)
        self._live_ignore_files = set(['runParams.txt'])
        # sync flag for limit syncing to avoid recursion
        self._syncing_limits = False

        # Build tabs
        self._build_params_tab()
        self._build_live_tab()
        self._build_postproc_tab()

        # Simulation helper classes for testing without hardware
        class _SimTemp:
            def __init__(self):
                self.Tinitial = 25
                self.Tfinal = 25
                self.numTemps = 1
                self.tempGrid = np.array([25.])
            def connectTempController(self):
                time.sleep(0.1)
                return 0
            def disconnTController(self):
                return 0
            def goToTemp(self, Tf, ramp, delay):
                # simulate ramp time
                time.sleep(min(0.2 + abs(Tf - (self.tempGrid[0] if len(self.tempGrid)>0 else self.Tinitial))/max(ramp,1), 2.0))
                return 0
            def goToRoomTemp(self, Tr=25, ramp=5):
                time.sleep(0.1)
                return 0

        class _SimImp:
            def __init__(self):
                self.devSerial = 'simDev'
                self.params = {}
                self.device = type('D', (), {'factory_reset': lambda self_: None})()
                self.session = type('S', (), {'disconnect_device': lambda self_, x: None})()
            def connectDevice(self):
                time.sleep(0.1)
                return 0
            def reloadParams(self):
                return 0
            def pullData(self, plot=False, trigger=False, numPoints=1024, numReps=1):
                # generate synthetic data
                n = int(min(numPoints, 4096))
                t = np.linspace(0, 1, n)
                re = np.sin(2 * np.pi * 5 * t) + 1.0 + 0.01 * np.random.randn(n)
                im = np.cos(2 * np.pi * 5 * t) + 0.5 + 0.01 * np.random.randn(n)
                aux = 0.1 * np.sin(2 * np.pi * 1 * t) + 0.01 * np.random.randn(n)
                data = {
                    'tickStampImps': t * 60e6,
                    'tickStampDemods': t * 60e6,
                    'timeStampImps': t,
                    'timeStampDemods': t,
                    'ImpedanceRe': re.tolist(),
                    'ImpedanceIm': im.tolist(),
                    'AbsZ': np.sqrt(re**2 + im**2).tolist(),
                    'AuxInput1': aux.tolist()
                }
                time.sleep(0.2)
                return data
            def writeDataJson(self, data, fName):
                try:
                    os.makedirs(os.path.dirname(fName), exist_ok=True)
                    with open(fName, 'w') as f:
                        json.dump(data, f, default=lambda o: o.tolist() if hasattr(o, 'tolist') else o)
                except Exception:
                    pass
                return 0

        # expose sim classes for use in methods
        self._SimTemp = _SimTemp
        self._SimImp = _SimImp

        self.tabControl.pack(expand=1, fill='both')

    def _build_params_tab(self):
        self.paramsTab = ttk.Frame(self.tabControl)
        self.tabControl.add(self.paramsTab, text='Parameters')

        frm = ttk.Frame(self.paramsTab, padding=8)
        frm.pack(fill='both', expand=True)

        # Temperature group
        tframe = ttk.LabelFrame(frm, text='Temperature Controller Parameters', padding=8)
        tframe.grid(row=0, column=0, sticky='nw', padx=6, pady=6)

        ttk.Label(tframe, text='Initial (C)').grid(row=0, column=0, sticky='w')
        self.tinit_e = ttk.Entry(tframe, width=8)
        self.tinit_e.insert(0, '25')
        self.tinit_e.grid(row=0, column=1)

        ttk.Label(tframe, text='Final (C)').grid(row=1, column=0, sticky='w')
        self.tfin_e = ttk.Entry(tframe, width=8)
        self.tfin_e.insert(0, '25')
        self.tfin_e.grid(row=1, column=1)

        ttk.Label(tframe, text='# Temps').grid(row=2, column=0, sticky='w')
        self.ntemp_e = ttk.Entry(tframe, width=8)
        self.ntemp_e.insert(0, '1')
        self.ntemp_e.grid(row=2, column=1)

        ttk.Label(tframe, text='Ramp (C/min)').grid(row=3, column=0, sticky='w')
        self.tramp_e = ttk.Entry(tframe, width=8)
        self.tramp_e.insert(0, '5')
        self.tramp_e.grid(row=3, column=1)

        ttk.Label(tframe, text='Stable Delay (s)').grid(row=4, column=0, sticky='w')
        self.tdelay_e = ttk.Entry(tframe, width=8)
        self.tdelay_e.insert(0, '0')
        self.tdelay_e.grid(row=4, column=1)

        # Combined Impedance + Zurich device parameters
        imps_frame = ttk.LabelFrame(frm, text='Impedance Analyzer Parameters', padding=8)
        # place to the right of temperature controls and allow extra vertical space
        imps_frame.grid(row=0, column=1, rowspan=2, sticky='ne', padx=6, pady=6)

        # Impedance inputs
        ttk.Label(imps_frame, text='Num Points (power of 2)').grid(row=0, column=0, sticky='w')
        self.npts_e = ttk.Entry(imps_frame, width=10)
        self.npts_e.insert(0, '13')
        self.npts_e.grid(row=0, column=1)

        ttk.Label(imps_frame, text='Num Reps').grid(row=1, column=0, sticky='w')
        self.nreps_e = ttk.Entry(imps_frame, width=10)
        self.nreps_e.insert(0, '1')
        self.nreps_e.grid(row=1, column=1)

        # Zurich device parameters (explicit inputs mirroring zurichInstruments_Control.assignParam)
        # list of parameters and sensible defaults taken from zurichInstruments_Control.assignParam
        self.z_param_list = [
            ('Oscillation Frequency', '501000'),
            ('Max bandwidth', '10000'),
            ('Input Control', '0 - Manual'),
            ('Current Range', '0.010'),
            ('Voltage Range', '3'),
            ('Omega Suppression', '80'),
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
            'Input Control': [
                '0 - Manual',
                '1 - Auto',
                '2 - Current Zone'
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

        self.z_params_vars = {}
        # lay out parameters starting at row 2 to leave space for impedance inputs
        for idx, (pname, pdef) in enumerate(self.z_param_list):
            r = (idx // 2) + 2
            c = (idx % 2) * 2
            lbl = ttk.Label(imps_frame, text=pname)
            lbl.grid(row=r, column=c, sticky='w', padx=4, pady=2)
            var = tk.StringVar(value=pdef)
            # if parameter has a set of known options, use a Combobox dropdown
            if pname in param_options:
                cb = ttk.Combobox(imps_frame, textvariable=var, values=param_options[pname], width=16, state='readonly')
                cb.set(pdef)
                cb.grid(row=r, column=c+1, sticky='w', padx=4, pady=2)
            else:
                ent = ttk.Entry(imps_frame, textvariable=var, width=16)
                ent.grid(row=r, column=c+1, sticky='w', padx=4, pady=2)
            self.z_params_vars[pname] = var

        # Data group
        dframe = ttk.LabelFrame(frm, text='Output Data Parameters', padding=8)
        dframe.grid(row=1, column=0, sticky='sw', padx=6, pady=6)

        ttk.Label(dframe, text='Output Type').grid(row=0, column=0, sticky='w')
        self.outtype_cb = ttk.Combobox(dframe, values=['txt','h5'], width=6)
        self.outtype_cb.set('txt')
        self.outtype_cb.grid(row=0, column=1)

        ttk.Label(dframe, text='Root Folder').grid(row=1, column=0, sticky='w')
        self.rootfolder_e = ttk.Entry(dframe, width=40)
        # default to current user's Desktop/DATA/DLTS to avoid hard-coded other-user paths
        default_root = os.path.join(str(Path.home()), 'Desktop', 'DATA', 'DLTS')
        self.rootfolder_e.insert(0, os.path.expanduser(default_root))
        self.rootfolder_e.grid(row=1, column=1, columnspan=1, sticky='w')
        # Browse button to select root folder via file explorer
        ttk.Button(dframe, text='Browse...', command=self.browse_root_folder).grid(row=1, column=2, padx=4)

        self.liveplot_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dframe, text='Live Plot', variable=self.liveplot_var).grid(row=2, column=0, sticky='w')
        self.sensefail_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dframe, text='Sense Run Failure', variable=self.sensefail_var).grid(row=2, column=1, sticky='w')
        # Simulation mode for testing without hardware
        self.sim_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dframe, text='Simulation Mode', variable=self.sim_var).grid(row=3, column=0, sticky='w')

        # Device / control buttons
        cframe = ttk.Frame(frm)
        cframe.grid(row=1, column=1, sticky='se', padx=6, pady=6)

        self.connect_btn = ttk.Button(cframe, text='Connect Devices', command=self.connect_devices)
        self.connect_btn.grid(row=0, column=0, padx=4, pady=4)

        self.apply_btn = ttk.Button(cframe, text='Apply Params', command=self.apply_params)
        self.apply_btn.grid(row=0, column=1, padx=4, pady=4)

        self.status_lbl = ttk.Label(frm, text='Not connected', foreground='red')
        # relocate status to an open area on the Parameters tab (right side)
        self.status_lbl.grid(row=2, column=1, sticky='e', padx=8, pady=6)

        # Device parameters frame (loads params from ziDevice)
        dparams_frame = ttk.LabelFrame(frm, text='Device Parameters (Zurich)', padding=6)
        dparams_frame.grid(row=3, column=0, columnspan=2, sticky='we', padx=6, pady=6)
        # Buttons to load and push
        dpbtns = ttk.Frame(dparams_frame)
        dpbtns.pack(fill='x')
        ttk.Button(dpbtns, text='Load Device Params', command=self.load_device_params).pack(side='left', padx=4, pady=4)
        ttk.Button(dpbtns, text='Push Params to Device', command=self.push_device_params).pack(side='left', padx=4, pady=4)

        # container for parameter widgets
        self.dp_container = ttk.Frame(dparams_frame)
        self.dp_container.pack(fill='both', expand=True)
        self.device_param_vars = {}

    def _build_live_tab(self):
        self.liveTab = ttk.Frame(self.tabControl)
        self.tabControl.add(self.liveTab, text='Live Plot')

        left = ttk.Frame(self.liveTab)
        left.pack(side='left', fill='both', expand=True)

        # Matplotlib figure
        self.fig, self.axes = plt.subplots(2,2, figsize=(6,5))
        # reduce whitespace among plots
        try:
            self.fig.subplots_adjust(hspace=0.28, wspace=0.22)
        except Exception:
            pass
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        # Add matplotlib navigation toolbar to allow pan/zoom interactivity
        try:
            toolbar = NavigationToolbar2Tk(self.canvas, left)
            toolbar.update()
            self.canvas.get_tk_widget().pack(fill='both', expand=True)
        except Exception:
            pass

        # connect axis limit change callbacks to synchronize zoom/pan
        try:
            for ax in self.axes.flatten():
                # callbacks pass the Axes instance
                ax.callbacks.connect('xlim_changed', self._on_xlim_changed)
                ax.callbacks.connect('ylim_changed', self._on_ylim_changed)
        except Exception:
            pass

        # ...existing code...

        ctrl = ttk.Frame(self.liveTab)
        ctrl.pack(side='right', fill='y')

        # Plot controls: polling interval, max traces, watch folder
        pctrl = ttk.LabelFrame(ctrl, text='Plot Controls', padding=6)
        pctrl.pack(fill='x', padx=6, pady=6)

        ttk.Label(pctrl, text='Poll Interval (s)').grid(row=0, column=0, sticky='w')
        self.poll_interval_var = tk.DoubleVar(value=self._live_poll_interval)
        self.poll_spin = ttk.Spinbox(pctrl, from_=0.1, to=10.0, increment=0.1, textvariable=self.poll_interval_var, width=6)
        self.poll_spin.grid(row=0, column=1, sticky='w', padx=4)

        ttk.Label(pctrl, text='Max Traces').grid(row=0, column=2, sticky='w')
        self.max_traces_var = tk.IntVar(value=self._live_max_traces)
        self.max_spin = ttk.Spinbox(pctrl, from_=1, to=20, increment=1, textvariable=self.max_traces_var, width=4)
        self.max_spin.grid(row=0, column=3, sticky='w', padx=4)

        ttk.Label(pctrl, text='Watch Folder').grid(row=1, column=0, sticky='w', pady=(6,0))
        self.watchfolder_e = ttk.Entry(pctrl, width=36)
        self.watchfolder_e.grid(row=1, column=1, columnspan=2, sticky='w', padx=4, pady=(6,0))
        ttk.Button(pctrl, text='Browse', command=lambda: self._pick_watch_folder()).grid(row=1, column=3, sticky='w', padx=4, pady=(6,0))
        ttk.Button(pctrl, text='Load Folder Now', command=lambda: self._load_watch_folder_now()).grid(row=2, column=0, columnspan=4, sticky='we', pady=(6,0))

        # small listbox showing loaded files and their temperature labels
        ttk.Label(pctrl, text='Loaded files:').grid(row=3, column=0, sticky='w', pady=(6,0))
        self.loaded_files_list = tk.Listbox(pctrl, height=5, width=40)
        self.loaded_files_list.grid(row=4, column=0, columnspan=4, sticky='we', pady=(2,0))

        self.start_btn = ttk.Button(ctrl, text='Start Run', command=self.start_run)
        self.start_btn.pack(padx=6, pady=6)
        self.stop_btn = ttk.Button(ctrl, text='Stop Run', command=self.stop_run, state='disabled')
        self.stop_btn.pack(padx=6, pady=6)

        self.log_text = tk.Text(ctrl, width=40, height=15)
        self.log_text.pack(padx=6, pady=6)

        # Progress bar
        self.progress = ttk.Progressbar(ctrl, orient='horizontal', length=200, mode='determinate')
        self.progress.pack(padx=6, pady=6)
        self.progress['value'] = 0

    def _build_postproc_tab(self):
        self.postTab = ttk.Frame(self.tabControl)
        self.tabControl.add(self.postTab, text='Post Processing')

        frm = ttk.Frame(self.postTab, padding=8)
        frm.pack(fill='both', expand=True)

        ttk.Label(frm, text='Select data file(s) to analyze:').pack(anchor='w')
        self.filelistbox = tk.Listbox(frm, height=6)
        self.filelistbox.pack(fill='both', expand=True)

        fbtns = ttk.Frame(frm)
        fbtns.pack(fill='x')
        ttk.Button(fbtns, text='Add files', command=self.add_files).pack(side='left', padx=4, pady=4)
        ttk.Button(fbtns, text='Clear', command=lambda: self.filelistbox.delete(0,'end')).pack(side='left', padx=4, pady=4)
        ttk.Button(fbtns, text='Run Analysis', command=self.run_postproc).pack(side='right', padx=4, pady=4)

        self.postproc_txt = tk.Text(frm, height=10)
        self.postproc_txt.pack(fill='both', expand=True)

    def connect_devices(self):
        # Allow simulation mode
        if getattr(self, 'sim_var', None) and self.sim_var.get():
            # create simulated devices
            tempDev = self._SimTemp()
            impdDev = self._SimImp()
            try:
                tempDev.connectTempController()
                impdDev.connectDevice()
            except Exception:
                pass
            self.run.runDevices = [tempDev, impdDev]
            self.connected = True
            self.status_lbl.config(text='Simulation devices ready', foreground='orange')
            self.log('Simulation mode: devices ready')
            return

        try:
            # temperature controller
            tempDev = tsC.mK2000B()
            tempDev.connectTempController()

            # impedance analyzer
            impdDev = ziC.ziDevice()
            impdDev.connectDevice()

            self.run.runDevices = [tempDev, impdDev]
            self.connected = True
            self.status_lbl.config(text='Devices connected', foreground='green')
            self.log('Devices connected')
        except Exception as e:
            # give the user the option to fall back to simulation
            self.log('Connection error: ' + str(e))
            use_sim = messagebox.askyesno('Connection Error', f'Could not connect to hardware:\n{e}\n\nUse Simulation Mode instead?')
            if use_sim:
                tempDev = self._SimTemp()
                impdDev = self._SimImp()
                try:
                    tempDev.connectTempController()
                    impdDev.connectDevice()
                except Exception:
                    pass
                self.run.runDevices = [tempDev, impdDev]
                self.connected = True
                self.status_lbl.config(text='Simulation devices ready', foreground='orange')
                self.log('Simulation mode: devices ready')
            else:
                messagebox.showerror('Connection Error', str(e))

    def _extract_param_value(self, param_name, string_value):
        """Extract numeric value from human-readable parameter string.

        For combobox parameters like "0 - Manual", extract the "0".
        For numeric parameters, convert to int or float.
        """
        if param_name in ['Input Control', 'Equivalent Circuit Mode', 'Threshold Input Signal',
                          'Logic Unit Not', 'Aux Output Signal', 'Signal Output Add', 'Trigger Source Signal']:
            # Extract the numeric part before the " - "
            if ' - ' in string_value:
                try:
                    return int(string_value.split(' - ')[0])
                except ValueError:
                    return string_value
            else:
                try:
                    return int(string_value)
                except ValueError:
                    return string_value
        else:
            # For non-combobox parameters, try to convert to int or float
            try:
                if isinstance(string_value, str) and string_value.lower() in ['true', 'false']:
                    return True if string_value.lower() == 'true' else False
                else:
                    try:
                        return int(string_value)
                    except ValueError:
                        try:
                            return float(string_value)
                        except ValueError:
                            return string_value
            except Exception:
                return string_value

    def _convert_to_readable_format(self, param_name, value):
        """Convert numeric value to human-readable format for combobox display."""
        param_options = {
            'Input Control': {0: '0 - Manual', 1: '1 - Auto', 2: '2 - Current Zone'},
            'Equivalent Circuit Mode': {0: '0 - 4-Terminal', 1: '1 - 2-Terminal'},
            'Logic Unit Not': {0: '0 - Off', 1: '1 - On'},
            'Signal Output Add': {0: '0 - False', 1: '1 - True'},
        }

        if param_name in param_options:
            try:
                val_int = int(float(value)) if isinstance(value, (str, float)) else int(value)
                return param_options[param_name].get(val_int, str(value))
            except (ValueError, KeyError, TypeError):
                return str(value)
        return str(value)

    def apply_params(self):
        if not self.connected:
            messagebox.showwarning('Not connected', 'Please connect devices first')
            return

        # construct runParams similar to runDlts_Tools.initSetup but using GUI values
        tmpParams = dict()
        tmpParams['tInitial'] = float(self.tinit_e.get())
        tmpParams['tFinal'] = float(self.tfin_e.get())
        tmpParams['numTemps'] = int(self.ntemp_e.get())
        tmpParams['tRamp'] = float(self.tramp_e.get())
        tmpParams['tStableDelay'] = float(self.tdelay_e.get())

        # create temp grid
        tempDev = self.run.runDevices[0]
        tempDev.Tinitial = tmpParams['tInitial']
        tempDev.Tfinal = tmpParams['tFinal']
        tempDev.numTemps = tmpParams['numTemps']
        tempDev.tempGrid = np.linspace(float(tmpParams['tInitial']), float(tmpParams['tFinal']), int(tmpParams['numTemps']), endpoint=True)

        impParams = dict()
        # numPoints stored as power entry by default in runDlts_Tools
        numPointsPower = float(self.npts_e.get())
        impParams['numPoints'] = int(2**numPointsPower)
        impParams['numReps'] = int(self.nreps_e.get())
        # collect Zurich device params from GUI fields
        try:
            for pname, _ in getattr(self, 'z_param_list', []):
                sval = self.z_params_vars.get(pname).get() if pname in self.z_params_vars else None
                if sval is None:
                    continue
                # Extract numeric value from human-readable string if needed
                newval = self._extract_param_value(pname, sval)
                impParams[pname] = newval
                # if device connected, copy into device params dict
                try:
                    impdDev = self.run.runDevices[1]
                    if hasattr(impdDev, 'params'):
                        impdDev.params[pname] = newval
                except Exception:
                    pass
        except Exception:
            pass

        dtaParams = dict()
        dtaParams['outputType'] = self.outtype_cb.get()
        dtaParams['rootFolder'] = self.rootfolder_e.get()
        dtaParams['livePlot'] = bool(self.liveplot_var.get())
        dtaParams['senseRunFailure'] = bool(self.sensefail_var.get())

        self.run.runParams = dict()
        self.run.runParams['temperature'] = tmpParams
        self.run.runParams['impedance'] = impParams
        self.run.runParams['data'] = dtaParams

        # set file names structure
        rootFolder = dtaParams['rootFolder']
        p_root = Path(rootFolder)
        if not p_root.exists():
            create = messagebox.askyesno('Create folder?', f'Root folder {rootFolder} does not exist. Create it?')
            if create:
                try:
                    p_root.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    messagebox.showerror('Folder error', f'Could not create folder {rootFolder}: {e}')
                    # offer folder selection
                    new = filedialog.askdirectory(initialdir=str(Path.home()))
                    if new:
                        self.rootfolder_e.delete(0, 'end')
                        self.rootfolder_e.insert(0, new)
                        return
                    else:
                        return
            else:
                return

        # test write permission by creating and deleting a temporary file
        try:
            testfile = p_root / ('.permtest_{}'.format(int(time.time())))
            with open(testfile, 'w') as tf:
                tf.write('ok')
            testfile.unlink()
        except Exception as e:
            res = messagebox.askyesno('No write permission', f'Cannot write to {rootFolder}: {e}\nChoose another folder?')
            if res:
                new = filedialog.askdirectory(initialdir=str(Path.home()))
                if new:
                    self.rootfolder_e.delete(0, 'end')
                    self.rootfolder_e.insert(0, new)
                    return
            return

        timeFolder = time.strftime('%m%d%y')
        topFolder = os.path.join(dtaParams['rootFolder'], timeFolder)
        os.makedirs(topFolder, exist_ok=True)
        self.run.dataFolder = topFolder
        self.run.runOutputFileType = dtaParams['outputType']
        if dtaParams['outputType'] == 'txt':
            fName = []
            for T in tempDev.tempGrid:
                if '-' in str(T):
                    fName.append(self.run.dataFolder + 'n'+ str(np.abs(T)).replace('.','p')+'.txt')
                else:
                    fName.append(self.run.dataFolder + 'p'+ str(np.abs(T)).replace('.','p')+'.txt')
            self.run.dataFileNames = fName

        self.log('Parameters applied')

        # apply some impedance params to device if present
        impdDev = self.run.runDevices[1]
        try:
            # copy minimal parameters into device params dict if available
            if hasattr(impdDev, 'params'):
                impdDev.params['Data Transfer Rate'] = impParams.get('demodRate', impdDev.params.get('Data Transfer Rate', 60000))
                # NOTE: not all params mapped here; user can modify device module if needed
        except Exception:
            pass

    def load_device_params(self):
        """Load device parameters from the connected impedance device and
        populate editable fields in the Parameters tab."""
        if not self.connected:
            messagebox.showwarning('Not connected', 'Please connect devices first')
            return
        try:
            impdDev = self.run.runDevices[1]
        except Exception:
            messagebox.showerror('Device error', 'Impedance device not available')
            return

        if not hasattr(impdDev, 'params') or not isinstance(impdDev.params, dict):
            messagebox.showinfo('No params', 'Device has no editable params')
            return

        self.log(f'Loaded {len(self.device_param_vars)} device parameters')
        # Also copy values into the explicit Zurich parameter fields if present
        try:
            for pname, var in getattr(self, 'z_params_vars', {}).items():
                if pname in impdDev.params:
                    val = impdDev.params.get(pname)
                    # Convert to readable format if it's a combobox parameter
                    readable_val = self._convert_to_readable_format(pname, val)
                    var.set(readable_val)
        except Exception:
            pass

    def push_device_params(self):
        """Push edited parameters back to the device's params dict and call
        setParam for parameters that the device wrapper supports."""
        if not self.connected:
            messagebox.showwarning('Not connected', 'Please connect devices first')
            return
        impdDev = self.run.runDevices[1]
        if not hasattr(impdDev, 'params'):
            messagebox.showerror('Device error', 'Impedance device has no params attribute')
            return

        success = []
        failed = []
        for k, var in self.device_param_vars.items():
            sval = var.get()
            # try to convert to int or float or bool
            newval = sval
            try:
                if sval.lower() in ['true', 'false']:
                    newval = True if sval.lower() == 'true' else False
                else:
                    try:
                        newval = int(sval)
                    except Exception:
                        try:
                            newval = float(sval)
                        except Exception:
                            newval = sval
            except Exception:
                newval = sval

            try:
                impdDev.params[k] = newval
                # if device has setParam, try to push it
                if hasattr(impdDev, 'setParam'):
                    try:
                        impdDev.setParam(k)
                    except Exception:
                        # pushing parameter may require the session; ignore individual failures
                        pass
                success.append(k)
            except Exception as e:
                failed.append((k, str(e)))

        # Also push explicit Zurich parameter fields
        for k, var in getattr(self, 'z_params_vars', {}).items():
            sval = var.get()
            newval = self._extract_param_value(k, sval)

            try:
                impdDev.params[k] = newval
                if hasattr(impdDev, 'setParam'):
                    try:
                        impdDev.setParam(k)
                    except Exception:
                        pass
                success.append(k)
            except Exception as e:
                failed.append((k, str(e)))
        msg = f'Pushed {len(success)} params.'
        if failed:
            msg += f' {len(failed)} failed.'
        messagebox.showinfo('Push Params', msg)
        self.log(msg)

    def _run_loop(self):
        # Implementation of the measurement loop that mirrors runDlts_Tools.runExperiment
        self._stop_request = False
        tempDev = self.run.runDevices[0]
        impdDev = self.run.runDevices[1]
        tmpParams = self.run.runParams['temperature']
        impParams = self.run.runParams['impedance']
        dtaParams = self.run.runParams['data']

        total_steps = max(1, len(tempDev.tempGrid))
        # reset progress
        try:
            self.root.after(0, lambda: self.progress.config(value=0))
        except Exception:
            pass

        for i in range(len(tempDev.tempGrid)):
            if self._stop_request:
                self.log('Run stopped by user')
                break
            ramp = tmpParams['tRamp']
            delay = tmpParams['tStableDelay']
            targetT = tempDev.tempGrid[i]
            self.log(f'Going to T = {targetT} C (ramp {ramp})')
            try:
                tempDev.goToTemp(targetT, ramp, delay)
            except Exception as e:
                self.log('Temperature command failed: ' + str(e))
            time.sleep(1)
            if not i == 0:
                try:
                    impdDev.device.factory_reset()
                except Exception as e:
                    self.log('Factory reset failed: ' + str(e))
            try:
                impdDev.reloadParams()
            except Exception:
                pass

            numPoints = impParams['numPoints']
            numReps = impParams['numReps']
            outType = self.run.runOutputFileType
            if outType == 'txt':
                fName = self.run.dataFileNames[i]
                self.log('Acquiring data...')
                try:
                    data = impdDev.pullData(plot=False, trigger=True, numPoints=numPoints, numReps=numReps)
                    impdDev.writeDataJson(data, fName)
                    self.log(f'Data saved to {fName}')
                    if dtaParams.get('livePlot', True):
                        # register this newly acquired data immediately for plotting
                        try:
                            self._register_live_dataset(fName, data)
                        except Exception:
                            pass
                except Exception as e:
                    self.log('Data acquisition failed: ' + str(e))
            # update progress
            try:
                percent = int(((i+1) / float(total_steps)) * 100)
                self.root.after(0, lambda p=percent: self.progress.config(value=p))
            except Exception:
                pass

        # finish
        try:
            # save run params
            fName = os.path.join(self.run.dataFolder, 'runParams.txt')
            impdDev.writeDataJson(self.run.runParams, fName)
            self.log('Run parameters saved')
            tempDev.goToRoomTemp(Tr=35)
            tempDev.disconnTController()
            try:
                impdDev.session.disconnect_device(impdDev.devSerial)
            except Exception:
                pass
            self.log('Run finished')
        except Exception as e:
            self.log('Finish error: ' + str(e))
        # ensure progress shows complete when not stopped
        try:
            if not self._stop_request:
                self.root.after(0, lambda: self.progress.config(value=100))
        except Exception:
            pass

        # re-enable buttons
        # stop live watcher if running
        try:
            self._stop_live_watcher()
        except Exception:
            pass
        self.root.after(0, lambda: self.start_btn.config(state='normal'))
        self.root.after(0, lambda: self.stop_btn.config(state='disabled'))

    def start_run(self):
        if not self.connected:
            messagebox.showwarning('Not connected', 'Please connect devices first')
            return
        if not hasattr(self.run, 'runParams') or self.run.runParams is None:
            messagebox.showwarning('No params', 'Please apply parameters before starting')
            return

        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.log('Starting run...')
        self._run_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._run_thread.start()
        # start live folder watcher if live plotting is enabled
        try:
            if getattr(self, 'run', None) and self.run.runParams.get('data', {}).get('livePlot', True):
                self._start_live_watcher()
        except Exception:
            pass

    def stop_run(self):
        self._stop_request = True
        self.log('Stop requested...')
        # stop live folder watcher
        try:
            self._stop_live_watcher()
        except Exception:
            pass

    def _update_live_plot(self, data):
        # Safely update the matplotlib figure from the main thread
        def _draw():
            try:
                for ax in self.axes.flatten():
                    ax.clear()
                # plot AuxInput1
                self.axes[0,0].plot(data['timeStampDemods'], data.get('AuxInput1', []))
                self.axes[0,0].set_title('Aux Input 1')
                # Impedance Re
                self.axes[0,1].plot(data['timeStampImps'], data.get('ImpedanceRe', []))
                self.axes[0,1].set_title('Impedance Re')
                # Impedance Im
                self.axes[1,0].plot(data['timeStampImps'], data.get('ImpedanceIm', []))
                self.axes[1,0].set_title('Impedance Im')
                # AbsZ
                self.axes[1,1].plot(data['timeStampImps'], data.get('AbsZ', []))
                self.axes[1,1].set_title('AbsZ')
                try:
                    self.fig.subplots_adjust(hspace=0.28, wspace=0.22)
                except Exception:
                    try:
                        self.fig.tight_layout()
                    except Exception:
                        pass
                self.canvas.draw()
            except Exception as e:
                self.log('Plot update error: ' + str(e))

        self.root.after(0, _draw)

    # -- Live file watcher and dataset management -------------------------------------------------
    def _register_live_dataset(self, fpath, data):
        """Register or update a live dataset coming from file path `fpath`.

        `data` should be a dict with keys similar to those produced by pullData/writeDataJson.
        """
        try:
            fname = os.path.basename(fpath)
            # try to convert to absolute path if relative
            fpath = os.path.abspath(fpath)
            # parse arrays
            aux_x = np.array(data.get('timeStampDemods', []))
            aux_y = np.array(data.get('AuxInput1', []))
            imp_x = np.array(data.get('timeStampImps', []))
            re_y = np.array(data.get('ImpedanceRe', []))
            im_y = np.array(data.get('ImpedanceIm', []))
            abs_z = np.array(data.get('AbsZ', []))

            # determine a label from filename
            label = self._label_from_fname(fname)
            dataset = {
                'file': fpath,
                'label': label,
                'aux_x': aux_x, 'aux_y': aux_y,
                'imp_x': imp_x, 're_y': re_y, 'im_y': im_y, 'abs_z': abs_z,
                'mtime': os.path.getmtime(fpath) if os.path.exists(fpath) else time.time()
            }

            if fpath not in self._live_file_order:
                self._live_file_order.append(fpath)
            self._live_datasets[fpath] = dataset
            # enforce max traces limit
            try:
                max_t = int(self._live_max_traces)
            except Exception:
                max_t = self._live_max_traces
            while len(self._live_file_order) > max_t:
                old = self._live_file_order.pop(0)
                try:
                    del self._live_datasets[old]
                except Exception:
                    pass
            # refresh plot display
            self._refresh_live_plots()
        except Exception as e:
            self.log('Register live dataset error: ' + str(e))

    def _refresh_live_plots(self):
        """Redraw the live subplots from registered datasets.

        Oldest datasets plotted faint (low alpha); newest dataset drawn with full alpha.
        """
        def _draw():
            try:
                # clear axes
                for ax in self.axes.flatten():
                    ax.clear()

                N = len(self._live_file_order)
                if N == 0:
                    # nothing to plot
                    for ax in self.axes.flatten():
                        ax.set_title('')
                    self.canvas.draw_idle()
                    return
                for idx, fpath in enumerate(self._live_file_order):
                    ds = self._live_datasets.get(fpath)
                    if ds is None:
                        continue
                    # compute alpha using exponential fade: oldest faint, newest full
                    try:
                        gamma = float(self._live_fade_gamma)
                    except Exception:
                        gamma = 3.0
                    if N > 1:
                        age_norm = float(idx) / float(N - 1)  # 0..1 (oldest..newest)
                    else:
                        age_norm = 1.0
                    # map age_norm to alpha via normalized exponential: alpha = minA + (1-minA)*((1-exp(-gamma*age_norm))/(1-exp(-gamma)))
                    minA = 0.2
                    denom = (1.0 - np.exp(-gamma)) if gamma != 0 else 1.0
                    numer = (1.0 - np.exp(-gamma * age_norm))
                    alpha = minA + (1.0 - minA) * (numer / denom if denom != 0 else age_norm)
                    # only label the newest dataset (last in the ordered list)
                    is_newest = (idx == (N - 1))
                    label = ds.get('label', os.path.basename(fpath)) if is_newest else '_nolegend_'
                    # Aux Input 1
                    if len(ds.get('aux_x', [])) and len(ds.get('aux_y', [])):
                        self.axes[0,0].plot(ds['aux_x'], ds['aux_y'], label=label, alpha=alpha)
                    # Impedance Re
                    if len(ds.get('imp_x', [])) and len(ds.get('re_y', [])):
                        self.axes[0,1].plot(ds['imp_x'], ds['re_y'], label=label, alpha=alpha)
                    # Impedance Im
                    if len(ds.get('imp_x', [])) and len(ds.get('im_y', [])):
                        self.axes[1,0].plot(ds['imp_x'], ds['im_y'], label=label, alpha=alpha)
                    # AbsZ
                    if len(ds.get('imp_x', [])) and len(ds.get('abs_z', [])):
                        self.axes[1,1].plot(ds['imp_x'], ds['abs_z'], label=label, alpha=alpha)

                # set titles
                titles = ['Aux Input 1', 'Impedance Re', 'Impedance Im', 'AbsZ']
                for ax, t in zip(self.axes.flatten(), titles):
                    ax.set_title(t)


                self.fig.tight_layout()
                try:
                    self.canvas.draw_idle()
                except Exception:
                    self.canvas.draw()
            except Exception as e:
                self.log('Refresh live plot error: ' + str(e))

        self.root.after(0, _draw)

    def _label_from_fname(self, fname):
        """Convert filenames like 'p12p5.txt' or 'n14p0.txt' into human-readable temperature labels.

        Returns a string like '+12.5 C' or '-14.0 C'. If parsing fails, returns the bare filename.
        """
        try:
            base = os.path.splitext(fname)[0]
            sign = '+' if base.startswith('p') else ('-' if base.startswith('n') else '')
            if sign:
                s = base[1:]
                s = s.replace('p', '.')
                return f"{sign}{s} C"
            return fname
        except Exception:
            return fname


    # -- Axis sync handlers --------------------------------------------------------------------
    def _on_xlim_changed(self, ax):
        try:
            if self._syncing_limits:
                return
            self._syncing_limits = True
            new_xlim = ax.get_xlim()
            for other in self.axes.flatten():
                if other is ax:
                    continue
                try:
                    other.set_xlim(new_xlim)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._syncing_limits = False

    def _on_ylim_changed(self, ax):
        try:
            if self._syncing_limits:
                return
            self._syncing_limits = True
            new_ylim = ax.get_ylim()
            for other in self.axes.flatten():
                if other is ax:
                    continue
                try:
                    other.set_ylim(new_ylim)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._syncing_limits = False

    def _read_data_file(self, fpath):
        """Attempt to read a data file. Supports JSON (preferred) and simple whitespace columns.

        Returns a dict similar to pullData output or None on failure.
        """
        try:
            with open(fpath, 'r') as f:
                txt = f.read()
            try:
                data = json.loads(txt)
                return data
            except Exception:
                pass
            # fallback: try numpy loadtxt
            try:
                arr = np.loadtxt(fpath)
                if arr.ndim == 1 and arr.size >= 2:
                    # single row -> treat as y-values
                    y = arr
                    return {'timeStampImps': list(range(len(y))), 'AbsZ': y}
                elif arr.ndim == 2 and arr.shape[1] >= 2:
                    x = arr[:,0].tolist()
                    y = arr[:,1].tolist()
                    return {'timeStampImps': x, 'AbsZ': y}
            except Exception:
                pass
        except Exception:
            return None

    def _start_live_watcher(self):
        """Start background thread that polls the data folder for new/updated files."""
        if self._live_watcher_thread and self._live_watcher_thread.is_alive():
            return
        self._live_watcher_stop.clear()

        def _poll():
            last_seen_mtimes = {}
            while not self._live_watcher_stop.is_set():
                try:
                    # refresh runtime settings from UI controls if available
                    try:
                        self._live_poll_interval = float(self.poll_interval_var.get())
                    except Exception:
                        pass
                    try:
                        self._live_max_traces = int(self.max_traces_var.get())
                    except Exception:
                        pass

                    folder = getattr(self.run, 'dataFolder', None)
                    if folder and os.path.isdir(folder):
                        # list txt and h5 files
                        files = [os.path.join(folder, f) for f in os.listdir(folder) if (f.lower().endswith('.txt') or f.lower().endswith('.h5')) and os.path.basename(f) not in self._live_ignore_files]
                        # sort by mtime
                        files_sorted = sorted(files, key=lambda p: os.path.getmtime(p))
                        # respect max traces setting: only consider the newest max_traces files
                        try:
                            max_t = int(self._live_max_traces)
                        except Exception:
                            max_t = self._live_max_traces
                        if max_t and len(files_sorted) > max_t:
                            files_sorted = files_sorted[-max_t:]
                        for f in files_sorted:
                            try:
                                m = os.path.getmtime(f)
                                if f not in last_seen_mtimes or last_seen_mtimes[f] != m:
                                    last_seen_mtimes[f] = m
                                    data = self._read_data_file(f)
                                    if data is not None:
                                        self._register_live_dataset(f, data)
                            except Exception:
                                pass
                except Exception:
                    pass
                time.sleep(self._live_poll_interval)

        self._live_watcher_thread = threading.Thread(target=_poll, daemon=True)
        self._live_watcher_thread.start()

    def _stop_live_watcher(self):
        try:
            if self._live_watcher_thread and self._live_watcher_thread.is_alive():
                self._live_watcher_stop.set()
                self._live_watcher_thread.join(timeout=2.0)
        except Exception:
            pass

    def _pick_watch_folder(self):
        try:
            cur = self.watchfolder_e.get() if hasattr(self, 'watchfolder_e') else str(Path.home())
            new = filedialog.askdirectory(initialdir=cur, title='Select Watch Folder')
            if new:
                self.watchfolder_e.delete(0, 'end')
                self.watchfolder_e.insert(0, new)
        except Exception as e:
            messagebox.showerror('Folder selection', str(e))

    def _load_watch_folder_now(self):
        """Immediately load files from the watch folder into the live plot (useful to load example data)."""
        try:
            folder = self.watchfolder_e.get().strip()
            if not folder:
                messagebox.showwarning('No folder', 'Please select a watch folder first')
                return
            if not os.path.isdir(folder):
                messagebox.showerror('Not a folder', f'{folder} is not a valid directory')
                return
            # set runtime folder so watcher will also use it
            self.run.dataFolder = folder
            # update internal poll interval and max traces from controls
            try:
                self._live_poll_interval = float(self.poll_interval_var.get())
            except Exception:
                pass
            try:
                self._live_max_traces = int(self.max_traces_var.get())
            except Exception:
                pass
            # read files present and register up to max_traces newest
            files = [os.path.join(folder, f) for f in os.listdir(folder) if (f.lower().endswith('.txt') or f.lower().endswith('.h5')) and os.path.basename(f) not in self._live_ignore_files]
            files_sorted = sorted(files, key=lambda p: os.path.getmtime(p))
            if len(files_sorted) > self._live_max_traces:
                files_sorted = files_sorted[-self._live_max_traces:]
            for f in files_sorted:
                try:
                    data = self._read_data_file(f)
                    if data is not None:
                        self._register_live_dataset(f, data)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror('Load folder error', str(e))

    def add_files(self):
        files = filedialog.askopenfilenames(title='Select data files', filetypes=[('Text files','*.txt'),('HDF5','*.h5'),('All files','*.*')])
        for f in files:
            self.filelistbox.insert('end', f)

    def browse_root_folder(self):
        """Open a folder selection dialog and set the Root Folder entry."""
        try:
            current = self.rootfolder_e.get() if hasattr(self, 'rootfolder_e') else str(Path.home())
            initial = current if os.path.isdir(current) else str(Path.home())
            newdir = filedialog.askdirectory(initialdir=initial, title='Select Root Folder')
            if newdir:
                self.rootfolder_e.delete(0, 'end')
                self.rootfolder_e.insert(0, newdir)
        except Exception as e:
            messagebox.showerror('Folder selection error', str(e))

    def run_postproc(self):
        selected = list(self.filelistbox.get(0, 'end'))
        if not selected:
            messagebox.showwarning('No files', 'Please add files to analyze')
            return
        # For simplicity, run the existing leveling test for the first file
        for f in selected:
            try:
                self.postproc_txt.insert('end', f'Analyzing {f}...\n')
                # Use existing helper
                rdT.dltsRun.testDataLeveling(f, plot=True)
                self.postproc_txt.insert('end', f'Finished analysis for {f}\n')
            except Exception as e:
                self.postproc_txt.insert('end', f'Error analyzing {f}: {e}\n')

    def log(self, msg):
        t = time.strftime('%H:%M:%S')
        self.log_text.insert('end', f'[{t}] {msg}\n')
        self.log_text.see('end')


if __name__ == '__main__':
    import sys
    # allow enabling simulation mode via command-line flag or environment variable
    sim_flag = ('--simulation' in sys.argv) or (os.environ.get('DLTS_SIM', '') == '1')

    root = tk.Tk()
    app = DLTSGui(root)
    try:
        if sim_flag and hasattr(app, 'sim_var'):
            app.sim_var.set(True)
    except Exception:
        pass

    root.mainloop()


def run_gui(simulation=False, block=True):
    """Helper to launch the GUI from interactive sessions.

    Parameters
    - simulation (bool): if True, enable simulation mode automatically (creates simulated devices on connect).
    - block (bool): if True (default) call root.mainloop() and block until window closed.
                    If False, return the (root, app) pair so caller can control the event loop
                    (e.g. in IPython use ``%gui tk`` and block=False).

    Returns
    - (root, app) tuple when block is False, otherwise None after mainloop returns.
    """
    root = tk.Tk()
    app = DLTSGui(root)
    # set simulation checkbox if requested
    try:
        if simulation:
            # ensure the variable exists and set it
            if hasattr(app, 'sim_var'):
                app.sim_var.set(True)
    except Exception:
        pass

    if block:
        root.mainloop()
        return None
    else:
        return root, app



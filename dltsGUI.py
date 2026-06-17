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
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
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
        tframe = ttk.LabelFrame(frm, text='Temperature Sweep', padding=8)
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

        # Impedance group
        iframe = ttk.LabelFrame(frm, text='Impedance', padding=8)
        iframe.grid(row=0, column=1, sticky='ne', padx=6, pady=6)

        ttk.Label(iframe, text='Num Points (power of 2)').grid(row=0, column=0, sticky='w')
        self.npts_e = ttk.Entry(iframe, width=10)
        self.npts_e.insert(0, '13')
        self.npts_e.grid(row=0, column=1)

        ttk.Label(iframe, text='Num Reps').grid(row=1, column=0, sticky='w')
        self.nreps_e = ttk.Entry(iframe, width=10)
        self.nreps_e.insert(0, '1')
        self.nreps_e.grid(row=1, column=1)

        # Data group
        dframe = ttk.LabelFrame(frm, text='Data Storage', padding=8)
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
        self.rootfolder_e.grid(row=1, column=1, columnspan=2)

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
        self.status_lbl.grid(row=2, column=0, columnspan=2, sticky='w', padx=8, pady=6)

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
        self.fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

        ctrl = ttk.Frame(self.liveTab)
        ctrl.pack(side='right', fill='y')

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

        # clear previous widgets
        for child in self.dp_container.winfo_children():
            child.destroy()
        self.device_param_vars = {}

        # create rows for each parameter
        row = 0
        for k, v in impdDev.params.items():
            lbl = ttk.Label(self.dp_container, text=k)
            lbl.grid(row=row, column=0, sticky='w', padx=2, pady=1)
            var = tk.StringVar(value=str(v))
            ent = ttk.Entry(self.dp_container, textvariable=var, width=30)
            ent.grid(row=row, column=1, sticky='we', padx=2, pady=1)
            self.device_param_vars[k] = var
            row += 1

        self.log(f'Loaded {len(self.device_param_vars)} device parameters')

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
                        self._update_live_plot(data)
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

    def stop_run(self):
        self._stop_request = True
        self.log('Stop requested...')

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
                self.fig.tight_layout()
                self.canvas.draw()
            except Exception as e:
                self.log('Plot update error: ' + str(e))

        self.root.after(0, _draw)

    def add_files(self):
        files = filedialog.askopenfilenames(title='Select data files', filetypes=[('Text files','*.txt'),('HDF5','*.h5'),('All files','*.*')])
        for f in files:
            self.filelistbox.insert('end', f)

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



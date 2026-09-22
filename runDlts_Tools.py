import json
import time
import zhinst.core
import zhinst.toolkit as zt
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os
import copy
import h5py
import statistics
import itertools
import torch
import lmfit

from tkinter.filedialog import askopenfilenames
from datetime import datetime
from numpy.ma.extras import apply_along_axis
from scipy.interpolate import CubicSpline
from sklearn.mixture import GaussianMixture
from uncertainties import unumpy, ufloat
from scipy.stats import weibull_min
from scipy.integrate import quad
from lmfit.models import LognormalModel, GaussianModel

import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="uncertainties")

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT


def _get_runtime_param_value(param_vars, param_name, fallback_bucket=None):
    """Read the current value from either the UI variables or the synced plain-value dict."""
    if fallback_bucket is not None and param_name in fallback_bucket:
        return fallback_bucket[param_name]

    if param_vars is None or param_name not in param_vars:
        return None

    try:
        return param_vars[param_name].get()
    except Exception:
        return param_vars[param_name]

class dltsRun:
    def __init__(self, fName=None):
        self.impDevice = None
        self.tempDevice = None
        self.impDeviceParams = None
        self.tempDeviceParams = None
        self.outputParams = None
        self.dataFolder = None
        self.runOutputFileType = None
        self.dataFileNames = None
        self.paramsFileName = None
        # self.livePlot = True
        # self.senseRunFailure = True
        # self.excludedRuns = []

    def check_device_connections(self):
        if hasattr(dltsc, 'impDev') and hasattr(dltsc, 'tempDev'):
            if dltsc.impDev is None and dltsc.tempDev is None:
                print("Error: Impedance Analyzer device and temperature stage device are not connected.")
                returnVal = [0, 0]
            if not dltsc.impDev is None and dltsc.tempDev is None:
                print("Error: Temperature controller device is not connected.")
                returnVal = [1, 0]
            if dltsc.impDev is None and not dltsc.tempDev is None:
                print("Error: Impedance Analyzer device is not connected.")
                returnVal = [0, 1]
            if not dltsc.impDev is None and not dltsc.tempDev is None:
                print("Impedance Analyzer device and temperature stage device are connected.")
                self.impDevice = dltsc.impDev
                self.tempDevice = dltsc.tempDev
                returnVal = [1, 1]

        if hasattr(dltsc, 'impDev') and not hasattr(dltsc, 'tempDev'):
            if dltsc.impDev is None:
                print("Error: Impedance Analyzer device is not connected and "
                      "temperature stage device does not exist.")
                returnVal = [0, -1]
            if not dltsc.impDev is None:
                print("Error: Temperature controller device does not exist.")
                returnVal = [1, -1]

        if not hasattr(dltsc, 'impDev') and hasattr(dltsc, 'tempDev'):
            if dltsc.tempDev is None:
                print("Error: Temperature controller device is not connected and "
                      "impedance analyzer device does not exist.")
                returnVal = [-1, 0]
            if not dltsc.tempDev is None:
                print("Error: Impedance analyzer device does not exist.")
                returnVal = [-1, 1]

        if not hasattr(dltsc, 'impDev') and not hasattr(dltsc, 'tempDev'):
            print("Error: Impedance Analyzer device and Temperature controller device do not exist.")
            returnVal = [-1, -1]

        return returnVal

    def check_device_parameters(self, device='impDev'):
        if device == 'impDev':
            self.impDeviceParams = dict()
            impfail = []
            param_vars = getattr(dltsc, 'z_params_vars', {})
            push_values = getattr(dltsc, 'z_params_for_push', {})
            if hasattr(dltsc, 'z_params_vars'):
                for p in param_vars:
                    value = _get_runtime_param_value(param_vars, p, push_values)
                    self.impDeviceParams[p] = value
                    if value is None:
                        impfail.append(p)
            else:
                dltsc.log_to_textbox("Error: Impedance analyzer parameters do not exist.")

            if len(impfail)>0:
                for f in impfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(impfail)

        if device == 'tempDev':
            self.tempDeviceParams = dict()
            tempfail = []
            param_vars = getattr(dltsc, 't_params_vars', {})
            push_values = getattr(dltsc, 't_params_for_push', {})
            if hasattr(dltsc, 't_params_vars'):
                for p in param_vars:
                    value = _get_runtime_param_value(param_vars, p, push_values)
                    self.tempDeviceParams[p] = value
                    if value is None:
                        tempfail.append(p)
            else:
                dltsc.log_to_textbox("Error: Temperature controller parameters do not exist.")

            if len(tempfail) > 0:
                for f in tempfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(tempfail)

        if device == 'output':
            self.outputParams = dict()
            outputfail = []
            param_vars = getattr(dltsc, 'd_params_vars', {})
            if hasattr(dltsc, 'd_params_vars'):
                for p in param_vars:
                    value = _get_runtime_param_value(param_vars, p)
                    self.outputParams[p] = value
                    if value is None:
                        outputfail.append(p)
            else:
                dltsc.log_to_textbox("Error: Output parameters do not exist.")
            if len(outputfail) > 0:
                for f in outputfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(outputfail)

    def check_setup(self):
        returnVal = 0
        # 1. Check if devices exists, if not report error
        device_status = self.check_device_connections()
        if sum(device_status) < 2:
            dltsc.log_to_textbox("Error: One or more devices are not connected.")
            returnVal -= 1
        else:
            dltsc.log_to_textbox("All devices are connected.")
            returnVal += 1
        # 2. Check device parameters and I/O parameters, report the errors if any
        param_status = self.check_device_parameters('impDev')
        param_status += self.check_device_parameters('tempDev')
        param_status += self.check_device_parameters('output')
        if param_status > 0:
            dltsc.log_to_textbox("Error: One or more device parameters are not set.")
            returnVal -= 1
        else:
            dltsc.log_to_textbox("All device parameters are set.")
            returnVal += 1

        return returnVal

    def init_experiment(self):
        hardware_status = self.check_setup()
        if hardware_status < 2:
            dltsc.log_to_textbox("Error: Cannot initialize experiment. Hardware is not ready.")
            return -1
        else:
            dltsc.log_to_textbox("1. Hardware initialized.")
            self.tempDevice.set_temp_grid()
            dltsc.log_to_textbox("2. Temperature grid set.")

            rootFolder = self.outputParams['Data Root Folder']
            outputType = str(self.outputParams['Data File Format']).strip().lower()
            if outputType == 'json':
                ext = '.json'
            elif outputType == 'hdf5':
                ext = '.h5'
            elif outputType == 'txt':
                ext = '.txt'
            else:
                ext = '.json'

            timeAndDate = datetime.now()
            temp = '{:02d}'.format(timeAndDate.month) + '{:02d}'.format(timeAndDate.day) + \
                   '{:02d}'.format(timeAndDate.year)[-2:] + '\\'
            topFolder = rootFolder + '\\' + temp
            if not os.path.exists(topFolder):
                os.makedirs(topFolder)

            timeAndDate = datetime.now()
            temp = '{:02d}'.format(timeAndDate.hour) + '{:02d}'.format(timeAndDate.minute) + \
                   '{:02d}'.format(timeAndDate.second) + '\\'
            subFolder = topFolder + '\\' + temp
            if not os.path.exists(subFolder):
                os.makedirs(subFolder)

            self.runOutputFileType = outputType
            self.dataFolder = subFolder

            fName = []
            for i in range(len(dltsc.tempDev.tempGrid)):
                if '-' in str(dltsc.tempDev.tempGrid[i]):
                   prefix = 'n'
                else:
                   prefix = 'p'
                fName.append(self.dataFolder + prefix +
                            str(np.abs(dltsc.tempDev.tempGrid[i])).replace('.','p') + ext)
            self.dataFileNames = fName
            self.paramsFileName = self.dataFolder + 'runParams.txt'

            # Publish this run's file manifest so liveDataTab.py can watch for
            # each temperature's file without reaching into this instance.
            dltsc.run_dataFolder = self.dataFolder
            dltsc.run_dataFileNames = list(self.dataFileNames)
            dltsc.run_outputFileType = self.runOutputFileType

            dltsc.log_to_textbox("3. Output file names set.")
            return 0

    def run_experiment(self):
        tempDev = self.tempDevice
        impdDev = self.impDevice
        for i in range(len(tempDev.tempGrid)):
            ramp = tempDev.tRamp
            delay = tempDev.tStableDelay
            tempDev.go_to_temp(tempDev.tempGrid[i], ramp, delay)
            time.sleep(1)
            if not i==0:
                impdDev.device.factory_reset()
            impdDev.reload_params()

            numPoints = 2 ** dltsc.recast_param_type('output', 'Number of Points (power of 2)')
            numReps = dltsc.recast_param_type('output', 'Number of Reps')
            outType = str(self.runOutputFileType).strip().lower()
            if outType in ('txt', 'json', 'hdf5'):
                fName = self.dataFileNames[i]
                data = impdDev.pull_data(plot=False, trigger=True,
                                       numPoints=numPoints, numReps=numReps)
                if outType == 'hdf5':
                   impdDev.writeDataH5(data, fName, i, shape=[1, 8, 1], start=(i == 0), finish=(i == len(tempDev.tempGrid) - 1))
                else:
                   impdDev.writeDataJson(data, fName)

        return 0

    def finish_experiment(self):
        tempDev = self.tempDevice
        impdDev = self.impDevice

        if self.impDeviceParams is not None and self.tempDeviceParams is not None and self.outputParams is not None:
            runParams = {**self.impDeviceParams, **self.tempDeviceParams, **self.outputParams}
        else:
            runParams = {}
        fName = self.paramsFileName
        if impdDev is not None and hasattr(impdDev, 'writeDataJson') and fName is not None:
            impdDev.writeDataJson(runParams, fName)

        if tempDev is not None:
            tempDev.go_to_room_temp(Tr=30)

        dltsc.log_to_textbox("Run complete: devices remain connected for the next run until the GUI is closed.")
        return 0
        
        
        
        
        
        
        

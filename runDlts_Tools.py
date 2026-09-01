import time
from datetime import datetime
import zhinst.core
import zhinst.toolkit as zt
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os
import copy
from tkinter.filedialog import askopenfilenames

from numpy.ma.extras import apply_along_axis
from scipy.interpolate import CubicSpline
import json
from sklearn.mixture import GaussianMixture
import h5py
import statistics
from uncertainties import unumpy, ufloat
import itertools
from scipy.stats import weibull_min
import torch
from scipy.integrate import quad
import lmfit
from lmfit.models import LognormalModel, GaussianModel

import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="uncertainties")

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT

class dltsRun:
    def __init__(self, fName=None):
        self.runDevices = []
        self.runParams = None
        self.dataFolder = None
        self.runOutputFileType = None
        self.dataFileNames = None
        self.paramsFileName = None
        self.livePlot = True
        self.senseRunFailure = True
        self.excludedRuns = []

    @staticmethod
    def check_device_connections():
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

    @staticmethod
    def check_device_parameters(device='impDev'):
        if device == 'impDev':
            impfail = []
            if hasattr(dltsc, 'z_params_vars'):
                for p in dltsc.z_params_vars:
                    # Perform checks on each parameter 'p'
                    if dltsc.z_params_vars[p].get() is None:
                        impfail.append(p)
                    else:
                        pass
            else:
                dltsc.log_to_textbox("Error: Impedance analyzer parameters do not exist.")

            if len(impfail)>0:
                for f in impfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(impfail)

        if device == 'tempDev':
            tempfail = []
            if hasattr(dltsc, 't_params_vars'):
                for p in dltsc.t_params_vars:
                    # Perform checks on each parameter 'p'
                    if dltsc.t_params_vars[p].get() is None:
                        tempfail.append(p)
                    else:
                        pass
            else:
                dltsc.log_to_textbox("Error: Temperature controller parameters do not exist.")

            if len(tempfail) > 0:
                for f in tempfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(tempfail)

        if device == 'output':
            outputfail = []
            if hasattr(dltsc, 'd_params_vars'):
                for p in dltsc.d_params_vars:
                    # Perform checks on each parameter 'p'
                    if dltsc.d_params_vars[p].get() is None:
                        outputfail.append(p)
                    else:
                        pass
            else:
                dltsc.log_to_textbox("Error: Output parameters do not exist.")
            if len(outputfail) > 0:
                for f in outputfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(outputfail)

    def init_devices(self):
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
        hardware_status = self.init_devices()
        if hardware_status < 2:
            dltsc.log_to_textbox("Error: Cannot initialize experiment. Hardware is not ready.")
            return -1
        else:
            dltsc.log_to_textbox("1. Hardware initialized.")
            dltsc.tempDev.set_temp_grid()
            dltsc.log_to_textbox("2. Temperature grid set.")

            rootFolder = dltsc.d_params_vars['Data Root Folder'].get()
            outputType = dltsc.d_params_vars['Data File Format'].get()

            timeAndDate = datetime.now()
            temp = '{:02d}'.format(timeAndDate.month) + '{:02d}'.format(timeAndDate.day) + \
                   '{:02d}'.format(timeAndDate.year)[-2:] + '\\'
            topFolder = rootFolder + temp
            if not os.path.exists(topFolder):
                os.makedirs(topFolder)
            self.runOutputFileType = outputType
            self.dataFolder = topFolder

            fName = []
            if outputType == 'txt':
                for i in range(len(dltsc.tempDev.tempGrid)):
                    if '-' in str(dltsc.tempDev.tempGrid[i]):
                        fName.append(self.dataFolder + 'n' + str(np.abs(dltsc.tempDev.tempGrid[i])).replace('.',
                                                                                                                 'p') + '.txt')
                    else:
                        fName.append(self.dataFolder + 'p' + str(np.abs(dltsc.tempDev.tempGrid[i])).replace('.',
                                                                                                                 'p') + '.txt')
            self.dataFileNames = fName
            self.paramsFileName = self.dataFolder + 'runParams.txt'
            dltsc.log_to_textbox("3. Output file names set.")
            return 0

    def run_experiment(self):
        tempDev = dltsc.tempDev
        impdDev = dltsc.impDev
        for i in range(len(tempDev.tempGrid)):
            ramp = tempDev.tRamp
            delay = tempDev.tStableDelay
            tempDev.goToTemp(tempDev.tempGrid[i], ramp, delay)
            time.sleep(1)
            if not i==0:
                impdDev.device.factory_reset()
            impdDev.reloadParams()

            # numPoints = impdDev.numPoints
            # numReps = impdDev.numReps
            # outType = self.runOutputFileType
            # if outType=='txt':
            #     fName = self.dataFileNames[i]
            #     data = impdDev.pullData(plot=False, trigger=True,
            #                             numPoints=numPoints, numReps=numReps)
            #     impdDev.writeDataJson(data, fName)

        return 0

    def finishExperiment(self):
        tempDev = self.runDevices[0]
        impdDev = self.runDevices[1]
        
        runParams = self.runParams
        fName = self.paramsFileName
        impdDev.writeDataJson(runParams, fName)
        
        tempDev.goToRoomTemp(Tr=35)
        tempDev.disconnTController()
        impdDev.session.disconnect_device('dev32271')
        
        return 0        
        
        
        
        
        
        
        

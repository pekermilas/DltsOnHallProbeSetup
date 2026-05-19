# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 13:11:22 2026

@author: spencer
"""
import serial
import serial.tools.list_ports
import time
import numpy as np
import matplotlib.pyplot as plt
import lmfit
from lmfit.models import *

import time
import zhinst.core
import zhinst.toolkit as zt
import zhinst.ziPython as zi
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import json
from pathlib import Path

import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT

# class NumpyEncoder(json.JSONEncoder):
#     def default(self, obj):
#         if isinstance(obj, np.ndarray):
#             return obj.tolist()
#         return super().default(obj)

if __name__ == '__main__':
    
    tempDev = tsC.mK2000B()
    tempDev.connectTempController()
    impdDev = ziC.ziDevice()
    impdDev.connectDevice()
    
    # Set impedance analyzer parameters
    impdDev.device.factory_reset()
    impdDev.loadParams()
    
    # Set temperature controller parameters
    tempDev.setTempGrid()
    
    # data = dict()
    # for i in range(len(tempDev.tempGrid)):
    #     tempDev.goToTemp(tempDev.tempGrid[i])
    #     time.sleep(1)
    #     impdDev.reloadParams()
    #     data[tempDev.tempGrid[i].item()] = impdDev.pullData(plot=False, trigger=True, numPoints=2**12)

    # fName = 'C:/Users/spencer/Desktop/DATA/DLTS/05062026/readable.txt'
    
    # impdDev.writeData(data, fName)
    
    
    rootFolder = 'C:/Users/spencer/Desktop/DATA/DLTS/05182026/'
    fName = 'test.h5'

    f = h5py.File(rootFolder+fName, 'w')
    dltsData = f.create_dataset('dlts', shape=(len(tempDev.tempGrid), 6, numPoints ), 
                                dtype='float32', compression="gzip", 
                                compression_opts=9)
        
    for i in range(len(tempDev.tempGrid)):
        tempDev.goToTemp(tempDev.tempGrid[i])
        time.sleep(1)
        impdDev.reloadParams()
        
        numPoints = 2**12
        fileName = rootFolder+fName
        data = impdDev.pullData(plot=False, trigger=True, numPoints=numPoints)
        shape = [len(tempDev.tempGrid), 6, numPoints]
        if i==0:
            impdDev.writeDataH5(data, fileName, i, shape, start=True, finish=False)
        if i==len(tempDev.tempGrid)-1: 
            impdDev.writeDataH5(data, fileName, i, shape, start=False, finish=True)
        if (i>0 and i<len(tempDev.tempGrid)-1):
            impdDev.writeDataH5(data, fileName, i, shape, start=False, finish=False)
            
        # fName = str(tempDev.tempGrid[i]).replace('.','p')+'.txt'
        # impdDev.writeDataJson(data, rootFolder+fName)
    
    f.close()
    
    tempDev.goToRoomTemp(Tr=30)
    tempDev.disconnTController()
    impdDev.session.disconnect_device('dev32271')

    data = iaT.impdData()
    data.readData()
    # fExcite will replace 'Oscillation Frequency'!!!
    fExcite = wellBehaveFrequencies(fUpper, fLower)

    # # impdDev.close()
    # data = impdDev.pullData(plot=True, trigger=False, numPoints=2**12)


    # # PLOT TOOLS are needed!!!!
    
    # fig, ax1 = plt.subplots()
    
    # # Plot first dataset on the primary y-axis (left)
    # ax1.plot(data[25]['timeStampImps'], data[25]['ImpedanceIm'], color='tab:blue')
    # ax1.set_ylabel('Primary Axis', color='tab:blue')
    
    # # Create the twin axis
    # ax2 = ax1.twinx()
    
    # # Plot second dataset on the secondary y-axis (right)
    # ax2.plot(data[35]['timeStampImps'], data[35]['ImpedanceIm'], color='tab:red')
    # ax2.set_ylabel('Secondary Axis', color='tab:red')
    
    # plt.show()
    
    # fig, ax1 = plt.subplots()
    
    # # Plot first dataset on the primary y-axis (left)
    # ax1.plot(data[25]['timeStampDemods'], data[25]['AuxInput1'], color='tab:blue')
    # ax1.set_ylabel('Primary Axis', color='tab:blue')
    
    # # Create the twin axis
    # ax2 = ax1.twinx()
    
    # # Plot second dataset on the secondary y-axis (right)
    # ax2.plot(data[35]['timeStampDemods'], data[35]['AuxInput1'], color='tab:red')
    # ax2.set_ylabel('Secondary Axis', color='tab:red')
    
    # plt.show()
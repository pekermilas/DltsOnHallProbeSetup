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

    # IMPLEMENT Delta C as based on a given user TIME input!
    # IMPLEMENT Sampling through the acquired data, use difference!!!

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
    
    # Batch process!!!
    # nm = np.arange(30, 125, 5)
    # data = dict()

    # for i in range(19):
    #     d = iaT.impdData()
    #     d.readData()
    #     data[nm[i]] = d.dataValues
        
    # plt.plot(data[30]['tickStampImps'], data[30]['ImpedanceIm'])


    # for i in range(19):
    #     if i==0:
    #         x = np.array(data[list(data)[i]]['tickStampImps'])
    #         y = np.array(data[list(data)[i]]['ImpedanceIm'])
    #         y = y[(x<0.0045) & (x>0.0005)]
    #         x = x[(x<0.0045) & (x>0.0005)]
    #     else:
    #         xt = np.array(data[list(data)[i]]['tickStampImps'])
    #         yt = np.array(data[list(data)[i]]['ImpedanceIm'])
    #         ytt = yt[(xt<0.0045) & (xt>0.0005)]
    #         xtt = xt[(xt<0.0045) & (xt>0.0005)]
            
    #         x = np.column_stack((x, xtt))
    #         y = np.column_stack((y, ytt))
    
    # import itertools
    
    # lidx = np.argmin(y[1:,0]-y[:-1,0])+3
    # hidx = np.argmax(y[1:,0]-y[:-1,0])-5
    # arr = np.arange(lidx, hidx+1)
    # combs = list(itertools.combinations(arr,2))
    # XY = np.array(combs)
    # Z = np.zeros((len(XY),19))
    # for i in range(19):
    #     for j in range(len(XY)):
    #         Z[j,i] = y[XY[j,1],i]-y[XY[j,0],i]
            
    # for i in range(19):
    #     plt.plot(Z[:,i])
    
    # # plt.plot(nm+273, np.max(Z,axis=0))
    # peaks, properties = find_peaks(Z[:,0], prominence=(1.0e-12, 2.443489417030587e-12))
    # plt.plot(Z[:,0])
    # plt.plot(peaks, Z[peaks,0], "x")

    # x[(x[:,0]<0.0045) & (x[:,0]>0.0005),0]

    # To plot Delta C over indices as a whole
    # for i in np.unique(X):
    #     idx = np.where(X==i)[0]
    #     plt.plot(XY[idx,1], Z[idx,0])

    # Normalized emission traces
    for i in range(19):
        plt.plot(x[:,i], y[:,i]/np.max(y[:,i]), label=str(nm[i]))
    plt.legend()    

    # 0.0010264 0.0010268
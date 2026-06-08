# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 13:11:22 2026

@author: spencer
"""
import h5py
import json

import importlib
import lmfit
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
import numpy as np
import numpy as np
import os
import pandas as pd
import serial
import time
import time
from lmfit.models import *
from pathlib import Path

os.environ["LOKY_MAX_CPU_COUNT"] = "4"

import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT
importlib.reload(iaT)

# class NumpyEncoder(json.JSONEncoder):
#     def default(self, obj):
#         if isinstance(obj, np.ndarray):
#             return obj.tolist()
#         return super().default(obj)

if __name__ == '__main__':
    
    # tempDev = tsC.mK2000B()
    # tempDev.connectTempController()
    # impdDev = ziC.ziDevice()
    # impdDev.connectDevice()
    #
    # # Set impedance analyzer parameters
    # impdDev.device.factory_reset()
    # impdDev.loadParams()
    #
    # # Set temperature controller parameters
    # tempDev.setTempGrid()
    #
    # # data = dict()
    # # for i in range(len(tempDev.tempGrid)):
    # #     tempDev.goToTemp(tempDev.tempGrid[i])
    # #     time.sleep(1)
    # #     impdDev.reloadParams()
    # #     data[tempDev.tempGrid[i].item()] = impdDev.pullData(plot=False, trigger=True, numPoints=2**12)
    #
    # # fName = 'C:/Users/spencer/Desktop/DATA/DLTS/05062026/readable.txt'
    #
    # # impdDev.writeData(data, fName)
    #
    #
    # rootFolder = 'C:/Users/spencer/Desktop/DATA/DLTS/05282026/'
    #
    # # # This is for dumping data into .h5
    # # # ------------------------------------------------------------------------
    # # fName = 'test.h5'
    #
    # # f = h5py.File(rootFolder+fName, 'w')
    # # dltsData = f.create_dataset('dlts', shape=(len(tempDev.tempGrid), 6, numPoints),
    # #                             dtype='float32', compression="gzip",
    # #                             compression_opts=9)
    #
    # # for i in range(len(tempDev.tempGrid)):
    # #     tempDev.goToTemp(tempDev.tempGrid[i])
    # #     time.sleep(1)
    # #     impdDev.reloadParams()
    #
    # #     numPoints = 2**12
    # #     fileName = rootFolder+fName
    # #     data = impdDev.pullData(plot=False, trigger=True, numPoints=numPoints)
    # #     shape = [len(tempDev.tempGrid), 6, numPoints]
    # #     if i==0:
    # #         impdDev.writeDataH5(data, fileName, i, shape, start=True, finish=False)
    # #     if i==len(tempDev.tempGrid)-1:
    # #         impdDev.writeDataH5(data, fileName, i, shape, start=False, finish=True)
    # #     if (i>0 and i<len(tempDev.tempGrid)-1):
    # #         impdDev.writeDataH5(data, fileName, i, shape, start=False, finish=False)
    #
    # #     # fName = str(tempDev.tempGrid[i]).replace('.','p')+'.txt'
    # #     # impdDev.writeDataJson(data, rootFolder+fName)
    #
    # # f.close()
    #
    # # # This is for dumping data into .JSON
    # # # ------------------------------------------------------------------------
    # for i in range(len(tempDev.tempGrid)):
    #     tempDev.goToTemp(tempDev.tempGrid[i])
    #     time.sleep(1)
    #     if not i==0:
    #         impdDev.device.factory_reset()
    #     impdDev.reloadParams()
    #
    #     numPoints = 2**13
    #     fName = str(tempDev.tempGrid[i]).replace('.','p')+'.txt'
    #     data = impdDev.pullData(plot=False, trigger=True, numPoints=numPoints)
    #     impdDev.writeDataJson(data, rootFolder+fName)
    #
    # tempDev.goToRoomTemp(Tr=30)
    # tempDev.disconnTController()
    # impdDev.session.disconnect_device('dev32271')

    data = iaT.impdData()
    data.readData()
    # # Plot raw data
    # for i in range(len(data.dataTemps)):
    #     idx = data.dataTemps[i]
    #     plt.plot(data.dataValues[idx]['timeStampImps'],data.dataValues[idx]['ImpedanceIm'])
    
    # # Sample emission levels
    # # m,c,l = data.findDataLevels()
    # m, c, l = data.findDataLevelsv2()
    #
    # for i in range(len(m)):
    # # for i in range(5):
    #     t = data.dataTemps[i]
    #     plt.scatter(data.dataValues[t]['timeStampImps'],
    #                 data.dataValues[t]['ImpedanceIm'],c=l[i],
    #                 # data.dataValues[t]['ImpedanceIm'], c=k[i],
    #                 cmap='coolwarm', s=4)
    
    emiss = data.sampleEmissions()
    # for i in range(len(data.dataTemps)):
    #     idx = data.dataTemps[i]
    #     plt.errorbar(emiss[idx]['x'],emiss[idx]['y'],yerr=emiss[idx]['err'])
        
    for i in list(emiss):
        emiss[i]['x'] = emiss[i]['x'][1:-1]
        emiss[i]['y'] = emiss[i]['y'][1:-1]
        emiss[i]['err'] = emiss[i]['err'][1:-1]

    t1 = np.arange(1,4)*0.001
    t2 = np.arange(1,5)*0.002
    delC, errC, delT = data.calculateDeltaCapacitanceT1T2(t1, t2, plot=False)
    data.fitDeltaCapacitanceVsTemperature(delC[:,0], delC[:,10],
                                          errC[:,0],2,
                                          100000, 'gaussian')

    data.fitDeltaCapacitanceVsTemperaturev2(delC[:, 0], delC[:, 5],
                                          errC[:, 5],2, 'lognormal')
    # peakTemps, peakVals, splines = data.estimatePeakTemperatures(delC, delT, plot=True)
    # # print("Peak Temperatures:", peakTemps)
    # # print("Peak Values:", peakVals)
    #
    # # # fExcite will replace 'Oscillation Frequency'!!!
    # # fExcite = wellBehaveFrequencies(fUpper, fLower)
    #
    # # # # impdDev.close()
    # # # data = impdDev.pullData(plot=True, trigger=False, numPoints=2**12)
    #
    # # # IMPLEMENT Delta C as based on a given user TIME input!
    # # # IMPLEMENT Sampling through the acquired data, use difference!!!
    #
    # # # # PLOT TOOLS are needed!!!!
    #
    # # # fig, ax1 = plt.subplots()
    #
    # # # # Plot first dataset on the primary y-axis (left)
    # # # ax1.plot(data[25]['timeStampImps'], data[25]['ImpedanceIm'], color='tab:blue')
    # # # ax1.set_ylabel('Primary Axis', color='tab:blue')
    #
    # # # # Create the twin axis
    # # # ax2 = ax1.twinx()
    #
    # # # # Plot second dataset on the secondary y-axis (right)
    # # # ax2.plot(data[35]['timeStampImps'], data[35]['ImpedanceIm'], color='tab:red')
    # # # ax2.set_ylabel('Secondary Axis', color='tab:red')
    #
    # # # plt.show()
    #
    # # # fig, ax1 = plt.subplots()
    #
    # # # # Plot first dataset on the primary y-axis (left)
    # # # ax1.plot(data[25]['timeStampDemods'], data[25]['AuxInput1'], color='tab:blue')
    # # # ax1.set_ylabel('Primary Axis', color='tab:blue')
    #
    # # # # Create the twin axis
    # # # ax2 = ax1.twinx()
    #
    # # # # Plot second dataset on the secondary y-axis (right)
    # # # ax2.plot(data[35]['timeStampDemods'], data[35]['AuxInput1'], color='tab:red')
    # # # ax2.set_ylabel('Secondary Axis', color='tab:red')
    #
    # # # plt.show()
    #
    # # # Batch process!!!
    # nm = np.arange(30, 125, 5)
    # # data = dict()
    #
    # for i in range(19):
    #     d = iaT.impdData()
    #     d.readData()
    #     # data[nm[i]] = d.dataValues
    #     data[nm[i]] = d
    #
    # for i in range(19):
    #     a,b,c = data[nm[i]].sampleEmissions()
    #     plt.plot(a,b/np.median(b),'.')
    #     # plt.plot(a,b,'.')
    #     print(len(a))
    #
    # t = 50 * np.arange(41)[1:]
    # aa = np.zeros((len(t),len(nm)))
    # bb = np.zeros((len(t),len(nm)))
    # for i in range(len(t)):
    #     minT1 = 0.0
    #     maxT1 = 0.001
    #     window = t[i] * 1e-6
    #     for j in range(len(nm)):
    #         aa[i,j],bb[i,j],cc = data[nm[j]].calculateDeltaCapacitance(window, minT1, maxT1)
    #
    # for i in range(len(t)):
    #     plt.plot(nm,aa[i,:]/np.max(aa[i,:]),label=str(t[i]))
    #     # plt.plot(nm,aa[i,:],label=str(t[i]))
    # plt.legend()
    # # # plt.plot(data[30]['tickStampImps'], data[30]['ImpedanceIm'])
    #
    #
    # # # for i in range(19):
    # # #     if i==0:
    # # #         x = np.array(data[list(data)[i]]['tickStampImps'])
    # # #         y = np.array(data[list(data)[i]]['ImpedanceIm'])
    # # #         y = y[(x<0.0045) & (x>0.0005)]
    # # #         x = x[(x<0.0045) & (x>0.0005)]
    # # #     else:
    # # #         xt = np.array(data[list(data)[i]]['tickStampImps'])
    # # #         yt = np.array(data[list(data)[i]]['ImpedanceIm'])
    # # #         ytt = yt[(xt<0.0045) & (xt>0.0005)]
    # # #         xtt = xt[(xt<0.0045) & (xt>0.0005)]
    #
    # # #         x = np.column_stack((x, xtt))
    # # #         y = np.column_stack((y, ytt))
    #
    # # # import itertools
    #
    # # # lidx = np.argmin(y[1:,0]-y[:-1,0])+3
    # # # hidx = np.argmax(y[1:,0]-y[:-1,0])-5
    # # # arr = np.arange(lidx, hidx+1)
    # # # combs = list(itertools.combinations(arr,2))
    # # # XY = np.array(combs)
    # # # Z = np.zeros((len(XY),19))
    # # # for i in range(19):
    # # #     for j in range(len(XY)):
    # # #         Z[j,i] = y[XY[j,1],i]-y[XY[j,0],i]
    #
    # # # for i in range(19):
    # # #     plt.plot(Z[:,i])
    #
    # # # # plt.plot(nm+273, np.max(Z,axis=0))
    # # # peaks, properties = find_peaks(Z[:,0], prominence=(1.0e-12, 2.443489417030587e-12))
    # # # plt.plot(Z[:,0])
    # # # plt.plot(peaks, Z[peaks,0], "x")
    #
    # # # x[(x[:,0]<0.0045) & (x[:,0]>0.0005),0]
    #
    # # # To plot Delta C over indices as a whole
    # # # for i in np.unique(X):
    # # #     idx = np.where(X==i)[0]
    # # #     plt.plot(XY[idx,1], Z[idx,0])
    #
    # # # Normalized emission traces
    # # for i in range(19):
    # #     plt.plot(x[:,i], y[:,i]/np.max(y[:,i]), label=str(nm[i]))
    # # plt.legend()
    #
    # # #Choice of repetition window
    # # m,c,l = data.findDataLevels()
    # # plt.scatter(data.dataValues['tickStampImps'], data.dataValues['ImpedanceIm'],c=l, cmap='coolwarm', s=4)
    #
    # # for i in range(len(l)):
    # #     if i==0:
    # #         idx = [0]
    # #         val = [l[0]]
    # #     else:
    # #         if not l[i]==val[-1]:
    # #             idx.append(i)
    # #             val.append(l[i])
    #
    #
    # # plt.hlines(m[1]+0.5*np.sqrt(c[1]),0.0,0.08,linestyles='-.')
    # # plt.hlines(m[1]-0.5*np.sqrt(c[1]),0.0,0.08,linestyles='-.')
    # # plt.hlines(m[0]-0.5*np.sqrt(c[0]),0.0,0.08,linestyles='-.')
    # # plt.hlines(m[0]+0.5*np.sqrt(c[0]),0.0,0.08,linestyles='-.')
    #
    # # plt.hlines(m[1]+1*np.sqrt(c[1]),0.0,0.08,linestyles='-')
    # # plt.hlines(m[1]-1*np.sqrt(c[1]),0.0,0.08,linestyles='-')
    # # plt.hlines(m[0]-1*np.sqrt(c[0]),0.0,0.08,linestyles='-')
    # # plt.hlines(m[0]+1*np.sqrt(c[0]),0.0,0.08,linestyles='-')
    #
    # # plt.hlines(m[1]+2*np.sqrt(c[1]),0.0,0.08,linestyles='--')
    # # plt.hlines(m[1]-2*np.sqrt(c[1]),0.0,0.08,linestyles='--')
    # # plt.hlines(m[0]-2*np.sqrt(c[0]),0.0,0.08,linestyles='--')
    # # plt.hlines(m[0]+2*np.sqrt(c[0]),0.0,0.08,linestyles='--')
    #
    # # m,c,l = data.findDataLevels()
    # # value = m[1]+0.5*np.sqrt(c[1])
    # # arr = np.array(d.dataValues['ImpedanceIm'])
    # # arrx = np.array(d.dataValues['timeStampImps'])
    # # k=5
    # # idx = np.argsort(np.abs(arr - value))[:k]
    #
    # # plt.vlines(arrx[idx], np.min(arr), np.max(arr), colors='red', linestyles='dashed')
    #
    # # # a = np.sort(idx)
    # # a = np.array([57, 1290, 2524, 3757])
    # # xxx = arrx[a[0]:a[1]+1]
    # # for i in range(len(a)-1):
    # #     if i==0:
    # #         yyy = arr[a[i]:a[i+1]]
    # #     else:
    # #         if i==len(a)-1:
    # #             temp = arr[a[i]:]
    # #         else:
    # #             temp = arr[a[i]:a[i+1]]
    # #         if len(temp>1233):
    # #             temp=temp[:1233]
    # #         yyy = np.column_stack((yyy,temp))
    #
    #
    #
    # # # 0.0010264 0.0010268
    
    
    
    
    
    
    
     
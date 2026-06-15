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
import numpy as np
import os
import pandas as pd
import serial
import time
from lmfit.models import *
from pathlib import Path
import statistics

os.environ["LOKY_MAX_CPU_COUNT"] = "4"

import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT

importlib.reload(iaT)

# class NumpyEncoder(json.JSONEncoder):
#     def default(self, obj):
#         if isinstance(obj, np.ndarray):
#             return obj.tolist()
#         return super().default(obj)

if __name__ == '__main__':


    # data = iaT.impdData()
    # data.readData()
    # fN = 'C:/Users/peker/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-1p0.txt'
    fN = 'C:/Users/peker/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-72p0.txt'
    data = iaT.impdData(fName=fN)
    data.readData()

    m, c, l = data.findDataLevelsScikitLearn()
    plt.scatter(data.dataValues[list(data.dataValues)[0]]['timeStampImps'],
                # data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'],c=l[idx],
                data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'], c=l[:],
                cmap='coolwarm', s=4)
    x = np.array(data.dataValues[list(data.dataValues)[0]]['timeStampImps'])
    y = np.array(data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'])

    # Data sanity check by evolution of standard deviation
    #------------------------------------------------------
    for j in range(len(l[0])):
        if j == 0:
            idx = [0]
            val = [l[0, 0]]
        else:
            if not l[0, j] == val[-1]:
                idx.append(j)
                val.append(l[0, j])
    diffs = []
    pairs = []
    for j in range(len(val)):
        if (val[j] == 1) and (j + 1 < len(idx)):
            diffs.append(idx[j + 1] - idx[j])
            pairs.append([idx[j], idx[j + 1]])

    commonLength = statistics.mode(np.array(diffs)[np.array(diffs) > 1])
    idx = np.array(pairs)[np.where(np.array(diffs) == commonLength)[0]]
    if len(idx) > 0:
        if len(idx) == 1:
            yy = np.array(y[idx[0]:idx[1]])
            xx = np.array(x[idx[0]:idx[1]])
            xx = xx - xx[0]
        if len(idx) > 1:
            yy = np.array(y[idx[0][0]:idx[0][1]])
            xx = np.array(x[idx[0][0]:idx[0][1]])
            xx = xx - xx[0]
            for k in range(1, len(idx)):
                temp = np.array(y[idx[k][0]:idx[k][1]])
                yy = np.column_stack((yy, temp))
                temp = np.array(x[idx[k][0]:idx[k][1]])
                temp = temp - temp[0]
                xx = np.column_stack((xx, temp))
    std0 = np.mean(np.std(yy,axis=0))
    std1 = np.std(yy)

    # Data sanity check by fitting
    # ------------------------------------------------------
    xx = x[l[0]==1]
    yy = y[l[0] == 1]

    xx = xx / xx[0]
    yy = yy / yy[0]
    # Fit linear model using lmfit
    from lmfit.models import LinearModel, PolynomialModel
    
    # Linear fit
    model_linear = LinearModel()
    params_linear = model_linear.guess(yy, x=xx)
    result_linear = model_linear.fit(yy, params_linear, x=xx)

    # Cubic polynomial fit
    model_cubic = PolynomialModel(degree=3)
    params_cubic = model_cubic.guess(yy, x=xx)
    result_cubic = model_cubic.fit(yy, params_cubic, x=xx)

    # Report linear fit results
    print("\n=== Linear Fit Results ===")
    print(f"Slope: {result_linear.params['slope'].value:.6e} ± {result_linear.params['slope'].stderr:.6e}")
    print(f"Intercept: {result_linear.params['intercept'].value:.6e} ± {result_linear.params['intercept'].stderr:.6e}")
    print(f"R-squared: {result_linear.rsquared}")
    print(f"Chi-squared: {result_linear.chisqr}")
    print(f"Reduced chi-squared: {result_linear.redchi}")

    # Report cubic fit results
    print("\n=== Cubic Polynomial Fit Results ===")
    print(f"c3 (x^3 coefficient): {result_cubic.params['c3'].value:.6e} ± {result_cubic.params['c3'].stderr:.6e}")
    print(f"c2 (x^2 coefficient): {result_cubic.params['c2'].value:.6e} ± {result_cubic.params['c2'].stderr:.6e}")
    print(f"c1 (x coefficient): {result_cubic.params['c1'].value:.6e} ± {result_cubic.params['c1'].stderr:.6e}")
    print(f"c0 (constant): {result_cubic.params['c0'].value:.6e} ± {result_cubic.params['c0'].stderr:.6e}")
    print(f"R-squared: {result_cubic.rsquared}")
    print(f"Chi-squared: {result_cubic.chisqr}")
    print(f"Reduced chi-squared: {result_cubic.redchi}")
    
    # Plot both fits overlayed with data
    plt.figure(figsize=(10, 6))
    plt.scatter(xx, yy, label='Data', s=4, alpha=0.6, color='black')
    yfit_linear = result_linear.best_fit
    yfit_cubic = result_cubic.best_fit
    plt.plot(xx, yfit_linear, 'r-', linewidth=2, label=f'Linear Fit (R²={result_linear.rsquared:.4f})')
    plt.plot(xx, yfit_cubic, 'b-', linewidth=2, label=f'Cubic Fit (R²={result_cubic.rsquared:.4f})')
    plt.xlabel('Normalized Time Stamp')
    plt.ylabel('Normalized Impedance')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()
    
    # plt.plot(xx, yy, '.', markersize=2)
    #
    # rdT.testDataLeveling(dataFile=data.fileName)

    # # # Plot raw data
    # # for i in range(len(data.dataTemps)):
    # #     idx = data.dataTemps[i]
    # #     plt.plot(data.dataValues[idx]['timeStampImps'],data.dataValues[idx]['ImpedanceIm'])
    #
    # # Sample emission levels
    # m, c, l = data.findDataLevelsScikitLearn()
    # sortedTemps = np.sort(data.dataTemps)
    # # # for i in range(len(m)):
    # # for i in range(10,15):
    # #     # t = data.dataTemps[i]
    # #     t = sortedTemps[12]
    # #     idx = np.where(data.dataTemps==sortedTemps[i])[0][0]
    # #     plt.scatter(data.dataValues[t]['timeStampImps'],
    # #                 data.dataValues[t]['ImpedanceIm'],c=l[idx],
    # #                 # data.dataValues[t]['ImpedanceIm'], c=k[idx],
    # #                 cmap='coolwarm', s=4)
    # #     print(t)
    #
    # datasets = []
    # for i in range(len(m)):
    #     t = sortedTemps[i]
    #     idx = np.where(data.dataTemps == sortedTemps[i])[0][0]
    #     temp = np.column_stack((data.dataValues[t]['timeStampImps'],
    #                             data.dataValues[t]['ImpedanceIm']))
    #     temp = np.column_stack((temp,l[idx]))
    #     datasets.append(temp)
    #
    # # Interactive plotting section
    # fig, ax = plt.subplots()
    # current_idx = [0]  # Using a list to allow modification within the event handler
    #
    # def update_plot(idx, keep_limits=False):
    #     if keep_limits:
    #         xlim = ax.get_xlim()
    #         ylim = ax.get_ylim()
    #
    #     ax.clear()
    #     data_to_plot = datasets[idx]
    #     ax.scatter(data_to_plot[:, 0], data_to_plot[:, 1], c=data_to_plot[:, 2],
    #                cmap='coolwarm', s=4)
    #     ax.set_title(f"Temperature: {sortedTemps[idx]}")
    #     ax.set_xlabel("Time (s)")
    #     ax.set_ylabel("Impedance Im")
    #
    #     if keep_limits:
    #         ax.set_xlim(xlim)
    #         ax.set_ylim(ylim)
    #
    #     fig.canvas.draw()
    #
    # def on_press(event):
    #     if event.key == 'right':
    #         current_idx[0] = (current_idx[0] + 1) % len(datasets)
    #         update_plot(current_idx[0], keep_limits=False) # Changed to False
    #     elif event.key == 'left':
    #         current_idx[0] = (current_idx[0] - 1) % len(datasets)
    #         update_plot(current_idx[0], keep_limits=False) # Changed to False
    #     elif event.key == 'escape' or event.key == 'r':
    #         update_plot(current_idx[0], keep_limits=False)
    #
    # fig.canvas.mpl_connect('key_press_event', on_press)
    # update_plot(0)
    # plt.show()
    #
    # # plt.scatter(datasets[0][:,0],datasets[0][:,1],c=datasets[0][:,2],
    # #             # data.dataValues[t]['ImpedanceIm'], c=k[idx],
    # #             cmap='coolwarm', s=4)
    #
    #
    #
    # emiss = data.sampleEmissions()
    # # for i in range(len(data.dataTemps)):
    # #     idx = data.dataTemps[i]
    # #     plt.errorbar(emiss[idx]['x'],emiss[idx]['y'],yerr=emiss[idx]['err'])
    #
    # for i in list(emiss):
    #     emiss[i]['x'] = emiss[i]['x'][1:-1]
    #     emiss[i]['y'] = emiss[i]['y'][1:-1]
    #     emiss[i]['err'] = emiss[i]['err'][1:-1]
    #
    # t1 = np.arange(1,4)*0.001
    # t2 = np.arange(1,5)*0.002
    # delC, errC, delT = data.calculateDeltaCapacitanceT1T2(t1, t2, plot=False)
    # # data.fitDeltaCapacitanceVsTemperatureFitToMixtures(delC[:,0], delC[:,10],
    # #                                       errC[:,0],2,
    # #                                       100000, 'gaussian')
    # #
    # # data.fitDeltaCapacitanceVsTemperatureFitToFunctions(delC[:, 0], delC[:, 10],
    # #                                       errC[:, 10],5, 'lognormal')
    #
    # data.findDeltaCapacitanceMaxima(delC[:, 0], delC[:, 1:], errC[:, 1:],
    #                                 nComponents=[2,3], mixtureType='lognormal',
    #                                 plot=True, fitMethod='lmfit')
    #
    # # peakTemps, peakVals, splines = data.estimatePeakTemperatures(delC, delT, plot=True)
    # # # print("Peak Temperatures:", peakTemps)
    # # # print("Peak Values:", peakVals)
    # #
    # # # # fExcite will replace 'Oscillation Frequency'!!!
    # # # fExcite = wellBehaveFrequencies(fUpper, fLower)
    # #
    # # # # # impdDev.close()
    # # # # data = impdDev.pullData(plot=True, trigger=False, numPoints=2**12)
    # #
    # # # # IMPLEMENT Delta C as based on a given user TIME input!
    # # # # IMPLEMENT Sampling through the acquired data, use difference!!!
    # #
    # # # # # PLOT TOOLS are needed!!!!
    # #
    # # # # fig, ax1 = plt.subplots()
    # #
    # # # # # Plot first dataset on the primary y-axis (left)
    # # # # ax1.plot(data[25]['timeStampImps'], data[25]['ImpedanceIm'], color='tab:blue')
    # # # # ax1.set_ylabel('Primary Axis', color='tab:blue')
    # #
    # # # # # Create the twin axis
    # # # # ax2 = ax1.twinx()
    # #
    # # # # # Plot second dataset on the secondary y-axis (right)
    # # # # ax2.plot(data[35]['timeStampImps'], data[35]['ImpedanceIm'], color='tab:red')
    # # # # ax2.set_ylabel('Secondary Axis', color='tab:red')
    # #
    # # # # plt.show()
    # #
    # # # # fig, ax1 = plt.subplots()
    # #
    # # # # # Plot first dataset on the primary y-axis (left)
    # # # # ax1.plot(data[25]['timeStampDemods'], data[25]['AuxInput1'], color='tab:blue')
    # # # # ax1.set_ylabel('Primary Axis', color='tab:blue')
    # #
    # # # # # Create the twin axis
    # # # # ax2 = ax1.twinx()
    # #
    # # # # # Plot second dataset on the secondary y-axis (right)
    # # # # ax2.plot(data[35]['timeStampDemods'], data[35]['AuxInput1'], color='tab:red')
    # # # # ax2.set_ylabel('Secondary Axis', color='tab:red')
    # #
    # # # # plt.show()
    # #
    # # # # Batch process!!!
    # # nm = np.arange(30, 125, 5)
    # # # data = dict()
    # #
    # # for i in range(19):
    # #     d = iaT.impdData()
    # #     d.readData()
    # #     # data[nm[i]] = d.dataValues
    # #     data[nm[i]] = d
    # #
    # # for i in range(19):
    # #     a,b,c = data[nm[i]].sampleEmissions()
    # #     plt.plot(a,b/np.median(b),'.')
    # #     # plt.plot(a,b,'.')
    # #     print(len(a))
    # #
    # # t = 50 * np.arange(41)[1:]
    # # aa = np.zeros((len(t),len(nm)))
    # # bb = np.zeros((len(t),len(nm)))
    # # for i in range(len(t)):
    # #     minT1 = 0.0
    # #     maxT1 = 0.001
    # #     window = t[i] * 1e-6
    # #     for j in range(len(nm)):
    # #         aa[i,j],bb[i,j],cc = data[nm[j]].calculateDeltaCapacitance(window, minT1, maxT1)
    # #
    # # for i in range(len(t)):
    # #     plt.plot(nm,aa[i,:]/np.max(aa[i,:]),label=str(t[i]))
    # #     # plt.plot(nm,aa[i,:],label=str(t[i]))
    # # plt.legend()
    # # # # plt.plot(data[30]['tickStampImps'], data[30]['ImpedanceIm'])
    # #
    # #
    # # # # for i in range(19):
    # # # #     if i==0:
    # # # #         x = np.array(data[list(data)[i]]['tickStampImps'])
    # # # #         y = np.array(data[list(data)[i]]['ImpedanceIm'])
    # # # #         y = y[(x<0.0045) & (x>0.0005)]
    # # # #         x = x[(x<0.0045) & (x>0.0005)]
    # # # #     else:
    # # # #         xt = np.array(data[list(data)[i]]['tickStampImps'])
    # # # #         yt = np.array(data[list(data)[i]]['ImpedanceIm'])
    # # # #         ytt = yt[(xt<0.0045) & (xt>0.0005)]
    # # # #         xtt = xt[(xt<0.0045) & (xt>0.0005)]
    # #
    # # # #         x = np.column_stack((x, xtt))
    # # # #         y = np.column_stack((y, ytt))
    # #
    # # # # import itertools
    # #
    # # # # lidx = np.argmin(y[1:,0]-y[:-1,0])+3
    # # # # hidx = np.argmax(y[1:,0]-y[:-1,0])-5
    # # # # arr = np.arange(lidx, hidx+1)
    # # # # combs = list(itertools.combinations(arr,2))
    # # # # XY = np.array(combs)
    # # # # Z = np.zeros((len(XY),19))
    # # # # for i in range(19):
    # # # #     for j in range(len(XY)):
    # # # #         Z[j,i] = y[XY[j,1],i]-y[XY[j,0],i]
    # #
    # # # # for i in range(19):
    # # # #     plt.plot(Z[:,i])
    # #
    # # # # # plt.plot(nm+273, np.max(Z,axis=0))
    # # # # peaks, properties = find_peaks(Z[:,0], prominence=(1.0e-12, 2.443489417030587e-12))
    # # # # plt.plot(Z[:,0])
    # # # # plt.plot(peaks, Z[peaks,0], "x")
    # #
    # # # # x[(x[:,0]<0.0045) & (x[:,0]>0.0005),0]
    # #
    # # # # To plot Delta C over indices as a whole
    # # # # for i in np.unique(X):
    # # # #     idx = np.where(X==i)[0]
    # # # #     plt.plot(XY[idx,1], Z[idx,0])
    # #
    # # # # Normalized emission traces
    # # # for i in range(19):
    # # #     plt.plot(x[:,i], y[:,i]/np.max(y[:,i]), label=str(nm[i]))
    # # # plt.legend()
    # #
    # # # #Choice of repetition window
    # # # m,c,l = data.findDataLevels()
    # # # plt.scatter(data.dataValues['tickStampImps'], data.dataValues['ImpedanceIm'],c=l, cmap='coolwarm', s=4)
    # #
    # # # for i in range(len(l)):
    # # #     if i==0:
    # # #         idx = [0]
    # # #         val = [l[0]]
    # # #     else:
    # # #         if not l[i]==val[-1]:
    # # #             idx.append(i)
    # # #             val.append(l[i])
    # #
    # #
    # # # plt.hlines(m[1]+0.5*np.sqrt(c[1]),0.0,0.08,linestyles='-.')
    # # # plt.hlines(m[1]-0.5*np.sqrt(c[1]),0.0,0.08,linestyles='-.')
    # # # plt.hlines(m[0]-0.5*np.sqrt(c[0]),0.0,0.08,linestyles='-.')
    # # # plt.hlines(m[0]+0.5*np.sqrt(c[0]),0.0,0.08,linestyles='-.')
    # #
    # # # plt.hlines(m[1]+1*np.sqrt(c[1]),0.0,0.08,linestyles='-')
    # # # plt.hlines(m[1]-1*np.sqrt(c[1]),0.0,0.08,linestyles='-')
    # # # plt.hlines(m[0]-1*np.sqrt(c[0]),0.0,0.08,linestyles='-')
    # # # plt.hlines(m[0]+1*np.sqrt(c[0]),0.0,0.08,linestyles='-')
    # #
    # # # plt.hlines(m[1]+2*np.sqrt(c[1]),0.0,0.08,linestyles='--')
    # # # plt.hlines(m[1]-2*np.sqrt(c[1]),0.0,0.08,linestyles='--')
    # # # plt.hlines(m[0]-2*np.sqrt(c[0]),0.0,0.08,linestyles='--')
    # # # plt.hlines(m[0]+2*np.sqrt(c[0]),0.0,0.08,linestyles='--')
    # #
    # # # m,c,l = data.findDataLevels()
    # # # value = m[1]+0.5*np.sqrt(c[1])
    # # # arr = np.array(d.dataValues['ImpedanceIm'])
    # # # arrx = np.array(d.dataValues['timeStampImps'])
    # # # k=5
    # # # idx = np.argsort(np.abs(arr - value))[:k]
    # #
    # # # plt.vlines(arrx[idx], np.min(arr), np.max(arr), colors='red', linestyles='dashed')
    # #
    # # # # a = np.sort(idx)
    # # # a = np.array([57, 1290, 2524, 3757])
    # # # xxx = arrx[a[0]:a[1]+1]
    # # # for i in range(len(a)-1):
    # # #     if i==0:
    # # #         yyy = arr[a[i]:a[i+1]]
    # # #     else:
    # # #         if i==len(a)-1:
    # # #             temp = arr[a[i]:]
    # # #         else:
    # # #             temp = arr[a[i]:a[i+1]]
    # # #         if len(temp>1233):
    # # #             temp=temp[:1233]
    # # #         yyy = np.column_stack((yyy,temp))
    # #
    # #
    # #
    # # # # 0.0010264 0.0010268
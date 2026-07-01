# -*- coding: utf-8 -*-
"""
Created on Tue Jun 16 10:32:58 2026

@author: spencer
"""
%reset -f
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

data =  iaT.impdData()
data.readData()
data.sampleEmissions(showLevels=False, library='scikitlearn', algorithm='hybrid',
                     interactivePlot=False, interactiveDataIndex=0,
                     assignDataEmissions=False, useStoredEmissions=True,
                     returnClusterIndices=False, temperature=None,
                     alignmentDebug=True)
data.findDataLevels('sklearn','hybrid',False,True)

import numpy as np

runDLTS_Tools.py
#-----------------------------------
model_key = 'gmm'
n_t = len(data.dataTemps)
n_pts = len(data.dataValues[data.dataTemps[0]]['ImpedanceIm'])
means = np.full((n_t, 2), np.nan)
stds = np.full((n_t, 2), np.nan)
labels = np.full((n_t, n_pts), -1.0)

for i, t in enumerate(data.dataTemps):
    raw = np.asarray(data.dataValues[t]['ImpedanceIm'], dtype=float).ravel()
    if raw.size != n_pts:
        raise ValueError(f"Inconsistent ImpedanceIm length at {t} K.")

    if not np.all(np.isfinite(raw)):
        finite = raw[np.isfinite(raw)]
        fill_val = np.median(finite) if finite.size > 0 else 0.0
        raw = np.where(np.isfinite(raw), raw, fill_val)

    scale = np.min(raw)
    if np.isclose(scale, 0.0):
        scale = np.max(np.abs(raw))
    if np.isclose(scale, 0.0):
        scale = 1.0

    d = (raw / scale).reshape(-1, 1)
    gmm = GaussianMixture(n_components=2, random_state=0, covariance_type='full', reg_covar=1e-8)
    gmm.fit(d)
    gmm_labels = gmm.predict(d).astype(int)
    gmm_means = gmm.means_.flatten() * scale

    km = KMeans(n_clusters=2, random_state=0, n_init=10)
    km.fit(d)
    km_labels = km.labels_.astype(int)
    km_means = km.cluster_centers_.flatten() * scale


# --- Pre-compute GMM / KMeans / Hybrid labels for all temperature indices -----
n_temps       = len(data.dataTemps)
all_km_labels     = [None] * n_temps
all_gmm_labels    = [None] * n_temps
all_hybrid_labels = [None] * n_temps
all_hybrid_keep   = [None] * n_temps

for i in range(n_temps):
    t   = data.dataTemps[i]
    raw = np.asarray(data.dataValues[t]['ImpedanceIm'], dtype=float).ravel()

    # Fill any non-finite values with the median
    if not np.all(np.isfinite(raw)):
        finite   = raw[np.isfinite(raw)]
        fill_val = np.median(finite) if finite.size > 0 else 0.0
        raw      = np.where(np.isfinite(raw), raw, fill_val)

    # Normalisation scale
    scale = np.min(raw)
    # if np.isclose(scale, 0.0):
    #     scale = np.max(np.abs(raw))
    # if np.isclose(scale, 0.0):
    #     scale = 1.0

    d = (raw / scale).reshape(-1, 1)

    # --- GMM ---
    gmm_model = GaussianMixture(n_components=2, random_state=0)
    gmm_model.fit(d)
    gmm_lbl   = gmm_model.fit_predict(d).astype(int)
    # Cluster means back in original (possibly negative) space
    gmm_means = gmm_model.means_.flatten() * scale
    # print(len(np.unique(gmm_lbl)))

    # --- KMeans ---
    km_model = KMeans(n_clusters=2, random_state=0, n_init=10)
    km_model.fit(d)
    km_lbl   = km_model.labels_.astype(int)
    km_means = km_model.cluster_centers_.flatten() * scale

    # Canonicalize: label 0 = cluster with the LARGER mean value.
    # Use np.argmax so the comparison works correctly for negative data too.
    if np.argmax(km_means) != 0:
        km_lbl   = 1 - km_lbl
        km_means = km_means[::-1].copy()

    if np.argmax(gmm_means) != 0:
        gmm_lbl   = 1 - gmm_lbl
        gmm_means = gmm_means[::-1].copy()

    # Hybrid: keep only points where both models agree, drop disagreements.
    hybrid_keep = (gmm_lbl == km_lbl)
    hybrid_lbl = gmm_lbl[hybrid_keep]

    all_km_labels[i]     = km_lbl
    all_gmm_labels[i]    = gmm_lbl
    all_hybrid_labels[i] = hybrid_lbl
    all_hybrid_keep[i]   = hybrid_keep

# --- Interactive 3-panel plot (← / → to step through i) ---------------------
current = [0]

fig, axes = plt.subplots(nrows=3, figsize=(10, 8), sharex=True, sharey=True)
axes[-1].set_xlabel('Time (s)', fontsize=10)

def update_cluster_plot(idx):
    t   = data.dataTemps[idx]
    ts  = np.asarray(data.dataValues[t]['timeStampImps'])
    imp = np.asarray(data.dataValues[t]['ImpedanceIm'])

    axes[0].cla()
    axes[0].scatter(ts, imp, c=all_km_labels[idx], cmap='coolwarm', s=4, vmin=0, vmax=1)
    axes[0].set_ylabel('K-Means', fontsize=10)

    axes[1].cla()
    axes[1].scatter(ts, imp, c=all_gmm_labels[idx], cmap='coolwarm', s=4, vmin=0, vmax=1)
    axes[1].set_ylabel('GMM', fontsize=10)

    keep = all_hybrid_keep[idx]
    ts_h = ts[keep]
    imp_h = imp[keep]
    lbl_h = all_hybrid_labels[idx]
    axes[2].cla()
    axes[2].scatter(ts_h, imp_h, c=lbl_h, cmap='coolwarm', s=4, vmin=0, vmax=1)
    axes[2].set_ylabel('Hybrid', fontsize=10)
    axes[-1].set_xlabel('Time (s)', fontsize=10)
    fig.suptitle(f'i = {idx}  /  T = {t} K    (← / → to navigate)', fontsize=11)
    fig.canvas.draw_idle()

def on_cluster_key(event):
    if event.key == 'right':
        current[0] = (current[0] + 1) % n_temps
    elif event.key == 'left':
        current[0] = (current[0] - 1) % n_temps
    else:
        return
    update_cluster_plot(current[0])

fig.canvas.mpl_connect('key_press_event', on_cluster_key)
update_cluster_plot(current[0])
plt.tight_layout()
plt.show()
# --- end interactive cluster plot ---------------------------------------------




        # data = impdDev.pullData(plot=False, trigger=True, numPoints=numPoints)
        # impdDev.writeDataJson(data, rootFolder+fName)




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
    
    
runDLTS.py
#-----------------------------------
    xx = data.dataValues['tickStampImps']
    
    plt.plot(xx, yy, '.', markersize=2)
    
    rdT.testDataLeveling(dataFile=data.fileName)

    # # Plot raw data
    # for i in range(len(data.dataTemps)):
    #     idx = data.dataTemps[i]
    #     plt.plot(data.dataValues[idx]['timeStampImps'],data.dataValues[idx]['ImpedanceIm'])
    
    # Sample emission levels
    m, c, l = data.findDataLevelsScikitLearn()
    sortedTemps = np.sort(data.dataTemps)
    # # for i in range(len(m)):
    # for i in range(10,15):
    #     # t = data.dataTemps[i]
    #     t = sortedTemps[12]
    #     idx = np.where(data.dataTemps==sortedTemps[i])[0][0]
    #     plt.scatter(data.dataValues[t]['timeStampImps'],
    #                 data.dataValues[t]['ImpedanceIm'],c=l[idx],
    #                 # data.dataValues[t]['ImpedanceIm'], c=k[idx],
    #                 cmap='coolwarm', s=4)
    #     print(t)
    
    ###THIS IS INTERACTIVE PLOT!!!!!!!!!!!!!!!
    datasets = []
    for i in range(len(m)):
        t = sortedTemps[i]
        idx = np.where(data.dataTemps == sortedTemps[i])[0][0]
        temp = np.column_stack((data.dataValues[t]['timeStampImps'],
                                data.dataValues[t]['ImpedanceIm']))
        temp = np.column_stack((temp,l[idx]))
        datasets.append(temp)
    
    # Interactive plotting section
    fig, ax = plt.subplots()
    current_idx = [0]  # Using a list to allow modification within the event handler
    
    def update_plot(idx, keep_limits=False):
        if keep_limits:
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
    
        ax.clear()
        data_to_plot = datasets[idx]
        ax.scatter(data_to_plot[:, 0], data_to_plot[:, 1], c=data_to_plot[:, 2],
                   cmap='coolwarm', s=4)
        ax.set_title(f"Temperature: {sortedTemps[idx]}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Impedance Im")
    
        if keep_limits:
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
    
        fig.canvas.draw()
    
    def on_press(event):
        if event.key == 'right':
            current_idx[0] = (current_idx[0] + 1) % len(datasets)
            update_plot(current_idx[0], keep_limits=False) # Changed to False
        elif event.key == 'left':
            current_idx[0] = (current_idx[0] - 1) % len(datasets)
            update_plot(current_idx[0], keep_limits=False) # Changed to False
        elif event.key == 'escape' or event.key == 'r':
            update_plot(current_idx[0], keep_limits=False)
    
    fig.canvas.mpl_connect('key_press_event', on_press)
    update_plot(0)
    plt.show()
    ###THIS IS INTERACTIVE PLOT!!!!!!!!!!!!!!!
    
    
    
    # plt.scatter(datasets[0][:,0],datasets[0][:,1],c=datasets[0][:,2],
    #             # data.dataValues[t]['ImpedanceIm'], c=k[idx],
    #             cmap='coolwarm', s=4)
    
    
    
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
    # data.fitDeltaCapacitanceVsTemperatureFitToMixtures(delC[:,0], delC[:,10],
    #                                       errC[:,0],2,
    #                                       100000, 'gaussian')
    #
    # data.fitDeltaCapacitanceVsTemperatureFitToFunctions(delC[:, 0], delC[:, 10],
    #                                       errC[:, 10],5, 'lognormal')
    
    data.findDeltaCapacitanceMaxima(delC[:, 0], delC[:, 1:], errC[:, 1:],
                                    nComponents=[2,3], mixtureType='lognormal',
                                    plot=True, fitMethod='lmfit')
    
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
    
    
impedanceAnalysis_Tools.py
#-----------------------------------
    # @staticmethod
    # def leftSkewedWeibull(x, alpha, beta, gamma):
    #     """PDF of a left-skewed 3-parameter Weibull distribution."""
    #     # We use the built-in scipy weibull_min but flip the x-axis relative to gamma
    #     x_shifted = gamma - x
    #     # Prevent evaluations outside the valid domain
    #     pdf = np.zeros_like(x, dtype=float)
    #     mask = x_shifted > 0
    #     if np.any(mask):
    #         pdf[mask] = weibull_min.pdf(x_shifted[mask], c=beta, scale=alpha)
    #     return pdf
    #
    # def fitLeftSkewedWeibull(self, x, y, alpha0=15.0, beta0=4.0, gamma0=None):
    #     """Fit leftSkewedWeibull to data (x, y) using lmfit.
    #
    #     Parameters
    #     ----------
    #     x : array-like
    #         Independent variable (e.g. temperature).
    #     y : array-like
    #         Dependent variable (e.g. delta-C signal).
    #     alpha0 : float, optional
    #         Initial guess for the scale parameter (default 15.0).
    #     beta0 : float, optional
    #         Initial guess for the shape parameter (default 4.0).
    #     gamma0 : float, optional
    #         Initial guess for the location (upper-bound) parameter.
    #         If None, defaults to ``max(x) + 10``.
    #
    #     Returns
    #     -------
    #     result : lmfit.model.ModelResult
    #         The full lmfit fit result object.
    #     """
    #     from lmfit import Model
    #
    #     model = Model(self.leftSkewedWeibull)
    #
    #     if gamma0 is None:
    #         gamma0 = np.max(x) + 10.0
    #
    #     params = model.make_params()
    #     params['alpha'].set(value=alpha0, min=0.001)
    #     params['beta'].set(value=beta0, min=3.6)
    #     params['gamma'].set(value=gamma0, min=np.max(x))
    #
    #     result = model.fit(y, params, x=np.asarray(x, dtype=float))
    #     return result
    #
    # def testPeakTemperatures(self, delC, delTs=None, nPoints=1000, plot=True):
    #     x = delC[:, 0]
    #     nCurves = delC.shape[1] - 1
    #     peakTemps = np.zeros(nCurves)
    #     peakVals = np.zeros(nCurves)
    #     fitResults = []
    #     tFine = np.linspace(np.min(x), np.max(x), nPoints)
    #     for i in range(nCurves):
    #         y = delC[:, i + 1]
    #         result = self.fitLeftSkewedWeibull(x, y)
    #         fitResults.append(result)
    #         yFine = result.eval(x=tFine)
    #         maxIdx = np.argmax(yFine)
    #         peakTemps[i] = tFine[maxIdx]
    #         peakVals[i] = yFine[maxIdx]
    #
    #     if plot:
    #         fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=nCurves // 2, sharex=True, sharey=True)
    #         for i in range(nCurves // 2):
    #             if delTs is not None:
    #                 lbl0 = 't2=' + str(int(delTs[2 * i, 1] * 1000)) + 'ms - t1=' + \
    #                     str(int(delTs[2 * i, 0] * 1000)) + 'ms'
    #                 lbl1 = 't2=' + str(int(delTs[2 * i + 1, 1] * 1000)) + 'ms - t1=' + \
    #                     str(int(delTs[2 * i + 1, 0] * 1000)) + 'ms'
    #             else:
    #                 lbl0 = None
    #                 lbl1 = None
    #
    #             c0 = np.max(delC[:, 2 * i + 1])
    #             yFine0 = fitResults[2 * i].eval(x=tFine)
    #             ax[i, 0].plot(tFine, yFine0 / c0, '-', color='blue', linewidth=1)
    #             ax[i, 0].plot(x, delC[:, 2 * i + 1] / c0, 'o', color='r', markersize=3, label=lbl0)
    #             ax[i, 0].legend(fontsize=12)
    #             ax[i, 0].tick_params(axis='x', labelsize=18)
    #             ax[i, 0].tick_params(axis='y', labelsize=18)
    #             ax[i, 0].set_ylim([0.0, 1.05])
    #             ax[i, 0].set_yticks([0.5])
    #             ax[i, 0].set_xticks([50 - 23, 100 - 23, 150 - 23, 200 - 23],
    #                                 labels=[str(50 + 200), str(100 + 200), str(150 + 200), str(200 + 200)])
    #
    #             c1 = np.max(delC[:, 2 * i + 2])
    #             yFine1 = fitResults[2 * i + 1].eval(x=tFine)
    #             ax[i, 1].plot(tFine, yFine1 / c1, '-', color='blue', linewidth=1)
    #             ax[i, 1].plot(x, delC[:, 2 * i + 2] / c1, 'o', color='r', markersize=3, label=lbl1)
    #             ax[i, 1].legend(fontsize=12)
    #             ax[i, 1].tick_params(axis='x', labelsize=18)
    #             ax[i, 1].tick_params(axis='y', labelsize=18)
    #             ax[i, 1].set_ylim([0.0, 1.05])
    #             ax[i, 1].set_yticks([0.5])
    #             ax[i, 1].set_xticks([50 - 23, 100 - 23, 150 - 23, 200 - 23],
    #                                 labels=[str(50 + 200), str(100 + 200), str(150 + 200), str(200 + 200)])
    #
    #         fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
    #         fig.supylabel(r'$\delta C$/C', fontsize=18)
    #         fig.subplots_adjust(top=0.975, bottom=0.090,
    #                             left=0.070, right=0.990,
    #                             wspace=0.000, hspace=0.0)
    #         plt.show()
    #
    #     return peakTemps, peakVals, fitResults
    #
    # def estimatePeakTemperatures(self, delC, delTs=None, s=None, nPoints=1000, plot=False):
    #     temperatures = np.array(self.dataTemps)
    #     nCurves = delC.shape[1] - 1
    #     peakTemps = np.zeros(nCurves)
    #     peakVals = np.zeros(nCurves)
    #     splines = []
    #     tFine = np.linspace(np.min(temperatures), np.max(temperatures), nPoints)
    #     for j in range(nCurves):
    #         y = delC[:, j+1]
    #         spl = make_smoothing_spline(temperatures, y, lam=s)
    #         splines.append(spl)
    #         yFine = spl(tFine)
    #         maxIdx = np.argmax(yFine)
    #         peakTemps[j] = tFine[maxIdx]
    #         peakVals[j] = yFine[maxIdx]
    #
    #     if plot:
    #         fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=nCurves//2, sharex=True, sharey=True)
    #         for i in range(nCurves//2):
    #             if delTs is not None:
    #                 lbl0 = 't2=' + str(int(delTs[2*i,1]*1000)) + 'ms - t1=' + \
    #                     str(int(delTs[2*i,0]*1000)) + 'ms'
    #                 lbl1 = 't2=' + str(int(delTs[2*i+1,1]*1000)) + 'ms - t1=' + \
    #                     str(int(delTs[2*i+1,0]*1000)) + 'ms'
    #             else:
    #                 lbl0 = None
    #                 lbl1 = None
    #
    #             c0 = np.max(delC[:,2*i+1])
    #             yFine0 = splines[2*i](tFine)
    #             ax[i,0].plot(tFine, yFine0/c0, '-', color='blue', linewidth=1)
    #             ax[i,0].plot(temperatures, delC[:,2*i+1]/c0, 'o', color='r', markersize=3, label=lbl0)
    #             ax[i,0].legend(fontsize=12)
    #             ax[i,0].tick_params(axis='x', labelsize=18)
    #             ax[i,0].tick_params(axis='y', labelsize=18)
    #             ax[i,0].set_ylim([0.0,1.05])
    #             ax[i,0].set_yticks([0.5])
    #             ax[i,0].set_xticks([50-23, 100-23, 150-23, 200-23],
    #                                labels=[str(50+200), str(100+200), str(150+200), str(200+200)])
    #
    #             c1 = np.max(delC[:,2*i+2])
    #             yFine1 = splines[2*i+1](tFine)
    #             ax[i,1].plot(tFine, yFine1/c1, '-', color='blue', linewidth=1)
    #             ax[i,1].plot(temperatures, delC[:,2*i+2]/c1, 'o', color='r', markersize=3, label=lbl1)
    #             ax[i,1].legend(fontsize=12)
    #             ax[i,1].tick_params(axis='x', labelsize=18)
    #             ax[i,1].tick_params(axis='y', labelsize=18)
    #             ax[i,1].set_ylim([0.0,1.05])
    #             ax[i,1].set_yticks([0.5])
    #             ax[i,1].set_xticks([50-23, 100-23, 150-23, 200-23],
    #                                labels=[str(50+200), str(100+200), str(150+200), str(200+200)])
    #
    #         fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
    #         fig.supylabel(r'$\delta C$/C', fontsize=18)
    #         fig.subplots_adjust(top=0.975, bottom=0.090,
    #                             left=0.070, right=0.990,
    #                             wspace=0.000, hspace=0.0)
    #         plt.show()
    #
    #     return peakTemps, peakVals, splines
    #
    # # # @staticmethod
    # # # def find_nearest(array, value):
    # # #     array = np.asarray(array)
    # # #     idx = (np.abs(array - value)).argmin()
    # # #     return idx, array[idx]
    #
    # # def calculateDeltaCapacitance(self, window=0.001, minT1=0, maxT1=0): #CORRECT THIS!!!
    # #     x, y, err = self.sampleEmissions()
    # #     yCS = CubicSpline(x, y, bc_type='natural')
    # #     errCS = CubicSpline(x, err, bc_type='natural')
    # #     if window < x[-1]-x[0]:
    # #         if (minT1==0) and (maxT1==0):
    # #             p0 = yCS(x[0])
    # #             p1 = yCS(x[0]+window)
    # #             e0 = np.abs(errCS(x[0]))
    # #             e1 = np.abs(errCS(x[0]+window))
    # #             delC = ufloat(p1,e1) - ufloat(p0,e0)
    # #             delCVal = delC.nominal_value
    # #             delCErr = delC.std_dev
    # #         if (minT1==0) and (maxT1>0):
    # #             if maxT1 < x[-1]-window:
    # #                 maxT1Idx = np.where(x < maxT1)[0]
    # #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    # #                 for i in range(len(maxT1Idx)):
    # #                     p0 = yCS(x[maxT1Idx[i]])
    # #                     p1 = yCS(x[maxT1Idx[i]]+window)
    # #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    # #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    # #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    # #             else:
    # #                 newMaxT1Idx = np.where(x < x[-1]-window)[0][-1]
    # #                 maxT1 = x[newMaxT1Idx]
    # #                 maxT1Idx = np.where(x < maxT1)[0]
    # #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    # #                 for i in range(len(maxT1Idx)):
    # #                     p0 = yCS(x[maxT1Idx[i]])
    # #                     p1 = yCS(x[maxT1Idx[i]]+window)
    # #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    # #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    # #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    # #             delCVal = delC.mean().nominal_value
    # #             delCErr = delC.mean().std_dev
    # #             returnVal = 0
    # #         if (minT1>0) and (maxT1==minT1):
    # #             minT1Idx = np.where(x < minT1)[0][-1]
    # #             p0 = yCS(x[minT1Idx])
    # #             p1 = yCS(x[minT1Idx]+window)
    # #             e0 = np.abs(errCS(x[minT1Idx]))
    # #             e1 = np.abs(errCS(x[minT1Idx]+window))
    # #             delC = ufloat(p1,e1) - ufloat(p0,e0)
    # #             delCVal = delC.nominal_value
    # #             delCErr = delC.std_dev
    # #             returnVal = 0
    # #         if (minT1>0) and (maxT1>minT1):
    # #             minT1Idx = np.where(x < minT1)[0][-1]
    # #             if maxT1 < x[-1]-window:
    # #                 maxT1Idx = np.where(x < maxT1)[0]
    # #                 maxT1Idx = maxT1Idx[maxT1Idx>=minT1Idx]
    # #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    # #                 for i in range(len(maxT1Idx)):
    # #                     p0 = yCS(x[maxT1Idx[i]])
    # #                     p1 = yCS(x[maxT1Idx[i]]+window)
    # #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    # #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    # #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    # #             else:
    # #                 newMaxT1Idx = np.where(x < x[-1]-window)[0][-1]
    # #                 maxT1 = x[newMaxT1Idx]
    # #                 maxT1Idx = np.where(x < maxT1)[0]
    # #                 maxT1Idx = maxT1Idx[maxT1Idx>=minT1Idx]
    # #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    # #                 for i in range(len(maxT1Idx)):
    # #                     p0 = yCS(x[maxT1Idx[i]])
    # #                     p1 = yCS(x[maxT1Idx[i]]+window)
    # #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    # #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    # #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    # #             delCVal = delC.mean().nominal_value
    # #             delCErr = delC.mean().std_dev
    # #             returnVal = 0
    #
    # #     else:
    # #         print("Window is larger than data span!")
    # #         delCVal = 0
    # #         delCErr = 0
    # #         returnVal = -1
    # #     return delCVal, delCErr, returnVal
    #
    # # def deltaCapacitancePlots(self, window=1000, temperatures=30, minT1=0, maxT1=1000, smooth=False):
    # #     maxT1 = maxT1 * 1e-6
    # #     for i in range(len(window)):
    # #         window = window[i] * 1e-6
    # #         for j in range(len(temperatures)):
    # #             aa[i,j],bb[i,j],cc = data[temperatures[j]].calculateDeltaCapacitance(window, minT1, maxT1)
    #
    # #     for i in range(len(t)):
    # #         plt.plot(nm,aa[i,:]/np.max(aa[i,:]),label=str(t[i]))
    #
    # #     return 0
            
# -*- coding: utf-8 -*-
"""
Created on Wed May  6 13:23:08 2026

@author: spencer
"""

import time
import zhinst.core
import zhinst.toolkit as zt
import zhinst.ziPython as zi
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from tkinter.filedialog import askopenfilenames

from numpy.ma.extras import apply_along_axis
from scipy.interpolate import make_smoothing_spline, CubicSpline
import json
from sklearn.mixture import GaussianMixture
from sklearn.cluster import KMeans
import h5py
import statistics
from uncertainties import unumpy, ufloat
import itertools
from scipy.stats import weibull_min, mode
import torch
from scipy.integrate import quad
import lmfit
from lmfit.models import LognormalModel, GaussianModel

import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="uncertainties")

import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC

class impdData:
    def __init__(self, fName=None):
        self.fileName = fName
        self.rootFolder = None
        self.dataValues = None
        self.dataTemps = None
        self.dataExcitationLevelParams = None
        self.dataExcitationClusterParams = None
        self.dataEmissionLevelParams = None
        self.dataEmissionClusterParams = None

        self.dataEmissionLevelParams = None
        self.dataEmissions = None
        self.dataSignals = None
        self.dataType = None
        self.subType = None
        self.dataParams = None

    def readData(self):
        print("Fix other data file import cases and exception for not choosing file! ")
        if self.fileName is None:
            self.fileName = askopenfilenames(title="Select a file",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])

        if isinstance(self.fileName, str):
            self.fileName = [self.fileName]

        # Skip files whose name (excluding path) contains no numeric digits.
        filtered = []
        for f in self.fileName:
            basename = f.replace('\\', '/').rsplit('/', 1)[-1]
            if any(c.isdigit() for c in basename):
                filtered.append(f)
            else:
                print(f"Skipping '{basename}': no number found in filename.")
        self.fileName = filtered

        if not self.fileName:
            print("No valid data files selected (none contained a number in the filename).")
            return -1

        if self.rootFolder is None:
            idx = self.fileName[0][::-1].find('/')
            self.rootFolder = self.fileName[0][:-idx]
        
        strippedFName = []
        for i in range(len(self.fileName)):
            temp = self.fileName[i].replace(self.rootFolder,"")
            strippedFName.append(temp)
        
        if self.dataTemps is None:
            self.dataTemps = []
            for i in range(len(self.fileName)):
                idx = strippedFName[i].find('.')
                t0 = '+' if strippedFName[i][0]=='p' else '-'
                t = strippedFName[i][1:idx].replace("p",".")
                t = t0 + t
                if t.strip():
                    self.dataTemps.append(int(float(t))+273)
                else:
                    print(f"Warning: Could not extract temperature from filename: {self.fileName[i]}")

        try:
            data = dict()
            for i in range(len(self.fileName)):
                with open(self.fileName[i], 'r', encoding='utf-8') as file:
                    data[self.dataTemps[i]] = json.load(file)
            self.dataValues = data
            with open(self.rootFolder+'runParams.txt', 'r', encoding='utf-8') as file:
                param = json.load(file)
            self.dataParams = param
            return 0
        
        except FileNotFoundError:
            print("Error: The file does not exist.")
            self.fileName = None
            return -1

        # except json.JSONDecodeError:
        #     data = pd.read_csv(self.fileName, header=None, skiprows=1, sep=';')
        #     keys = list(data.iloc[:,3])
        #     vals = data.iloc[:,4:].to_numpy()
            
        #     self.dataValues = dict()
        #     for i in range(len(keys)):
        #         self.dataValues[keys[i]] = vals[i,:]
        #     self.dataType = "sweep" 
        #     self.subType = "cv" if "auxin0" in list(self.dataValues) else "freq"
        #     if self.subType=='cv':
        #         print("CV sweep uses two data files!\n")
        #         print("Run this function again to load the second file!")
            # return 0

    def wellBehaveFrequencies(self, fUpper, fLower):
        if self.dataType is None:
            print("Data doesn't exist!!!")
            return -1
        else:
            if self.dataType=="sweep":
                x = np.ascontiguousarray(self.dataValues['frequency'], dtype=np.float64)
                y = np.ascontiguousarray(np.rad2deg(self.dataValues['phasez']), dtype=np.float64)
                
                # Smooth the data for analysis
                xn = np.linspace(np.min(x), np.max(x), 1000)
                yn = make_smoothing_spline(x,y,lam=10)(xn)
                
                # fmin = np.min(xn[(yn<fUpper) & (yn>fLower)])
                # fmax = np.max(xn[(yn<fUpper) & (yn>fLower)])
                fRelevant = xn[(yn<fUpper) & (yn>fLower)]
                
                # This frequency will replace 501k frequency!!!
                return np.median(fRelevant)
            else:
                print("Data is not a sweep!!!")
                return 1

    def findDataLevelsScikit(self, dataType = 'emission', model='gmm', interactivePlot=False):
        if self.dataTemps is None or self.dataValues is None or len(self.dataTemps) == 0:
            raise ValueError("No loaded data found. Call readData() first.")

        model_key = str(model).strip().lower()
        if model_key not in ('gmm', 'kmeans', 'hybrid'):
            raise ValueError("model must be one of: 'gmm', 'kmeans', 'hybrid'")

        n_t = len(self.dataTemps)
        if dataType=='emission':
            n_pts = len(self.dataValues[self.dataTemps[0]]['ImpedanceIm'])
        if dataType=='excitation':
            n_pts = len(self.dataValues[self.dataTemps[0]]["AuxInput1"])

        means = np.full((n_t, 2), np.nan)
        stds = np.full((n_t, 2), np.nan)
        labels = np.full((n_t, n_pts), -1.0)

        for i, t in enumerate(self.dataTemps):
            if dataType=='emission':
                raw = np.asarray(self.dataValues[t]['ImpedanceIm'], dtype=float).ravel()
            if dataType=='excitation':
                raw = np.asarray(self.dataValues[t]["AuxInput1"], dtype=float).ravel()

            if raw.size != n_pts:
                raise ValueError(f"Inconsistent data length at {t} K.")

            if not np.all(np.isfinite(raw)):
                finite = raw[np.isfinite(raw)]
                fill_val = np.median(finite) if finite.size > 0 else 0.0
                raw = np.where(np.isfinite(raw), raw, fill_val)

            scale = np.min(raw)
            sorted_raw = np.sort(raw)
            second_min = sorted_raw[1] if len(sorted_raw) > 1 else scale

            if abs(second_min) > 0 and abs(scale) > 20.0 * abs(second_min):
                print(f"Warning: Unusable data at index {i}, temperature {t} K — "
                      f"scale ({scale:.4e}) is more than 20x smaller than second minimum "
                      f"({second_min:.4e}). All labels set to -1.")
                labels[i] = -1.0
                continue

            d = (raw / scale).reshape(-1, 1)

            gmm = GaussianMixture(n_components=2, random_state=0, covariance_type='full', reg_covar=1e-8)
            gmm.fit(d)
            gmm_labels = gmm.predict(d).astype(int)
            gmm_means = gmm.means_.flatten() * scale

            km = KMeans(n_clusters=2, random_state=0, n_init=10)
            km.fit(d)
            km_labels = km.labels_.astype(int)
            km_means = km.cluster_centers_.flatten() * scale

            # Canonicalize both models: label 0 = higher mean level.
            if np.argmax(km_means) != 0:
                km_labels = 1 - km_labels
                km_means = km_means[::-1].copy()

            if np.argmax(gmm_means) != 0:
                gmm_labels = 1 - gmm_labels
                gmm_means = gmm_means[::-1].copy()

            if model_key == 'gmm':
                lbl = gmm_labels
            elif model_key == 'kmeans':
                lbl = km_labels
            else:
                # Hybrid keeps only agreement points; disagreement points are dropped.
                lbl = np.full_like(km_labels, -1)
                agree = (gmm_labels == km_labels)
                lbl[agree] = km_labels[agree]

            labels[i] = lbl
            for k in range(2):
                sel = raw[lbl == k]
                means[i, k] = np.mean(sel) if sel.size > 0 else np.nan
                stds[i, k] = np.std(sel) if sel.size > 0 else np.nan

            if np.all(np.isfinite(means[i])) and means[i, 0] < means[i, 1]:
                means[i] = means[i][::-1]
                stds[i] = stds[i][::-1]
                if model_key == 'hybrid':
                    valid = labels[i] >= 0
                    labels[i, valid] = 1 - labels[i, valid]
                else:
                    labels[i] = 1 - labels[i]

        if interactivePlot:
            if model_key != 'hybrid':
                print("Interactive view is only supported for model='hybrid'.")
            else:
                fig, axes = plt.subplots(nrows=3, figsize=(10, 8), sharex=True, sharey='col')
                axes[-1].set_xlabel('Time (s)', fontsize=10)
                current = [0]

                def _safe_ylim(values, pad_frac=0.1):
                    finite_vals = np.asarray(values, dtype=float)
                    finite_vals = finite_vals[np.isfinite(finite_vals)]
                    if finite_vals.size == 0:
                        return (-1.0, 1.0)

                    y_min = float(np.min(finite_vals))
                    y_max = float(np.max(finite_vals))
                    if y_min == y_max:
                        pad = max(abs(y_min) * pad_frac, 1e-12)
                    else:
                        pad = (y_max - y_min) * pad_frac
                    return (y_min - pad, y_max + pad)

                def update_cluster_plot(idx):
                    t = self.dataTemps[idx]

                    if dataType=='emission':
                        ts = np.asarray(self.dataValues[t]['timeStampImps'])
                        data = np.asarray(self.dataValues[t]['ImpedanceIm'])
                    if dataType=='excitation':
                        ts = np.asarray(self.dataValues[t]["timeStampDemods"])
                        data = np.asarray(self.dataValues[t]["AuxInput1"])

                    data_ylim = _safe_ylim(data)

                    scale_local = np.min(data)
                    sorted_imp = np.sort(data)
                    second_min_local = sorted_imp[1] if len(sorted_imp) > 1 else scale_local
                    if abs(second_min_local) > 0 and abs(scale_local) > 20.0 * abs(second_min_local):
                        for ax in axes:
                            ax.cla()
                            ax.text(0.5, 0.5, 'UNUSABLE DATA', transform=ax.transAxes,
                                    ha='center', va='center', fontsize=14, color='red')
                        fig.suptitle(f'i = {idx}  /  T = {t} K  [UNUSABLE — scale outlier]', fontsize=11)
                        fig.canvas.draw_idle()
                        return
                    d_local = (data / scale_local).reshape(-1, 1)

                    gmm_local = GaussianMixture(n_components=2, random_state=0, covariance_type='full', reg_covar=1e-8)
                    gmm_local.fit(d_local)
                    gmm_lbl = gmm_local.predict(d_local).astype(int)
                    gmm_means_local = gmm_local.means_.flatten() * scale_local

                    km_local = KMeans(n_clusters=2, random_state=0, n_init=10)
                    km_local.fit(d_local)
                    km_lbl = km_local.labels_.astype(int)
                    km_means_local = km_local.cluster_centers_.flatten() * scale_local

                    if np.argmax(km_means_local) != 0:
                        km_lbl = 1 - km_lbl
                    if np.argmax(gmm_means_local) != 0:
                        gmm_lbl = 1 - gmm_lbl

                    keep = (gmm_lbl == km_lbl)
                    hyb_lbl = np.full_like(km_lbl, -1)
                    hyb_lbl[keep] = km_lbl[keep]

                    axes[0].cla()
                    axes[0].scatter(ts, data, c=km_lbl, cmap='coolwarm', s=4, vmin=0, vmax=1)
                    axes[0].set_ylabel('K-Means', fontsize=10)

                    axes[1].cla()
                    axes[1].scatter(ts, data, c=gmm_lbl, cmap='coolwarm', s=4, vmin=0, vmax=1)
                    axes[1].set_ylabel('GMM', fontsize=10)

                    axes[2].cla()
                    axes[2].scatter(ts[keep], data[keep], c=hyb_lbl[keep], cmap='coolwarm', s=4, vmin=0, vmax=1)
                    axes[2].set_ylabel('Hybrid', fontsize=10)
                    axes[-1].set_xlabel('Time (s)', fontsize=10)

                    for row in range(3):
                        axes[row].set_ylim(data_ylim)

                    fig.suptitle(f'i = {idx}  /  T = {t} K    (left/right to navigate)', fontsize=11)
                    fig.canvas.draw_idle()

                def on_key(event):
                    if event.key == 'right':
                        current[0] = (current[0] + 1) % len(self.dataTemps)
                    elif event.key == 'left':
                        current[0] = (current[0] - 1) % len(self.dataTemps)
                    else:
                        return
                    update_cluster_plot(current[0])

                fig.canvas.mpl_connect('key_press_event', on_key)
                update_cluster_plot(current[0])
                plt.tight_layout()
                plt.show()

        return means, stds, labels

    # This is a caller function. It calls findDataLevelsScikit for finding data classes/levels
    def findDataLevels(self, dataType = 'excitation', algorithm='gmm', recalculate=True, interactivePlot=False):
        alg_key = str(algorithm).strip().lower()
        if not recalculate: 
            if dataType == 'excitation':
                if self.dataExcitationLevelParams is not None:
                    m = self.dataExcitationLevelParams['means']
                    c = self.dataExcitationLevelParams['stds']
                    l = self.dataExcitationLevelParams['labels']
                if self.dataExcitationLevelParams is None:
                    print("No stored data levels found. Recalculating...")
                    recalculate = True
            if dataType == 'emission':
                if self.dataEmissionLevelParams is not None:
                    m = self.dataEmissionLevelParams['means']
                    c = self.dataEmissionLevelParams['stds']
                    l = self.dataEmissionLevelParams['labels']
                if self.dataEmissionLevelParams is None:
                    print("No stored data levels found. Recalculating...")
                    recalculate = True
            if not dataType == 'excitation' and not dataType == 'emission':
                print("Invalid data type. Must be 'excitation' or 'emission'.")
                return -1

        if recalculate:
            if alg_key in ('gmm', 'gaussianmixture'):
                m, c, l = self.findDataLevelsScikit(dataType=dataType, model='gmm', interactivePlot=interactivePlot)
            elif alg_key in ('kmeans',):
                m, c, l = self.findDataLevelsScikit(dataType=dataType, model='kmeans', interactivePlot=interactivePlot)
            elif alg_key in ('hybrid', 'gmmkmeans', 'kmeansgmm'):
                m, c, l = self.findDataLevelsScikit(dataType=dataType, model='hybrid', interactivePlot=interactivePlot)
            else:
                raise ValueError(
                    "Unknown algorithm: " + str(algorithm) +
                    ". Valid options are: 'gmm', 'kmeans', 'hybrid'."
                )
            if dataType == "excitation":
                self.dataExcitationLevelParams = dict()
                self.dataExcitationLevelParams.update({'means':m, 'stds':c, 'labels':l})
            elif dataType == "emission":
                self.dataEmissionLevelParams = dict()
                self.dataEmissionLevelParams.update({'means':m, 'stds':c, 'labels':l})
        return m, c, l

    @staticmethod
    def find_nearest(array, value):
        array = np.asarray(array)
        idx = (np.abs(array - value)).argmin()
        return idx

    @staticmethod
    def find_signal_blocks(arr, val):
        def get_blocks_for_target(target):
            modified = list(arr)
            n = len(modified)

            # Step 1: Convert -1s into the target value if they bridge two target blocks
            i = 0
            while i < n:
                if modified[i] == -1:
                    start = i
                    while i < n and modified[i] == -1:
                        i += 1
                    end = i - 1

                    # Check immediate neighbors of the -1 block
                    left_neighbor = modified[start - 1] if start > 0 else None
                    right_neighbor = modified[end + 1] if end < n - 1 else None

                    # Bridge if trapped strictly between two blocks of the target value
                    if left_neighbor == target and right_neighbor == target:
                        for k in range(start, end + 1):
                            modified[k] = target
                else:
                    i += 1

            # Step 2: Extract the start and end indices of the consolidated target blocks
            blocks = []
            i = 0
            while i < n:
                if modified[i] == target:
                    start = i
                    while i < n and modified[i] == target:
                        i += 1
                    blocks.append((start, i - 1))
                else:
                    i += 1
            return blocks

        return get_blocks_for_target(val)

    def excitationClusters(self, recalculate=False):
        if not recalculate:
            if self.dataExcitationClusterParams is None:
                print("No stored data clusters found. Recalculating...")
                recalculate = True
        if recalculate:
            self.dataExcitationClusterParams = dict()
            m, c, l = self.findDataLevels(dataType="excitation", algorithm="hybrid", recalculate=False ,interactivePlot=False)
            blocks = dict()
            clusterSizesFreqs = dict()
            for i in range(len(self.dataTemps)):
                blocks[self.dataTemps[i]] = dict()
                high = self.find_signal_blocks(l[i],0)
                low = self.find_signal_blocks(l[i],1)

                blocks[self.dataTemps[i]]["high"] = dict()
                blocks[self.dataTemps[i]]["low"] = dict()

                # 1. Identify the high and low clusters, i.e. excitation and emission sections
                # 2. Sort the clusters by length for later alignment work
                # -------------------------------------------------------------------------------
                clusterSizesFreqs[self.dataTemps[i]] = dict()
                freqHighLengths = dict()
                for h1, h2 in enumerate(high):
                    val = list(h2)
                    val.append(val[1]-val[0])
                    blocks[self.dataTemps[i]]["high"][h1] = val
                    if not val[1]-val[0] in freqHighLengths.keys():
                        freqHighLengths[val[1]-val[0]] = 1
                    else:
                        freqHighLengths[val[1]-val[0]] += 1
                # freqHighLengths.popitem()
                highFreqs = np.array([int(key) for key in freqHighLengths.keys()])
                highVals = np.array([int(value) for value in freqHighLengths.values()])
                highClusters = np.column_stack((highFreqs, highVals))
                sortedHighClusters = sorted(highClusters, key=lambda x: x[1], reverse=True)
                clusterSizesFreqs[self.dataTemps[i]]['high'] = sortedHighClusters

                freqLowLengths = dict()
                for l1, l2 in enumerate(low):
                    val = list(l2)
                    val.append(val[1]-val[0])
                    blocks[self.dataTemps[i]]["low"][l1] = val
                    if not val[1]-val[0] in freqLowLengths.keys():
                        freqLowLengths[val[1]-val[0]] = 1
                    else:
                        freqLowLengths[val[1]-val[0]] += 1
                freqLowLengths.popitem()
                lowFreqs = np.array([int(key) for key in freqLowLengths.keys()])
                lowVals = np.array([int(value) for value in freqLowLengths.values()])
                lowClusters = np.column_stack((lowFreqs, lowVals))
                sortedLowClusters = sorted(lowClusters, key=lambda x: x[1], reverse=True)
                clusterSizesFreqs[self.dataTemps[i]]['low'] = sortedLowClusters

            self.dataExcitationClusterParams['clusterBlocks'] = blocks
            self.dataExcitationClusterParams['clusterSizesFreqs'] = clusterSizesFreqs

        # return blocks, clusterSizesFreqs
        return 0

    def emissionClusters(self, basis='free', recalculate=False):
        if not recalculate:
            if self.dataEmissionClusterParams is None:
                print("No stored data clusters found. Recalculating...")
                recalculate = True
        if recalculate:
            self.dataEmissionClusterParams = dict()
            if basis=='excitation':
                self.alignExcitationClusters()
                self.dataEmissionClusterParams["clusterBlocks"] = self.dataExcitationClusterParams["clusterBlocks"]
                self.dataEmissionClusterParams["clusterSizesFreqs"] = self.dataExcitationClusterParams["clusterSizesFreqs"]
            if basis=='free':
                m, c, l = self.findDataLevels(dataType="emission", algorithm="hybrid", recalculate=False ,interactivePlot=False)
                blocks = dict()
                clusterSizesFreqs = dict()
                for i in range(len(self.dataTemps)):
                    blocks[self.dataTemps[i]] = dict()
                    high = self.find_signal_blocks(l[i],0)
                    low = self.find_signal_blocks(l[i],1)

                    blocks[self.dataTemps[i]]["high"] = dict()
                    blocks[self.dataTemps[i]]["low"] = dict()

                    clusterSizesFreqs[self.dataTemps[i]] = dict()
                    freqHighLengths = dict()
                    for h1, h2 in enumerate(high):
                        val = list(h2)
                        val.append(val[1] - val[0])
                        blocks[self.dataTemps[i]]["high"][h1] = val
                        if not val[1] - val[0] in freqHighLengths.keys():
                            freqHighLengths[val[1] - val[0]] = 1
                        else:
                            freqHighLengths[val[1] - val[0]] += 1
                    # freqHighLengths.popitem()
                    highFreqs = np.array([int(key) for key in freqHighLengths.keys()])
                    highVals = np.array([int(value) for value in freqHighLengths.values()])
                    highClusters = np.column_stack((highFreqs, highVals))
                    sortedHighClusters = sorted(highClusters, key=lambda x: x[1], reverse=True)
                    clusterSizesFreqs[self.dataTemps[i]]["high"] = sortedHighClusters

                    freqLowLengths = dict()
                    for l1, l2 in enumerate(low):
                        val = list(l2)
                        val.append(val[1] - val[0])
                        blocks[self.dataTemps[i]]["low"][l1] = val
                        if not val[1] - val[0] in freqLowLengths.keys():
                            freqLowLengths[val[1] - val[0]] = 1
                        else:
                            freqLowLengths[val[1] - val[0]] += 1
                    freqLowLengths.popitem()
                    lowFreqs = np.array([int(key) for key in freqLowLengths.keys()])
                    lowVals = np.array([int(value) for value in freqLowLengths.values()])
                    lowClusters = np.column_stack((lowFreqs, lowVals))
                    sortedLowClusters = sorted(lowClusters, key=lambda x: x[1], reverse=True)
                    clusterSizesFreqs[self.dataTemps[i]]["low"] = sortedLowClusters
            self.dataEmissionClusterParams["clusterBlocks"] = blocks
            self.dataEmissionClusterParams["clusterSizesFreqs"] = clusterSizesFreqs
        return 0

    def alignClusters(self, dataType='excitation', recalculate=False):
        if not recalculate:
            if dataType == 'excitation':
                if self.dataExcitationLevelParams is None or self.dataExcitationClusterParams is None:
                    print("No stored data clusters found. Recalculating...")
                    recalculate = True
            if dataType == 'emission':
                if self.dataEmissionClusterParams is None:
                    print("No stored data clusters found. Recalculating...")
                    recalculate = True
            if not dataType == 'excitation' and not dataType == 'emission':
                print("Invalid data type. Must be 'excitation' or 'emission'.")
                return -1
        if recalculate:
            if not dataType == 'excitation' and not dataType == 'emission':
                print("Invalid data type. Must be 'excitation' or 'emission'.")
                return -1
            else:
                if dataType == 'excitation':
                    self.excitationClusters()
                if dataType == 'emission':
                    self.emissionClusters()

                for i in range(len(self.dataTemps)):
                    T = self.dataTemps[i]
                    if dataType == 'excitation':
                        high = np.asarray(self.dataExcitationClusterParams['clusterSizesFreqs'][T]['high'])
                        low = np.asarray(self.dataExcitationClusterParams["clusterSizesFreqs"][T]["low"])
                    elif dataType == 'emission':
                        high = np.asarray(self.dataEmissionClusterParams['clusterSizesFreqs'][T]['high'])
                        low = np.asarray(self.dataEmissionClusterParams["clusterSizesFreqs"][T]["low"])
                    commonLengthHigh = np.min(high[:,0])
                    commonLengthLow = np.min(low[:,0])

                    if dataType == 'excitation':
                        for j in range(len(self.dataExcitationClusterParams["clusterBlocks"][T]["high"])):
                            trim = self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][-1] - commonLengthHigh
                            if trim > 0:
                                self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][1] -= trim
                                self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][-1] -= trim

                        for j in range(len(self.dataExcitationClusterParams["clusterBlocks"][T]["low"])):
                            trim = self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1] - commonLengthLow
                            if trim > 0:
                                self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][1] -= trim
                                self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1] -= trim
                    if dataType == 'emission':
                        for j in range(len(self.dataEmissionClusterParams["clusterBlocks"][T]["high"])):
                            trim = self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1] - commonLengthHigh
                            if trim > 0:
                                self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][1] -= trim
                                self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1] -= trim

                        for j in range(len(self.dataEmissionClusterParams["clusterBlocks"][T]["low"])):
                            trim = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1] - commonLengthLow
                            if trim > 0:
                                self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][1] -= trim
                                self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1] -= trim
        return 0



    # def emissionClusters(self):
    #     return

    def sampleEmissions(self, algorithm='gmm', interactivePlot=False,
                        assignDataEmissions=False, useStoredEmissions=False):


        return 0

    def calculateDelCNormalized(self, t1=0.003, t2=0.203, emissionIndex=0, plot=False):
        if self.dataClusterIndices is None:
            self.sampleEmissions()

        # If emission index is -1 average over all emissions
        # If emission index is larger than existing indices go use the last one
        # If emission index is anything else use it as it is
        tauEmissions = np.zeros(len(self.dataTemps))
        delCNormalized = np.zeros(len(self.dataTemps))
        if emissionIndex >= 0:
            if emissionIndex > len(self.dataClusterIndices[self.dataTemps[0]]) - 1:
                emissionIndex = len(self.dataClusterIndices[self.dataTemps[0]]) - 1
            for i in range(len(self.dataTemps)):
                t = self.dataEmissions[self.dataTemps[i]][emissionIndex][:,0]
                t = t-t[0]

                C = self.dataEmissions[self.dataTemps[i]][emissionIndex][:,1]
                # # Model C values using smoothing cubic spline
                # C_spline = make_smoothing_spline(t, C)
                # Cinf = C_spline(t[-1])
                Cinf = C[-1]
                C = C/Cinf
                
                # Tau emission calculation
                x1 = t[self.find_nearest(t, t1)]
                x2 = t[self.find_nearest(t, t2)]
                tauEmissions[i] = (x2-x1)/np.log(x2/x1)

                # Normalized delta C calculation
                delCNormalized[i] = C[self.find_nearest(t, t2)]-C[self.find_nearest(t, t1)]
        else:
            print("averaging all emissions")
            for i in range(len(self.dataTemps)):
                tempTauEmissions = np.zeros(len(self.dataClusterIndices[self.dataTemps[i]]))
                tempDelCNormalized = np.zeros(len(self.dataClusterIndices[self.dataTemps[i]]))
                for j in range(len(self.dataClusterIndices[self.dataTemps[i]])):
                    t = self.dataEmissions[self.dataTemps[i]][j][:,0]
                    t = t-t[0]

                    C = self.dataEmissions[self.dataTemps[i]][j][:,1]
                    # # Model C values using smoothing cubic spline
                    # C_spline = make_smoothing_spline(t, C)
                    # Cinf = C_spline(t[-1])
                    Cinf = C[-1]
                    C = C/Cinf

                    # Tau emission calculation
                    x1 = t[self.find_nearest(t, t1)]
                    x2 = t[self.find_nearest(t, t2)]
                    tempTauEmissions[j] = (x2-x1)/np.log(x2/x1)

                    # Normalized delta C calculation
                    tempDelCNormalized[j] = C[self.find_nearest(t, t2)]-C[self.find_nearest(t, t1)]
                tauEmissions[i] = np.mean(tempTauEmissions)
                delCNormalized[i] = np.mean(tempDelCNormalized)

        if plot:
            fig, ax1 = plt.subplots()
            temps = np.array(self.dataTemps)
            ax1.plot(temps-273, delCNormalized,'.')
            ax1.set_xlabel("Temperature (C)")
            ax1.set_ylabel("Normalized Delta C")
            ax1.set_title("Normalized Delta C vs Temperature")
            ax1.tick_params(axis="x", labelcolor="blue")

            ax2 = ax1.twiny()
            ax2.plot(temps, delCNormalized, ".")
            ax2.set_xlabel("Temperature (K)")
            ax2.tick_params(axis="x", labelcolor="red")

            plt.show()
        return 0

    def test(self, t1=0.003, t2=0.203, emissionIndex=0, plot=False):
        self.calculateDelCNormalized(t1, t2, emissionIndex, plot)
        return 0





    # def calculateDeltaCapacitanceT1T2(self, t1, t2, plot=False):
    #     emiss, _ = self.sampleEmissions()
    #     allPairs = np.array(list(itertools.product(t1,t2)))
    #     delTs = allPairs[allPairs[:,0] < allPairs[:,1]]
    #
    #     delC = np.zeros((len(self.dataTemps),len(delTs)+1))
    #     errC = np.zeros((len(self.dataTemps),len(delTs)+1))
    #     for i in range(len(self.dataTemps)):
    #         t = self.dataTemps[i]
    #         groups = emiss.get(t, {})
    #         if len(groups) == 0:
    #             raise ValueError(f"No selected data groups found for temperature {t} K.")
    #
    #         # Prefer the longest group for downstream delta-C calculations.
    #         best_key = max(groups, key=lambda k: groups[k].shape[0])
    #         data_xy = groups[best_key]
    #         x = data_xy[:, 0]
    #         y = data_xy[:, 1]
    #         err = np.full_like(y, np.std(y) if y.size > 0 else 0.0, dtype=float)
    #         yCS = CubicSpline(x, y, bc_type='natural')
    #         errCS = CubicSpline(x, err, bc_type='natural')
    #
    #         delC[i,0] = t
    #         errC[i,0] = t
    #         for j in range(len(delTs)):
    #             p0 = yCS(delTs[j,0])
    #             e0 = np.abs(errCS(delTs[j,0]))
    #             p1 = yCS(delTs[j,1])
    #             e1 = np.abs(errCS(delTs[j,1]))
    #
    #             delC[i, j + 1] = p1-p0
    #             errC[i, j + 1] = np.sqrt(e1*e1+e0*e0)
    #     for i in range(1,len(delTs)+1):
    #         errC[errC[:,i]==np.max(errC[:,i]),i]=0
    #
    #     # ADD ERRORS!!!
    #
    #     if plot:
    #         fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=len(delTs)//2, sharex=True, sharey=True)
    #         for i in range(len(delTs)//2):
    #             lbl0 = 't2=' + str(int(delTs[2*i,1]*1000)) + 'ms - t1=' + \
    #                 str(int(delTs[2*i,0]*1000)) + 'ms'
    #             lbl1 = 't2=' + str(int(delTs[2*i+1,1]*1000)) + 'ms - t1=' + \
    #                 str(int(delTs[2*i+1,0]*1000)) + 'ms'
    #
    #             c0 = 1 # This needs to be corrected for C(steady-state) value
    #             e0 = 1  # This needs to be corrected for C(steady-state) value
    #             ax[i,0].plot(delC[:,0], delC[:,2*i+1]/c0,'-',color='blue',linewidth=1)
    #             ax[i,0].errorbar(delC[:,0], delC[:,2*i+1]/c0,
    #                              yerr=errC[:,2*i+1]/e0, label=lbl0, fmt='o', color='r',
    #                              markersize=3, ecolor='cyan', elinewidth=1)
    #             ax[i,0].legend(fontsize=12)
    #             ax[i,0].tick_params(axis='x', labelsize=18)
    #             ax[i,0].tick_params(axis='y', labelsize=18)
    #             ax[i,0].set_ylim([-0.01*np.min(delC[:,2*i+1]/c0),
    #                               2.0*np.max(delC[:,2*i+1]/c0)])
    #             # ax[i,0].set_ylim([0.0,1.05])
    #             # ax[i,0].set_yticks([0.5])
    #             ax[i,0].set_xticks([50-23, 100-23, 150-23, 200-23],
    #                                labels=[str(50+200), str(100+200), str(150+200), str(200+200)])
    #
    #             c1 = 1 # This needs to be corrected for C(steady-state) value
    #             e1 = 1  # This needs to be corrected for C(steady-state) value
    #             ax[i,1].plot(delC[:,0], delC[:,2*i+2]/c1,'-',color='blue',linewidth=1)
    #             ax[i,1].errorbar(delC[:,0], delC[:,2*i+2]/c1,
    #                              yerr=errC[:,2*i+2]/e1, label=lbl1, fmt='o', color='r',
    #                              markersize=3, ecolor='cyan', elinewidth=1)
    #             ax[i,1].legend(fontsize=12)
    #             ax[i,1].tick_params(axis='x', labelsize=18)
    #             ax[i,1].tick_params(axis='y', labelsize=18)
    #             ax[i,1].set_ylim([-0.01*np.min(delC[:,2*i+2]/c1),
    #                               2.0*np.max(delC[:,2*i+2]/c1)])
    #             # ax[i,1].set_ylim([0.0,1.05])
    #             # ax[i,1].set_yticks([0.5])
    #             ax[i,1].set_xticks([50-23, 100-23, 150-23, 200-23],
    #                                labels=[str(50+200), str(100+200), str(150+200), str(200+200)])
    #
    #         fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
    #         fig.supylabel(r'$\delta C$/C', fontsize=18)
    #         fig.subplots_adjust(top=0.975, bottom=0.090,
    #                             left=0.070, right=0.990,
    #                             wspace=0.000, hspace=0.0)
    #
    #         plt.show()
    #
    #     return delC, errC, delTs
    #
    # # This fit function uses PDF estimate of the data and fit via mixture models.
    # @staticmethod
    # def fitDeltaCapacitanceVsTemperatureFitToMixtures(xx, yy, err, nComponents=2,
    #                                                   nDrawnPoints=10000, mixtureType='lognormal',
    #                                                   plot=True):
    #     x = np.array(xx, dtype=float)
    #     y = np.array(yy, dtype=float)
    #     err = np.array(err, dtype=float)
    #
    #     mixtureType = mixtureType.strip().lower()
    #     if mixtureType not in ('gaussian', 'lognormal'):
    #         raise ValueError("mixtureType must be 'gaussian' or 'lognormal', got: " + str(mixtureType))
    #
    #     # Reflect the y graph around x = x[-1] (horizontal mirror of the curve)
    #     # so that y at mirrored x[0] position equals y[0]
    #     xMirror = 2.0 * x[-1] - x[-2::-1]  # mirror x about x[-1], excluding pivot
    #     yMirror = y[-2::-1]                   # reverse y values (y at x[0] maps to far end)
    #     errMirror = err[-2::-1]               # mirror errors (symmetric)
    #     xOrig = np.array(x, copy=True)        # save original x range for reflecting back
    #
    #     # Use only reflected y for calculation (do not merge with original)
    #     # Normalize reflected y to create a PDF (area under curve = 1)
    #     spl = make_smoothing_spline(xMirror, yMirror)
    #     area, _ = quad(lambda val: float(spl(val)), xMirror[0], xMirror[-1])
    #     yNorm = yMirror / area
    #
    #     # Build normalized spline for sampling
    #     splNorm = make_smoothing_spline(xMirror, yNorm)
    #
    #     # Draw points from the PDF using inverse CDF sampling
    #     xFine = np.linspace(xMirror[0], xMirror[-1], nDrawnPoints)
    #     pdfFine = splNorm(xFine)
    #     pdfFine = np.maximum(pdfFine, 0)
    #     cdf = np.cumsum(pdfFine)
    #     cdf = cdf / cdf[-1]
    #     u = np.random.uniform(0, 1, nDrawnPoints)
    #     samples = np.interp(u, cdf, xFine)
    #
    #     # Fit mixture model to the drawn samples (in reflected space)
    #     torch.manual_seed(0)
    #     data_tensor = torch.tensor(samples.reshape(-1, 1), dtype=torch.float32)
    #
    #     sample_mean = float(np.mean(samples))
    #     sample_var = float(np.var(samples))
    #     dists = []
    #     for k in range(nComponents):
    #         if mixtureType == 'lognormal':
    #             log_samples = np.log(np.maximum(samples, 1e-12))
    #             log_mean = float(np.mean(log_samples))
    #             log_var = float(np.var(log_samples))
    #             d = LogNormal(
    #                 means=torch.tensor([log_mean + (k - nComponents / 2.0) * 0.5], dtype=torch.float32),
    #                 covs=torch.tensor([[log_var]], dtype=torch.float32),
    #             )
    #         else:  # gaussian
    #             d = Normal(
    #                 means=torch.tensor([sample_mean + (k - nComponents / 2.0) * 0.5 * np.sqrt(sample_var)], dtype=torch.float32),
    #                 covs=torch.tensor([[sample_var]], dtype=torch.float32),
    #             )
    #         dists.append(d)
    #     model = GeneralMixtureModel(dists)
    #     model.fit(data_tensor)
    #
    #     # Extract fit parameters
    #     gmm_means = [model.distributions[j].means.detach().numpy().flatten()[0] for j in range(nComponents)]
    #     gmm_covs = [model.distributions[j].covs.detach().numpy().flatten()[0] for j in range(nComponents)]
    #     gmm_weights = model.priors.detach().numpy().flatten()
    #
    #     # Build mixture PDF on reflected x range
    #     xPlot = np.linspace(xMirror[0], xMirror[-1], 1000)
    #     mixPdf = np.zeros_like(xPlot)
    #     for j in range(nComponents):
    #         mu = gmm_means[j]
    #         sigma2 = gmm_covs[j]
    #         sigma = np.sqrt(sigma2)
    #         if mixtureType == 'lognormal':
    #             mixPdf += gmm_weights[j] * (1.0 / (xPlot * sigma * np.sqrt(2 * np.pi))) * \
    #                 np.exp(-0.5 * (np.log(xPlot) - mu)**2 / sigma2)
    #         else:  # gaussian
    #             mixPdf += gmm_weights[j] * (1.0 / (sigma * np.sqrt(2 * np.pi))) * \
    #                 np.exp(-0.5 * (xPlot - mu)**2 / sigma2)
    #     mixPdf = np.nan_to_num(mixPdf, nan=0.0, posinf=0.0, neginf=0.0)
    #
    #     # Reflect back: map mirrored x back to original x range
    #     xOrigMax = xOrig[-1]
    #     xReflectedBack = 2.0 * xOrigMax - xMirror
    #     yReflectedBack = yMirror
    #
    #     # Reflect samples back
    #     samplesBack = 2.0 * xOrigMax - samples
    #
    #     # Reflect fit curve back
    #     xPlotBack = 2.0 * xOrigMax - xPlot
    #     mixPdfBack = mixPdf
    #     sortIdx = np.argsort(xPlotBack)
    #     xPlotBack = xPlotBack[sortIdx]
    #     mixPdfBack = mixPdfBack[sortIdx]
    #
    #     # Plot reflected-back y, histogram of reflected-back samples, and mixture fit overlaid
    #     if plot:
    #         fitLabel = mixtureType.capitalize() + ' mixture fit (reflected back)'
    #         fig, ax = plt.subplots(figsize=(10, 6))
    #         ax.plot(xReflectedBack, yReflectedBack, 'ro-', markersize=4, label='Reflected-back y')
    #         ax2 = ax.twinx()
    #         ax2.hist(samplesBack, bins=50, density=True, alpha=0.4, color='gray', label='Drawn samples (reflected back)')
    #         ax2.plot(xPlotBack, mixPdfBack, 'b-', linewidth=2, label=fitLabel)
    #         ax.set_xlabel('Temperature', fontsize=14)
    #         ax.set_ylabel('Delta Capacitance', fontsize=14)
    #         ax2.set_ylabel('Probability Density', fontsize=14)
    #         lines1, labels1 = ax.get_legend_handles_labels()
    #         lines2, labels2 = ax2.get_legend_handles_labels()
    #         ax.legend(lines1 + lines2, labels1 + labels2, fontsize=12)
    #         ax.set_title('Reflected-back y and ' + str(nComponents) + '-component ' + mixtureType.capitalize() + ' mixture fit', fontsize=14)
    #         plt.tight_layout()
    #         plt.show()
    #
    #     def spline_fit_func(temp):
    #         return spl(2.0 * xOrigMax - temp)
    #
    #     def mixture_fit_func(temp):
    #         tPlot = 2.0 * xOrigMax - np.array(temp, dtype=float)
    #         mixPdf = np.zeros_like(tPlot, dtype=float)
    #         for j in range(nComponents):
    #             mu = gmm_means[j]
    #             sigma2 = gmm_covs[j]
    #             sigma = np.sqrt(sigma2)
    #             if mixtureType == 'lognormal':
    #                 valid = tPlot > 0
    #                 if np.any(valid):
    #                     mixPdf[valid] += gmm_weights[j] * (1.0 / (tPlot[valid] * sigma * np.sqrt(2 * np.pi))) * \
    #                         np.exp(-0.5 * (np.log(tPlot[valid]) - mu)**2 / sigma2)
    #             else:  # gaussian
    #                 mixPdf += gmm_weights[j] * (1.0 / (sigma * np.sqrt(2 * np.pi))) * \
    #                     np.exp(-0.5 * (tPlot - mu)**2 / sigma2)
    #         mixPdf = np.nan_to_num(mixPdf, nan=0.0, posinf=0.0, neginf=0.0)
    #         return mixPdf * area
    #
    #     return model, spline_fit_func, mixture_fit_func, samples, samplesBack, gmm_means, gmm_covs, gmm_weights
    #
    # # This fit function uses non-linear least squares to fit a mixture model to the data.
    # @staticmethod
    # def fitDeltaCapacitanceVsTemperatureFitToFunctions(xx, yy, err, nComponents=[2,3],
    #                                                    mixtureType='lognormal', plot=True):
    #     x = np.array(xx, dtype=float)
    #     y = np.array(yy, dtype=float)
    #     err = np.array(err, dtype=float)
    #
    #     mixtureType = mixtureType.strip().lower()
    #     # Validate mixtureType
    #     if mixtureType not in ('gaussian', 'lognormal'):
    #         print(f"Warning: mixtureType must be 'gaussian' or 'lognormal'. Defaulting to 'lognormal'.")
    #         mixtureType = 'lognormal'
    #
    #     # Reflect the data across the vertical line x = x[-1] (horizontal reflection)
    #     xMirror = 2.0 * x[-1] - x[-2::-1]  # mirror x about x[-1], excluding pivot
    #     yMirror = y[-2::-1]                   # reverse y values to match mirrored x
    #     errMirror = err[-2::-1]               # mirror errors
    #
    #     # Use only reflected data
    #     xFull = xMirror
    #     yFull = yMirror
    #     errFull = errMirror
    #
    #     # Fit a smoothing cubic spline to the reflected data
    #     spl = make_smoothing_spline(xFull, yFull)
    #
    #     # Plotting preparation
    #     xPlot = np.linspace(xFull[0], xFull[-1], 1000)
    #     yPlot_spline = spl(xPlot)
    #
    #     # lmfit iterative fitting over nComponents to find the best redchi
    #     if mixtureType == 'gaussian':
    #         CompModel = GaussianModel
    #     else:
    #         CompModel = LognormalModel
    #
    #     best_result = None
    #     best_redchi = np.inf
    #     best_n = 0
    #
    #     for n in range(nComponents[0], nComponents[1] + 1):
    #         model = None
    #         for i in range(1, n + 1):
    #             prefix = f'c{i}_'
    #             if model is None:
    #                 model = CompModel(prefix=prefix)
    #             else:
    #                 model += CompModel(prefix=prefix)
    #
    #         params = model.make_params()
    #
    #         # Initial guesses based on dividing the x range
    #         x_range = xFull[-1] - xFull[0]
    #         for i in range(1, n + 1):
    #             prefix = f'c{i}_'
    #             x_target = xFull[0] + (i - 0.5) * (x_range / n)
    #             idx = np.abs(xFull - x_target).argmin()
    #
    #             if mixtureType == 'lognormal':
    #                 params[prefix + 'center'].set(value=np.log(max(xFull[idx], 1e-3)),
    #                                               min=np.log(max(1e-3, np.min(xFull) / 10.0)),
    #                                               max=np.log(np.max(xFull) * 10.0))
    #                 params[prefix + 'amplitude'].set(value=max(yFull[idx] * 10, 1e-3),
    #                                                  min=0,
    #                                                  max=max(yFull) * x_range * 100.0)
    #                 params[prefix + 'sigma'].set(value=0.1, min=0.01, max=5.0)
    #             else:  # gaussian
    #                 params[prefix + 'center'].set(value=xFull[idx],
    #                                               min=xFull[0] - x_range,
    #                                               max=xFull[-1] + x_range)
    #                 params[prefix + 'amplitude'].set(value=max(yFull[idx] * 10, 1e-3),
    #                                                  min=0,
    #                                                  max=max(yFull) * x_range * 100.0)
    #                 params[prefix + 'sigma'].set(value=x_range / (n * 5.0), min=0.01, max=x_range)
    #
    #         # Perform the fit
    #         weights = 1.0 / np.where(errFull > 0, errFull, np.mean(errFull[errFull > 0]) if np.any(errFull > 0) else 1.0)
    #         try:
    #             result_tmp = model.fit(yFull, params, x=xFull, weights=weights)
    #             if np.abs(1-result_tmp.redchi) < np.abs(1.-best_redchi):
    #                 best_redchi = result_tmp.redchi
    #                 best_result = result_tmp
    #                 best_n = n
    #         except Exception as e:
    #             print(f"Fit failed for n={n}: {e}")
    #
    #     if best_result is None:
    #         print("Warning: All fits failed in fitDeltaCapacitanceVsTemperatureFitToFunctions.")
    #         return None, spl, lambda temp: np.zeros_like(temp)
    #
    #     result = best_result
    #     nComponentsBest = best_n
    #     yPlot_lmfit = result.eval(x=xPlot)
    #
    #     # Reflect back: map mirrored data and fits back to original x range
    #     xOrigMax = x[-1]
    #     xBack = 2.0 * xOrigMax - xFull
    #     yBack = yFull
    #     errBack = errFull
    #
    #     xPlotBack = 2.0 * xOrigMax - xPlot
    #     yPlot_spline_back = yPlot_spline
    #     yPlot_lmfit_back = yPlot_lmfit
    #
    #     # Sort for proper line plotting in original space
    #     sortIdxBack = np.argsort(xBack)
    #     xBack = xBack[sortIdxBack]
    #     yBack = yBack[sortIdxBack]
    #     errBack = errBack[sortIdxBack]
    #
    #     sortIdxPlot = np.argsort(xPlotBack)
    #     xPlotBack = xPlotBack[sortIdxPlot]
    #     yPlot_spline_back = yPlot_spline_back[sortIdxPlot]
    #     yPlot_lmfit_back = yPlot_lmfit_back[sortIdxPlot]
    #
    #     # Plot the back-reflected data, spline fit, and lmfit result overlayed
    #     if plot:
    #         fig, ax = plt.subplots(figsize=(10, 6))
    #         ax.errorbar(xBack, yBack, yerr=errBack, fmt='ro', markersize=4,
    #                     ecolor='gray', elinewidth=1, capsize=2, label='Back-Reflected Data')
    #         ax.plot(xPlotBack, yPlot_spline_back, 'b-', linewidth=2, label='Smoothing Spline Fit (Back-Reflected)')
    #         ax.plot(xPlotBack, yPlot_lmfit_back, 'g--', linewidth=2, label=f'{nComponentsBest}-Comp {mixtureType.capitalize()} Fit (Best, lmfit, Back-Reflected)')
    #
    #         ax.set_xlabel('Temperature', fontsize=14)
    #         ax.set_ylabel('Delta Capacitance', fontsize=14)
    #         ax.legend(fontsize=12)
    #         ax.set_title(f'Comparison of Back-Reflected Fits ({mixtureType.capitalize()})', fontsize=14)
    #         plt.tight_layout()
    #         plt.show()
    #
    #     # Define the fit functions that work on the original temperature range (back-reflected)
    #     def spline_fit_func(temp):
    #         return spl(2.0 * xOrigMax - temp)
    #
    #     def lmfit_fit_func(temp):
    #         return result.eval(x=2.0 * xOrigMax - temp)
    #
    #     return result, spline_fit_func, lmfit_fit_func
    #
    # def findDeltaCapacitanceMaxima(self,delCx, delCy, delCErr, nComponents=[2,3],
    #                                mixtureType='lognormal', plot=True, fitMethod='lmfit'):
    #     result = []
    #     csModel = []
    #     lmModel = []
    #     for i in range(delCy.shape[1]):
    #         xx = np.array(delCx, copy=True)
    #         yy = np.array(delCy[:, i], copy=True)
    #         err = np.array(delCErr[:, i], copy=True)
    #         if fitMethod == 'lmfit':
    #             temp = self.fitDeltaCapacitanceVsTemperatureFitToFunctions(xx, yy, err,
    #                                                                       nComponents, mixtureType,
    #                                                                       plot=plot)
    #         if fitMethod == 'mixtures':
    #             temp = self.fitDeltaCapacitanceVsTemperatureFitToMixtures(xx, yy, err,
    #                                                                       nComponents[0], 10000,
    #                                                                       mixtureType, plot=plot)
    #         result.append(temp[0])
    #         csModel.append(temp[1])
    #         lmModel.append(temp[2])
    #         if result[-1] is not None:
    #             if hasattr(result[-1], 'redchi'):
    #                 print(result[-1].redchi)
    #             else:
    #                 print("Fit completed (mixture model method).")
    #         else:
    #             print("Fit failed for this curve.")
    #     return result, csModel, lmModel


            
            
            
            
            
            

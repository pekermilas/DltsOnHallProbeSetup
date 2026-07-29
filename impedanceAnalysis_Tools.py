# -*- coding: utf-8 -*-
"""
Created on Wed May  6 13:23:08 2026

@author: spencer
"""

import os
import time
import zhinst.core
import zhinst.toolkit as zt
import zhinst.ziPython as zi
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import statsmodels.api as sm

import itertools
import h5py
import statistics
import torch
import lmfit
import pywt
import json

from tkinter.filedialog import askopenfilenames
from numpy.ma.extras import apply_along_axis
from uncertainties import unumpy, ufloat
from sklearn.mixture import GaussianMixture
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA, FastICA
from scipy.stats import weibull_min, mode
from scipy.integrate import quad
from scipy.signal import savgol_filter
from scipy.interpolate import UnivariateSpline
from scipy.interpolate import CubicSpline
from scipy.optimize import differential_evolution
from lmfit.models import LognormalModel, GaussianModel
from fastlowess import Lowess

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
        self.dataEmissions = None
        self.dataParams = None

    @staticmethod
    def _normalize_file_selection(file_selection):
        if file_selection is None:
            return []
        if isinstance(file_selection, str):
            return [file_selection]
        return list(file_selection)

    @staticmethod
    def _extract_txt_temperature(file_path):
        basename = os.path.basename(file_path)
        idx = basename.find('.')
        if idx <= 1:
            return None

        t0 = '+' if basename[0] == 'p' else '-'
        t = basename[1:idx].replace('p', '.')
        t = t0 + t
        if not t.strip():
            return None
        return int(float(t)) + 273

    @staticmethod
    def _extract_csv_temperature(data_name):
        stopIdx = data_name.find('C_')
        if stopIdx <= 0:
            return None

        if data_name[0] == 'p':
            t0 = '+'
            t = data_name[1:stopIdx]
            t = t0 + t
        elif data_name[0] == 'n':
            t0 = '-'
            t = data_name[1:stopIdx]
            t = t0 + t
        else:
            t = data_name[:stopIdx]

        if not t.strip():
            return None
        return int(float(t)) + 273

    @staticmethod
    def _merge_nested_dict(existing, incoming, concatenate_arrays=False):
        if existing is None:
            return incoming
        if not isinstance(existing, dict) or not isinstance(incoming, dict):
            return incoming

        merged = dict(existing)
        for key, value in incoming.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = impdData._merge_nested_dict(
                    merged[key],
                    value,
                    concatenate_arrays=concatenate_arrays,
                )
            elif concatenate_arrays and key in merged and isinstance(merged[key], np.ndarray) and isinstance(value, np.ndarray):
                merged[key] = np.concatenate((merged[key], value))
            elif concatenate_arrays and key in merged and isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = merged[key] + value
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _append_records(existing_records, new_records):
        if existing_records is None:
            return new_records

        merged = dict(existing_records)
        for temp, record in new_records.items():
            if temp in merged:
                merged[temp] = impdData._merge_nested_dict(merged[temp], record, concatenate_arrays=True)
            else:
                merged[temp] = record
        return merged

    @staticmethod
    def _append_unique_temps(existing_temps, new_temps):
        if existing_temps is None:
            return list(new_temps)

        merged = list(existing_temps)
        for temp in new_temps:
            if temp not in merged:
                merged.append(temp)
        return merged

    def readData(self):

        if self.fileName is None:
            self.fileName = askopenfilenames(title="Select a file",
                filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")])

        if isinstance(self.fileName, str):
            self.fileName = [self.fileName]

        # data is a structure of nested dictionaries.
        # First layer of the dictionary has data temperatures as keys.
        # Second layer of the dictionary has data source names (tickStampImps, ImpedanceRe, ImpedanceIm, etc.) as keys.
        # tickStampImps : Impedance time stamps in units of hardware clock ticks
        # tickStampDemods : Demodulator time stamps in units of hardware clock ticks
        # timeStampImps : Impedance time stamps in units of seconds
        # timeStampDemods : Demodulator time stamps in units of seconds
        # ImpedanceRe : Real part of the impedance in units of Ohms
        # ImpedanceIm : Imaginary part of the impedance or Capacitance in units of Farads
        # AuxInput1 : Demodulation signal or Excitation in units of Volts
        # AbsZ : Absolute value of Impedance in units of Ohms

        if self.fileName[0][-3:]=='txt':
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
                self.rootFolder = os.path.dirname(self.fileName[0]) + os.sep

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
                print("Error: Params file does not exist.")
                self.fileName = None
                return -1

        if self.fileName[0][-3:] == 'csv':
            emmHeader = []
            emmSignal = []
            excHeader = []
            excSignal = []
            impHeader = []
            impSignal = []

            for i in range(len(self.fileName)):
                if '_imps_0' in self.fileName[i]:
                    if '_header_' in self.fileName[i]:
                        emmHeader.append(self.fileName[i])
                    else:
                        emmSignal.append(self.fileName[i])
                if '_auxin0_' in self.fileName[i]:
                    if '_header_' in self.fileName[i]:
                        excHeader.append(self.fileName[i])
                    else:
                        excSignal.append(self.fileName[i])
                if '_r_avg_' in self.fileName[i]:
                    if '_header_' in self.fileName[i]:
                        impHeader.append(self.fileName[i])
                    else:
                        impSignal.append(self.fileName[i])

            if len(emmHeader) == 0:
                emmHeader.append(askopenfilenames(title="Select emission header")[0])
            if len(emmSignal) == 0:
                emmSignal.append(askopenfilenames(title="Select emission data")[0])
            if len(excHeader) == 0:
                excHeader.append(askopenfilenames(title="Select excitation header")[0])
            if len(excSignal) == 0:
                excSignal.append(askopenfilenames(title="Select excitation data")[0])

            if len(emmHeader) == 0 or len(emmSignal) == 0 or len(excHeader) == 0 or len(excSignal) == 0:
                print("No valid data files selected (none contained a number in the filename).")
                return -1

            if self.rootFolder is None:
                self.rootFolder = os.path.dirname(self.fileName[0]) + os.sep

            strippedEmmHeader = emmHeader[0].replace(self.rootFolder,"")
            strippedEmmSignal = emmSignal[0].replace(self.rootFolder,"")
            strippedExcHeader = excHeader[0].replace(self.rootFolder,"")
            strippedExcSignal = excSignal[0].replace(self.rootFolder,"")

            header = pd.read_csv(emmHeader[0], sep=';')
            headerKeys = list(header)
            dataNames = header[headerKeys[16]].to_list()
            dataLengths = header[headerKeys[22]].to_numpy()
            dataReps = header[headerKeys[28]].to_numpy()

            if self.dataTemps is None:
                self.dataTemps = []
            for i in range(len(dataNames)):
                stopIdx = dataNames[i].find('C_')
                if dataNames[i][0]=='p':
                    t0 = '+'
                    t = dataNames[i][1:stopIdx]
                    t = t0 + t
                else:
                    if dataNames[i][0]=='n':
                        t0 = '-'
                        t = dataNames[i][1:stopIdx]
                        t = t0 + t
                    else:
                        t = dataNames[i][:stopIdx]
                if t.strip():
                    self.dataTemps.append(int(float(t))+273)
                else:
                    print(f"Warning: Could not extract temperature from filename: {self.fileName[i]}")
            try:
                data = dict()
                signalEmm = pd.read_csv(emmSignal[0], sep=';')
                chunk = signalEmm['chunk'].to_numpy()
                clockTicks = signalEmm['timestamp'].to_numpy()
                impedance = signalEmm['value'].to_numpy()
                for i in range(len(self.dataTemps)):
                    data[self.dataTemps[i]] = dict()
                    data[self.dataTemps[i]]['tickStampImps'] = clockTicks[chunk==i]
                    data[self.dataTemps[i]]['timeStampImps'] = clockTicks[chunk==i]/(60*10**6)
                    data[self.dataTemps[i]]['ImpedanceIm'] = impedance[chunk==i]

                signalExc = pd.read_csv(excSignal[0], sep=';')
                chunk = signalExc['chunk'].to_numpy()
                clockTicks = signalExc['timestamp'].to_numpy()
                auxInput1 = signalExc['value'].to_numpy()
                for i in range(len(self.dataTemps)):
                    data[self.dataTemps[i]]['tickStampDemods'] = clockTicks[chunk==i]
                    data[self.dataTemps[i]]['timeStampDemods'] = clockTicks[chunk==i]/(60*10**6)
                    data[self.dataTemps[i]]['AuxInput1'] = auxInput1[chunk==i]

                if not (len(impHeader) == 0 or len(impSignal) == 0):
                    signalImp = pd.read_csv(impSignal[0], sep=';')
                    chunk = signalImp['chunk'].to_numpy()
                    clockTicks = signalImp['timestamp'].to_numpy()
                    impedanceAbs = signalImp['value'].to_numpy()
                    for i in range(len(self.dataTemps)):
                        data[self.dataTemps[i]]['AbsZ'] = impedanceAbs[chunk == i]
                        # ZSqr = np.asarray(data[self.dataTemps[i]]['AbsZ'])**2
                        # CSqr = np.asarray(data[self.dataTemps[i]]['ImpedanceIm'])**2
                        data[self.dataTemps[i]]['ImpedanceRe'] = np.zeros_like(data[self.dataTemps[i]]['AbsZ'])

                self.dataValues = data
                return 0

            except FileNotFoundError:
                print("Error: Params file does not exist.")
                self.fileName = None
                return -1

    def appendData(self, fName=None):
        # Use a LOCAL variable for the files to append.
        # Never reuse self.fileName here — that still points to whatever readData() loaded.
        if fName is not None:
            append_files = self._normalize_file_selection(fName)
        else:
            append_files = self._normalize_file_selection(
                askopenfilenames(
                    title="Select files to append",
                    filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")],
                )
            )

        if not append_files:
            print("No files selected.")
            return -1

        file_ext = os.path.splitext(append_files[0])[1].lower()

        # Append TXT/JSON data files.
        if file_ext == '.txt':
            filtered = []
            for f in append_files:
                basename = os.path.basename(f)
                if any(c.isdigit() for c in basename):
                    filtered.append(f)
                else:
                    print(f"Skipping '{basename}': no number found in filename.")
            append_files = filtered

            if not append_files:
                print("No valid data files selected (none contained a number in the filename).")
                return -1

            append_root = os.path.dirname(append_files[0]) + os.sep

            new_data = dict()
            new_temps = []
            for file_path in append_files:
                temp = self._extract_txt_temperature(file_path)
                if temp is None:
                    print(f"Warning: Could not extract temperature from filename: {file_path}")
                    continue
                with open(file_path, 'r', encoding='utf-8') as file:
                    new_data[temp] = json.load(file)
                new_temps.append(temp)

            if not new_data:
                print("No valid TXT data could be parsed.")
                return -1

            self.dataValues = self._append_records(self.dataValues, new_data)
            self.dataTemps = self._append_unique_temps(self.dataTemps, new_temps)

            params_path = os.path.join(append_root, 'runParams.txt')
            try:
                with open(params_path, 'r', encoding='utf-8') as file:
                    param = json.load(file)
                self.dataParams = self._merge_nested_dict(self.dataParams, param, concatenate_arrays=False)
            except FileNotFoundError:
                print("Warning: runParams.txt not found alongside the appended files.")

            return 0

        # Append CSV data files.
        if file_ext == '.csv':
            emmHeader = []
            emmSignal = []
            excHeader = []
            excSignal = []
            impHeader = []
            impSignal = []

            for i in range(len(append_files)):
                if '_imps_0' in append_files[i]:
                    if '_header_' in append_files[i]:
                        emmHeader.append(append_files[i])
                    else:
                        emmSignal.append(append_files[i])
                if '_auxin0_' in append_files[i]:
                    if '_header_' in append_files[i]:
                        excHeader.append(append_files[i])
                    else:
                        excSignal.append(append_files[i])
                if '_r_avg_' in append_files[i]:
                    if '_header_' in append_files[i]:
                        impHeader.append(append_files[i])
                    else:
                        impSignal.append(append_files[i])

            if len(emmHeader) == 0:
                emmHeader.append(askopenfilenames(title="Select emission header")[0])
            if len(emmSignal) == 0:
                emmSignal.append(askopenfilenames(title="Select emission data")[0])
            if len(excHeader) == 0:
                excHeader.append(askopenfilenames(title="Select excitation header")[0])
            if len(excSignal) == 0:
                excSignal.append(askopenfilenames(title="Select excitation data")[0])

            if len(emmHeader) == 0 or len(emmSignal) == 0 or len(excHeader) == 0 or len(excSignal) == 0:
                print("No valid data files selected (none contained a number in the filename).")
                return -1

            if self.rootFolder is None:
                self.rootFolder = os.path.dirname(append_files[0]) + os.sep

            header = pd.read_csv(emmHeader[0], sep=';')
            headerKeys = list(header)
            dataNames = header[headerKeys[16]].to_list()

            temp_pairs = []
            new_temps = []
            for i in range(len(dataNames)):
                temp = self._extract_csv_temperature(dataNames[i])
                if temp is None:
                    print(f"Warning: Could not extract temperature from filename: {dataNames[i]}")
                    continue
                temp_pairs.append((i, temp))
                new_temps.append(temp)

            if not new_temps:
                print("No valid CSV temperatures found.")
                return -1

            new_data = dict()
            signalEmm = pd.read_csv(emmSignal[0], sep=';')
            chunk = signalEmm['chunk'].to_numpy()
            clockTicks = signalEmm['timestamp'].to_numpy()
            impedance = signalEmm['value'].to_numpy()
            for src_idx, temp in temp_pairs:
                record = dict()
                record['tickStampImps'] = clockTicks[chunk == src_idx]
                record['timeStampImps'] = clockTicks[chunk == src_idx] / (60 * 10 ** 6)
                record['ImpedanceIm'] = impedance[chunk == src_idx]
                if temp in new_data:
                    new_data[temp] = self._merge_nested_dict(new_data[temp], record, concatenate_arrays=True)
                else:
                    new_data[temp] = record

            signalExc = pd.read_csv(excSignal[0], sep=';')
            chunk = signalExc['chunk'].to_numpy()
            clockTicks = signalExc['timestamp'].to_numpy()
            auxInput1 = signalExc['value'].to_numpy()
            for src_idx, temp in temp_pairs:
                record = dict()
                record['tickStampDemods'] = clockTicks[chunk == src_idx]
                record['timeStampDemods'] = clockTicks[chunk == src_idx] / (60 * 10 ** 6)
                record['AuxInput1'] = auxInput1[chunk == src_idx]
                new_data[temp] = self._merge_nested_dict(new_data[temp], record, concatenate_arrays=True)

            if not (len(impHeader) == 0 or len(impSignal) == 0):
                signalImp = pd.read_csv(impSignal[0], sep=';')
                chunk = signalImp['chunk'].to_numpy()
                impedanceAbs = signalImp['value'].to_numpy()
                for src_idx, temp in temp_pairs:
                    record = dict()
                    record['AbsZ'] = impedanceAbs[chunk == src_idx]
                    record['ImpedanceRe'] = np.zeros_like(record['AbsZ'])
                    new_data[temp] = self._merge_nested_dict(new_data[temp], record, concatenate_arrays=True)

            self.dataValues = self._append_records(self.dataValues, new_data)
            self.dataTemps = self._append_unique_temps(self.dataTemps, new_temps)
            return 0

        print("Unsupported file type. Please select .txt or .csv files.")
        return -1

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

    def findDataLevelsScikit(self, dataType = 'emission', model='gmm',
                             interactivePlot=False):
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
    def findDataLevels(self, dataType = 'excitation', algorithm='gmm',
                       recalculate=True, interactivePlot=False):
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

        for i in range(len(self.dataTemps)):
            prePulseIndices = np.arange(np.where(l[i]==0)[0][0])
            postPulseIndices = np.arange(np.where(l[i]==1)[0][-1], len(l[i]))
            l[i][prePulseIndices] = -1
            l[i][postPulseIndices] = -1

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

    @staticmethod
    def find_cluster_stats(dataLabels,classLabels):
        l = classLabels
        blocks = dict()
        clusterSizesFreqs = dict()
        for i in range(len(dataLabels)):
            blocks[dataLabels[i]] = dict()
            high = impdData.find_signal_blocks(l[i], 0)
            low = impdData.find_signal_blocks(l[i], 1)

            blocks[dataLabels[i]]["high"] = dict()
            blocks[dataLabels[i]]["low"] = dict()

            # 1. Identify the high and low clusters, i.e. excitation and emission sections
            # 2. Sort the clusters by length for later alignment work
            # -------------------------------------------------------------------------------
            clusterSizesFreqs[dataLabels[i]] = dict()
            freqHighLengths = dict()
            for h1, h2 in enumerate(high):
                val = list(h2)
                val.append(val[1] - val[0])
                blocks[dataLabels[i]]["high"][h1] = val
                if (val[1] - val[0]) not in freqHighLengths.keys():
                    freqHighLengths[val[1] - val[0]] = 1
                else:
                    freqHighLengths[val[1] - val[0]] += 1
            # freqHighLengths.popitem()
            highFreqs = np.array([int(key) for key in freqHighLengths.keys()])
            highVals = np.array([int(value) for value in freqHighLengths.values()])
            highClusters = np.column_stack((highFreqs, highVals))
            sortedHighClusters = sorted(highClusters, key=lambda x: x[1], reverse=True)
            clusterSizesFreqs[dataLabels[i]]["high"] = sortedHighClusters

            freqLowLengths = dict()
            for l1, l2 in enumerate(low):
                val = list(l2)
                val.append(val[1] - val[0])
                blocks[dataLabels[i]]["low"][l1] = val
                if (val[1] - val[0]) not in freqLowLengths.keys():
                    freqLowLengths[val[1] - val[0]] = 1
                else:
                    freqLowLengths[val[1] - val[0]] += 1
            freqLowLengths.popitem()
            lowFreqs = np.array([int(key) for key in freqLowLengths.keys()])
            lowVals = np.array([int(value) for value in freqLowLengths.values()])
            lowClusters = np.column_stack((lowFreqs, lowVals))
            sortedLowClusters = sorted(lowClusters, key=lambda x: x[1], reverse=True)
            clusterSizesFreqs[dataLabels[i]]["low"] = sortedLowClusters

        return blocks, clusterSizesFreqs
    
    def findClusters(self, dataType='excitation', method='free',
                     recalculate=False, align=False):
        if not recalculate:
            if dataType == 'excitation':
                if self.dataExcitationClusterParams is None:
                    print("No stored data clusters found. Recalculating...")
                    recalculate = True
            if dataType == 'emission':
                if self.dataEmissionClusterParams is None:
                    print("No stored data clusters found. Recalculating...")
                    recalculate = True
            if not dataType == "excitation" and not dataType == "emission":
                print("Invalid data type. Must be 'excitation' or 'emission'.")
                return -1

        if recalculate:
            if not dataType == 'excitation' and not dataType == 'emission':
                print("Invalid data type. Must be 'excitation' or 'emission'.")
                return -1
            if dataType == 'excitation':
                self.dataExcitationClusterParams = dict()
                m, c, l = self.findDataLevels(
                    dataType=dataType,
                    algorithm="hybrid",
                    recalculate=True,
                    interactivePlot=False,
                )
                blocks, clusterSizesFreqs = self.find_cluster_stats(self.dataTemps, l)
                self.dataExcitationClusterParams["clusterBlocks"] = blocks
                self.dataExcitationClusterParams["clusterSizesFreqs"] = clusterSizesFreqs
                if align:
                    self.alignClusters(dataType="excitation")
            if dataType == 'emission':
                self.dataEmissionClusterParams = dict()
                if method == 'free':
                    m, c, l = self.findDataLevels(
                        dataType=dataType,
                        algorithm="hybrid",
                        recalculate=True,
                        interactivePlot=False,
                    )
                    blocks, clusterSizesFreqs = self.find_cluster_stats(self.dataTemps, l)
                    self.dataEmissionClusterParams["clusterBlocks"] = blocks
                    self.dataEmissionClusterParams["clusterSizesFreqs"] = clusterSizesFreqs
                    if align:
                        self.alignClusters(dataType="emission")
                if method == 'synced':
                    m, c, l = self.findDataLevels(
                        dataType='excitation',
                        algorithm="hybrid",
                        recalculate=True,
                        interactivePlot=False)
                    blocks, clusterSizesFreqs = self.find_cluster_stats(self.dataTemps, l)
                    self.dataEmissionClusterParams["clusterBlocks"] = blocks
                    self.dataEmissionClusterParams["clusterSizesFreqs"] = clusterSizesFreqs
                    if align:
                        self.alignClusters(dataType="emission")
                if not method == 'free' and not method == 'synced':
                    print("Invalid method. Must be 'free' or 'synced'.")
                    return -1

        return 0

    def alignClusters(self, dataType='excitation', method='free'):
        if not dataType == 'excitation' and not dataType == 'emission':
            print("Invalid data type. Must be 'excitation' or 'emission'.")
            return -1
        else:
            if dataType == 'excitation':
                self.findClusters(dataType='excitation', method=method)
            if dataType == 'emission':
                self.findClusters(dataType='emission', method=method)

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
                            self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][1] -= int(trim)
                            self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][-1] -= int(trim)

                    for j in range(len(self.dataExcitationClusterParams["clusterBlocks"][T]["low"])):
                        trim = self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1] - commonLengthLow
                        if trim > 0:
                            self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][1] -= int(trim)
                            self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1] -= int(trim)
                if dataType == 'emission':
                    for j in range(len(self.dataEmissionClusterParams["clusterBlocks"][T]["high"])):
                        trim = self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1] - commonLengthHigh
                        if trim > 0:
                            self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][1] -= int(trim)
                            self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1] -= int(trim)

                    for j in range(len(self.dataEmissionClusterParams["clusterBlocks"][T]["low"])):
                        trim = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1] - commonLengthLow
                        if trim > 0:
                            self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][1] -= int(trim)
                            self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1] -= int(trim)

            for i in range(len(self.dataTemps)):
                T = self.dataTemps[i]
                if dataType == 'excitation':
                    highs = dict()
                    for j in self.dataExcitationClusterParams['clusterBlocks'][T]['high'].keys():
                        length = self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][-1]
                        if length not in highs.keys():
                            highs[length] = 1
                        else:
                            highs[length] += 1
                    lows = dict()
                    for j in self.dataExcitationClusterParams['clusterBlocks'][T]['low'].keys():
                        length = self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1]
                        if length not in lows.keys():
                            lows[length] = 1
                        else:
                            lows[length] += 1
                    highList = []
                    for k in highs.keys():
                        highList.append(np.array((k, highs[k])))
                    lowList = []
                    for k in lows.keys():
                        lowList.append(np.array((k, lows[k])))

                    self.dataExcitationClusterParams["clusterSizesFreqs"][T]["high"] = highList
                    self.dataExcitationClusterParams["clusterSizesFreqs"][T]["low"] = lowList
                        
                if dataType == 'emission':
                    highs = dict()
                    for j in self.dataEmissionClusterParams['clusterBlocks'][T]['high'].keys():
                        length = self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1]
                        if length not in highs.keys():
                            highs[length] = 1
                        else:
                            highs[length] += 1
                    lows = dict()
                    for j in self.dataEmissionClusterParams['clusterBlocks'][T]['low'].keys():
                        length = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1]
                        if length not in lows.keys():
                            lows[length] = 1
                        else:
                            lows[length] += 1
                    highList = []
                    for k in highs.keys():
                        highList.append(np.array((k, highs[k])))
                    lowList = []
                    for k in lows.keys():
                        lowList.append(np.array((k, lows[k])))

                    self.dataEmissionClusterParams["clusterSizesFreqs"][T]["high"] = highList
                    self.dataEmissionClusterParams["clusterSizesFreqs"][T]["low"] = lowList

            lengthsHigh = np.zeros(len(self.dataTemps))
            lengthsLow = np.zeros(len(self.dataTemps))
            for i in range(len(self.dataTemps)):
                T = self.dataTemps[i]
                if dataType == 'emission':
                    if len(self.dataEmissionClusterParams["clusterSizesFreqs"][T]["low"])>1:
                        targetKey = list(self.dataEmissionClusterParams["clusterBlocks"][T]['low'])[-1]
                        self.dataEmissionClusterParams["clusterBlocks"][T]["low"].pop(targetKey)
                        self.dataEmissionClusterParams["clusterSizesFreqs"][T]["low"].pop(-1)

                    lengthsHigh[i] = self.dataEmissionClusterParams["clusterBlocks"][T]["high"][0][-1]
                    lengthsLow[i] = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][0][-1]
                if dataType == 'excitation':
                    if len(self.dataExcitationClusterParams["clusterSizesFreqs"][T]["low"])>1:
                        targetKey = list(self.dataExcitationClusterParams["clusterBlocks"][T]["low"])[-1]
                        self.dataExcitationClusterParams["clusterBlocks"][T]["low"].pop(targetKey)
                        self.dataExcitationClusterParams["clusterSizesFreqs"][T]["low"].pop(-1)
                    
                    lengthsHigh[i] = self.dataExcitationClusterParams["clusterBlocks"][T]["high"][0][-1]
                    lengthsLow[i] = self.dataExcitationClusterParams["clusterBlocks"][T]["low"][0][-1]

            shortestHigh = np.min(lengthsHigh)
            shortestLow = np.min(lengthsLow)
            for i in range(len(self.dataTemps)):
                T = self.dataTemps[i]
                if dataType == 'emission':
                    if self.dataEmissionClusterParams['clusterSizesFreqs'][T]['high'][0][0]>shortestHigh:
                        self.dataEmissionClusterParams['clusterSizesFreqs'][T]['high'][0][0] = shortestHigh
                        for j in range(len(self.dataEmissionClusterParams["clusterBlocks"][T]["high"])):
                            trim = self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1]-shortestHigh
                            if trim > 0:
                                self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][1] -= int(trim)
                                self.dataEmissionClusterParams["clusterBlocks"][T]["high"][j][-1] -= int(trim)
                    if self.dataEmissionClusterParams['clusterSizesFreqs'][T]['low'][0][0]>shortestLow:
                        self.dataEmissionClusterParams['clusterSizesFreqs'][T]['low'][0][0] = shortestLow
                        for j in range(len(self.dataEmissionClusterParams["clusterBlocks"][T]["low"])):
                            trim = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1]-shortestLow
                            if trim > 0:
                                self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][1] -= int(trim)
                                self.dataEmissionClusterParams["clusterBlocks"][T]["low"][j][-1] -= int(trim)
                if dataType == 'excitation':
                    if self.dataExcitationClusterParams['clusterSizesFreqs'][T]['high'][0][0]>shortestHigh:
                        self.dataExcitationClusterParams['clusterSizesFreqs'][T]['high'][0][0] = shortestHigh
                        for j in range(len(self.dataExcitationClusterParams["clusterBlocks"][T]["high"])):
                            trim = self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][-1]-shortestHigh
                            if trim > 0:
                                self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][1] -= int(trim)
                                self.dataExcitationClusterParams["clusterBlocks"][T]["high"][j][-1] -= int(trim)
                    if self.dataExcitationClusterParams['clusterSizesFreqs'][T]['low'][0][0]>shortestLow:
                        self.dataExcitationClusterParams['clusterSizesFreqs'][T]['low'][0][0] = shortestLow
                        for j in range(len(self.dataExcitationClusterParams["clusterBlocks"][T]["low"])):
                            trim = self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1]-shortestLow
                            if trim > 0:
                                self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][1] -= int(trim)
                                self.dataExcitationClusterParams["clusterBlocks"][T]["low"][j][-1] -= int(trim)

        return 0

    def selectedEmissions(self, emissionIndex=0, trimHead = 10, trimTail = 10, plot=False):
        if self.dataEmissionClusterParams is None or self.dataEmissionLevelParams is None:
            self.findClusters(dataType='emission', method='synced', recalculate=True, align=True)

        T = self.dataTemps[0]
        maxIndex = self.dataEmissionClusterParams["clusterSizesFreqs"][T]['low'][0][1]-1
        minIndex = -1
        if emissionIndex > maxIndex:
            print(f"Warning: emissionIndex {emissionIndex} exceeds max index {maxIndex}. Using max index instead.")
            emissionIndex = maxIndex
        if emissionIndex < minIndex:
            print(f"Warning: emissionIndex {emissionIndex} is below min index {minIndex}. Using min index instead.")
            emissionIndex = 0
        if emissionIndex > minIndex and emissionIndex < maxIndex:
            self.dataEmissions = dict()
            for i in range(len(self.dataTemps)):
                T = self.dataTemps[i]
                selectedIndex = self.dataEmissionClusterParams["clusterBlocks"][T]['low'][emissionIndex]
                selectedIndex = [int(x) for x in selectedIndex]
                x = np.asarray(self.dataValues[T]['timeStampImps'][selectedIndex[0]+trimHead:selectedIndex[1]+1-trimTail])
                x = x-x[0]
                y = np.asarray(self.dataValues[T]['ImpedanceIm'][selectedIndex[0]+trimHead:selectedIndex[1]+1-trimTail])
                self.dataEmissions[T] = dict()
                self.dataEmissions[T]["x"] = x
                self.dataEmissions[T]["y"] = y
                self.dataEmissions[T]["ymean"] = y
                self.dataEmissions[T]["yerr"] = np.zeros(y.shape[0])
        if emissionIndex < 0:
            self.dataEmissions = dict()
            for i in range(len(self.dataTemps)):
                T = self.dataTemps[i]
                selectedIndices = list(self.dataEmissionClusterParams["clusterBlocks"][T]["low"])
                selectedIndex = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][selectedIndices[0]]
                selectedIndex = [int(x) for x in selectedIndex]
                x = np.asarray(self.dataValues[T]["timeStampImps"][selectedIndex[0]+trimHead : selectedIndex[1]+1-trimTail])
                x = x - x[0]
                for j in range(len(selectedIndices)):
                    selectedIndex = self.dataEmissionClusterParams["clusterBlocks"][T]["low"][selectedIndices[j]]
                    selectedIndex = [int(x) for x in selectedIndex]
                    if j == 0:
                        y = np.asarray(self.dataValues[T]["ImpedanceIm"][selectedIndex[0]+trimHead : selectedIndex[1]+1-trimTail])
                    else:
                        temp = np.asarray(self.dataValues[T]["ImpedanceIm"][selectedIndex[0]+trimHead : selectedIndex[1]+1-trimTail])
                        y = np.column_stack((y, temp))
                self.dataEmissions[T] = dict()
                self.dataEmissions[T]['x'] = x
                self.dataEmissions[T]["y"] = y
                self.dataEmissions[T]['ymean'] = np.mean(y,axis=1)
                self.dataEmissions[T]['yerr'] = np.std(y,axis=1)

        return 0

    @staticmethod
    def waveletDenoise(signal, index=-1, wavelet="db4", level=1, mode="soft"):
        """
        Denoises a 1D signal using Discrete Wavelet Transform (DWT).

        Parameters:
        - signal: Dict() of arrays object containing the noisy data, x, y, and ymean.
        - wavelet: String name of the wavelet family (e.g., 'db4', 'sym8', 'coif1').
        - level: Decomposition depth level.
        - mode: Thresholding style ('soft' or 'hard').
        """
        yMean = np.asarray(signal["ymean"])
        y = np.asarray(signal["y"])
        x = np.asarray(signal["x"])

        maxIndex = y.shape[1]-1
        if index == -1:
            yRaw = np.array(yMean, copy=True)
        if index > -1 and index < maxIndex:
            yRaw = np.array(y[:,index], copy=True)
        if index > maxIndex:
            yRaw = np.array(y[:, maxIndex], copy=True)
        if index < -1:
            yRaw = np.array(y[:, 0], copy=True)

        # 1. Decompose the signal into Wavelet coefficients
        # Returns: [cA_n, cD_n, cD_n-1, ..., cD1]
        coeffs = pywt.wavedec(yRaw, wavelet, level=level)

        # 2. Extract the finest detail coefficients (cD1) to estimate noise variance
        cD1 = coeffs[-1]

        # Calculate Median Absolute Deviation (MAD) as a robust estimator for sigma
        # 0.6745 is the scaling factor for a standard normal distribution
        median_absolute_deviation = np.median(np.abs(cD1 - np.median(cD1)))
        sigma = median_absolute_deviation / 0.6745

        # 3. Calculate the Universal Threshold value
        n = len(yRaw)
        threshold = sigma * np.sqrt(2 * np.log(n))

        # 4. Apply thresholding to all detail coefficients (leave approximation cA_n untouched)
        new_coeffs = [coeffs[0]]  # Keep the approximation coefficients (coarse signal trend)
        for detail_coeff in coeffs[1:]:
            # Filter high-frequency noise out of the detail tracks
            thresholded_detail = pywt.threshold(detail_coeff, value=threshold, mode=mode)
            new_coeffs.append(thresholded_detail)

        # 5. Reconstruct the clean signal from the modified coefficients
        yFiltered = pywt.waverec(new_coeffs, wavelet)
        yDenoised = yFiltered[:n]

        # Ensure the reconstructed signal matches the original length
        return x, yDenoised, yRaw

    @staticmethod
    def pcaDenoise(signal, index=-1, window_size=None):
        """
        Denoises a 1D signal using Principal Component Analysis (PCA).

        Parameters:
        - signal: Dict() of arrays object containing the noisy data, x, y, and ymean.
        - window_size: Size of the sliding window for framing the signal.
        - plot: Boolean flag to plot the original and denoised signals.
        """

        yMean = np.asarray(signal["ymean"])
        y = np.asarray(signal["y"])
        x = np.asarray(signal["x"])

        maxIndex = y.shape[1]-1
        if index == -1:
            yRaw = np.array(yMean, copy=True)
        if index > -1 and index < maxIndex:
            yRaw = np.array(y[:,index], copy=True)
        if index > maxIndex:
            yRaw = np.array(y[:, maxIndex], copy=True)
        if index < -1:
            yRaw = np.array(y[:, 0], copy=True)

        # 1. Frame the 1D signal into a 2D matrix (Sliding Window)
        if window_size is None:
            window_size = len(yRaw) // 1000
        Y = np.array([yRaw[i : i + window_size] for i in range(len(yRaw) - window_size)])

        # 3. Apply PCA and keep only the first principal component
        # The 1st component will capture the dominant slow-frequency wave
        pca = PCA(n_components=1)
        yTransformed = pca.fit_transform(Y)
        yFiltered = pca.inverse_transform(yTransformed)

        # 4. Reconstruct the 1D signal from the overlapping windows
        yDenoised = np.zeros_like(yRaw)
        counts = np.zeros_like(yRaw)

        for i in range(len(yFiltered)):
            yDenoised[i : i + window_size] += yFiltered[i]
            counts[i : i + window_size] += 1

        # Avoid dividing by zero at the position of -1
        yDenoised[:-1] /= counts[:-1]
        yDenoised[-1] = np.mean([yDenoised[-2], yDenoised[-3]])
        
        return x, yDenoised, yRaw

    @staticmethod
    def savitzkyGolayDenoise(signal, index=-1, window_size=None, order=2):
        """
        Denoises a 1D signal using a Savitzky-Golay filter.
        """
        yMean = np.asarray(signal["ymean"])
        y = np.asarray(signal["y"])
        x = np.asarray(signal["x"])

        maxIndex = y.shape[1]-1
        if index == -1:
            yRaw = np.array(yMean, copy=True)
        if index > -1 and index < maxIndex:
            yRaw = np.array(y[:,index], copy=True)
        if index > maxIndex:
            yRaw = np.array(y[:, maxIndex], copy=True)
        if index < -1:
            yRaw = np.array(y[:, 0], copy=True)

        # 2. Apply the Savitzky-Golay filter
        if window_size is None:
            window_size = len(yRaw) // 1000
        yDenoised = savgol_filter(yRaw, window_length=window_size, polyorder=order)

        return x, yDenoised, yRaw

    @staticmethod
    def lowessDenoise(signal, index=-1, fraction=None):
        """
        Denoises a 1D signal using a Locally Weighted Scatterplot Smoothing (LOWESS) interpolation.
        """
        yMean = np.asarray(signal["ymean"])
        y = np.asarray(signal["y"])
        x = np.asarray(signal["x"])

        maxIndex = y.shape[1]-1
        if index == -1:
            yRaw = np.array(yMean, copy=True)
        if index > -1 and index < maxIndex:
            yRaw = np.array(y[:,index], copy=True)
        if index > maxIndex:
            yRaw = np.array(y[:, maxIndex], copy=True)
        if index < -1:
            yRaw = np.array(y[:, 0], copy=True)

        if fraction is None:
            fraction = 0.1
        lowess_result = Lowess(fraction=fraction, iterations=3, robustness_method="bisquare").fit(x, yRaw)
        yDenoised = lowess_result.y

        return x, yDenoised, yRaw

    def filterEmissions(self, method='pca', filterIndex=-1, recalculate=False, interactivePlot=True):
        method_key = str(method).strip().lower()
        if method_key not in ('pca', 'wavelet', 'sgolay', 'lowess'):
            raise ValueError("method must be one of: 'pca', 'wavelet', 'sgolay', 'lowess'")

        if self.dataEmissions is None:
            self.selectedEmissions(emissionIndex=-1, trimHead=10, trimTail=10, plot=False)

        if self.dataEmissions is None or len(self.dataEmissions) == 0:
            raise ValueError("No emission data found. Run selectedEmissions() first.")

        if not recalculate and 'yFiltered' not in self.dataEmissions[self.dataTemps[0]]:
            recalculate = True

        if not recalculate and 'filterMethod' in self.dataEmissions[self.dataTemps[0]]:
            if self.dataEmissions[self.dataTemps[0]]['filterMethod'] != method_key:
                recalculate = True

        if recalculate:
            for i in range(len(self.dataTemps)):
                T = self.dataTemps[i]
                if method_key == 'pca':
                    x, yDenoised, yRaw = self.pcaDenoise(self.dataEmissions[T], index=filterIndex, window_size=None)
                if method_key == 'wavelet':
                    x, yDenoised, yRaw = self.waveletDenoise(self.dataEmissions[T], index=filterIndex, wavelet="db4", level=4, mode="soft")
                if method_key == 'sgolay':
                    x, yDenoised, yRaw = self.savitzkyGolayDenoise(self.dataEmissions[T], index=filterIndex, window_size=None, order=2)
                if method_key == 'lowess':
                    x, yDenoised, yRaw = self.lowessDenoise(self.dataEmissions[T], index=filterIndex, fraction=None)
                self.dataEmissions[T]['yFiltered'] = yDenoised
                self.dataEmissions[T]['yRaw'] = yRaw

                if method_key == 'pca':
                    self.dataEmissions[T]['filterMethod'] = 'pca'
                if method_key == 'wavelet':
                    self.dataEmissions[T]['filterMethod'] = 'wavelet'
                if method_key == 'sgolay':
                    self.dataEmissions[T]['filterMethod'] = 'sgolay'
                if method_key == 'lowess':
                    self.dataEmissions[T]['filterMethod'] = 'lowess'

                self.dataEmissions[T]['filterIndex'] = filterIndex

        if interactivePlot:
            fig, ax = plt.subplots(figsize=(10, 6))
            current = [0]

            def update_filtered_plot(idx):
                T = self.dataTemps[idx]
                x = np.asarray(self.dataEmissions[T]['x'])
                yFiltered = np.asarray(self.dataEmissions[T]['yFiltered'])
                yRaw = np.asarray(self.dataEmissions[T]['yRaw'])

                ax.cla()
                ax.plot(x, yFiltered, '-', color='red', linewidth=1.5, label='Filtered')

                # Overlay original traces as dense point markers.
                if yRaw.ndim == 1:
                    ax.plot(x, yRaw, ',', color='black', alpha=0.35, label='Raw')
                else:
                    for j in range(yRaw.shape[1]):
                        lbl = 'Raw' if j == 0 else None
                        ax.plot(x, yRaw[:, j], ',', color='black', alpha=0.35, label=lbl)

                ax.set_xlabel('Time (s)', fontsize=10)
                ax.set_ylabel('Signal (a.u.)', fontsize=10)
                ax.set_title(f'i = {idx}  /  T = {T} K    (left/right to navigate)', fontsize=11)
                ax.legend(loc='best', fontsize=9)
                fig.canvas.draw_idle()

            def on_key(event):
                if event.key == 'right':
                    current[0] = (current[0] + 1) % len(self.dataTemps)
                elif event.key == 'left':
                    current[0] = (current[0] - 1) % len(self.dataTemps)
                else:
                    return
                update_filtered_plot(current[0])

            fig.canvas.mpl_connect('key_press_event', on_key)
            update_filtered_plot(current[0])
            plt.tight_layout()
            plt.show()

        return 0

    def calculateDelCNormalized(self, t1=0.003, t2=0.203,
                                emissionIndex=-1, denoiseEmission=False, smoothCapacitance=True,
                                plot=False):

        # Denoising the Emission is for better estimating the many sample averaged data
        # Smoothing the Capacitance is for estimating the real value of C right at t1 and/or t2

        if self.dataEmissions is None:
            self.selectedEmissions(emissionIndex=-1, trimHead=10, trimTail=10, plot=False)

        # if denoiseEmission and 'filterMethod' not in self.dataEmissions[self.dataTemps[0]]:
        self.filterEmissions(method='pca', filterIndex=emissionIndex, recalculate=False, interactivePlot=False)

        # If emission index is -1 and denoiseEmission is False, use ymean and yerr
        # If emission index is -1 and denoiseEmission is True, use yFiltered and yerr
        # If emission index is larger than existing indices, use the last emission
        # If emission index is smaller than -1, use the first emission
        # If emission index is any of the existing indices, use the index

        delCNormalized = np.zeros((len(self.dataTemps),4))
        for i in range(len(self.dataTemps)):
            if denoiseEmission:
                t = np.asarray(self.dataEmissions[self.dataTemps[i]]['x'])
                C = np.asarray(self.dataEmissions[self.dataTemps[i]]['yFiltered'])
                Cerr = np.asarray(self.dataEmissions[self.dataTemps[i]]['yerr'])

            else:
                t = np.asarray(self.dataEmissions[self.dataTemps[i]]['x'])
                C = np.asarray(self.dataEmissions[self.dataTemps[i]]['yRaw'])
                Cerr = np.asarray(self.dataEmissions[self.dataTemps[i]]['yerr'])

            if t1 < np.min(t): t1 = np.min(t)
            if t2 > np.max(t): t2 = np.max(t)

            if smoothCapacitance:
                # Model C and Cerr values using smoothing cubic spline
                csC = CubicSpline(t, C)
                csCerr = CubicSpline(t, Cerr)
                deltaC = csC(t2) - csC(t1)
                tau = (t2 - t1) / np.log(t2 / t1)
                delCNormalized[i] = np.array([self.dataTemps[i], tau, deltaC, deltaC / csC(t[-1])])
            else:
                nearestIndex1 = self.find_nearest(t, t1)
                nearestIndex2 = self.find_nearest(t, t2)
                deltaC = C[nearestIndex2] - C[nearestIndex1]
                tau = (t[nearestIndex2] - t[nearestIndex1]) / np.log(t[nearestIndex2] / t[nearestIndex1])
                delCNormalized[i] = np.array([self.dataTemps[i], tau, deltaC, deltaC / C[-1]])

        delCNormalized = delCNormalized[delCNormalized[:, 0].argsort()]

        if plot:
            fig, ax = plt.subplots()
            ax.plot(delCNormalized[:,0], delCNormalized[:,3],'.-')
            ax.set_xlabel("Temperature (K)")
            ax.set_ylabel("Normalized Delta C")
            ax.set_title("Normalized Delta C vs Temperature")
            plt.show()

        return delCNormalized

    def test(self, t1=None, t2=None, plot=True):
        if t1 is None:
            t1 = np.arange(1,3,1) * 0.010
        if t2 is None:
            t2 = np.arange(1,3,1) * 0.010

        C = np.zeros((len(t1)*(len(t2)-1)//2,4))
        idx=0
        for i in range(len(t1)):
            for j in range(len(t2)):
                if t2[j] > t1[i]:
                    temp = self.calculateDelCNormalized(t1=t1[i], t2=t2[j], emissionIndex=-1, denoiseEmission=False,
                                                        smoothCapacitance=False, plot=False)
                    csC = CubicSpline(temp[:,0], temp[:,3])
                    bounds = [(np.min(temp[:,0]), np.max(temp[:,0]))]
                    # result = differential_evolution(csC, bounds, integrality=[True])
                    result = differential_evolution(csC, bounds)
                    maxC = -result.fun
                    maxT = result.x[0]
                    C[idx] = np.array([t1[i],t2[j], maxT, maxC])
                    idx += 1

        if plot:
            fig, ax = plt.subplots()
            levels = np.arange(np.min(C[:, 2]), np.max(C[:, 2]), (np.max(C[:, 2])-np.min(C[:, 2]))/40)
            cntr = ax.tricontourf(C[:, 0], C[:, 1], C[:, 2], levels=levels, cmap='viridis')
            ax.tricontour(C[:, 0], C[:, 1], C[:, 2], levels=levels,
                          colors=['0.25', '0.5', '0.5', '0.5', '0.5'],
                          # linewidths=[1.0, 0.5, 0.5, 0.5, 0.5])
                          linewidths=[0.2, 0.1, 0.1, 0.1, 0.1])
            ax.scatter(C[C[:, 1] == 2*C[:, 0], 0], C[C[:, 1] == 2*C[:, 0], 1], marker='*', color='red', label='2x')
            ax.scatter(C[C[:, 1] == 5*C[:, 0], 0], C[C[:, 1] == 5*C[:, 0], 1], marker='x', color='black', label='5x')
            ax.scatter(C[C[:, 1] == 10*C[:, 0], 0], C[C[:, 1] == 10*C[:, 0], 1], marker='+', color='blue', label='10x')
            ax.scatter(C[C[:, 1] == 20*C[:, 0], 0], C[C[:, 1] == 20*C[:, 0], 1], marker='D', color='magenta', label='20x')
            ax.set_xlabel(r"$t_{1} (s)$", fontsize=10)
            ax.set_ylabel(r"$t_{2} (s)$", fontsize=10)
            # ax.set_title(f'i = {idx}  /  T = {T} K    (left/right to navigate)', fontsize=11)++++++++++
            cbar = fig.colorbar(cntr, ax=ax)
            cbar.set_label("Maximum T (K) Value Scale")
            plt.legend()
            plt.show()

            fig, ax = plt.subplots()
            levels = np.arange(np.min(C[:, 3]), np.max(C[:, 3]), (np.max(C[:, 3]) - np.min(C[:, 3])) / 40)
            cntr = ax.tricontourf(C[:, 0], C[:, 1], C[:, 3], levels=levels, cmap='viridis')
            ax.tricontour(C[:, 0], C[:, 1], C[:, 3], levels=levels,
                          colors=['0.25', '0.5', '0.5', '0.5', '0.5'],
                          # linewidths=[1.0, 0.5, 0.5, 0.5, 0.5])
                          linewidths=[0.2, 0.1, 0.1, 0.1, 0.1])
            ax.set_xlabel(r"$t_{1} (s)$", fontsize=10)
            ax.set_ylabel(r"$t_{2} (s)$", fontsize=10)
            # ax.set_title(f'i = {idx}  /  T = {T} K    (left/right to navigate)', fontsize=11)
            ax.scatter(C[C[:, 1] == 2*C[:, 0], 0], C[C[:, 1] == 2*C[:, 0], 1], marker='*', color='red', label='2x')
            ax.scatter(C[C[:, 1] == 5*C[:, 0], 0], C[C[:, 1] == 5*C[:, 0], 1], marker='x', color='black', label='5x')
            ax.scatter(C[C[:, 1] == 10*C[:, 0], 0], C[C[:, 1] == 10*C[:, 0], 1], marker='+', color='blue',label='10x')
            ax.scatter(C[C[:, 1] == 20*C[:, 0], 0], C[C[:, 1] == 20*C[:, 0], 1], marker='D', color='magenta', label='20x')
            cbar = fig.colorbar(cntr, ax=ax)
            cbar.set_label("Maximum Delta C Value Scale")
            plt.show()

        return C


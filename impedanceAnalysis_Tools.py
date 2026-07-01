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
from scipy.stats import weibull_min
from pomegranate.gmm import GeneralMixtureModel
from pomegranate.distributions import Normal
from pomegranate.distributions import LogNormal
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
        self.dataEmissions = None
        self.dataClusterIndices = None
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
            
    def findDataLevelsScikit(self, model='gmm', interactivePlot=False):
        if self.dataTemps is None or self.dataValues is None or len(self.dataTemps) == 0:
            raise ValueError("No loaded data found. Call readData() first.")

        model_key = str(model).strip().lower()
        if model_key not in ('gmm', 'kmeans', 'hybrid'):
            raise ValueError("model must be one of: 'gmm', 'kmeans', 'hybrid'")

        n_t = len(self.dataTemps)
        n_pts = len(self.dataValues[self.dataTemps[0]]['ImpedanceIm'])
        means = np.full((n_t, 2), np.nan)
        stds = np.full((n_t, 2), np.nan)
        labels = np.full((n_t, n_pts), -1.0)

        for i, t in enumerate(self.dataTemps):
            raw = np.asarray(self.dataValues[t]['ImpedanceIm'], dtype=float).ravel()
            if raw.size != n_pts:
                raise ValueError(f"Inconsistent ImpedanceIm length at {t} K.")

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
                fig, axes = plt.subplots(nrows=3, figsize=(10, 8), sharex=True, sharey=True)
                axes[-1].set_xlabel('Time (s)', fontsize=10)
                current = [0]

                def update_cluster_plot(idx):
                    t = self.dataTemps[idx]
                    ts = np.asarray(self.dataValues[t]['timeStampImps'])
                    imp = np.asarray(self.dataValues[t]['ImpedanceIm'])

                    scale_local = np.min(imp)
                    sorted_imp = np.sort(imp)
                    second_min_local = sorted_imp[1] if len(sorted_imp) > 1 else scale_local
                    if abs(second_min_local) > 0 and abs(scale_local) > 20.0 * abs(second_min_local):
                        for ax in axes:
                            ax.cla()
                            ax.text(0.5, 0.5, 'UNUSABLE DATA', transform=ax.transAxes,
                                    ha='center', va='center', fontsize=14, color='red')
                        fig.suptitle(f'i = {idx}  /  T = {t} K  [UNUSABLE — scale outlier]', fontsize=11)
                        fig.canvas.draw_idle()
                        return
                    d_local = (imp / scale_local).reshape(-1, 1)

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
                    axes[0].scatter(ts, imp, c=km_lbl, cmap='coolwarm', s=4, vmin=0, vmax=1)
                    axes[0].set_ylabel('K-Means', fontsize=10)

                    axes[1].cla()
                    axes[1].scatter(ts, imp, c=gmm_lbl, cmap='coolwarm', s=4, vmin=0, vmax=1)
                    axes[1].set_ylabel('GMM', fontsize=10)

                    axes[2].cla()
                    axes[2].scatter(ts[keep], imp[keep], c=hyb_lbl[keep], cmap='coolwarm', s=4, vmin=0, vmax=1)
                    axes[2].set_ylabel('Hybrid', fontsize=10)
                    axes[-1].set_xlabel('Time (s)', fontsize=10)
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

    def findDataLevelsPomegranate(self):
        # Import locally so the method works even in stale notebook sessions
        # where module globals were loaded before these symbols existed.
        try:
            import torch
            from pomegranate.gmm import GeneralMixtureModel as _GeneralMixtureModel
            from pomegranate.distributions import Normal as _Normal
        except Exception as exc:
            raise ImportError(
                "Could not import pomegranate mixture classes. "
                "Verify the pomegranate installation and restart the Python kernel."
            ) from exc

        if self.dataTemps is None or self.dataValues is None or len(self.dataTemps) == 0:
            raise ValueError("No loaded data found. Call readData() first.")

        ref_len = len(np.asarray(self.dataValues[self.dataTemps[0]]['ImpedanceIm']))
        means = np.full((len(self.dataTemps), 2), np.nan)
        covars = np.full((len(self.dataTemps), 2), np.nan)
        labels = np.full((len(self.dataTemps), ref_len), -1.0)
        for i in range(len(self.dataTemps)):
            t = self.dataTemps[i]
            raw = np.asarray(self.dataValues[t]['ImpedanceIm'], dtype=float).ravel()
            raw = raw[np.isfinite(raw)]

            if len(raw) != ref_len:
                raise ValueError(
                    f"Inconsistent ImpedanceIm length at {t} K: expected {ref_len}, got {len(raw)}"
                )

            if raw.size == 0:
                print(f"Warning: Skipping {t} K (empty ImpedanceIm trace).")
                continue

            scale = np.min(raw)
            if np.isclose(scale, 0.0):
                scale = np.max(np.abs(raw))
            if np.isclose(scale, 0.0):
                # Completely flat / zero trace: only one level can be identified.
                means[i] = np.array([0.0, 0.0])
                covars[i] = np.array([0.0, 0.0])
                labels[i] = np.zeros(ref_len)
                continue

            d = np.array(raw / scale, copy=True)
            d = d.reshape(-1, 1)

            # pomegranate can fail during initialization if one component gets no samples.
            # This happens often for nearly constant/degenerate traces.
            if np.unique(d).size < 2 or d.shape[0] < 2:
                means[i] = np.array([np.mean(raw), np.mean(raw)])
                covars[i] = np.array([np.var(raw), np.var(raw)])
                labels[i] = np.zeros(ref_len)
                continue

            torch.manual_seed(0)
            model = _GeneralMixtureModel([_Normal(), _Normal()])
            tensor_d = torch.tensor(d, dtype=torch.float32)

            try:
                model.fit(tensor_d)
            except Exception:
                # Retry once with a tiny deterministic jitter to avoid empty clusters.
                rng = np.random.default_rng(0)
                jitter = 1e-6 * rng.normal(size=d.shape)
                tensor_d = torch.tensor(d + jitter, dtype=torch.float32)
                try:
                    model.fit(tensor_d)
                except Exception:
                    # Fallback to sklearn GMM for this temperature if pomegranate still fails.
                    gmm = GaussianMixture(n_components=2, random_state=0, reg_covar=1e-8)
                    gmm.fit(d)
                    means[i] = gmm.means_.flatten() * scale
                    covars[i] = gmm.covariances_.flatten() * scale**2
                    labels[i] = gmm.predict(d)
                    continue

            extracted_means = np.array([model.distributions[j].means.detach().numpy().flatten()[0] for j in range(2)])
            extracted_covars = np.array([model.distributions[j].covs.detach().numpy().flatten()[0] for j in range(2)])

            means[i] = extracted_means * scale
            covars[i] = extracted_covars * scale**2

            pred = model.predict(torch.tensor(d, dtype=torch.float32))
            labels[i] = pred.detach().numpy().flatten()

        for i in range(len(self.dataTemps)):
            if np.all(np.isfinite(means[i])) and means[i][0] < means[i][1]:
                means[i] = means[i][::-1]
                covars[i] = covars[i][::-1]
                labels[i] = 1 - labels[i]

        return means, covars, labels

    # This is a caller function. It calls findDataLevelsScikit or findDataLevelsPomegranate
    # for finding data classes/levels
    def findDataLevels(self, library='scikitlearn', algorithm='gmm', plot=False, interactivePlot=False):
        lib_key = str(library).strip().lower()
        alg_key = str(algorithm).strip().lower()

        if lib_key in ('scikitlearn', 'sklearn'):
            if alg_key in ('gmm', 'gaussianmixture'):
                m, c, l = self.findDataLevelsScikit(model='gmm', interactivePlot=interactivePlot)
            elif alg_key in ('kmeans',):
                m, c, l = self.findDataLevelsScikit(model='kmeans', interactivePlot=interactivePlot)
            elif alg_key in ('hybrid', 'gmmkmeans', 'kmeansgmm'):
                m, c, l = self.findDataLevelsScikit(model='hybrid', interactivePlot=interactivePlot)
            else:
                raise ValueError(
                    "Unknown sklearn algorithm: " + str(algorithm) +
                    ". Valid options are: 'gmm', 'kmeans', 'hybrid'."
                )
        elif lib_key in ('pomegranate', 'pom', 'pome'):
            if alg_key not in ('gmm', 'gaussianmixture'):
                raise ValueError(
                    "Unsupported pomegranate algorithm: " + str(algorithm) +
                    ". Use 'gmm'."
                )
            m, c, l = self.findDataLevelsPomegranate()
        else:
            raise ValueError(
                "Unknown library: " + str(library) +
                ". Valid options are: 'scikitlearn', 'pomegranate'."
            )

        if plot:
            for i in range(len(m)):
                t = self.dataTemps[i]
                if alg_key in ('hybrid', 'gmmkmeans', 'kmeansgmm'):
                    valid = l[i] >= 0
                    plt.scatter(np.asarray(self.dataValues[t]['timeStampImps'])[valid],
                                np.asarray(self.dataValues[t]['ImpedanceIm'])[valid], c=l[i][valid],
                                cmap='coolwarm', s=4)
                else:
                    plt.scatter(self.dataValues[t]['timeStampImps'],
                                self.dataValues[t]['ImpedanceIm'], c=l[i],
                                cmap='coolwarm', s=4)

        return m, c, l

    @staticmethod
    def find_nearest(array, value):
        array = np.asarray(array)
        idx = (np.abs(array - value)).argmin()
        return idx

    def sampleEmissions(self, showLevels=False, library='scikitlearn', algorithm='gmm',
                        interactivePlot=False, interactiveDataIndex=0,
                        assignDataEmissions=False, useStoredEmissions=False,
                        returnClusterIndices=False, temperature=None):
        def _normalize_one_emission_segment(seg):
            arr = np.asarray(seg, dtype=float)
            if arr.ndim == 1 and arr.size >= 2 and arr.size % 2 == 0:
                arr = arr.reshape(-1, 2)
            if arr.ndim != 2 or arr.shape[1] != 2:
                return None
            return arr

        def _normalize_emission_groups(groups):
            # Supported canonical shape: {idx: [[ts, imp], ...], ...}
            if groups is None:
                return {}

            # Legacy convenience shape: {'x': [...], 'y': [...]} -> one segment.
            if isinstance(groups, dict) and ('x' in groups and 'y' in groups):
                x = np.asarray(groups['x'], dtype=float).ravel()
                y = np.asarray(groups['y'], dtype=float).ravel()
                n = min(x.size, y.size)
                if n == 0:
                    return {}
                seg = np.column_stack((x[:n], y[:n]))
                return {0: seg}

            out = {}
            if isinstance(groups, dict):
                items = groups.items()
            else:
                items = enumerate(groups)

            for k, seg in items:
                norm = _normalize_one_emission_segment(seg)
                if norm is None or norm.size == 0:
                    continue
                try:
                    key = int(k)
                except Exception:
                    key = len(out)
                out[key] = norm

            return {idx: out[idx] for idx in sorted(out.keys())}

        def _normalize_emissions_map(emissions_in):
            if emissions_in is None or not isinstance(emissions_in, dict):
                return {}
            emissions_out = {}
            for t, groups in emissions_in.items():
                emissions_out[t] = _normalize_emission_groups(groups)
            return emissions_out

        def _normalize_cluster_entries(entries):
            # Backward-compatible normalization: a single (start, stop, start, stop)
            # tuple becomes a one-item list, and every entry is stored as ints.
            if entries is None:
                return []
            if isinstance(entries, tuple) and len(entries) == 4:
                entries = [entries]

            out = []
            for entry in entries:
                if entry is None:
                    continue
                if isinstance(entry, np.ndarray):
                    entry = entry.tolist()
                if isinstance(entry, (list, tuple)) and len(entry) == 4:
                    out.append(tuple(int(v) for v in entry))
            return out

        def _resolve_temperature_key(temp_query):
            if temp_query is None:
                return None
            try:
                q = float(temp_query)
            except (TypeError, ValueError):
                raise ValueError("temperature must be numeric (in K) or None.")

            for t in self.dataTemps:
                if np.isclose(float(t), q, rtol=0.0, atol=1e-9):
                    return t
            raise KeyError(f"Requested temperature {temp_query} K is not in loaded data.")

        # Build labels first, then segment each trace into continuous runs of the
        # smaller-mean label while ignoring points marked as -1.
        if useStoredEmissions and self.dataEmissions is not None:
            emissions = _normalize_emissions_map(self.dataEmissions)
            cluster_indices = self.dataClusterIndices if self.dataClusterIndices is not None else {}
            if interactivePlot:
                m, c, l = self.findDataLevels(library=library, algorithm=algorithm, plot=False)
        else:
            m, c, l = self.findDataLevels(library=library, algorithm=algorithm, plot=False)

            # Models were canonicalized: label 0 = higher mean, label 1 = lower mean, label -1 = transition/discard
            emissions = dict()
            cluster_indices = dict()
            tExc = self.dataParams["impedance"]["State Disable Time"]
            tEmm = self.dataParams['impedance']['State Enable Time']
            tTotal = tEmm + tExc

            for i, t in enumerate(self.dataTemps):
                ts = np.asarray(self.dataValues[t]['timeStampImps'], dtype=float)
                imp = np.asarray(self.dataValues[t]['ImpedanceIm'], dtype=float)
                lbl = np.asarray(l[i], dtype=int)

                # Use labels as a mask first: drop all -1 points from both
                # impedance and timestamps with identical indices.
                valid_mask = lbl != -1
                ts_masked = ts[valid_mask]
                imp_masked = imp[valid_mask]
                lbl_masked = lbl[valid_mask]

                # Find all contiguous runs of 1s in lbl_masked
                runs_1 = []
                in_run = False
                start = 0
                for j in range(len(lbl_masked)):
                    if lbl_masked[j] == 1:
                        if not in_run:
                            start = j
                            in_run = True
                    else:
                        if in_run:
                            runs_1.append([start, j - 1])
                            in_run = False
                if in_run:
                    runs_1.append([start, len(lbl_masked) - 1])

                # Calculate threshold for leveling to label 0
                min_zeros = 10
                if len(ts_masked) >= 2:
                    dt = ts_masked[1] - ts_masked[0]
                    if dt > 0:
                        min_zeros = max(5, int(0.1 * (tExc / dt)))

                # Merge runs of 1s if the number of 0s between them is less than min_zeros
                merged_runs_1 = []
                if len(runs_1) > 0:
                    current_run = runs_1[0]
                    for next_run in runs_1[1:]:
                        num_zeros = next_run[0] - current_run[1] - 1
                        if num_zeros < min_zeros:
                            current_run[1] = next_run[1]
                        else:
                            merged_runs_1.append(current_run)
                            current_run = next_run
                    merged_runs_1.append(current_run)

                file_groups = dict()
                file_cluster_indices = []
                group_idx = 0
                
                for run_idx, run in enumerate(merged_runs_1):
                    emmStartIdx = run[0]
                    emmStopIdx = run[1]
                    excStartIdx = emmStopIdx + 1
                    
                    if excStartIdx < len(lbl_masked) and lbl_masked[excStartIdx] == 0:
                        target_exc_stop_t = tExc + ts_masked[excStartIdx]
                        excStopIdx = int(np.searchsorted(ts_masked, target_exc_stop_t, side='left'))
                        excStopIdx = min(max(excStopIdx, excStartIdx), len(ts_masked) - 1)

                        # Prevent this excitation segment from running into the next emission run.
                        if run_idx + 1 < len(merged_runs_1):
                            next_emm_start = merged_runs_1[run_idx + 1][0]
                            excStopIdx = min(excStopIdx, next_emm_start - 1)

                        if excStopIdx < excStartIdx:
                            continue

                        file_cluster_indices.append((emmStartIdx, emmStopIdx, excStartIdx, excStopIdx))
                        
                        seg = np.column_stack((ts_masked[emmStartIdx:emmStopIdx+1], imp_masked[emmStartIdx:emmStopIdx+1]))
                        if seg.size > 0:
                            file_groups[group_idx] = seg
                            group_idx += 1

                # Keep all detected clusters for this temperature.

                emissions[t] = _normalize_emission_groups(file_groups)
                cluster_indices[t] = file_cluster_indices

            # Normalize once so callers always see "temperature -> list[(a,b,c,d)]".
            cluster_indices = {k: _normalize_cluster_entries(v) for k, v in cluster_indices.items()}

            self.dataClusterIndices = cluster_indices

        # Also normalize the stored-path branch where old sessions can contain one tuple.
        cluster_indices = {k: _normalize_cluster_entries(v) for k, v in cluster_indices.items()}
        emissions = _normalize_emissions_map(emissions)
        # Persist emissions with a stable nested-dictionary structure for all callers.
        self.dataEmissions = emissions
        self.dataClusterIndices = cluster_indices

        if interactivePlot:
            if interactiveDataIndex < 0 or interactiveDataIndex >= len(self.dataTemps):
                raise IndexError("interactiveDataIndex is out of range for the loaded data set.")

            current = [interactiveDataIndex]
            fig, axes = plt.subplots(nrows=2, figsize=(10, 8))

            def update_plot(idx):
                t = self.dataTemps[idx]
                ts = np.asarray(self.dataValues[t]['timeStampImps'], dtype=float)
                imp = np.asarray(self.dataValues[t]['ImpedanceIm'], dtype=float)
                lbl = np.asarray(l[idx], dtype=int)

                valid_mask = lbl != -1
                ts_masked = ts[valid_mask]
                imp_masked = imp[valid_mask]

                # First plot: Selected emissions and excitations
                axes[0].cla()

                # Break plotted lines at large timestamp jumps so removed (-1) points
                # appear as visible gaps in the selected traces.
                if len(ts_masked) >= 2:
                    base_dt = np.median(np.diff(ts_masked))
                    gap_threshold = 1.5 * base_dt
                else:
                    gap_threshold = np.inf

                def plot_with_gaps(t_seg, i_seg, color, label):
                    if len(t_seg) == 0:
                        return
                    if len(t_seg) == 1:
                        axes[0].plot(t_seg, i_seg, '-o', color=color, label=label,
                                     linewidth=1, markersize=2)
                        return

                    jump_idx = np.where(np.diff(t_seg) > gap_threshold)[0]
                    start = 0
                    first_chunk = True
                    for j in jump_idx:
                        end = j + 1
                        if end > start:
                            axes[0].plot(t_seg[start:end], i_seg[start:end], '-o', color=color,
                                         label=label if first_chunk else "", linewidth=1, markersize=2)
                            first_chunk = False
                        start = end
                    axes[0].plot(t_seg[start:], i_seg[start:], '-o', color=color,
                                 label=label if first_chunk else "", linewidth=1, markersize=2)

                for c_idx, (emmStart, emmStop, excStart, excStop) in enumerate(cluster_indices[t]):
                    t_emm = ts_masked[emmStart:emmStop+1]
                    i_emm = imp_masked[emmStart:emmStop+1]
                    plot_with_gaps(t_emm, i_emm, 'green', 'Emissions' if c_idx == 0 else "")

                    t_exc = ts_masked[excStart:excStop+1]
                    i_exc = imp_masked[excStart:excStop+1]
                    plot_with_gaps(t_exc, i_exc, 'red', 'Excitations' if c_idx == 0 else "")

                axes[0].set_xlabel('Time (s)')
                axes[0].set_ylabel('Impedance Im')
                axes[0].set_title(f'Selected Emissions (Green) & Excitations (Red) | T = {t} K')
                if len(cluster_indices[t]) > 0:
                    axes[0].legend()

                # Second plot: Whole data set with selected cluster boundaries starred
                axes[1].cla()
                axes[1].scatter(ts_masked, imp_masked, color='gray', s=4, label='Whole Data')
                
                star_ts = []
                star_imp = []
                for emmStart, emmStop, excStart, excStop in cluster_indices[t]:
                    for idx_val in (emmStart, emmStop, excStart, excStop):
                        if 0 <= idx_val < len(ts_masked):
                            star_ts.append(ts_masked[idx_val])
                            star_imp.append(imp_masked[idx_val])
                if star_ts:
                    axes[1].scatter(star_ts, star_imp, color='orange', marker='*', s=120, edgecolors='black', label='Starred Indices')
                
                axes[1].set_xlabel('Time (s)')
                axes[1].set_ylabel('Impedance Im')
                axes[1].set_title(f'Whole Masked Data with Selected Indices (*) | T = {t} K')
                axes[1].legend()

                fig.suptitle(f'Interactive Cluster View | T = {t} K | index {idx+1}/{len(self.dataTemps)} (left/right arrow keys to navigate)', fontsize=12)
                fig.canvas.draw_idle()

            def on_key(event):
                if event.key == 'right':
                    current[0] = (current[0] + 1) % len(self.dataTemps)
                elif event.key == 'left':
                    current[0] = (current[0] - 1) % len(self.dataTemps)
                else:
                    return
                update_plot(current[0])

            fig.canvas.mpl_connect('key_press_event', on_key)
            update_plot(current[0])
            plt.tight_layout()
            plt.show()

        emissions_keys = list(emissions)

        temp_key = _resolve_temperature_key(temperature)
        if temp_key is not None:
            selected = cluster_indices.get(temp_key, [])
            if returnClusterIndices:
                return emissions, emissions_keys, {temp_key: selected}
            return emissions, emissions_keys, selected

        if returnClusterIndices:
            return emissions, emissions_keys, cluster_indices
        return emissions, emissions_keys

    def calculateDeltaCapacitanceT1T2(self, t1, t2, plot=False):
        emiss, _ = self.sampleEmissions()
        allPairs = np.array(list(itertools.product(t1,t2)))
        delTs = allPairs[allPairs[:,0] < allPairs[:,1]]

        delC = np.zeros((len(self.dataTemps),len(delTs)+1))
        errC = np.zeros((len(self.dataTemps),len(delTs)+1))
        for i in range(len(self.dataTemps)):
            t = self.dataTemps[i]
            groups = emiss.get(t, {})
            if len(groups) == 0:
                raise ValueError(f"No selected data groups found for temperature {t} K.")

            # Prefer the longest group for downstream delta-C calculations.
            best_key = max(groups, key=lambda k: groups[k].shape[0])
            data_xy = groups[best_key]
            x = data_xy[:, 0]
            y = data_xy[:, 1]
            err = np.full_like(y, np.std(y) if y.size > 0 else 0.0, dtype=float)
            yCS = CubicSpline(x, y, bc_type='natural')
            errCS = CubicSpline(x, err, bc_type='natural')

            delC[i,0] = t
            errC[i,0] = t
            for j in range(len(delTs)):
                p0 = yCS(delTs[j,0])
                e0 = np.abs(errCS(delTs[j,0]))
                p1 = yCS(delTs[j,1])
                e1 = np.abs(errCS(delTs[j,1]))

                delC[i, j + 1] = p1-p0
                errC[i, j + 1] = np.sqrt(e1*e1+e0*e0)
        for i in range(1,len(delTs)+1):
            errC[errC[:,i]==np.max(errC[:,i]),i]=0

        # ADD ERRORS!!!

        if plot:
            fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=len(delTs)//2, sharex=True, sharey=True)
            for i in range(len(delTs)//2):
                lbl0 = 't2=' + str(int(delTs[2*i,1]*1000)) + 'ms - t1=' + \
                    str(int(delTs[2*i,0]*1000)) + 'ms'
                lbl1 = 't2=' + str(int(delTs[2*i+1,1]*1000)) + 'ms - t1=' + \
                    str(int(delTs[2*i+1,0]*1000)) + 'ms'

                c0 = 1 # This needs to be corrected for C(steady-state) value
                e0 = 1  # This needs to be corrected for C(steady-state) value
                ax[i,0].plot(delC[:,0], delC[:,2*i+1]/c0,'-',color='blue',linewidth=1)
                ax[i,0].errorbar(delC[:,0], delC[:,2*i+1]/c0,
                                 yerr=errC[:,2*i+1]/e0, label=lbl0, fmt='o', color='r',
                                 markersize=3, ecolor='cyan', elinewidth=1)
                ax[i,0].legend(fontsize=12)
                ax[i,0].tick_params(axis='x', labelsize=18)
                ax[i,0].tick_params(axis='y', labelsize=18)
                ax[i,0].set_ylim([-0.01*np.min(delC[:,2*i+1]/c0),
                                  2.0*np.max(delC[:,2*i+1]/c0)])
                # ax[i,0].set_ylim([0.0,1.05])
                # ax[i,0].set_yticks([0.5])
                ax[i,0].set_xticks([50-23, 100-23, 150-23, 200-23],
                                   labels=[str(50+200), str(100+200), str(150+200), str(200+200)])

                c1 = 1 # This needs to be corrected for C(steady-state) value
                e1 = 1  # This needs to be corrected for C(steady-state) value
                ax[i,1].plot(delC[:,0], delC[:,2*i+2]/c1,'-',color='blue',linewidth=1)
                ax[i,1].errorbar(delC[:,0], delC[:,2*i+2]/c1,
                                 yerr=errC[:,2*i+2]/e1, label=lbl1, fmt='o', color='r',
                                 markersize=3, ecolor='cyan', elinewidth=1)
                ax[i,1].legend(fontsize=12)
                ax[i,1].tick_params(axis='x', labelsize=18)
                ax[i,1].tick_params(axis='y', labelsize=18)
                ax[i,1].set_ylim([-0.01*np.min(delC[:,2*i+2]/c1),
                                  2.0*np.max(delC[:,2*i+2]/c1)])
                # ax[i,1].set_ylim([0.0,1.05])
                # ax[i,1].set_yticks([0.5])
                ax[i,1].set_xticks([50-23, 100-23, 150-23, 200-23],
                                   labels=[str(50+200), str(100+200), str(150+200), str(200+200)])

            fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
            fig.supylabel(r'$\delta C$/C', fontsize=18)
            fig.subplots_adjust(top=0.975, bottom=0.090, 
                                left=0.070, right=0.990,
                                wspace=0.000, hspace=0.0) 

            plt.show()
            
        return delC, errC, delTs

    # This fit function uses PDF estimate of the data and fit via mixture models.
    @staticmethod
    def fitDeltaCapacitanceVsTemperatureFitToMixtures(xx, yy, err, nComponents=2,
                                                      nDrawnPoints=10000, mixtureType='lognormal',
                                                      plot=True):
        x = np.array(xx, dtype=float)
        y = np.array(yy, dtype=float)
        err = np.array(err, dtype=float)

        mixtureType = mixtureType.strip().lower()
        if mixtureType not in ('gaussian', 'lognormal'):
            raise ValueError("mixtureType must be 'gaussian' or 'lognormal', got: " + str(mixtureType))

        # Reflect the y graph around x = x[-1] (horizontal mirror of the curve)
        # so that y at mirrored x[0] position equals y[0]
        xMirror = 2.0 * x[-1] - x[-2::-1]  # mirror x about x[-1], excluding pivot
        yMirror = y[-2::-1]                   # reverse y values (y at x[0] maps to far end)
        errMirror = err[-2::-1]               # mirror errors (symmetric)
        xOrig = np.array(x, copy=True)        # save original x range for reflecting back

        # Use only reflected y for calculation (do not merge with original)
        # Normalize reflected y to create a PDF (area under curve = 1)
        spl = make_smoothing_spline(xMirror, yMirror)
        area, _ = quad(lambda val: float(spl(val)), xMirror[0], xMirror[-1])
        yNorm = yMirror / area

        # Build normalized spline for sampling
        splNorm = make_smoothing_spline(xMirror, yNorm)

        # Draw points from the PDF using inverse CDF sampling
        xFine = np.linspace(xMirror[0], xMirror[-1], nDrawnPoints)
        pdfFine = splNorm(xFine)
        pdfFine = np.maximum(pdfFine, 0)
        cdf = np.cumsum(pdfFine)
        cdf = cdf / cdf[-1]
        u = np.random.uniform(0, 1, nDrawnPoints)
        samples = np.interp(u, cdf, xFine)

        # Fit mixture model to the drawn samples (in reflected space)
        torch.manual_seed(0)
        data_tensor = torch.tensor(samples.reshape(-1, 1), dtype=torch.float32)

        sample_mean = float(np.mean(samples))
        sample_var = float(np.var(samples))
        dists = []
        for k in range(nComponents):
            if mixtureType == 'lognormal':
                log_samples = np.log(np.maximum(samples, 1e-12))
                log_mean = float(np.mean(log_samples))
                log_var = float(np.var(log_samples))
                d = LogNormal(
                    means=torch.tensor([log_mean + (k - nComponents / 2.0) * 0.5], dtype=torch.float32),
                    covs=torch.tensor([[log_var]], dtype=torch.float32),
                )
            else:  # gaussian
                d = Normal(
                    means=torch.tensor([sample_mean + (k - nComponents / 2.0) * 0.5 * np.sqrt(sample_var)], dtype=torch.float32),
                    covs=torch.tensor([[sample_var]], dtype=torch.float32),
                )
            dists.append(d)
        model = GeneralMixtureModel(dists)
        model.fit(data_tensor)

        # Extract fit parameters
        gmm_means = [model.distributions[j].means.detach().numpy().flatten()[0] for j in range(nComponents)]
        gmm_covs = [model.distributions[j].covs.detach().numpy().flatten()[0] for j in range(nComponents)]
        gmm_weights = model.priors.detach().numpy().flatten()

        # Build mixture PDF on reflected x range
        xPlot = np.linspace(xMirror[0], xMirror[-1], 1000)
        mixPdf = np.zeros_like(xPlot)
        for j in range(nComponents):
            mu = gmm_means[j]
            sigma2 = gmm_covs[j]
            sigma = np.sqrt(sigma2)
            if mixtureType == 'lognormal':
                mixPdf += gmm_weights[j] * (1.0 / (xPlot * sigma * np.sqrt(2 * np.pi))) * \
                    np.exp(-0.5 * (np.log(xPlot) - mu)**2 / sigma2)
            else:  # gaussian
                mixPdf += gmm_weights[j] * (1.0 / (sigma * np.sqrt(2 * np.pi))) * \
                    np.exp(-0.5 * (xPlot - mu)**2 / sigma2)
        mixPdf = np.nan_to_num(mixPdf, nan=0.0, posinf=0.0, neginf=0.0)

        # Reflect back: map mirrored x back to original x range
        xOrigMax = xOrig[-1]
        xReflectedBack = 2.0 * xOrigMax - xMirror
        yReflectedBack = yMirror

        # Reflect samples back
        samplesBack = 2.0 * xOrigMax - samples

        # Reflect fit curve back
        xPlotBack = 2.0 * xOrigMax - xPlot
        mixPdfBack = mixPdf
        sortIdx = np.argsort(xPlotBack)
        xPlotBack = xPlotBack[sortIdx]
        mixPdfBack = mixPdfBack[sortIdx]

        # Plot reflected-back y, histogram of reflected-back samples, and mixture fit overlaid
        if plot:
            fitLabel = mixtureType.capitalize() + ' mixture fit (reflected back)'
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(xReflectedBack, yReflectedBack, 'ro-', markersize=4, label='Reflected-back y')
            ax2 = ax.twinx()
            ax2.hist(samplesBack, bins=50, density=True, alpha=0.4, color='gray', label='Drawn samples (reflected back)')
            ax2.plot(xPlotBack, mixPdfBack, 'b-', linewidth=2, label=fitLabel)
            ax.set_xlabel('Temperature', fontsize=14)
            ax.set_ylabel('Delta Capacitance', fontsize=14)
            ax2.set_ylabel('Probability Density', fontsize=14)
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, fontsize=12)
            ax.set_title('Reflected-back y and ' + str(nComponents) + '-component ' + mixtureType.capitalize() + ' mixture fit', fontsize=14)
            plt.tight_layout()
            plt.show()

        def spline_fit_func(temp):
            return spl(2.0 * xOrigMax - temp)

        def mixture_fit_func(temp):
            tPlot = 2.0 * xOrigMax - np.array(temp, dtype=float)
            mixPdf = np.zeros_like(tPlot, dtype=float)
            for j in range(nComponents):
                mu = gmm_means[j]
                sigma2 = gmm_covs[j]
                sigma = np.sqrt(sigma2)
                if mixtureType == 'lognormal':
                    valid = tPlot > 0
                    if np.any(valid):
                        mixPdf[valid] += gmm_weights[j] * (1.0 / (tPlot[valid] * sigma * np.sqrt(2 * np.pi))) * \
                            np.exp(-0.5 * (np.log(tPlot[valid]) - mu)**2 / sigma2)
                else:  # gaussian
                    mixPdf += gmm_weights[j] * (1.0 / (sigma * np.sqrt(2 * np.pi))) * \
                        np.exp(-0.5 * (tPlot - mu)**2 / sigma2)
            mixPdf = np.nan_to_num(mixPdf, nan=0.0, posinf=0.0, neginf=0.0)
            return mixPdf * area

        return model, spline_fit_func, mixture_fit_func, samples, samplesBack, gmm_means, gmm_covs, gmm_weights

    # This fit function uses non-linear least squares to fit a mixture model to the data.
    @staticmethod
    def fitDeltaCapacitanceVsTemperatureFitToFunctions(xx, yy, err, nComponents=[2,3],
                                                       mixtureType='lognormal', plot=True):
        x = np.array(xx, dtype=float)
        y = np.array(yy, dtype=float)
        err = np.array(err, dtype=float)

        mixtureType = mixtureType.strip().lower()
        # Validate mixtureType
        if mixtureType not in ('gaussian', 'lognormal'):
            print(f"Warning: mixtureType must be 'gaussian' or 'lognormal'. Defaulting to 'lognormal'.")
            mixtureType = 'lognormal'

        # Reflect the data across the vertical line x = x[-1] (horizontal reflection)
        xMirror = 2.0 * x[-1] - x[-2::-1]  # mirror x about x[-1], excluding pivot
        yMirror = y[-2::-1]                   # reverse y values to match mirrored x
        errMirror = err[-2::-1]               # mirror errors

        # Use only reflected data
        xFull = xMirror
        yFull = yMirror
        errFull = errMirror

        # Fit a smoothing cubic spline to the reflected data
        spl = make_smoothing_spline(xFull, yFull)

        # Plotting preparation
        xPlot = np.linspace(xFull[0], xFull[-1], 1000)
        yPlot_spline = spl(xPlot)

        # lmfit iterative fitting over nComponents to find the best redchi
        if mixtureType == 'gaussian':
            CompModel = GaussianModel
        else:
            CompModel = LognormalModel

        best_result = None
        best_redchi = np.inf
        best_n = 0

        for n in range(nComponents[0], nComponents[1] + 1):
            model = None
            for i in range(1, n + 1):
                prefix = f'c{i}_'
                if model is None:
                    model = CompModel(prefix=prefix)
                else:
                    model += CompModel(prefix=prefix)

            params = model.make_params()

            # Initial guesses based on dividing the x range
            x_range = xFull[-1] - xFull[0]
            for i in range(1, n + 1):
                prefix = f'c{i}_'
                x_target = xFull[0] + (i - 0.5) * (x_range / n)
                idx = np.abs(xFull - x_target).argmin()

                if mixtureType == 'lognormal':
                    params[prefix + 'center'].set(value=np.log(max(xFull[idx], 1e-3)),
                                                  min=np.log(max(1e-3, np.min(xFull) / 10.0)),
                                                  max=np.log(np.max(xFull) * 10.0))
                    params[prefix + 'amplitude'].set(value=max(yFull[idx] * 10, 1e-3),
                                                     min=0,
                                                     max=max(yFull) * x_range * 100.0)
                    params[prefix + 'sigma'].set(value=0.1, min=0.01, max=5.0)
                else:  # gaussian
                    params[prefix + 'center'].set(value=xFull[idx],
                                                  min=xFull[0] - x_range,
                                                  max=xFull[-1] + x_range)
                    params[prefix + 'amplitude'].set(value=max(yFull[idx] * 10, 1e-3),
                                                     min=0,
                                                     max=max(yFull) * x_range * 100.0)
                    params[prefix + 'sigma'].set(value=x_range / (n * 5.0), min=0.01, max=x_range)

            # Perform the fit
            weights = 1.0 / np.where(errFull > 0, errFull, np.mean(errFull[errFull > 0]) if np.any(errFull > 0) else 1.0)
            try:
                result_tmp = model.fit(yFull, params, x=xFull, weights=weights)
                if np.abs(1-result_tmp.redchi) < np.abs(1.-best_redchi):
                    best_redchi = result_tmp.redchi
                    best_result = result_tmp
                    best_n = n
            except Exception as e:
                print(f"Fit failed for n={n}: {e}")

        if best_result is None:
            print("Warning: All fits failed in fitDeltaCapacitanceVsTemperatureFitToFunctions.")
            return None, spl, lambda temp: np.zeros_like(temp)

        result = best_result
        nComponentsBest = best_n
        yPlot_lmfit = result.eval(x=xPlot)

        # Reflect back: map mirrored data and fits back to original x range
        xOrigMax = x[-1]
        xBack = 2.0 * xOrigMax - xFull
        yBack = yFull
        errBack = errFull

        xPlotBack = 2.0 * xOrigMax - xPlot
        yPlot_spline_back = yPlot_spline
        yPlot_lmfit_back = yPlot_lmfit

        # Sort for proper line plotting in original space
        sortIdxBack = np.argsort(xBack)
        xBack = xBack[sortIdxBack]
        yBack = yBack[sortIdxBack]
        errBack = errBack[sortIdxBack]

        sortIdxPlot = np.argsort(xPlotBack)
        xPlotBack = xPlotBack[sortIdxPlot]
        yPlot_spline_back = yPlot_spline_back[sortIdxPlot]
        yPlot_lmfit_back = yPlot_lmfit_back[sortIdxPlot]

        # Plot the back-reflected data, spline fit, and lmfit result overlayed
        if plot:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.errorbar(xBack, yBack, yerr=errBack, fmt='ro', markersize=4,
                        ecolor='gray', elinewidth=1, capsize=2, label='Back-Reflected Data')
            ax.plot(xPlotBack, yPlot_spline_back, 'b-', linewidth=2, label='Smoothing Spline Fit (Back-Reflected)')
            ax.plot(xPlotBack, yPlot_lmfit_back, 'g--', linewidth=2, label=f'{nComponentsBest}-Comp {mixtureType.capitalize()} Fit (Best, lmfit, Back-Reflected)')

            ax.set_xlabel('Temperature', fontsize=14)
            ax.set_ylabel('Delta Capacitance', fontsize=14)
            ax.legend(fontsize=12)
            ax.set_title(f'Comparison of Back-Reflected Fits ({mixtureType.capitalize()})', fontsize=14)
            plt.tight_layout()
            plt.show()

        # Define the fit functions that work on the original temperature range (back-reflected)
        def spline_fit_func(temp):
            return spl(2.0 * xOrigMax - temp)

        def lmfit_fit_func(temp):
            return result.eval(x=2.0 * xOrigMax - temp)

        return result, spline_fit_func, lmfit_fit_func

    def findDeltaCapacitanceMaxima(self,delCx, delCy, delCErr, nComponents=[2,3],
                                   mixtureType='lognormal', plot=True, fitMethod='lmfit'):
        result = []
        csModel = []
        lmModel = []
        for i in range(delCy.shape[1]):
            xx = np.array(delCx, copy=True)
            yy = np.array(delCy[:, i], copy=True)
            err = np.array(delCErr[:, i], copy=True)
            if fitMethod == 'lmfit':
                temp = self.fitDeltaCapacitanceVsTemperatureFitToFunctions(xx, yy, err,
                                                                          nComponents, mixtureType,
                                                                          plot=plot)
            if fitMethod == 'mixtures':
                temp = self.fitDeltaCapacitanceVsTemperatureFitToMixtures(xx, yy, err,
                                                                          nComponents[0], 10000,
                                                                          mixtureType, plot=plot)
            result.append(temp[0])
            csModel.append(temp[1])
            lmModel.append(temp[2])
            if result[-1] is not None:
                if hasattr(result[-1], 'redchi'):
                    print(result[-1].redchi)
                else:
                    print("Fit completed (mixture model method).")
            else:
                print("Fit failed for this curve.")
        return result, csModel, lmModel


            
            
            
            
            
            

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
import h5py
import statistics
from uncertainties import unumpy, ufloat
import itertools
from scipy.stats import weibull_min

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
        self.dataSignals = None
        self.dataType = None
        self.subType = None

    def readData(self):
        print("Fix other data file import cases and exception for not choosing file! ")
        if self.fileName is None:
            self.fileName = askopenfilenames(title="Select a file",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
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
                t = strippedFName[i][:idx].replace("p",".")
                self.dataTemps.append(int(float(t)))
        
        try:
            data = dict()
            for i in range(len(self.fileName)):
                with open(self.fileName[i], 'r', encoding='utf-8') as file:
                    data[self.dataTemps[i]] = json.load(file)
            self.dataValues = data
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
            
    def findDataLevels(self):
        means = np.zeros((len(self.dataTemps),2))
        covars = np.zeros((len(self.dataTemps),2))
        labels = np.zeros((len(self.dataTemps),len(self.dataValues[self.dataTemps[0]]['ImpedanceIm'])))
        for i in range(len(self.dataTemps)):
            t = self.dataTemps[i]
            scale = np.min(self.dataValues[t]['ImpedanceIm'])
            d = np.array(self.dataValues[t]['ImpedanceIm']/scale, copy=True)
            d = d.reshape(-1, 1)
            gmm = GaussianMixture(n_components=2, random_state=0)
            gmm.fit(d)
            means[i] = gmm.means_.flatten()*scale
            covars[i] = gmm.covariances_.flatten()*scale**2
            labels[i] = gmm.predict(d)
        return means, covars, labels

    def sampleEmissions(self, showLevels=False):
        m,c,l = self.findDataLevels()
        if showLevels:
            for i in range(len(m)):
                t = self.dataTemps[i]
                plt.scatter(self.dataValues[t]['timeStampImps'], 
                            self.dataValues[t]['ImpedanceIm'],c=l[i], 
                            cmap='coolwarm', s=4)
        
        emissions = dict()
        for i in range(len(m)):
            for j in range(len(l[i])):
                if j==0:
                    idx = [0]
                    val = [l[i,0]]
                else:
                    if not l[i,j]==val[-1]:
                        idx.append(j)
                        val.append(l[i,j])
            diffs = []
            pairs = []
            for j in range(len(val)):
                if (val[j]==1) and (j+1<len(idx)):
                    diffs.append(idx[j+1]-idx[j])
                    pairs.append([idx[j],idx[j+1]])
        

            t = self.dataTemps[i]
            commonLength = statistics.mode(np.array(diffs)[np.array(diffs)>1])
            idx = np.array(pairs)[np.where(np.array(diffs)==commonLength)[0]]
            if len(idx)>0:
                if len(idx)==1:
                    y = np.array(self.dataValues[t]['ImpedanceIm'][idx[0]:idx[1]])
                    x = np.array(self.dataValues[t]['timeStampImps'][idx[0]:idx[1]])
                    x = x - x[0]
                if len(idx)>1:
                    y = np.array(self.dataValues[t]['ImpedanceIm'][idx[0][0]:idx[0][1]])
                    x = np.array(self.dataValues[t]['timeStampImps'][idx[0][0]:idx[0][1]])
                    x = x - x[0] 
                    for k in range(1,len(idx)):
                        temp = np.array(self.dataValues[t]['ImpedanceIm'][idx[k][0]:idx[k][1]])
                        y = np.column_stack((y,temp))
                        temp = np.array(self.dataValues[t]['timeStampImps'][idx[k][0]:idx[k][1]])
                        temp = temp - temp[0]
                        x = np.column_stack((x,temp))
            
            yMean = np.mean(y,axis=1)
            yStd = np.std(y,axis=1)
        
        
            targetStd = np.min(yStd)*100
            # BURDAN SONRA EN UZAK IKI ALINACAK NOKTAYI BU&LUP ARALARINDAKINI AL!!!
            startIdx = np.min(np.where(yStd<targetStd)[0])
            stopIdx = np.max(np.where(yStd<targetStd)[0])
            
            xx = x[startIdx:stopIdx+1,0]
            yy = yMean[startIdx:stopIdx+1]
            err = yStd[startIdx:stopIdx+1]
            emissions[self.dataTemps[i]] = dict()
            emissions[self.dataTemps[i]]['x'] = np.array(xx, copy=True)
            emissions[self.dataTemps[i]]['y'] = np.array(yy, copy=True)
            emissions[self.dataTemps[i]]['err'] = np.array(err, copy=True)

        return emissions

    def calculateDeltaCapacitanceT1T2(self, t1, t2, plot=False):
        emiss = self.sampleEmissions()
        allPairs = np.array(list(itertools.product(t1,t2)))
        delTs = allPairs[allPairs[:,0] < allPairs[:,1]]

        delC = np.zeros((len(self.dataTemps),len(delTs)+1))
        errC = np.zeros((len(self.dataTemps),len(delTs)+1))
        for i in range(len(self.dataTemps)):
            x = emiss[self.dataTemps[i]]['x']
            y = emiss[self.dataTemps[i]]['y']
            err = emiss[self.dataTemps[i]]['err']
            yCS = CubicSpline(x, y, bc_type='natural')
            errCS = CubicSpline(x, err, bc_type='natural')

            delC[i,0] = self.dataTemps[i]
            errC[i,0] = self.dataTemps[i]
            for j in range(len(delTs)):
                p0 = yCS(delTs[j,0])
                e0 = np.abs(errCS(delTs[j,0]))
                p1 = yCS(delTs[j,1])
                e1 = np.abs(errCS(delTs[j,1]))

                delC[i,j+1] = p1-p0
                errC[i, j + 1] = np.sqrt(e1*e1+e0*e0)

        # ADD ERRORS!!!

        if plot:
            fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=len(delTs)//2, sharex=True, sharey=True)
            for i in range(len(delTs)//2):
                lbl0 = 't2=' + str(int(delTs[2*i,1]*1000)) + 'ms - t1=' + \
                    str(int(delTs[2*i,0]*1000)) + 'ms'
                lbl1 = 't2=' + str(int(delTs[2*i+1,1]*1000)) + 'ms - t1=' + \
                    str(int(delTs[2*i+1,0]*1000)) + 'ms'
                
                # c0 = np.max(delC[:,2*i+1])
                c0 = 1
                yErr = np.abs(errC[:, 2 * i + 1] / delC[:, 2 * i + 1])
                yErr[yErr==np.max(yErr)]=0
                ax[i,0].plot(delC[:,0], delC[:,2*i+1],'-',color='blue',linewidth=1)
                ax[i,0].errorbar(delC[:,0], delC[:,2*i+1],
                                 yerr=yErr, label=lbl0, fmt='o', color='r',
                                 markersize=3, ecolor='cyan', elinewidth=1)
                ax[i,0].legend(fontsize=12)
                ax[i,0].tick_params(axis='x', labelsize=18)
                ax[i,0].tick_params(axis='y', labelsize=18)
                ax[i,0].set_ylim([0.0,1.05])
                ax[i,0].set_yticks([0.5])
                ax[i,0].set_xticks([50-23, 100-23, 150-23, 200-23],
                                   labels=[str(50+200), str(100+200), str(150+200), str(200+200)])
                
                # c1 = np.max(delC[:,2*i+2])
                c1 = 1
                yErr = np.abs(errC[:,2*i+2]/delC[:,2*i+2])
                yErr[yErr==np.max(yErr)]=0
                ax[i,1].plot(delC[:,0], delC[:,2*i+2],'-',color='blue',linewidth=1)
                ax[i,1].errorbar(delC[:,0], delC[:,2*i+2],
                                 yerr=yErr, label=lbl1, fmt='o', color='r',
                                 markersize=3, ecolor='cyan', elinewidth=1)
                ax[i,1].legend(fontsize=12)
                ax[i,1].tick_params(axis='x', labelsize=18)
                ax[i,1].tick_params(axis='y', labelsize=18)
                ax[i,1].set_ylim([0.0,1.05])
                ax[i,1].set_yticks([0.5])
                ax[i,1].set_xticks([50-23, 100-23, 150-23, 200-23],
                                   labels=[str(50+200), str(100+200), str(150+200), str(200+200)])

            fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
            fig.supylabel(r'$\delta C$/C', fontsize=18)
            fig.subplots_adjust(top=0.975, bottom=0.090, 
                                left=0.070, right=0.990,
                                wspace=0.000, hspace=0.0) 

            plt.show()
            
        return delC, errC, delTs

    @staticmethod
    def leftSkewedWeibull(x, alpha, beta, gamma):
        """PDF of a left-skewed 3-parameter Weibull distribution."""
        # We use the built-in scipy weibull_min but flip the x-axis relative to gamma
        x_shifted = gamma - x
        # Prevent evaluations outside the valid domain
        pdf = np.zeros_like(x, dtype=float)
        mask = x_shifted > 0
        if np.any(mask):
            pdf[mask] = weibull_min.pdf(x_shifted[mask], c=beta, scale=alpha)
        return pdf

    def fitLeftSkewedWeibull(self, x, y, alpha0=15.0, beta0=4.0, gamma0=None):
        """Fit leftSkewedWeibull to data (x, y) using lmfit.

        Parameters
        ----------
        x : array-like
            Independent variable (e.g. temperature).
        y : array-like
            Dependent variable (e.g. delta-C signal).
        alpha0 : float, optional
            Initial guess for the scale parameter (default 15.0).
        beta0 : float, optional
            Initial guess for the shape parameter (default 4.0).
        gamma0 : float, optional
            Initial guess for the location (upper-bound) parameter.
            If None, defaults to ``max(x) + 10``.

        Returns
        -------
        result : lmfit.model.ModelResult
            The full lmfit fit result object.
        """
        from lmfit import Model

        model = Model(self.leftSkewedWeibull)

        if gamma0 is None:
            gamma0 = np.max(x) + 10.0

        params = model.make_params()
        params['alpha'].set(value=alpha0, min=0.001)
        params['beta'].set(value=beta0, min=3.6)
        params['gamma'].set(value=gamma0, min=np.max(x))

        result = model.fit(y, params, x=np.asarray(x, dtype=float))
        return result

    def testPeakTemperatures(self, delC, delTs=None, nPoints=1000, plot=True):
        x = delC[:, 0]
        nCurves = delC.shape[1] - 1
        peakTemps = np.zeros(nCurves)
        peakVals = np.zeros(nCurves)
        fitResults = []
        tFine = np.linspace(np.min(x), np.max(x), nPoints)
        for i in range(nCurves):
            y = delC[:, i + 1]
            result = self.fitLeftSkewedWeibull(x, y)
            fitResults.append(result)
            yFine = result.eval(x=tFine)
            maxIdx = np.argmax(yFine)
            peakTemps[i] = tFine[maxIdx]
            peakVals[i] = yFine[maxIdx]

        if plot:
            fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=nCurves // 2, sharex=True, sharey=True)
            for i in range(nCurves // 2):
                if delTs is not None:
                    lbl0 = 't2=' + str(int(delTs[2 * i, 1] * 1000)) + 'ms - t1=' + \
                        str(int(delTs[2 * i, 0] * 1000)) + 'ms'
                    lbl1 = 't2=' + str(int(delTs[2 * i + 1, 1] * 1000)) + 'ms - t1=' + \
                        str(int(delTs[2 * i + 1, 0] * 1000)) + 'ms'
                else:
                    lbl0 = None
                    lbl1 = None

                c0 = np.max(delC[:, 2 * i + 1])
                yFine0 = fitResults[2 * i].eval(x=tFine)
                ax[i, 0].plot(tFine, yFine0 / c0, '-', color='blue', linewidth=1)
                ax[i, 0].plot(x, delC[:, 2 * i + 1] / c0, 'o', color='r', markersize=3, label=lbl0)
                ax[i, 0].legend(fontsize=12)
                ax[i, 0].tick_params(axis='x', labelsize=18)
                ax[i, 0].tick_params(axis='y', labelsize=18)
                ax[i, 0].set_ylim([0.0, 1.05])
                ax[i, 0].set_yticks([0.5])
                ax[i, 0].set_xticks([50 - 23, 100 - 23, 150 - 23, 200 - 23],
                                    labels=[str(50 + 200), str(100 + 200), str(150 + 200), str(200 + 200)])

                c1 = np.max(delC[:, 2 * i + 2])
                yFine1 = fitResults[2 * i + 1].eval(x=tFine)
                ax[i, 1].plot(tFine, yFine1 / c1, '-', color='blue', linewidth=1)
                ax[i, 1].plot(x, delC[:, 2 * i + 2] / c1, 'o', color='r', markersize=3, label=lbl1)
                ax[i, 1].legend(fontsize=12)
                ax[i, 1].tick_params(axis='x', labelsize=18)
                ax[i, 1].tick_params(axis='y', labelsize=18)
                ax[i, 1].set_ylim([0.0, 1.05])
                ax[i, 1].set_yticks([0.5])
                ax[i, 1].set_xticks([50 - 23, 100 - 23, 150 - 23, 200 - 23],
                                    labels=[str(50 + 200), str(100 + 200), str(150 + 200), str(200 + 200)])

            fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
            fig.supylabel(r'$\delta C$/C', fontsize=18)
            fig.subplots_adjust(top=0.975, bottom=0.090,
                                left=0.070, right=0.990,
                                wspace=0.000, hspace=0.0)
            plt.show()

        return peakTemps, peakVals, fitResults

    def estimatePeakTemperatures(self, delC, delTs=None, s=None, nPoints=1000, plot=False):
        temperatures = np.array(self.dataTemps)
        nCurves = delC.shape[1] - 1
        peakTemps = np.zeros(nCurves)
        peakVals = np.zeros(nCurves)
        splines = []
        tFine = np.linspace(np.min(temperatures), np.max(temperatures), nPoints)
        for j in range(nCurves):
            y = delC[:, j+1]
            spl = make_smoothing_spline(temperatures, y, lam=s)
            splines.append(spl)
            yFine = spl(tFine)
            maxIdx = np.argmax(yFine)
            peakTemps[j] = tFine[maxIdx]
            peakVals[j] = yFine[maxIdx]

        if plot:
            fig, ax = plt.subplots(figsize=(12, 10), ncols=2, nrows=nCurves//2, sharex=True, sharey=True)
            for i in range(nCurves//2):
                if delTs is not None:
                    lbl0 = 't2=' + str(int(delTs[2*i,1]*1000)) + 'ms - t1=' + \
                        str(int(delTs[2*i,0]*1000)) + 'ms'
                    lbl1 = 't2=' + str(int(delTs[2*i+1,1]*1000)) + 'ms - t1=' + \
                        str(int(delTs[2*i+1,0]*1000)) + 'ms'
                else:
                    lbl0 = None
                    lbl1 = None

                c0 = np.max(delC[:,2*i+1])
                yFine0 = splines[2*i](tFine)
                ax[i,0].plot(tFine, yFine0/c0, '-', color='blue', linewidth=1)
                ax[i,0].plot(temperatures, delC[:,2*i+1]/c0, 'o', color='r', markersize=3, label=lbl0)
                ax[i,0].legend(fontsize=12)
                ax[i,0].tick_params(axis='x', labelsize=18)
                ax[i,0].tick_params(axis='y', labelsize=18)
                ax[i,0].set_ylim([0.0,1.05])
                ax[i,0].set_yticks([0.5])
                ax[i,0].set_xticks([50-23, 100-23, 150-23, 200-23],
                                   labels=[str(50+200), str(100+200), str(150+200), str(200+200)])

                c1 = np.max(delC[:,2*i+2])
                yFine1 = splines[2*i+1](tFine)
                ax[i,1].plot(tFine, yFine1/c1, '-', color='blue', linewidth=1)
                ax[i,1].plot(temperatures, delC[:,2*i+2]/c1, 'o', color='r', markersize=3, label=lbl1)
                ax[i,1].legend(fontsize=12)
                ax[i,1].tick_params(axis='x', labelsize=18)
                ax[i,1].tick_params(axis='y', labelsize=18)
                ax[i,1].set_ylim([0.0,1.05])
                ax[i,1].set_yticks([0.5])
                ax[i,1].set_xticks([50-23, 100-23, 150-23, 200-23],
                                   labels=[str(50+200), str(100+200), str(150+200), str(200+200)])

            fig.supxlabel(r'Temperature ($^\circ$K)', fontsize=18)
            fig.supylabel(r'$\delta C$/C', fontsize=18)
            fig.subplots_adjust(top=0.975, bottom=0.090, 
                                left=0.070, right=0.990,
                                wspace=0.000, hspace=0.0) 
            plt.show()

        return peakTemps, peakVals, splines

    # # @staticmethod
    # # def find_nearest(array, value):
    # #     array = np.asarray(array)
    # #     idx = (np.abs(array - value)).argmin()
    # #     return idx, array[idx]
    
    # def calculateDeltaCapacitance(self, window=0.001, minT1=0, maxT1=0): #CORRECT THIS!!!
    #     x, y, err = self.sampleEmissions()
    #     yCS = CubicSpline(x, y, bc_type='natural')
    #     errCS = CubicSpline(x, err, bc_type='natural')
    #     if window < x[-1]-x[0]:
    #         if (minT1==0) and (maxT1==0):
    #             p0 = yCS(x[0])
    #             p1 = yCS(x[0]+window)
    #             e0 = np.abs(errCS(x[0]))
    #             e1 = np.abs(errCS(x[0]+window))
    #             delC = ufloat(p1,e1) - ufloat(p0,e0)
    #             delCVal = delC.nominal_value
    #             delCErr = delC.std_dev
    #         if (minT1==0) and (maxT1>0):
    #             if maxT1 < x[-1]-window:
    #                 maxT1Idx = np.where(x < maxT1)[0]
    #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    #                 for i in range(len(maxT1Idx)):
    #                     p0 = yCS(x[maxT1Idx[i]])
    #                     p1 = yCS(x[maxT1Idx[i]]+window)
    #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    #             else:
    #                 newMaxT1Idx = np.where(x < x[-1]-window)[0][-1]
    #                 maxT1 = x[newMaxT1Idx]
    #                 maxT1Idx = np.where(x < maxT1)[0]
    #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    #                 for i in range(len(maxT1Idx)):
    #                     p0 = yCS(x[maxT1Idx[i]])
    #                     p1 = yCS(x[maxT1Idx[i]]+window)
    #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    #             delCVal = delC.mean().nominal_value
    #             delCErr = delC.mean().std_dev
    #             returnVal = 0
    #         if (minT1>0) and (maxT1==minT1):
    #             minT1Idx = np.where(x < minT1)[0][-1]
    #             p0 = yCS(x[minT1Idx])
    #             p1 = yCS(x[minT1Idx]+window)
    #             e0 = np.abs(errCS(x[minT1Idx]))
    #             e1 = np.abs(errCS(x[minT1Idx]+window))
    #             delC = ufloat(p1,e1) - ufloat(p0,e0)
    #             delCVal = delC.nominal_value
    #             delCErr = delC.std_dev
    #             returnVal = 0
    #         if (minT1>0) and (maxT1>minT1):
    #             minT1Idx = np.where(x < minT1)[0][-1]
    #             if maxT1 < x[-1]-window:
    #                 maxT1Idx = np.where(x < maxT1)[0]
    #                 maxT1Idx = maxT1Idx[maxT1Idx>=minT1Idx]
    #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    #                 for i in range(len(maxT1Idx)):
    #                     p0 = yCS(x[maxT1Idx[i]])
    #                     p1 = yCS(x[maxT1Idx[i]]+window)
    #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    #             else:
    #                 newMaxT1Idx = np.where(x < x[-1]-window)[0][-1]
    #                 maxT1 = x[newMaxT1Idx]
    #                 maxT1Idx = np.where(x < maxT1)[0]
    #                 maxT1Idx = maxT1Idx[maxT1Idx>=minT1Idx]
    #                 delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
    #                 for i in range(len(maxT1Idx)):
    #                     p0 = yCS(x[maxT1Idx[i]])
    #                     p1 = yCS(x[maxT1Idx[i]]+window)
    #                     e0 = np.abs(errCS(x[maxT1Idx[i]]))
    #                     e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
    #                     delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
    #             delCVal = delC.mean().nominal_value
    #             delCErr = delC.mean().std_dev
    #             returnVal = 0

    #     else:
    #         print("Window is larger than data span!")
    #         delCVal = 0
    #         delCErr = 0
    #         returnVal = -1
    #     return delCVal, delCErr, returnVal
            
    # def deltaCapacitancePlots(self, window=1000, temperatures=30, minT1=0, maxT1=1000, smooth=False):
    #     maxT1 = maxT1 * 1e-6
    #     for i in range(len(window)):
    #         window = window[i] * 1e-6
    #         for j in range(len(temperatures)):
    #             aa[i,j],bb[i,j],cc = data[temperatures[j]].calculateDeltaCapacitance(window, minT1, maxT1)
        
    #     for i in range(len(t)):
    #         plt.plot(nm,aa[i,:]/np.max(aa[i,:]),label=str(t[i]))
        
    #     return 0
            
            
            
            
            
            
            
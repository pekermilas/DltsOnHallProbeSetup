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
from tkinter.filedialog import askopenfilename
from scipy.interpolate import make_splrep, CubicSpline
import json
from sklearn.mixture import GaussianMixture
import h5py
import statistics
from uncertainties import unumpy, ufloat
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
        if self.fileName is None:
            self.fileName = askopenfilename(title="Select a file",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        try:
            with open(self.fileName, 'r', encoding='utf-8') as file:
                self.dataValues = json.load(file)
            self.dataTemps = list(self.dataValues)
            self.dataSignals = list(self.dataValues[self.dataTemps[0]])
            self.dataType = "sweep" if "absz" in list(self.dataValues) else "series"
            self.subType = "cv" if "auxin0" in list(self.dataValues) else "freq"

            # CV SWEEP DATA REQUIRES TO BE WRITTEN INTO SINGLE FILE
            return 0
        
        except FileNotFoundError:
            print("Error: The file does not exist.")
            self.fileName = None
            return -1

        except json.JSONDecodeError:
            data = pd.read_csv(self.fileName, header=None, skiprows=1, sep=';')
            keys = list(data.iloc[:,3])
            vals = data.iloc[:,4:].to_numpy()
            
            self.dataValues = dict()
            for i in range(len(keys)):
                self.dataValues[keys[i]] = vals[i,:]
            self.dataType = "sweep" 
            self.subType = "cv" if "auxin0" in list(self.dataValues) else "freq"
            if self.subType=='cv':
                print("CV sweep uses two data files!\n")
                print("Run this function again to load the second file!")
            return 0

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
                yn = make_splrep(x,y,s=10)(xn)
                
                # fmin = np.min(xn[(yn<fUpper) & (yn>fLower)])
                # fmax = np.max(xn[(yn<fUpper) & (yn>fLower)])
                fRelevant = xn[(yn<fUpper) & (yn>fLower)]
                
                # This frequency will replace 501k frequency!!!
                return np.median(fRelevant)
            else:
                print("Data is not a sweep!!!")
                return 1
            
    def findDataLevels(self):
        scale = np.min(self.dataValues['ImpedanceIm'])
        d = np.array(self.dataValues['ImpedanceIm']/scale, copy=True)
        d = d.reshape(-1, 1)
        gmm = GaussianMixture(n_components=2, random_state=0)
        gmm.fit(d)
        m = gmm.means_.flatten()*scale
        c = gmm.covariances_.flatten()*scale**2
        l = gmm.predict(d)
        return m, c, l
            
    def sampleEmissions(self, showLevels=False):
        m,c,l = self.findDataLevels()
        if showLevels:
            plt.scatter(self.dataValues['timeStampImps'], 
                        self.dataValues['ImpedanceIm'],c=l, 
                        cmap='coolwarm', s=4)
        for i in range(len(l)):
            if i==0:
                idx = [0]
                val = [l[0]]
            else:
                if not l[i]==val[-1]:
                    idx.append(i)
                    val.append(l[i])
        diffs = []
        pairs = []
        for i in range(len(val)):
            if (val[i]==1) and (i+1<len(idx)):
                diffs.append(idx[i+1]-idx[i])
                pairs.append([idx[i],idx[i+1]])
        
        commonLength = statistics.mode(np.array(diffs))
        idx = np.array(pairs)[np.where(np.array(diffs)==commonLength)[0]]
        if len(idx)>0:
            if len(idx)==1:
                y = np.array(self.dataValues['ImpedanceIm'][idx[0]:idx[1]])
                x = np.array(self.dataValues['timeStampImps'][idx[0]:idx[1]])
                x = x - x[0]
            if len(idx)>1:
                y = np.array(self.dataValues['ImpedanceIm'][idx[0][0]:idx[0][1]])
                x = np.array(self.dataValues['timeStampImps'][idx[0][0]:idx[0][1]])
                x = x - x[0] 
                for i in range(1,len(idx)):
                    temp = np.array(self.dataValues['ImpedanceIm'][idx[i][0]:idx[i][1]])
                    y = np.column_stack((y,temp))
                    temp = np.array(self.dataValues['timeStampImps'][idx[i][0]:idx[i][1]])
                    temp = temp - temp[0]
                    x = np.column_stack((x,temp))
        
        yMean = np.mean(y,axis=1)
        yStd = np.std(y,axis=1)
        
        targetStd = np.min(yStd)*100
        # BURDAN SONRA EN UZAK IKI ALINACAK NOKTAYI BU&LUP ARALARINDAKINI AL!!!
        startIdx = np.min(np.where(yStd<targetStd)[0])
        stopIdx = np.max(np.where(yStd<targetStd)[0])
        
        a = x[startIdx:stopIdx+1,0]
        b = yMean[startIdx:stopIdx+1]
        d = yStd[startIdx:stopIdx+1]
        
        return a,b,d

    @staticmethod
    def find_nearest(array, value):
        array = np.asarray(array)
        idx = (np.abs(array - value)).argmin()
        return idx, array[idx]
    
    def calculateDeltaCapacitance(self, x, y, err, window=0.001, minT1=0, maxT1=0):
        yCS = CubicSpline(x, y, bc_type='natural')
        errCS = CubicSpline(x, err, bc_type='natural')
        if window < x[-1]-x[0]:
            if (minT1==0) and (maxT1==0):
                p0 = yCS(x[0])
                p1 = yCS(x[0]+window)
                e0 = np.abs(errCS(x[0]))
                e1 = np.abs(errCS(x[0]+window))
                delC = ufloat(p1,e1) - ufloat(p0,e0)
                delCVal = delC.nominal_value
                delCErr = delC.std_dev
            if (minT1==0) and (maxT1>0):
                if maxT1 < x[-1]-window:
                    maxT1Idx = np.where(x < maxT1)[0]
                    delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
                    for i in range(len(maxT1Idx)):
                        p0 = yCS(x[maxT1Idx[i]])
                        p1 = yCS(x[maxT1Idx[i]]+window)
                        e0 = np.abs(errCS(x[maxT1Idx[i]]))
                        e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
                        delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
                else:
                    newMaxT1Idx = np.where(x < x[-1]-window)[0][-1]
                    maxT1 = x[newMaxT1Idx]
                    maxT1Idx = np.where(x < maxT1)[0]
                    delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
                    for i in range(len(maxT1Idx)):
                        p0 = yCS(x[maxT1Idx[i]])
                        p1 = yCS(x[maxT1Idx[i]]+window)
                        e0 = np.abs(errCS(x[maxT1Idx[i]]))
                        e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
                        delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
                delCVal = delC.mean().nominal_value
                delCErr = delC.mean().std_dev
                returnVal = 0
            if (minT1>0) and (maxT1==minT1):
                minT1Idx = np.where(x < minT1)[0][-1]
                p0 = yCS(x[minT1Idx])
                p1 = yCS(x[minT1Idx]+window)
                e0 = np.abs(errCS(x[minT1Idx]))
                e1 = np.abs(errCS(x[minT1Idx]+window))
                delC = ufloat(p1,e1) - ufloat(p0,e0)
                delCVal = delC.nominal_value
                delCErr = delC.std_dev
                returnVal = 0
            if (minT1>0) and (maxT1>minT1):
                minT1Idx = np.where(x < minT1)[0][-1]
                if maxT1 < x[-1]-window:
                    maxT1Idx = np.where(x < maxT1)[0]
                    maxT1Idx = maxT1Idx[maxT1Idx>=minT1Idx]
                    delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
                    for i in range(len(maxT1Idx)):
                        p0 = yCS(x[maxT1Idx[i]])
                        p1 = yCS(x[maxT1Idx[i]]+window)
                        e0 = np.abs(errCS(x[maxT1Idx[i]]))
                        e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
                        delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
                else:
                    newMaxT1Idx = np.where(x < x[-1]-window)[0][-1]
                    maxT1 = x[newMaxT1Idx]
                    maxT1Idx = np.where(x < maxT1)[0]
                    maxT1Idx = maxT1Idx[maxT1Idx>=minT1Idx]
                    delC = unumpy.uarray(np.zeros(len(maxT1Idx)),np.zeros(len(maxT1Idx)))
                    for i in range(len(maxT1Idx)):
                        p0 = yCS(x[maxT1Idx[i]])
                        p1 = yCS(x[maxT1Idx[i]]+window)
                        e0 = np.abs(errCS(x[maxT1Idx[i]]))
                        e1 = np.abs(errCS(x[maxT1Idx[i]]+window))
                        delC[i] = ufloat(p1,e1) - ufloat(p0,e0)
                delCVal = delC.mean().nominal_value
                delCErr = delC.mean().std_dev
                returnVal = 0
            # else:
            #     print("Window start and stop problem!")
            #     delCVal = 0
            #     delCErr = 0
            #     returnVal = 1
                # error state
        else:
            print("Window is larger than data span!")
            delCVal = 0
            delCErr = 0
            returnVal = -1
        return delCVal, delCErr, returnVal
            
            
            
            
            
            
            
            
            
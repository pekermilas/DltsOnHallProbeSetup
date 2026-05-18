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
from scipy.interpolate import make_splrep
import json
from sklearn.mixture import GaussianMixture

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
        return m
            
            
            
            
            
            
            
            
            
            
            
            
            
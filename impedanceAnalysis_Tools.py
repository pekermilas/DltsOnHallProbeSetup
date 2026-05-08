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

import json

import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC

class impdData:
    def __init__(self, fName):
        self.fileName = fName or 'C:/Users/spencer/Desktop/DATA/DLTS/dataTestFile.txt'
        self.dataValues = None
        self.dataTemps = None
        self.dataSignals = None

    def readData(self):
        with open(self.fileName, 'r', encoding='utf-8') as file:
            self.dataValues = json.load(file)
        self.dataTemps = list(self.dataValues)
        self.dataSignals = list(self.dataValues[self.dataTemps[0]])
        return 0
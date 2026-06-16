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

    run = rdT.dltsRun()
    run.initSetup()
    run.runExperiment()
    run.finishExperiment()
    
    # data = iaT.impdData()
    # data.readData()
    # fN = 'C:/Users/peker/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-1p0.txt'
    # fN = 'C:/Users/peker/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-72p0.txt'
    # fN = 'C:/Users/pekermilas/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-1p0.txt'
    # fN = 'C:/Users/pekermilas/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-90p0.txt'
    # fN = 'C:/Users/pekermilas/Documents/GitHub/PekerPersonalCodeWorks/CemilDataAnalysis/06092026/-72p0.txt'

    # data = iaT.impdData(fName=fN)
    # data.readData()
    # run = rdT.dltsRun()
    # run.testDataLeveling(fN, plot=True)



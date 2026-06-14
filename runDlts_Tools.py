import time
from datetime import datetime
import zhinst.core
import zhinst.toolkit as zt
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os
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

class dltsRun:
    def __init__(self, fName=None):
        self.runDevices = []
        self.runParams = None
        self.dataFolder = None
        self.livePlot = True
        self.senseRunFailure = True
        self.runOutputFileType = 'txt'

    def initSetup(self):
        # Connect to devices
        tempDev = tsC.mK2000B()
        tempDev.connectTempController()
        impdDev = ziC.ziDevice()
        impdDev.connectDevice()
        self.runDevices = [tempDev, impdDev]

        # Set impedance analyzer parameters
        self.runDevices[1].device.factory_reset()
        self.runDevices[1].loadParams()
        impParams = self.runDevices[1].params
        # Add number of data point in mesurement
        pEntry = input("Please enter Number of Data Points (as power of 2): ")
        impParams['numPoints'] = 2**float(pEntry) if not len(pEntry) == 0 else 2**13

        # Set temperature controller parameters
        self.runDevices[0].setTempGrid()
        tmpParams = dict()
        tmpParams['tInitial'] = self.runDevices[0].Tinitial
        tmpParams['tFinal'] = self.runDevices[0].Tfinal
        tmpParams['numTemps'] = self.runDevices[0].numTemps

        # Set data storage parameters
        dtaParams = dict()
        pEntry = input("Please enter output file type (txt or h5): ")
        dtaParams['fileType'] = pEntry if not len(pEntry) == 0 else 'txt'
        rootFolder = 'C:/Users/spencer/Desktop/DATA/DLTS/'
        timeAndDate = datetime.now()
        temp = '{:02d}'.format(timeAndDate.month) + '{:02d}'.format(timeAndDate.day) + \
               '{:02d}'.format(timeAndDate.year)[-2:] + '\\'
        topFolder = rootFolder + temp
        if not os.path.exists(topFolder):
            os.makedirs(topFolder)
        self.dataFolder = topFolder

        fName=[]
        for i in range(len(self.runDevices[0].tempGrid)):
            if str(self.runDevices[0].tempGrid[i])=='-':
                fName.append('n'+ str(np.abs(self.runDevices[0].tempGrid[i])).replace('.','p')+'.txt')
            else:
                fName.append('p'+ str(np.abs(self.runDevices[0].tempGrid[i])).replace('.','p')+'.txt')











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
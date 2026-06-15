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
import impedanceAnalysis_Tools as iaT

class dltsRun:
    def __init__(self, fName=None):
        self.runDevices = []
        self.runParams = None
        self.dataFolder = None
        self.runOutputFileType = None
        self.dataFileNames = None
        self.paramsFileName = None
        self.livePlot = True
        self.senseRunFailure = True
        self.excludedRuns = []

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
        dtaParams['outputType'] = pEntry if not len(pEntry) == 0 else 'txt'
        pEntry = input("Please enter root folder for data: ")
        dtaParams['rootFolder'] = pEntry if not len(pEntry) == 0 else 'C:/Users/spencer/Desktop/DATA/DLTS/'

        rootFolder = dtaParams['rootFolder']
        timeAndDate = datetime.now()
        temp = '{:02d}'.format(timeAndDate.month) + '{:02d}'.format(timeAndDate.day) + \
               '{:02d}'.format(timeAndDate.year)[-2:] + '\\'
        topFolder = rootFolder + temp
        if not os.path.exists(topFolder):
            os.makedirs(topFolder)
        self.runOutputFileType = dtaParams['outputType']
        self.dataFolder = topFolder

        fName = []
        if dtaParams['outputType'] == 'txt':
            for i in range(len(self.runDevices[0].tempGrid)):
                if str(self.runDevices[0].tempGrid[i])=='-':
                    fName.append(self.dataFolder + 'n'+ str(np.abs(self.runDevices[0].tempGrid[i])).replace('.','p')+'.txt')
                else:
                    fName.append(self.dataFolder + 'p'+ str(np.abs(self.runDevices[0].tempGrid[i])).replace('.','p')+'.txt')
        self.dataFileNames = fName

        pEntry = input("Do you want live plot? (y/n): ")
        self.livePlot = True if not len(pEntry) == 0 and pEntry.lower() == 'y' else False
        dtaParams['livePlot'] = self.livePlot
        pEntry = input("Do you want to sense run failure? (y/n): " )
        self.senseRunFailure = True if not len(pEntry) == 0 and pEntry.lower() == 'y' else False
        dtaParams['senseRunFailure'] = self.senseRunFailure

        self.runParams = dict()
        self.runParams['temperature'] = tmpParams
        self.runParams['impedance'] = impParams
        self.runParams['data'] = dtaParams

        self.paramsFileName = self.dataFolder + 'runParams.txt'

        return 0

    def testDataLeveling(self, dataFile, plot=False):
        data = iaT.impdData(fName=dataFile)
        data.readData()

        m, c, l = data.findDataLevelsScikitLearn()
        if plot:
            plt.scatter(data.dataValues[list(data.dataValues)[0]]['timeStampImps'],
                        data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'], c=l[:],
                        cmap='coolwarm', s=4)
        x = np.array(data.dataValues[list(data.dataValues)[0]]['timeStampImps'])
        y = np.array(data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'])

        # Data sanity check by evolution of standard deviation
        # ------------------------------------------------------
        for j in range(len(l[0])):
            if j == 0:
                idx = [0]
                val = [l[0, 0]]
            else:
                if not l[0, j] == val[-1]:
                    idx.append(j)
                    val.append(l[0, j])
        diffs = []
        pairs = []
        for j in range(len(val)):
            if (val[j] == 1) and (j + 1 < len(idx)):
                diffs.append(idx[j + 1] - idx[j])
                pairs.append([idx[j], idx[j + 1]])

        commonLength = statistics.mode(np.array(diffs)[np.array(diffs) > 1])
        idx = np.array(pairs)[np.where(np.array(diffs) == commonLength)[0]]
        if len(idx) > 0:
            if len(idx) == 1:
                yy = np.array(y[idx[0]:idx[1]])
                xx = np.array(x[idx[0]:idx[1]])
                xx = xx - xx[0]
            if len(idx) > 1:
                yy = np.array(y[idx[0][0]:idx[0][1]])
                xx = np.array(x[idx[0][0]:idx[0][1]])
                xx = xx - xx[0]
                for k in range(1, len(idx)):
                    temp = np.array(y[idx[k][0]:idx[k][1]])
                    yy = np.column_stack((yy, temp))
                    temp = np.array(x[idx[k][0]:idx[k][1]])
                    temp = temp - temp[0]
                    xx = np.column_stack((xx, temp))
        std0 = np.mean(np.std(yy, axis=0))
        std1 = np.std(yy)

        return std0,std1


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
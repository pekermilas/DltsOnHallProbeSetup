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

    @staticmethod
    def testDataLeveling(dataFile, plot=False, method='std'):
        data = iaT.impdData(fName=dataFile)
        data.readData()

        m, c, l = data.findDataLevelsScikitLearn()
        if plot:
            plt.scatter(data.dataValues[list(data.dataValues)[0]]['timeStampImps'],
                        data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'], c=l[:],
                        cmap='coolwarm', s=4)
            plt.show()
        x = np.array(data.dataValues[list(data.dataValues)[0]]['timeStampImps'])
        y = np.array(data.dataValues[list(data.dataValues)[0]]['ImpedanceIm'])

        if method == 'std':
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
            return std0, std1

        if method == 'fit':
            # Data sanity check by fitting
            # ------------------------------------------------------
            xx = x[l[0] == 1]
            yy = y[l[0] == 1]

            xx = xx / xx[0]
            yy = yy / yy[0]
            # Fit linear model using lmfit
            from lmfit.models import LinearModel, PolynomialModel

            # Linear fit
            model_linear = LinearModel()
            params_linear = model_linear.guess(yy, x=xx)
            result_linear = model_linear.fit(yy, params_linear, x=xx)

            # Cubic polynomial fit
            model_cubic = PolynomialModel(degree=3)
            params_cubic = model_cubic.guess(yy, x=xx)
            result_cubic = model_cubic.fit(yy, params_cubic, x=xx)

            # Report linear fit results
            print("\n=== Linear Fit Results ===")
            print(f"Slope: {result_linear.params['slope'].value:.6e} ± {result_linear.params['slope'].stderr:.6e}")
            print(
                f"Intercept: {result_linear.params['intercept'].value:.6e} ± {result_linear.params['intercept'].stderr:.6e}")
            print(f"R-squared: {result_linear.rsquared}")
            print(f"Chi-squared: {result_linear.chisqr}")
            print(f"Reduced chi-squared: {result_linear.redchi}")

            # Report cubic fit results
            print("\n=== Cubic Polynomial Fit Results ===")
            print(f"c3 (x^3 coefficient): {result_cubic.params['c3'].value:.6e} ± {result_cubic.params['c3'].stderr:.6e}")
            print(f"c2 (x^2 coefficient): {result_cubic.params['c2'].value:.6e} ± {result_cubic.params['c2'].stderr:.6e}")
            print(f"c1 (x coefficient): {result_cubic.params['c1'].value:.6e} ± {result_cubic.params['c1'].stderr:.6e}")
            print(f"c0 (constant): {result_cubic.params['c0'].value:.6e} ± {result_cubic.params['c0'].stderr:.6e}")
            print(f"R-squared: {result_cubic.rsquared}")
            print(f"Chi-squared: {result_cubic.chisqr}")
            print(f"Reduced chi-squared: {result_cubic.redchi}")

            plt.figure(figsize=(10, 6))
            plt.scatter(xx, yy, label='Data', s=4, alpha=0.6, color='black')
            yfit_linear = result_linear.best_fit
            yfit_cubic = result_cubic.best_fit
            plt.plot(xx, yfit_linear, 'r-', linewidth=2, label=f'Linear Fit (R²={result_linear.rsquared:.4f})')
            plt.plot(xx, yfit_cubic, 'b-', linewidth=2, label=f'Cubic Fit (R²={result_cubic.rsquared:.4f})')
            plt.xlabel('Normalized Time Stamp')
            plt.ylabel('Normalized Impedance')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.show()
            return result_linear.rsquared,result_cubic.rsquared


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
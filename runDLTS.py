# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 13:11:22 2026

@author: spencer
"""
import serial
import serial.tools.list_ports
import time
import numpy as np
import matplotlib.pyplot as plt
import lmfit
from lmfit.models import *

import time
import zhinst.core
import zhinst.toolkit as zt
import zhinst.ziPython as zi
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC

if __name__ == '__main__':
    
    tempDev = tsC.mK2000B()
    tempDev.connectTempController()
    impdDev = ziC.ziDevice()
    impdDev.connectDevice()
    
    # Set impedance analyzer parameters
    impdDev.getConstants()
    impdDev.setConstants()
    
    # Set temperature controller parameters
    tempDev.setTempGrid()
    
    data = dict()
    for i in range(len(tempDev.tempGrid)):
        tempDev.goToTemp(tempDev.tempGrid[i])
        time.sleep(1)
        data[tempDev.tempGrid[i].item()] = impdDev.pullData(plot=False, trigger=True)
    # 

    # tempDev.disconnTController()
    # impdDev.close()
    impdDev.session.disconnect_device('dev32271')
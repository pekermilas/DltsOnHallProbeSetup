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
    
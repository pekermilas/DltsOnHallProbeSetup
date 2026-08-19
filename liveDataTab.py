import tkinter as tk
import os
import sys
import time

from tkinter import *
from tkinter import ttk
from tkinter import font
from tkinter import filedialog
from PIL import Image, ImageTk
from datetime import datetime
from pathlib import Path

from bokeh.colors.groups import purple
from param.ipython import blue

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT

def construct_livePlotTab():
    root = dltsc.root
    livePlotTab = dltsc.livePlotTab
    tabControl = dltsc.tabControl

    tabControl.add(livePlotTab, text='Live Plot')
    tabControl.pack(expand=1, fill="both")
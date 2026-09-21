import threading
import tkinter as tk
import threading
import time
import os
import json
import copy

from tkinter import *
from tkinter import ttk
from PIL import Image, ImageTk
from datetime import datetime

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt

import numpy as np
from pathlib import Path

import dltsConfig as dltsc
import zurichInstruments_Control as ziC
import instecTempStage_Control as tsC
import impedanceAnalysis_Tools as iaT
import runDlts_Tools as rdT

import runParamsTab as rpT
import liveDataTab as ldT
import postprocessingTab as ppT


dltsc.maxTextLineCount = 10
dltsc.textlinecount = 0
dltsc.textboxes = []
dltsc.root = tk.Tk()
dltsc.root.title('DLTS Control GUI')
try:
    # Start maximized: the Live Tools tab is dense enough that the extra room
    # keeps it from feeling crowded on typical displays.
    dltsc.root.state('zoomed')
except Exception:
    try:
        screen_w = dltsc.root.winfo_screenwidth()
        screen_h = dltsc.root.winfo_screenheight()
        dltsc.root.geometry(f'{screen_w}x{screen_h}+0+0')
    except Exception:
        pass
try:
    screen_h = dltsc.root.winfo_screenheight()
    min_h = min(780, max(760, screen_h - 180))
    dltsc.root.minsize(860, min_h)
except Exception:
    pass

s = ttk.Style()
s.configure('TNotebook.Tab', font=('Arial', 11), padding=6)

dltsc.tabControl = ttk.Notebook(dltsc.root, padding=0)


dltsc.runParamsTab = ttk.Frame(dltsc.tabControl)
rpT.construct_runParamsTab()

dltsc.livePlotTab = ttk.Frame(dltsc.tabControl)
ldT.construct_livePlotTab()

dltsc.postprocessingTab = ttk.Frame(dltsc.tabControl)
# ppT.construct_postprocessingTab()

def on_closing():
    try:
        if hasattr(dltsc, 'tempDev') and dltsc.tempDev is not None and getattr(dltsc.tempDev, 'state', False):
            dltsc.tempDev.disconnect_temp_controller()
    except Exception:
        pass

    try:
        if hasattr(dltsc, 'impDev') and dltsc.impDev is not None:
            if hasattr(dltsc.impDev, 'disconnect_device'):
                dltsc.impDev.disconnect_device()
    except Exception:
        pass

    dltsc.root.destroy()  # Manually close the window

dltsc.root.protocol("WM_DELETE_WINDOW", on_closing)
dltsc.root.mainloop()
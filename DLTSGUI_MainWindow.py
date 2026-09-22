import threading
import tkinter as tk
import threading
import time
import os
import json
import copy
import multiprocessing

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


# Qualitative Analysis' transient extraction runs in a separate process (see
# liveDataTab._compute_zi_transients/_compute_legacy_transients) so it never
# contends with the Tk main thread for the GIL, keeping tab switches and
# redraws responsive no matter how long that extraction takes. Windows'
# 'spawn' start method re-imports this script in the child process, so
# everything that builds/runs the GUI must be guarded behind __name__ ==
# '__main__' -- otherwise the child would open a second GUI (and that one a
# third, ...) instead of just running the extraction function it was asked for.
if __name__ == '__main__':
    multiprocessing.freeze_support()

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

        try:
            if hasattr(dltsc, 'manual_transientExecutor') and dltsc.manual_transientExecutor is not None:
                dltsc.manual_transientExecutor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        dltsc.root.destroy()  # Manually close the window

    dltsc.root.protocol("WM_DELETE_WINDOW", on_closing)
    dltsc.root.mainloop()
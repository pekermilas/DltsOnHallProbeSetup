import tkinter as tk
import threading
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

def start_dlts():
    # Simulate a heavy execution (e.g., file download, scraping, heavy calculations)
    dltsc.log_to_textbox("DLTS run started...")
    dlts = rdT.dltsRun()
    run = dlts.init_experiment()
    if run < 0:
        dltsc.log_to_textbox("Error: Failed to initialize the experiment.")
    else:
        dltsc.log_to_textbox("Experiment initialized successfully.")
        dlts.run_experiment()
        dlts.finish_experiment()
    time.sleep(5)
    dltsc.log_to_textbox("DLTS run completed!")

    # Re-enable the button safely once done
    dltsc.run_button.config(state="normal")

def start_thread():
    # 1. Disable the button to prevent the user from clicking it multiple times
    dltsc.run_button.config(state="disabled")
    # 2. Create a background thread for the heavy task
    taskThread = threading.Thread(target=start_dlts)
    # 3. Set daemon to True so the thread dies instantly if the GUI window is closed
    taskThread.daemon = True
    # 4. Start the background execution
    taskThread.start()

def construct_livePlotTab():
    root = dltsc.root
    livePlotTab = dltsc.livePlotTab
    tabControl = dltsc.tabControl

    tabControl.add(livePlotTab, text='Live Tools')
    tabControl.pack(expand=1, fill="both")

    # Allow tab content to expand with the notebook window.
    dltsc.livePlotTab.grid_rowconfigure(0, weight=0)
    dltsc.livePlotTab.grid_rowconfigure(1, weight=1)
    dltsc.livePlotTab.grid_columnconfigure(0, weight=1)



    runButtonFrame = tk.Frame(dltsc.livePlotTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=220)

    runButtonFrame.grid(row=0, column=0, padx=10, pady=(0, 2), sticky='nsew')
    runButtonFrame.grid_propagate(False)
    runButtonFrame.grid_columnconfigure(0, weight=1)
    runButtonFrame.grid_columnconfigure(1, weight=1)
    runButtonFrame.grid_columnconfigure(2, weight=0)
    runButtonFrame.grid_columnconfigure(3, weight=1)
    runButtonFrame.config()

    dltsc.run_button = tk.Button(runButtonFrame, text="Run DLTS", command=start_thread)
    dltsc.run_button.pack(fill='both', expand=True, padx=4, pady=0)


    reportLivesFrame = tk.Frame(dltsc.livePlotTab, highlightbackground="gray",
                              highlightthickness=1, highlightcolor='gray',
                              width=860, height=220)

    reportLivesFrame.grid(row=1, column=0, padx=10, pady=(0, 2), sticky='nsew')
    reportLivesFrame.grid_propagate(False)
    reportLivesFrame.grid_columnconfigure(0, weight=1)
    reportLivesFrame.grid_columnconfigure(1, weight=1)
    reportLivesFrame.grid_columnconfigure(2, weight=0)
    reportLivesFrame.grid_columnconfigure(3, weight=1)
    reportLivesFrame.config()

    dltsc.textbox = tk.Text(reportLivesFrame, wrap='none', width=1, height=10)
    dltsc.textbox.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
    if not hasattr(dltsc, 'textboxes') or dltsc.textboxes is None:
        dltsc.textboxes = []
    if dltsc.textbox not in dltsc.textboxes:
        dltsc.textboxes.append(dltsc.textbox)

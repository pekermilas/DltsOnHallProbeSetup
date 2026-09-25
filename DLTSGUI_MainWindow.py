import tkinter as tk
import multiprocessing
import matplotlib
matplotlib.use('TkAgg')

from tkinter import ttk

import dltsConfig as dltsc
import runParamsTab as rpT
import liveDataTab as ldT
import dataAnalysisTab as daT
import detailedAnalysisTab as deT


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

    dltsc.dataAnalysisTab = ttk.Frame(dltsc.tabControl)
    daT.construct_dataAnalysisTab()

    dltsc.detailedAnalysisTab = ttk.Frame(dltsc.tabControl)
    deT.construct_detailedAnalysisTab()

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

        try:
            if dltsc.detailed_executor is not None:
                dltsc.detailed_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        dltsc.root.destroy()  # Manually close the window

    dltsc.root.protocol("WM_DELETE_WINDOW", on_closing)
    dltsc.root.mainloop()
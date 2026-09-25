import sys

# Shorten the interpreter's GIL switch granularity (default 5ms) so a CPU-heavy
# background worker (e.g. Qualitative Analysis' transient extraction over many
# files) yields control back to the Tk main thread far more often, keeping tab
# switches and redraws responsive instead of visibly stalling behind it.
sys.setswitchinterval(0.001)

##---------------------GUI-------------------------
# Main GUI constants
root = None
tabControl = None
textbox = None
textboxes = None
textlinecount = None
maxTextLineCount = None

# Main TAB constants
runParamsTab = None
livePlotTab = None
dataAnalysisTab = None
detailedAnalysisTab = None
postprocessingTab = None

##---------------------RUNTIME-------------------------
# Devices
tempDev = None
impDev = None

##---------------------TEST-------------------------
sourcePrefixSelection = None
z_params_vars = dict()
z_params_for_push = dict()
z_param_inputField = None
t_params_vars = dict()
t_params_for_push = dict()
t_param_inputField = None
d_params_vars = dict()
d_params_for_push = dict()
d_param_inputField = None
root_data_folder = None
param_history = None
param_history_labels = None
param_history_selection = None
param_history_inputField = None

run_button = None

##---------------------RUN CONTROL (PAUSE / RESUME / REDO / RETAKE)-------------------------
run_dltsInstance = None     # the live runDlts_Tools.dltsRun instance for the run in progress or
                             # paused, so Pause/Resume/Redo/Retake reach the same connected devices
run_busy = None              # True while ANY run-thread (main sequence, resume, redo, retake) is active
run_pauseRequested = None    # bool: set by the Pause button; the run loop checks it between steps
run_paused = None            # bool: True once the run loop has actually stopped at a pause point
run_stepStatus = None        # tempGrid index -> 'pending' / 'running' / 'done' / 'failed' / 'paused'
run_stepListbox = None       # tk.Listbox showing each temperature grid step + its status
run_pauseButton = None
run_resumeButton = None
run_redoButton = None
run_retakeButton = None

##---------------------RUN FILE WATCH-------------------------
run_dataFolder = None
run_dataFileNames = None
run_outputFileType = None

##---------------------LIVE PLOT (AUTOMATED)-------------------------
livePlot_activeMode = None        # 'live' or 'offline' -- which dataset is currently displayed
livePlot_modeVar = None           # tk.StringVar backing the Live/Offline radio buttons
livePlot_denoiseMethodVar = None  # tk.StringVar backing the denoise dropdown
livePlot_datasetVar = None        # tk.StringVar backing the dataset (temperature) dropdown
livePlot_datasetCombo = None      # the dataset dropdown widget, so its values list can be refreshed
livePlot_figure = None
livePlot_axEmission0 = None
livePlot_axAllEmissions = None
livePlot_canvas = None
livePlot_statusLabel = None

# Live-run state: populated while a Run DLTS experiment is being watched/ingested.
livePlot_liveImpdData = None          # the accumulating impdData instance for the current run
livePlot_liveEmission0Data = None     # temp -> single emission-0 block {x, y/ymean, yFiltered}
livePlot_liveAllEmissionsData = None  # temp -> all emission blocks for that temp {x, y (2D, one column per block)}
livePlot_liveDatasetSel = None        # last-selected dataset (temperature, as a string) while viewing Live
livePlot_liveRunToken = None          # int, bumped each run start to invalidate a stale watcher/worker
livePlot_pollAfterId = None           # id returned by root.after(...) for the live-watch poll, for cancellation
livePlot_processedFiles = None        # set of data file paths already ingested into livePlot_liveImpdData
livePlot_liveIngestBusy = None        # True while a background live-ingest worker is running

# Offline-run state: populated by "Load Existing Run (Offline)", independent of the live state
# above so the user can switch back and forth between Live and Offline without losing either.
livePlot_offlineImpdData = None
livePlot_offlineEmission0Data = None
livePlot_offlineAllEmissionsData = None
livePlot_offlineDatasetSel = None
livePlot_offlineRunToken = None
livePlot_offlineIngestBusy = None

##---------------------MANUAL/QUALITATIVE ANALYSIS-------------------------
manual_dataDirectory = None
# temp -> one of:
#   file path (str)                        -- plain legacy per-temperature file
#   ('legacy_chunk', file_path, chunk_id)   -- legacy chunked CSV (chunk_id may be None)
#   ('zi', data_file, chunk_id)             -- Zurich Instruments chunk; data_file's
#                                              acquisition params live in manual_ziParamsByFile
# Explicitly tagged (rather than bare 2-tuples) so temperatures loaded from
# different-format sources can coexist in one registry after an append.
manual_datasetRegistry = None
manual_ziMode = None              # True/False/'mixed': format of the most recently loaded/combined data
manual_ziParamsByFile = None      # zi data_file path -> {'gridColOffset','gridColDelta','chunkSize'};
                                   # keyed per file so appended ZI sources keep their own acquisition params
manual_ziDataFile = None          # most-recently-loaded ZI data file (status/back-compat display only)
manual_ziGridColOffset = None
manual_ziGridColDelta = None
manual_ziChunkSize = None
manual_sourceFolders = None       # list of folder paths combined into manual_datasetRegistry so far
manual_samplingRate = None
manual_processedTransients = None # temp -> {time_ms, avg_cap_pf, C_infinity}
manual_paramVars = None           # dict of tk.StringVar: fp_ms, rb_ms, slice_start, slice_end
manual_tempListbox = None
manual_folderLabel = None
manual_selectFolderButton = None  # 'Select Source Folder' button, disabled while a worker is running
manual_appendFolderButton = None  # 'Append Source Folder' button, disabled while a worker is running
manual_extractButton = None       # 'Extract & Average Transients' button, disabled while a worker is running
manual_processingBusy = None      # True while _process_raw_transients' background worker is running
manual_loadingBusy = None         # True while _load_manual_directory_async' background worker is running
manual_transientExecutor = None   # persistent ProcessPoolExecutor for _process_raw_transients, so
                                   # repeat extractions skip the child process's one-time import cold-start
manual_figure = None
manual_ax = None
manual_canvas = None
manual_statusLabel = None

##---------------------DATA ANALYSIS (RATE WINDOW / ARRHENIUS)-------------------------
# Rate Window Analysis (top frame). Reads dltsc.manual_processedTransients (populated by
# the Qualitative Analysis "Extract & Average Transients" step in the Live Tools tab)
# rather than loading its own data, mirroring DrKayisScript.py's Tab 2 depending on Tab 1.
rateWindow_dataSourceVar = None   # tk.StringVar: which processed-transients source to analyze
                                   # (Qualitative Analysis / Automated Live / Automated Offline / Auto)
rateWindow_statusLabel = None     # shows which data source actually got used and how many temperatures
rateWindow_signalMethodVar = None # tk.StringVar: Measured C (default) / Smoothed C
rateWindow_denoiseVar = None      # tk.StringVar: 'None (raw)' (default) / pca / wavelet / sgolay / lowess --
                                   # only applies to the Measured C / Smoothed C signal methods
rateWindow_denoisedEmissions = None  # last impdData.calculate_delC_normalized() call's denoised/raw
                                      # emission snapshot, T -> {'x','yRaw','yFiltered','yerr','filterMethod'}
rateWindow_peakMethodVar = None   # tk.StringVar: 'Smoothing Spline' (default) or lmfit curve fit
rateWindow_windowVars = None      # list of 4 (t1Var, t2Var) tk.StringVar pairs, one per rate window set
rateWindow_signals = None         # rw_index -> {'T_k': array, 'Signal': array}
rateWindow_extractedPeaks = None  # rw_index -> {'T_peak':, 'S_peak':, 'e_n':}
rateWindow_peakTable = None       # ttk.Treeview showing per-window fit results
rateWindow_figure = None
rateWindow_ax = None
rateWindow_canvas = None

# Arrhenius Defect Mapping (bottom frame). Consumes rateWindow_extractedPeaks.
arrhenius_ndVar = None            # tk.StringVar, background doping Nd (cm^-3)
arrhenius_energyLabel = None
arrhenius_captureLabel = None
arrhenius_densityLabel = None
arrhenius_figure = None
arrhenius_ax = None
arrhenius_canvas = None

##---------------------DETAILED ANALYSIS (PORTED FROM DLTS_APP.py)-------------------------
# Multi-window ZI MFIA temperature-sweep analysis: many logspace-swept rate
# windows (not just 4) plus the 5 "standard" windows, an Arrhenius panel, an
# optional DLTS spectra panel, a 2D ΔC/C0(t,T) transient map, and a
# Rate-Window Analysis (Nt/Nd) map. Self-contained: its own data folder format
# (one subfolder per temperature) and its own analysis pipeline, independent
# of Qualitative Analysis / Automated Live Data / Quick Analysis's registries.
detailed_data = None          # tempC -> (t_ms array, cap array (pF), C_infinity)
detailed_temps = None         # sorted list of tempC (float, Celsius)
detailed_figure = None        # current matplotlib Figure (rebuilt each run)
detailed_canvas = None        # current FigureCanvasTkAgg embedding detailed_figure
detailed_figFrame = None      # frame the canvas/toolbar are packed into (cleared before each rebuild)
detailed_ax1 = None           # Arrhenius panel (always present after a run)
detailed_ax2 = None           # DLTS Spectra panel (optional)
detailed_ax3 = None           # 2D Transient Map panel (optional)
detailed_ax4 = None           # Rate-Window Analysis map panel (optional)
detailed_leg1 = None
detailed_leg2 = None
detailed_legM = None
detailed_legRW = None
detailed_annBox = None        # draggable Arrhenius results annotation
detailed_lastResMw = None     # last multi-window compute_arrhenius() result dict
detailed_lastResStd = None    # last standard-windows compute_arrhenius() result dict
detailed_lastNt = None
detailed_loadingBusy = None   # True while _detailed_load_data_async's background worker is running
detailedProcessingBusy = None # True while _detailed_run_analysis's background worker is running
detailed_executor = None      # this tab's own single-worker ProcessPoolExecutor: Load/Run math runs
                               # there (own GIL) so it never stalls the Tk main thread or other tabs
detailed_hitTestStale = None  # True between a canvas resize and its redraw, i.e. while legend/annotation
                               # hit-test transforms are stale; the drag press handler redraws only then

# Control variables (tk.StringVar/DoubleVar/IntVar/BooleanVar), seeded in
# construct_detailedAnalysisTab().
detailed_baseVar = None
detailed_gridOffVar = None
detailed_gridDtVar = None
detailed_chunkSizeVar = None
detailed_rbMsVar = None
detailed_cinfLoVar = None
detailed_cinfHiVar = None
detailed_gammaVar = None
detailed_ndVar = None
detailed_tpeakLoVar = None
detailed_tpeakHiVar = None
detailed_peakMethodVar = None # tk.StringVar: per-window peak finder -- lmfit parabola or smoothing spline
detailed_signalMethodVar = None # tk.StringVar: C(t) read-off -- nearest measured sample / spline-interpolated
detailed_denoiseVar = None    # tk.StringVar: 'None (raw)' / pca / wavelet / sgolay / lowess, applied per transient
detailed_nWinVar = None
detailed_t1MinVar = None
detailed_t1MaxVar = None
detailed_ratioVar = None
detailed_stdWinsVar = None
detailed_stdEntries = None    # list of 5 (t1Var, t2Var) DoubleVar pairs, the "standard windows"
detailed_showSpectraVar = None
detailed_nSpectraVar = None
detailed_showTmapVar = None
detailed_showTauVar = None
detailed_showRwmVar = None

# Widgets referenced outside their construction function.
detailed_loadButton = None
detailed_runButton = None
detailed_loadInfoLabel = None
detailed_statusLabel = None
detailed_resultsText = None


def init():
    ##---------------------GUI-------------------------
    # Main GUI constants
    global root
    global tabControl
    global textbox
    global textboxes
    global textlinecount
    global maxTextLineCount

    # Main TAB constants
    global runParamsTab
    global livePlotTab
    global dataAnalysisTab
    global detailedAnalysisTab
    global postprocessingTab

    ##---------------------RUNTIME-------------------------
    # Devices
    global tempDev
    global impDev

    ##---------------------TEST-------------------------
    global sourcePrefixSelection
    global z_params_vars
    global z_params_for_push
    global z_param_inputField
    global t_params_vars
    global t_params_for_push
    global t_param_inputField
    global d_params_vars
    global d_param_inputField
    global root_data_folder
    global param_history
    global param_history_labels
    global param_history_selection
    global param_history_inputField

    global run_button

    ##---------------------RUN CONTROL (PAUSE / RESUME / REDO / RETAKE)-------------------------
    global run_dltsInstance
    global run_busy
    global run_pauseRequested
    global run_paused
    global run_stepStatus
    global run_stepListbox
    global run_pauseButton
    global run_resumeButton
    global run_redoButton
    global run_retakeButton

    ##---------------------RUN FILE WATCH-------------------------
    global run_dataFolder
    global run_dataFileNames
    global run_outputFileType

    ##---------------------LIVE PLOT (AUTOMATED)-------------------------
    global livePlot_activeMode
    global livePlot_modeVar
    global livePlot_denoiseMethodVar
    global livePlot_datasetVar
    global livePlot_datasetCombo
    global livePlot_figure
    global livePlot_axEmission0
    global livePlot_axAllEmissions
    global livePlot_canvas
    global livePlot_statusLabel
    global livePlot_liveImpdData
    global livePlot_liveEmission0Data
    global livePlot_liveAllEmissionsData
    global livePlot_liveDatasetSel
    global livePlot_liveRunToken
    global livePlot_pollAfterId
    global livePlot_processedFiles
    global livePlot_liveIngestBusy
    global livePlot_offlineImpdData
    global livePlot_offlineEmission0Data
    global livePlot_offlineAllEmissionsData
    global livePlot_offlineDatasetSel
    global livePlot_offlineRunToken
    global livePlot_offlineIngestBusy

    ##---------------------MANUAL/QUALITATIVE ANALYSIS-------------------------
    global manual_dataDirectory
    global manual_datasetRegistry
    global manual_ziMode
    global manual_ziParamsByFile
    global manual_ziDataFile
    global manual_ziGridColOffset
    global manual_ziGridColDelta
    global manual_ziChunkSize
    global manual_sourceFolders
    global manual_samplingRate
    global manual_processedTransients
    global manual_paramVars
    global manual_tempListbox
    global manual_folderLabel
    global manual_selectFolderButton
    global manual_appendFolderButton
    global manual_extractButton
    global manual_processingBusy
    global manual_loadingBusy
    global manual_transientExecutor
    global manual_figure
    global manual_ax
    global manual_canvas
    global manual_statusLabel

    ##---------------------DATA ANALYSIS (RATE WINDOW / ARRHENIUS)-------------------------
    global rateWindow_dataSourceVar
    global rateWindow_statusLabel
    global rateWindow_signalMethodVar
    global rateWindow_denoiseVar
    global rateWindow_denoisedEmissions
    global rateWindow_peakMethodVar
    global rateWindow_windowVars
    global rateWindow_signals
    global rateWindow_extractedPeaks
    global rateWindow_peakTable
    global rateWindow_figure
    global rateWindow_ax
    global rateWindow_canvas
    global arrhenius_ndVar
    global arrhenius_energyLabel
    global arrhenius_captureLabel
    global arrhenius_densityLabel
    global arrhenius_figure
    global arrhenius_ax
    global arrhenius_canvas

    ##---------------------DETAILED ANALYSIS (PORTED FROM DLTS_APP.py)-------------------------
    global detailed_data
    global detailed_temps
    global detailed_figure
    global detailed_canvas
    global detailed_figFrame
    global detailed_ax1
    global detailed_ax2
    global detailed_ax3
    global detailed_ax4
    global detailed_leg1
    global detailed_leg2
    global detailed_legM
    global detailed_legRW
    global detailed_annBox
    global detailed_lastResMw
    global detailed_lastResStd
    global detailed_lastNt
    global detailed_loadingBusy
    global detailedProcessingBusy
    global detailed_executor
    global detailed_hitTestStale
    global detailed_baseVar
    global detailed_gridOffVar
    global detailed_gridDtVar
    global detailed_chunkSizeVar
    global detailed_rbMsVar
    global detailed_cinfLoVar
    global detailed_cinfHiVar
    global detailed_gammaVar
    global detailed_ndVar
    global detailed_tpeakLoVar
    global detailed_tpeakHiVar
    global detailed_peakMethodVar
    global detailed_signalMethodVar
    global detailed_denoiseVar
    global detailed_nWinVar
    global detailed_t1MinVar
    global detailed_t1MaxVar
    global detailed_ratioVar
    global detailed_stdWinsVar
    global detailed_stdEntries
    global detailed_showSpectraVar
    global detailed_nSpectraVar
    global detailed_showTmapVar
    global detailed_showTauVar
    global detailed_showRwmVar
    global detailed_loadButton
    global detailed_runButton
    global detailed_loadInfoLabel
    global detailed_statusLabel
    global detailed_resultsText

    z_params_vars = dict()
    z_params_for_push = dict()
    t_params_vars = dict()
    t_params_for_push = dict()
    d_params_vars = dict()

    run_busy = False
    run_pauseRequested = False
    run_paused = False
    run_stepStatus = dict()
    run_dataFileNames = []
    livePlot_activeMode = 'live'
    livePlot_liveRunToken = 0
    livePlot_offlineRunToken = 0
    livePlot_pollAfterId = None
    livePlot_processedFiles = set()
    livePlot_liveEmission0Data = dict()
    livePlot_liveAllEmissionsData = dict()
    livePlot_offlineEmission0Data = dict()
    livePlot_offlineAllEmissionsData = dict()
    livePlot_liveIngestBusy = False
    livePlot_offlineIngestBusy = False
    manual_datasetRegistry = dict()
    manual_ziParamsByFile = dict()
    manual_sourceFolders = list()
    manual_processedTransients = dict()
    manual_paramVars = dict()
    rateWindow_signals = dict()
    rateWindow_extractedPeaks = dict()
    detailed_data = dict()
    detailed_temps = list()
    detailed_loadingBusy = False
    detailedProcessingBusy = False
    detailed_executor = None
    detailed_hitTestStale = True

#-----------------------Global Functions--------------------------------#
def log_to_textbox(message):
    """Appends text to all shared GUI textboxes and manages line limits."""
    global textlinecount
    try:
        _textboxes = list(textboxes) if textboxes else []
    except NameError:
        _textboxes = []
    if not _textboxes:
        try:
            if textbox:
                _textboxes = [textbox]
        except NameError:
            pass
    for tb in _textboxes:
        if tb:
            tb.insert("end", f"{message}\n")
    if _textboxes:
        textlinecount += 1
        if textlinecount > maxTextLineCount:
            for tb in _textboxes:
                if tb:
                    tb.delete("1.0", "2.0")
            textlinecount -= 1

def recast_param_type(device, pname):
    if device == 'impDev':
        if pname in z_params_vars:
            oldValue = z_params_vars[pname].get()
            if pname == 'Oscillation Amplitude':
                newValue = float(oldValue)
            if pname == 'Oscillation Frequency':
                newValue = float(oldValue)
            if pname == 'Oscillation ON/OFF':
                if oldValue == '1 - On':
                    newValue = 1
                if oldValue == '0 - Off':
                    newValue = 0
            if pname == 'Max bandwidth':
                newValue = float(oldValue)
            if pname == 'Input Control':
                if oldValue == '0 - Manual':
                    newValue = 0
                if oldValue == '1 - Auto':
                    newValue = 1
                if oldValue == '2 - Current Zone':
                    newValue = 2
            if pname == 'Current Range':
                newValue = float(oldValue)
            if pname == 'Voltage Range':
                newValue = float(oldValue)
            if pname == 'Omega Suppression':
                newValue = float(oldValue)
            if pname == 'Filter Harmonic':
                newValue = int(oldValue)
            if pname == 'Filter Bandwidth':
                newValue = int(oldValue)
            if pname == 'Data Transfer Rate':
                newValue = int(oldValue)
            if pname == 'Equivalent Circuit Mode':
                if oldValue == '0 - 4-Terminal':
                    newValue = 0
                if oldValue == '1 - 2-Terminal':
                    newValue = 1
            if pname == 'Threshold Input Signal':
                if oldValue == '59 - TU Output Value':
                    newValue = 59
                if oldValue == '58 - Aux Output Overload':
                    newValue = 58
                if oldValue == '56 - Aux Input Overload':
                    newValue = 56
                if oldValue == '55 - Output Overload':
                    newValue = 55
                if oldValue == '54 - Input(I) Overload':
                    newValue = 54
                if oldValue == '53 - Input(V) Overload':
                    newValue = 53
                if oldValue == '52 - Trigger Out':
                    newValue = 52
                if oldValue == '51 - Trigger In':
                    newValue = 51
                if oldValue == '50 - DIO':
                    newValue = 50
                if oldValue == '3 - Demod Theta':
                    newValue = 3
                if oldValue == '2 - Demod R':
                    newValue = 2
                if oldValue == '1 - Demod Y':
                    newValue = 1
                if oldValue == '0 - Demod X':
                    newValue = 0
            if pname == 'State Enable Time':
                newValue = float(oldValue)
            if pname == 'State Disable Time':
                newValue = float(oldValue)
            if pname == 'Logic Unit Not':
                if oldValue == '0 - Off':
                    newValue = 0
                if oldValue == '1 - On':
                    newValue = 1
            if pname == 'Aux Output Signal':
                if oldValue == '0 - Demod X':
                    newValue = 0
                if oldValue == '1 - Demod Y':
                    newValue = 1
                if oldValue == '2 - Demod R':
                    newValue = 2
                if oldValue == '3 - Demod Theta':
                    newValue = 3
                if oldValue == '11 - TU Filtered Value':
                    newValue = 11
                if oldValue == '12 - Manual':
                    newValue = 12
                if oldValue == '13 - TU Output Value':
                    newValue = 13
            if pname == 'Aux Output Scale':
                newValue = float(oldValue)
            if pname == 'Aux Output Offset':
                newValue = float(oldValue)
            if pname == 'Aux Output Lower Limit':
                newValue = float(oldValue)
            if pname == 'Aux Output Upper Limit':
                newValue = float(oldValue)
            if pname == 'Signal Output Add':
                if oldValue == '1 - True':
                    newValue = 1
                if oldValue == '0 - False':
                    newValue = 0
            if pname == 'Trigger Source Signal':
                if oldValue == '0 - Off':
                    newValue = 0
                if oldValue == '1 - Osc Phi Demod 2':
                    newValue = 1
                if oldValue == '36 - Threshold 1':
                    newValue = 36
                if oldValue == '37 - Threshold 2':
                    newValue = 37
                if oldValue == '38 - Threshold 3':
                    newValue = 38
                if oldValue == '39 - Threshold 4':
                    newValue = 39
                if oldValue == '52 - MDS Sync Out':
                    newValue = 52
    if device == 'tempDev':
        if pname in t_params_vars:
            oldValue = t_params_vars[pname].get()
            if pname == 'Initial Temperature (C)':
                newValue = float(oldValue)
            if pname == 'Final Temperature (C)':
                newValue = float(oldValue)
            if pname == 'Temperature Step (C)':
                newValue = float(oldValue)
            if pname == 'Temperature Ramp (C/min)':
                newValue = float(oldValue)
            if pname == 'Stability Delay (s)':
                newValue = int(oldValue)
    if device == 'output':
        if pname in d_params_vars:
            oldValue = d_params_vars[pname].get()
            if pname == 'Number of Points (power of 2)':
                newValue = int(oldValue)
            if pname == 'Number of Reps':
                newValue = int(oldValue)

    return newValue


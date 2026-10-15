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
trapConcentrationTab = None
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
run_abortRequested = None    # bool: set when the GUI is closing; the run loop stops at the next check
                             # and discards a step whose acquisition overlapped the close

##---------------------APP CLOSE (RETURN TO ROOM TEMPERATURE)-------------------------
app_closing = None           # True once the window's close was requested (guards repeat clicks)
app_roomReturnSent = None    # True once the room-temperature ramp has been commanded on the way out,
                             # so the exit/console-close backstop doesn't send it again
app_closeDialog = None       # Toplevel shown while waiting for the stage to reach room temperature
app_closeStatusLabel = None  # its live "stage at X C -> room Y C" label
app_closeNowRequested = None # True when "Close now" was clicked: stop waiting, leave the controller ramping

##---------------------RUN FILE WATCH-------------------------
run_dataFolder = None
run_startTime = None         # datetime the run started (its folder's MMDDYY\HHMMSS); left end of the Temperature Trace
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

##---------------------MANUAL/QUALITATIVE ANALYSIS (LIVE TOOLS, LIVE RUN ONLY)-------------------------
# temp C -> step file path of the run folder being followed (legacy per-temperature
# entries only; see quickData_datasetRegistry for every format a saved folder can hold)
manual_datasetRegistry = None
manual_samplingRate = None
manual_processedTransients = None # temp -> {time_ms, avg_cap_pf, C_infinity, setpoint_C, stage_C, acquired_at}
manual_paramVars = None           # dict of tk.StringVar: fp_ms, rb_ms, slice_start, slice_end
manual_autoSliceEnd = None        # last Analysis Slice End (ms) set automatically from Reverse Bias;
                                   # while slice_end still holds it, it follows rb_ms edits
manual_tempListbox = None
manual_folderLabel = None         # 'Run folder: ...' label of the Live Run group
manual_extractButton = None       # 'Extract & Average Transients' button, disabled while a worker is running
manual_processingBusy = None      # True while _process_raw_transients' background worker is running
manual_transientExecutor = None   # persistent ProcessPoolExecutor for transient extraction (live frame and
                                   # Quick Analysis loader), so repeat extractions skip the child
                                   # process's one-time import cold-start
manual_figure = None
manual_ax = None                  # left axes: Averaged Capacitance Transients Profile
manual_axTemps = None             # right axes: Temperature Trace (°C vs time of measurement)
manual_canvas = None
manual_statusLabel = None
manual_liveFollowVar = None       # tk.BooleanVar: 'Follow live run' -- re-extract as run files are written
manual_liveRunFolder = None       # run folder the Qualitative frame adopted as its source while following
manual_liveFileMtimes = None      # run data file -> mtime it was last extracted at (new/rewritten = changed)
manual_livePollActive = None      # True while the follow loop (_qualitative_live_tick) is scheduled

##---------------------QUICK ANALYSIS: OFFLINE DATA (SAVED FOLDER LOADER)-------------------------
quickData_dataDirectory = None    # most recently selected (not appended) folder; the dialogs start there
# temp C -> one of:
#   file path (str)                        -- plain legacy per-temperature file
#   ('legacy_chunk', file_path, chunk_id)   -- legacy chunked CSV (chunk_id may be None)
#   ('zi', data_file, chunk_id)             -- Zurich Instruments chunk; data_file's
#                                              acquisition params live in quickData_ziParamsByFile
#   ('zi_subfolder', data_file, None)       -- ZI per-temperature subfolder export
# Explicitly tagged (rather than bare 2-tuples) so temperatures loaded from
# different-format sources can coexist in one registry after an append.
quickData_datasetRegistry = None
quickData_ziParamsByFile = None   # zi data_file path -> {'gridColOffset','gridColDelta','chunkSize'};
                                   # keyed per file so appended ZI sources keep their own acquisition params
quickData_sourceFolders = None    # list of folder paths combined into quickData_datasetRegistry so far
quickData_processedTransients = None  # temp -> {time_ms, avg_cap_pf, C_infinity, ...}: the 'Loaded Folder'
                                       # Data Source of Rate Window Analysis
quickData_paramVars = None        # dict of tk.StringVar: fp_ms, rb_ms
quickData_tempListbox = None
quickData_folderLabel = None
quickData_selectFolderButton = None   # disabled while a scan/extraction is running
quickData_appendFolderButton = None
quickData_extractButton = None
quickData_statusLabel = None
quickData_loadingBusy = None      # True while _scan_quick_folder_async' background worker is running
quickData_processingBusy = None   # True while _extract_quick_transients' background worker is running

##---------------------DATA ANALYSIS (RATE WINDOW / ARRHENIUS)-------------------------
# Rate Window Analysis. Reads averaged transients from its Data Source: the Offline
# Data column's loaded folder (dltsc.quickData_processedTransients), the live run's
# Qualitative Analysis (dltsc.manual_processedTransients), or Automated/Live Data.
rateWindow_dataSourceVar = None   # tk.StringVar: which processed-transients source to analyze
                                   # (Loaded Folder / Live Run Qualitative / Automated Live /
                                   # Automated Offline / Auto)
rateWindow_statusLabel = None     # shows which data source actually got used and how many temperatures
rateWindow_signalMethodVar = None # tk.StringVar: Measured C (default) / Smoothed C
rateWindow_denoiseVar = None      # tk.StringVar: 'None (raw)' (default) / pca / wavelet / sgolay / lowess --
                                   # only applies to the Measured C / Smoothed C signal methods
rateWindow_denoisedEmissions = None  # last impdData.calculate_delC_normalized() call's denoised/raw
                                      # emission snapshot, T -> {'x','yRaw','yFiltered','yerr','filterMethod'}
rateWindow_windowVars = None      # list of 5 (t1Var, t2Var) tk.StringVar pairs, one per rate window set
rateWindow_signals = None        # rw_index -> {'T_k': array (sorted), 'Signal': array, 'Signal_err': array
                                   # or None, 't1':, 't2': (ms), 'e_n': (s^-1)} of the last Compute
rateWindow_extractedPeaks = None  # Extracted Peaks row id 'w<set>r<region>p<peak>' -> {'set':, 'region':,
                                   # 'peakId': 'R<n>P<n>', 'primitive':, 'T_peak':, 'T_peak_err':, 'S_peak':,
                                   # 'S_peak_err':, 'onEdge':, 'e_n':, 't1':, 't2':} from Peak Deconvolution
rateWindow_rowInfo = None         # every Extracted Peaks row id -> (set index, peakId or None for a
                                   # 'no peak' / 'fit failed' row)
rateWindow_peakTable = None       # ttk.Treeview showing per-peak deconvolution results
rateWindow_figure = None
rateWindow_ax = None
rateWindow_canvas = None

# Peak Deconvolution (middle frame). Splits each rate window set's S(T) into
# primitives, region by region; fills rateWindow_extractedPeaks.
deconv_regions = None             # list of {'tLo':, 'tHi': (K), 'primitives': [PRIMITIVE_OPTIONS labels],
                                   # 'prominence': (fraction, Smoothing Spline regions only)}
deconv_results = None             # set index -> one dataAnalysisTab._deconvolve_region() result per region
deconv_displaySetVar = None       # tk.StringVar 'Set n': the set the deconvolution plot shows
deconv_displaySetCombo = None
deconv_regionListbox = None
deconv_primitiveListbox = None    # primitives of the region selected in deconv_regionListbox
deconv_primitiveVar = None        # tk.StringVar: primitive to add
deconv_tLoVar = None              # tk.StringVar: region lower bound (K), also set by dragging on the plot
deconv_tHiVar = None              # tk.StringVar: region upper bound (K)
deconv_prominenceVar = None       # tk.StringVar: Smoothing Spline minimum prominence (fraction)
deconv_fitInfoLabel = None        # per-region fit quality of the displayed set
deconv_statusLabel = None
deconv_spanSelector = None        # matplotlib SpanSelector on deconv_ax (rebuilt on every redraw)
deconv_figure = None
deconv_ax = None
deconv_residAx = None
deconv_canvas = None

# Arrhenius Defect Mapping (right frame). Consumes rateWindow_extractedPeaks.
arrhenius_ndVar = None            # tk.StringVar, background doping Nd (cm^-3)
arrhenius_gammaVar = None         # tk.StringVar, emission pre-factor gamma (cm^-2 s^-1 K^-2) for sigma
arrhenius_trapTable = None        # ttk.Treeview: one row per trap (peakId) -- Et, sigma, Nt, sets used
arrhenius_trapResults = None      # list of the last solver run's dA._arrhenius_fit results, one per
                                   # trap, plus 'peakId', 'Nt', 'Nt_err'
arrhenius_figure = None
arrhenius_ax = None
arrhenius_canvas = None
arrhenius_windowPoints = None     # Extracted Peaks row id -> (1000/T, ln(e_n/T^2)) of each point the last
                                   # solver run plotted
arrhenius_highlightArtists = None # matplotlib Line2D star markers for the peaks selected in the
                                   # Extracted Peaks table (removed and redrawn on each selection change)

##---------------------DETAILED ANALYSIS (PORTED FROM DLTS_APP.py)-------------------------
# Multi-window ZI MFIA temperature-sweep analysis: many logspace-swept rate
# windows (not just 4) plus the 5 "standard" windows, an Arrhenius panel, an
# optional DLTS spectra panel, a ΔC/C0(t,T) transient map, and a
# Rate-Window Analysis (Nt/Nd) map -- each panel its own figure and toolbar. Self-contained: its own data folder format
# (one subfolder per temperature) and its own analysis pipeline, independent
# of Qualitative Analysis / Automated Live Data / Quick Analysis's registries.
detailed_data = None          # tempC -> (t_ms array, cap array (pF), C_infinity)
detailed_temps = None         # sorted list of tempC (float, Celsius)
detailed_figFrame = None      # frame the panels (figure + toolbar each) are gridded into
detailed_figures = None       # panel key ('arr', 'spec', 'tmap', 'rwm') -> Figure of each shown panel
detailed_canvases = None      # panel key -> FigureCanvasTkAgg of that Figure
detailed_panelAxes = None     # panel key -> its main Axes (2D or 3D)
detailed_panelLegends = None  # panel key -> its legend beside the plot, or None (per its Labels choice)
detailed_linkCids = None      # panel key -> pending draw_event connection that links its x axis to its
                               # row partner's (see _detailed_link_panel)
detailed_linkBusy = None      # True while one linked panel sets its partner's x limits
detailed_lastOut = None       # last run's _compute_detailed_analysis result, redrawn on Display changes
detailed_lastParams = None    # the parameter snapshot that run used
detailed_lastResMw = None     # last run's first trap, multi-window _arrhenius_fit result dict
detailed_lastResStd = None    # last run's first trap, standard-windows result dict (or None)
detailed_lastNt = None        # last run's total Nt (all traps, transient amplitude)
detailed_lastTraps = None     # last run's multi-window results, one per trap (peak id R<r>P<k>)
detailed_lastTrapsStd = None  # last run's standard-window results, one per trap
detailed_regions = None       # peak regions: list of {'tLo', 'tHi' (K), 'primitives' ([] = default
                               # single-peak finder), 'prominence', 'source' ('Quick R<n>' or None)}
detailed_regionListbox = None
detailed_regionMethodVar = None   # tk.StringVar: method of the selected region (default / a Quick region)
detailed_regionMethodCombo = None
detailed_spanSelector = None  # matplotlib SpanSelector on the DLTS Spectra panel (picks a region's T range)
detailed_loadingBusy = None   # True while _detailed_load_data_async's background worker is running
detailedProcessingBusy = None # True while _detailed_run_analysis's background worker is running
detailed_executor = None      # this tab's own single-worker ProcessPoolExecutor: Load/Run math runs
                               # there (own GIL) so it never stalls the Tk main thread or other tabs

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
detailed_tpeakLoVar = None    # T min / T max (K) boxes of the Peak Regions controls
detailed_tpeakHiVar = None
detailed_peakMethodVar = None # tk.StringVar: default per-window peak finder for regions without primitives --
                               # lmfit parabola or smoothing spline
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
detailed_arrViewVar = None    # Display: Arrhenius 2D / 3D (peak height up)
detailed_tmapViewVar = None   # Display: transient map 2D colour map / 3D isohypse surface
detailed_rwmViewVar = None    # Display: rate-window map 2D colour map / 3D isohypse surface
detailed_arrLabelsVar = None  # Display: the one set of labels each panel shows (legend, trap ids, ...)
detailed_specLabelsVar = None
detailed_tmapLabelsVar = None
detailed_rwmLabelsVar = None
detailed_tFeVar = None        # fill-end time t_FE (ms): e_n and f(r) from the fill end (Dr. Kayi's v3.1)
detailed_c0PrePulseVar = None # tk.BooleanVar: C0 = min(pre-pulse level, tail mean) for step files (v3.1)
detailed_trapPresetVar = None # tk.StringVar: Z1/Z2, EH6/EH7 or Custom range -- fills T min / T max
detailed_methodTableVar = None  # tk.BooleanVar: redo the analysis with every peak method (results table)
detailed_stabilityVar = None  # tk.BooleanVar: range-stability scan of the primitive regions

# Widgets referenced outside their construction function.
detailed_loadButton = None
detailed_runButton = None
detailed_loadInfoLabel = None
detailed_statusLabel = None
detailed_resultsText = None
detailed_loadInfo = None      # _load_detailed_data_full's loadInfo of the loaded folder (fill pulses, f_osc,
                               # capacitance mode, 2nd pulse, t_FE of its format)
detailed_folder = None        # the loaded folder

##---------------------TRAP CONCENTRATION TAB-------------------------
# Nt with Dr. Kayi's v3.1 corrections (N_D(T), fill-pulse geometry g,
# large-signal term) from the traps of the last Detailed / Quick Analysis run,
# the fill-pulse scan analysis, and the sample comparison. Seeded in
# construct_trapConcentrationTab().
trapconc_sourceUpdated = None # callable(source) the analysis tabs call after a run, so Nt follows them
trapconc_sourceVar = None     # tk.StringVar: 'Detailed Analysis' / 'Quick Analysis'
trapconc_ndVar = None         # N_D from C-V (cm^-3)
trapconc_geomOnVar = None     # tk.BooleanVar: fill-pulse geometry correction
trapconc_vFillVar = None      # fill / reverse bias (V), set from AuxInput1 when the fill bias is consistent
trapconc_vRevVar = None
trapconc_vbiVar = None
trapconc_diamVar = None       # device diameter (mm)
trapconc_epsRVar = None
trapconc_wfModeVar = None     # W_F source: Measured C_fill / C-V ratio / V_bi model
trapconc_wfRatioVar = None
trapconc_lsVar = None         # tk.BooleanVar: large-signal term Nt = N_D a (2 - a) / g
trapconc_ndScaleVar = None    # tk.BooleanVar: N_D(T) = N_D (C0(T)/C0(T_ref))^2
trapconc_tRefVar = None       # T_ref (K) of the C-V measurement
trapconc_lastResults = None   # list of (trap, dP.trap_concentration result) of the last calculation
trapconc_lastSource = None    # dict describing the source of that calculation (name, tFe, nd, C0, fill)
trapconc_lastGeom = None      # geometry dict that calculation used
trapconc_recalcJob = None     # pending Tk after() id of a debounced recalculation
trapconc_figure = None
trapconc_canvas = None
trapconc_resultsText = None
trapconc_statusLabel = None
# Fill-pulse scan analysis
trapconc_fsFolders = None     # list of scan folders (bias and/or width scans)
trapconc_fsFolderLabel = None
trapconc_fsEtVar = None       # Et (eV) used for λ
trapconc_fsTVar = None        # scan temperature (K)
trapconc_fsT1Var = None       # ΔC = C(t2) - C(t1) after the pulse (ms)
trapconc_fsT2Var = None
trapconc_fsResult = None
trapconc_fsFigure = None
trapconc_fsCanvas = None
trapconc_fsText = None
# Sample comparison
trapconc_samples = None       # list of dict(name, data, temps, color)
trapconc_sampleListbox = None
trapconc_sampleNameVar = None # name for the next sample added ('' = folder name)
trapconc_swT1Var = None       # single rate window t1 / t2 (ms) and their log10 slider positions
trapconc_swT2Var = None
trapconc_swS1Var = None
trapconc_swS2Var = None
trapconc_swLock = None
trapconc_swInfoLabel = None
trapconc_spNormVar = None     # display options
trapconc_spLineVar = None
trapconc_spFitVar = None
trapconc_spPeaksVar = None
trapconc_spTLoVar = None      # peak / fit range (K), '' = the Detailed Analysis T min / T max
trapconc_spTHiVar = None
trapconc_spFigure = None
trapconc_spAx = None
trapconc_spCanvas = None
trapconc_spText = None
trapconc_spJob = None
trapconc_spCsv = None         # {sample name: (T (K), S)} of the last plot, for Export CSV
trapconc_spLoadingBusy = None


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
    global trapConcentrationTab
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
    global run_abortRequested

    ##---------------------APP CLOSE (RETURN TO ROOM TEMPERATURE)-------------------------
    global app_closing
    global app_roomReturnSent
    global app_closeDialog
    global app_closeStatusLabel
    global app_closeNowRequested

    ##---------------------RUN FILE WATCH-------------------------
    global run_dataFolder
    global run_startTime
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
    global manual_datasetRegistry
    global manual_samplingRate
    global manual_processedTransients
    global manual_paramVars
    global manual_autoSliceEnd
    global manual_tempListbox
    global manual_folderLabel
    global manual_extractButton
    global manual_processingBusy
    global manual_transientExecutor
    global manual_figure
    global manual_ax
    global manual_axTemps
    global manual_canvas
    global manual_statusLabel
    global manual_liveFollowVar
    global manual_liveRunFolder
    global manual_liveFileMtimes
    global manual_livePollActive

    ##---------------------QUICK ANALYSIS: OFFLINE DATA (SAVED FOLDER LOADER)-------------------------
    global quickData_dataDirectory
    global quickData_datasetRegistry
    global quickData_ziParamsByFile
    global quickData_sourceFolders
    global quickData_processedTransients
    global quickData_paramVars
    global quickData_tempListbox
    global quickData_folderLabel
    global quickData_selectFolderButton
    global quickData_appendFolderButton
    global quickData_extractButton
    global quickData_statusLabel
    global quickData_loadingBusy
    global quickData_processingBusy

    ##---------------------DATA ANALYSIS (RATE WINDOW / ARRHENIUS)-------------------------
    global rateWindow_dataSourceVar
    global rateWindow_statusLabel
    global rateWindow_signalMethodVar
    global rateWindow_denoiseVar
    global rateWindow_denoisedEmissions
    global rateWindow_windowVars
    global rateWindow_signals
    global rateWindow_extractedPeaks
    global rateWindow_rowInfo
    global rateWindow_peakTable
    global rateWindow_figure
    global rateWindow_ax
    global rateWindow_canvas
    global deconv_regions
    global deconv_results
    global deconv_displaySetVar
    global deconv_displaySetCombo
    global deconv_regionListbox
    global deconv_primitiveListbox
    global deconv_primitiveVar
    global deconv_tLoVar
    global deconv_tHiVar
    global deconv_prominenceVar
    global deconv_fitInfoLabel
    global deconv_statusLabel
    global deconv_spanSelector
    global deconv_figure
    global deconv_ax
    global deconv_residAx
    global deconv_canvas
    global arrhenius_ndVar
    global arrhenius_gammaVar
    global arrhenius_trapTable
    global arrhenius_trapResults
    global arrhenius_figure
    global arrhenius_ax
    global arrhenius_canvas
    global arrhenius_windowPoints
    global arrhenius_highlightArtists

    ##---------------------DETAILED ANALYSIS (PORTED FROM DLTS_APP.py)-------------------------
    global detailed_data
    global detailed_temps
    global detailed_figFrame
    global detailed_figures
    global detailed_canvases
    global detailed_panelAxes
    global detailed_panelLegends
    global detailed_linkCids
    global detailed_linkBusy
    global detailed_lastOut
    global detailed_lastParams
    global detailed_lastResMw
    global detailed_lastResStd
    global detailed_lastNt
    global detailed_lastTraps
    global detailed_lastTrapsStd
    global detailed_regions
    global detailed_regionListbox
    global detailed_regionMethodVar
    global detailed_regionMethodCombo
    global detailed_spanSelector
    global detailed_loadingBusy
    global detailedProcessingBusy
    global detailed_executor
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
    global detailed_arrViewVar
    global detailed_tmapViewVar
    global detailed_rwmViewVar
    global detailed_arrLabelsVar
    global detailed_specLabelsVar
    global detailed_tmapLabelsVar
    global detailed_rwmLabelsVar
    global detailed_loadButton
    global detailed_runButton
    global detailed_loadInfoLabel
    global detailed_statusLabel
    global detailed_resultsText
    global detailed_tFeVar
    global detailed_c0PrePulseVar
    global detailed_trapPresetVar
    global detailed_methodTableVar
    global detailed_stabilityVar
    global detailed_loadInfo
    global detailed_folder
    global trapconc_sourceUpdated
    global trapconc_lastResults
    global trapconc_lastSource
    global trapconc_lastGeom
    global trapconc_recalcJob
    global trapconc_fsFolders
    global trapconc_fsResult
    global trapconc_samples
    global trapconc_swLock
    global trapconc_spJob
    global trapconc_spCsv
    global trapconc_spLoadingBusy

    z_params_vars = dict()
    z_params_for_push = dict()
    t_params_vars = dict()
    t_params_for_push = dict()
    d_params_vars = dict()

    run_busy = False
    run_pauseRequested = False
    run_paused = False
    run_abortRequested = False
    app_closing = False
    app_roomReturnSent = False
    app_closeNowRequested = False
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
    manual_processedTransients = dict()
    manual_paramVars = dict()
    manual_autoSliceEnd = 490.0
    manual_liveFileMtimes = dict()
    manual_livePollActive = False
    quickData_datasetRegistry = dict()
    quickData_ziParamsByFile = dict()
    quickData_sourceFolders = list()
    quickData_processedTransients = dict()
    quickData_paramVars = dict()
    quickData_loadingBusy = False
    quickData_processingBusy = False
    rateWindow_signals = dict()
    rateWindow_extractedPeaks = dict()
    rateWindow_rowInfo = dict()
    deconv_regions = list()
    deconv_results = dict()
    arrhenius_trapResults = list()
    arrhenius_windowPoints = dict()
    arrhenius_highlightArtists = list()
    detailed_data = dict()
    detailed_regions = list()
    detailed_temps = list()
    detailed_loadingBusy = False
    detailedProcessingBusy = False
    detailed_executor = None
    detailed_figures = dict()
    detailed_canvases = dict()
    detailed_panelAxes = dict()
    detailed_panelLegends = dict()
    detailed_linkCids = dict()
    detailed_linkBusy = False
    detailed_loadInfo = dict()
    detailed_folder = None
    trapconc_sourceUpdated = None
    trapconc_lastResults = list()
    trapconc_lastSource = None
    trapconc_lastGeom = None
    trapconc_recalcJob = None
    trapconc_fsFolders = list()
    trapconc_fsResult = None
    trapconc_samples = list()
    trapconc_swLock = False
    trapconc_spJob = None
    trapconc_spCsv = dict()
    trapconc_spLoadingBusy = False

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
    if not _textboxes:
        # No GUI (the instrument classes or dltsRun used from a script): print
        # instead, so warnings such as pull_data()'s acquisition timeout are seen.
        print(message)
        return
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
            if pname == 'Room Temperature (C)':
                newValue = float(oldValue)
            if pname == 'Room Ramp (C/min)':
                newValue = float(oldValue)
    if device == 'output':
        if pname in d_params_vars:
            oldValue = d_params_vars[pname].get()
            if pname == 'Number of Points (power of 2)':
                newValue = int(oldValue)
            if pname == 'Number of Reps':
                newValue = int(oldValue)

    return newValue


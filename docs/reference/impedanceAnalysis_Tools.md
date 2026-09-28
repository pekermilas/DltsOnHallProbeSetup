# impedanceAnalysis_Tools

`impedanceAnalysis_Tools.py` is the analysis library for DLTS runs. It loads the per-temperature step files a run writes (`.h5`, JSON in `.txt`/`.json`, or Zurich Instruments LabOne `.csv` exports), repairs the time axis, splits each record into excitation (fill pulse) and emission blocks by clustering the pulse signal, averages the emission transients, denoises them, and computes the double-boxcar DLTS signal with error propagation. It also holds the peak finders used to locate the DLTS peak temperature.

Where the GUI uses it:

| GUI file | What it calls |
|---|---|
| `liveDataTab.py` | Live mode: `impdData(fName=[path])` + `read_data()` for the first file, then `append_data(fName=[path])` for each new step, on a worker thread; then `cleanup_data()`, `selected_emissions(emissionIndex=0)`, `filter_emissions(method=..., emissionIndex=0, recalculate=True, interactivePlot=False)`, `selected_emissions(emissionIndex=-1)`. Offline mode: the same chain after `read_data()` on the chosen files. Also `read_h5_record(filePath, keys=('AuxInput1', 'ImpedanceIm'))`. |
| `dataAnalysisTab.py` (Quick Analysis) | `impd.calculate_delC_normalized(...)` for each rate window, then `impdData._curveFit_peakFinder(...)` or `impdData._smoothingSpline_peakFinder(...)` for the peak. |
| `detailedAnalysisTab.py` | `impdData._pca_denoise`, `_wavelet_denoise`, `_savitzkyGolay_denoise`, `_lowess_denoise` on averaged transients, and `impdData._smoothingSpline_peakFinder` for Tp. |
| `runParamsTab.py`, `runDLTS.py` | Import the module; no live calls (comments and commented-out code only). |

## Import

```python
import impedanceAnalysis_Tools as iaT

impd = iaT.impdData(fName=[r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5"])
```

Importing the module also imports `zhinst.core`, `zhinst.toolkit`, `torch`, `zurichInstruments_Control` and `instecTempStage_Control`, so those packages must be installed even for offline analysis. The import does not connect to any hardware.

## Module constants and globals

The module defines no named constants. The table lists every module-level name and import-time setting, followed by the literal values hard-coded inside functions that act as constants.

| Name | Value / type | Meaning |
|---|---|---|
| `GAP_FACTOR` | `100` | `cleanup_data()` / `_gap_remove`: a time step larger than this many typical (median) steps is a gap and is closed. |
| `_STEP_STEM_PATTERN` | regex `^([npNP]?)(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?$` | Step file name without extension → sign, whole degrees, decimals. Same rule as `liveDataTab._LEGACY_FILENAME_PATTERN`; a missing sign letter means positive. |
| `_CSV_NAME_PATTERN` | regex `^([npNP]?)(\d+)(?:[pP.](\d+))?C_` | ZI export history name (`25C_000`, `n10C_000`, `p25p5C_000`) → sign, whole degrees, decimals. |
| `read_h5_record` | function | Reads one HDF5 step file. See [Module-level functions](#module-level-functions). |
| `impdData` | class | The analysis class. |
| `warnings.filterwarnings("ignore", category=FutureWarning, module="uncertainties")` | import-time setting | Silences `FutureWarning`s raised by the `uncertainties` package. Other warnings (for example `UserWarning: Using UFloat objects with std_dev==0`) still print. |
| `zi`, `zt` | modules `zhinst.core`, `zhinst.toolkit` | Imported, not used in this file. |
| `ziC`, `tsC` | modules `zurichInstruments_Control`, `instecTempStage_Control` | Imported, not used in this file. |
| `np`, `plt`, `pd`, `h5py`, `json`, `os`, `re`, `pywt` | modules | Used. |
| `sm`, `torch`, `lmfit`, `time`, `itertools`, `statistics` | modules | Imported; `lmfit` is used only through `lmfit.models`; the others are unused. |
| `askopenfilenames` | `tkinter.filedialog` function | Opens the file-picker dialog when no file names are given. |
| `GaussianMixture`, `KMeans`, `PCA` | scikit-learn classes | Used for level clustering and PCA denoising. |
| `savgol_filter`, `UnivariateSpline`, `CubicSpline`, `differential_evolution` | SciPy functions/classes | Used. |
| `GaussianModel`, `PseudoVoigtModel`, `VoigtModel`, `LorentzianModel` | lmfit models | Used by `_curveFit_peakFinder`. |
| `ufloat` | `uncertainties` function | Used for error propagation in `calculate_delC_normalized`. |
| `Lowess` | `fastlowess` class | Used by `_lowess_denoise`. |
| `apply_along_axis`, `unumpy`, `FastICA`, `weibull_min`, `mode`, `quad`, `BSpline`, `interp2d`, `LognormalModel` | various | Imported, not used. |

Hard-coded values inside functions:

| Value | Where | Meaning |
|---|---|---|
| `60 * 10**6` | `_ticks_per_second`, CSV branch of `read_data`/`append_data` | Instrument clock rate in ticks per second (60 MHz). |
| `+ 273.15`, rounded to 1e-6 K | `_celsius_to_kelvin_key` | °C to K conversion of the setpoint in a file or history name. |
| `20.0 *` second minimum | `find_data_levels_scikit` | A minimum more than 20 times larger in magnitude than the second-smallest value marks the record unusable. |
| `n_components=2`, `reg_covar=1e-8`, `random_state=0`; `n_clusters=2`, `n_init=10` | `find_data_levels_scikit` | GMM and K-Means settings (two levels). |
| `headerKeys[16]` | CSV branch of `read_data`/`append_data` | Column 17 of the LabOne header file holds the per-chunk data names that carry the temperature. |
| `trimHead=10`, `trimTail=10` | `selected_emissions`, `filter_emissions`, `calculate_delC_normalized` | Samples dropped at each end of an emission block. `calculate_delC_normalized` always uses 10/10. |
| `window_size=100`; `wavelet="db4", level=4, mode="soft"`; `window_size=None, order=2`; `fraction=None` (becomes 0.1) | `filter_emissions` | Fixed denoiser settings. |
| `iterations=3`, `robustness_method="bisquare"` | `_lowess_denoise` | LOWESS settings. |
| 100000 points; 2000 points | `_smoothingSpline_peakFinder` | Fine grid for the spline peak; coarser grid for bootstrap peaks. |
| 2000 points | `_curveFit_peakFinder` | Grid for the fitted curve. |

## Data model

All data lives in attributes of one `impdData` instance. Temperatures are kelvin floats everywhere; they come from the file name in °C, keep their decimals and are converted with `round(T_C + 273.15, 6)` (`p25p0` → 298.15, `p50p5` → 323.65, `n10p0` → 263.15). Convert back with `round(T_K - 273.15, 6)`.

```text
impd.dataTemps  = [298.15, 303.15, 308.15, ...]  # list[float], K, in file-selection order (not sorted)

impd.dataValues = {                           # one record per temperature
    298.15: {
        'tickStampImps':   array(N)           # 60 MHz ticks (int) or seconds (float), see below
        'tickStampDemods': array(N)
        'timeStampImps':   array(N)           # seconds
        'timeStampDemods': array(N)           # seconds
        'ImpedanceRe':     array(N)           # real part, Ohm (per the code comment)
        'ImpedanceIm':     array(N)           # imaginary part in Ohm, or capacitance in F,
                                              # depending on the equivalent-circuit mode
        'AuxInput1':       array(N)           # pulse / excitation signal, V
        'AbsZ':            array(N)           # |Z|, Ohm
    },
    303: {...},
}

impd.dataParams = {...}                       # runParams.txt as a dict, or None

impd.dataExcitationLevelParams = {            # also dataEmissionLevelParams (same shape)
    'means':  array(nT, 2)                    # column 0 = higher level, column 1 = lower level
    'stds':   array(nT, 2)
    'labels': array(nT, N) float              # 0 = higher level, 1 = lower level, -1 = dropped
}

impd.dataEmissionClusterParams = {            # also dataExcitationClusterParams
    'clusterBlocks': {
        298.15: {
            'high': {0: [start, end, end-start], 1: [...], ...}   # label-0 blocks
            'low':  {0: [start, end, end-start], 1: [...], ...}   # label-1 blocks = emission windows
        }, ...
    },
    'clusterSizesFreqs': {
        298.15: {
            'high': [array([length, count]), ...]
            'low':  [array([length, count]), ...]
        }, ...
    }
}

impd.dataEmissions = {                        # built by selected_emissions()
    298.15: {
        'x':              array(n)            # s, time from the first kept sample of the block
        'xTimeStampImps': array(n)            # s, the same samples on the record's own time axis
        'y':              array(n) or array(n, R)   # ImpedanceIm; one column per repeat
        'ymean':          array(n)            # mean over repeats (or y itself for one repeat)
        'yerr':           array(n)            # std over repeats (zeros for one repeat)
        # added by filter_emissions():
        'yFiltered':      array(n)            # denoised trace
        'yRaw':           array(n)            # the trace that was denoised
        'filterMethod':   'pca' | 'wavelet' | 'sgolay' | 'lowess'
        'filterIndex':    int                 # emissionIndex used for the filter
    }, ...
}
```

Details:

- **Channel values.** `.h5` records hold numpy arrays (`read_h5_record` converts `uint64` to `int64`). JSON records hold Python lists until `cleanup_data()` converts them to arrays. CSV records hold only the channels found in the CSV set (`tickStampImps`, `timeStampImps`, `ImpedanceIm`, `tickStampDemods`, `timeStampDemods`, `AuxInput1`, and `AbsZ` plus an all-zero `ImpedanceRe` if the `_r_avg_` files are present).
- **tickStamp channels.** They hold either integer 60 MHz clock ticks (untriggered acquisitions) or a float time axis in seconds starting at 0 (triggered acquisitions, which runs use; step 18.67 µs in the sample run). `_is_seconds_axis` tells them apart.
- **Block entries.** `[start, end, end-start]` are sample indices into the record, both ends inclusive. The third value is `end - start`, one less than the number of samples. `align_clusters()` shortens `end` and the third value in place.
- **Which blocks are emissions.** Label 0 is the higher mean level of the clustered signal and label 1 the lower one. The code uses the `'low'` (label 1) blocks as emission windows. In the sample run `AuxInput1` sits at −0.5 V and −1.5 V; the −1.5 V blocks are the emission windows.
- **Repeats.** In `dataEmissions[T]['y']` for `emissionIndex=-1`, rows are time samples and columns are repeats (pulses). The sample HDF5 run gives `y.shape == (301, 542)`: 320-sample blocks, trimmed by 10 + 10.
- **Rate-window output.** `calculate_delC_normalized()` returns `(N, 4)` rows of `[T (K), tau (s), deltaC, deltaC/C_inf]` and `(N, 2)` rows of `[deltaC_err, (deltaC/C_inf)_err]`, sorted by temperature.

## class impdData

Holds one DLTS run (one or many temperatures) and the analysis state derived from it. Every analysis step writes its result into an attribute, and later steps read those attributes.

| Name | Type | Set by | Meaning |
|---|---|---|---|
| `fileName` | `str`, `list[str]` or `None` | `__init__`, `read_data` (normalized to a list, digit-less names removed, set to `None` on `FileNotFoundError`), `append_data` (extended) | Step files loaded so far. |
| `rootFolder` | `str` ending in `os.sep`, or `None` | `read_data` (only when `None`), CSV branch of `append_data` | Folder of the first file. `runParams.txt` is read from here. |
| `dataValues` | `dict[int, dict]` | `read_data`, `append_data`, `cleanup_data` | Raw channel data per temperature. |
| `dataTemps` | `list[float]` | `read_data`, `append_data` | Temperatures in K (exact: 298.15 for 25 °C), in load order. |
| `dataParams` | `dict` or `None` | `read_data`, `append_data` (txt/h5 only) | Contents of `runParams.txt`. |
| `dataExcitationLevelParams` | `dict` or `None` | `find_data_levels(dataType='excitation', recalculate=True)` | Level means, stds, labels of `AuxInput1`. |
| `dataEmissionLevelParams` | `dict` or `None` | `find_data_levels(dataType='emission', recalculate=True)` | Level means, stds, labels of `ImpedanceIm`. |
| `dataExcitationClusterParams` | `dict` or `None` | `find_clusters(dataType='excitation')`, `align_clusters` | Blocks and block-length statistics from `AuxInput1`. |
| `dataEmissionClusterParams` | `dict` or `None` | `find_clusters(dataType='emission')`, `align_clusters` | Blocks used to cut emission transients. Set it to `None` to force re-clustering. |
| `dataEmissions` | `dict[int, dict]` or `None` | `selected_emissions`, `filter_emissions` | Cut, averaged and denoised emission transients. |

### \_\_init\_\_(self, fName=None)

Creates an empty instance. Nothing is read until `read_data()`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `fName` | `str`, list of `str`, or `None` | `None` | Step-file path(s). `None` makes `read_data()` open a file dialog. Pass files, not a folder. |

**Returns** the instance.

**Example**

```python
import glob
import impedanceAnalysis_Tools as iaT

files = sorted(glob.glob(r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\*.h5"))
impd = iaT.impdData(fName=files)
```

### read_data(self)

Loads every file in `self.fileName` into `dataValues`, keyed by temperature. The extension of the first file picks the loader.

- `.txt`, `.json`, `.h5`: files whose base name has no digit are skipped with a message. The temperature comes from the file name (`p25p0.h5` → 25.0 °C → 298.15 K; see `_extract_txt_temperature`); a file whose name encodes no temperature is skipped with `Warning: Could not extract temperature from filename`. Each file is read with `_load_record`, so `.h5` and JSON files can be mixed in one list. `runParams.txt` is then loaded from `rootFolder` into `dataParams`.
- `.csv` (LabOne export): files are sorted by name fragment into emission (`_imps_0`), excitation (`_auxin0_`) and impedance (`_r_avg_`) sets, each split into header (`_header_`) and data files. Temperatures come from column 17 of the emission header; the `chunk` column maps rows to temperatures. Time stamps are `timestamp / 60e6`. `runParams.txt` is not read.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | Uses `self.fileName`. |

**Returns** `0` on success, `-1` if no file was chosen, no temperature could be parsed, the type is unsupported, or a file is missing.

**Side effects**

- Opens a Tk file dialog when `fileName` is `None`. In the CSV branch it opens more dialogs if a header or data file of the emission/excitation set is missing.
- Replaces `fileName`, `dataValues`, `dataTemps`, `dataParams`; sets `rootFolder` if it was `None`.
- Prints warnings for skipped files, unparsable temperatures and a missing `runParams.txt`.

**Call order** first call on a new instance. Use `append_data()` to add files later.

**Example**

```python
impd = iaT.impdData(fName=files)
if impd.read_data() != 0:
    raise RuntimeError("load failed")
print(impd.dataTemps)                      # [298.15, 303.15, 308.15, 313.15, 318.15, 323.15]
print(impd.dataParams['Number of Reps'])
```

### append_data(self, fName=None)

Adds more step files to an instance that already holds data. Uses the same loaders as `read_data()`. A new temperature gets its own record. A temperature already present is merged with `_append_records`: arrays and lists of the same channel are concatenated end to end.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `fName` | `str`, list of `str`, or `None` | `None` | Files to add. `None` opens a file dialog. `self.fileName` is not used as input. |

**Returns** `0` on success, `-1` on no files, no parsable temperature or unsupported type.

**Side effects**

- Updates `dataValues`, `dataTemps` (new temperatures appended at the end), and extends `fileName`.
- txt/h5/json: reads `runParams.txt` from the folder of the first appended file and merges it into `dataParams` (new values overwrite old ones). Does not set `rootFolder`.
- CSV: sets `rootFolder` if `None`; may open file dialogs; does not touch `dataParams`.
- Does not reset cluster or emission results. Set `dataEmissionClusterParams = None` before `selected_emissions()` so the new temperatures are clustered (this is what `liveDataTab.py` does).

**Call order** after `read_data()` (or on a fresh instance; `_append_records` accepts `dataValues=None`).

**Example**

```python
impd = iaT.impdData(fName=[files[0]])
impd.read_data()
impd.append_data(fName=files[1:])
impd.cleanup_data()
impd.dataEmissionClusterParams = None      # force re-clustering
impd.selected_emissions(emissionIndex=-1)
```

### cleanup_data(self)

Repairs the time axis of every record. For each temperature it runs `_zero_time_fill` (replaces zero time stamps by interpolated values) and then `_gap_remove` (closes every jump in the time stamps larger than `GAP_FACTOR` typical steps).

How the two kinds of `tickStamp*` channel are handled:

- **Clock ticks (integer, untriggered acquisitions).** Every zero tick is a missing sample. It is filled by linear interpolation between its valid neighbours, or extrapolated with the median step at the ends. `timeStamp*` is recomputed as `ticks / 60e6`.
- **Seconds (float, triggered acquisitions, which runs use).** The zero at index 0 is the real t = 0 and is kept. Only zeros after index 0 are filled, using a float median step. `timeStamp*` is recomputed as `ticks / 1.0`, so the axis stays in seconds.

`timeStamp*` and `tickStampDemods` are rewritten only when a zero was filled or a gap was closed; after a fix, `tickStampDemods`/`timeStampDemods` become copies of the `Imps` channels.

| Name | Type | Default | Meaning |
|---|---|---|---|
| (none) | | | Works on `dataValues` for every temperature in `dataTemps`. |

**Returns** `0`.

**Side effects** mutates `dataValues[T]` in place; converts list channels to numpy arrays.

**Call order** after `read_data()`/`append_data()`, before clustering. `selected_emissions()` calls it itself when `dataEmissionClusterParams` is `None`.

**Example**

```python
impd.read_data()
impd.cleanup_data()
t = impd.dataValues[298.15]['timeStampImps']  # seconds
```

### find_data_levels_scikit(self, dataType = 'emission', model='gmm', interactivePlot=False)

Splits each record's samples into two levels. For every temperature it divides the signal by its minimum, fits both a 2-component Gaussian mixture and 2-cluster K-Means, and relabels both so label 0 is the higher level. Non-finite samples are replaced by the median first. A record whose minimum is more than 20 times the second-smallest value in magnitude is marked unusable (all labels −1, means/stds NaN).

| Name | Type | Default | Meaning |
|---|---|---|---|
| `dataType` | `str` | `'emission'` | `'emission'` clusters `ImpedanceIm`; `'excitation'` clusters `AuxInput1`. Any other value fails with `UnboundLocalError`. |
| `model` | `str` | `'gmm'` | `'gmm'`, `'kmeans'`, or `'hybrid'` (keeps only samples where GMM and K-Means agree; the rest get label −1). Case-insensitive. |
| `interactivePlot` | `bool` | `False` | Shows a 3-panel figure (K-Means, GMM, Hybrid) per temperature; left/right arrow keys step through temperatures. Only works with `model='hybrid'`; otherwise prints a message. |

**Returns** `(means, stds, labels)`: `means` and `stds` are `(nT, 2)` arrays (column 0 higher level, column 1 lower level); `labels` is an `(nT, N)` float array of 0, 1 or −1.

**Side effects** prints warnings for unusable records; with `interactivePlot=True` opens a blocking matplotlib window. Does not store its result (see `find_data_levels`).

Raises `ValueError` if no data is loaded, if `model` is invalid, or if a record's length differs from the first record's.

**Call order** after `read_data()`, ideally after `cleanup_data()`.

**Example**

```python
means, stds, labels = impd.find_data_levels_scikit(dataType='excitation', model='hybrid')
print(means[0])     # e.g. [-0.501, -1.500] V
```

### find_data_levels(self, dataType = 'excitation', algorithm='gmm', recalculate=True, interactivePlot=False)

Wrapper around `find_data_levels_scikit` that stores the result and trims labels. After getting the labels it sets to −1 every sample before the first label-0 sample and every sample from the last label-1 sample to the end, so partial blocks at the record edges are dropped.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `dataType` | `str` | `'excitation'` | `'excitation'` or `'emission'`. |
| `algorithm` | `str` | `'gmm'` | `'gmm'`/`'gaussianmixture'`, `'kmeans'`, or `'hybrid'`/`'gmmkmeans'`/`'kmeansgmm'`. Case-insensitive. |
| `recalculate` | `bool` | `True` | `False` reuses stored levels if present (recomputes and prints a message if not). |
| `interactivePlot` | `bool` | `False` | Passed to `find_data_levels_scikit`. |

**Returns** `(means, stds, labels)` as above, with edge samples set to −1. Returns `-1` for an invalid `dataType` when `recalculate=False`. Raises `ValueError` for an unknown `algorithm`.

**Side effects** with `recalculate=True`, replaces `dataExcitationLevelParams` or `dataEmissionLevelParams` with `{'means', 'stds', 'labels'}`. The edge trimming is applied to the same `labels` array that was stored, so the stored labels are trimmed too.

**Call order** after `read_data()` and `cleanup_data()`. Called by `find_clusters()`.

**Example**

```python
m, s, l = impd.find_data_levels(dataType='excitation', algorithm='hybrid')
print(impd.dataExcitationLevelParams['labels'].shape)   # (nT, N)
```

### find_clusters(self, dataType='excitation', method='free', recalculate=False, align=False)

Turns the level labels into blocks of consecutive samples and records how often each block length occurs. It always calls `find_data_levels(..., algorithm="hybrid", recalculate=True)`, then `_find_cluster_stats`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `dataType` | `str` | `'excitation'` | Which cluster set to build: `'excitation'` or `'emission'`. |
| `method` | `str` | `'free'` | Emission only. `'free'` clusters `ImpedanceIm` itself. `'synced'` clusters `AuxInput1` and uses those blocks for the emission set (the pulse defines the emission windows). Ignored for excitation. |
| `recalculate` | `bool` | `False` | `False` does nothing if the chosen cluster set already exists. |
| `align` | `bool` | `False` | Runs `align_clusters(dataType)` after building the blocks. |

**Returns** `0`, or `-1` for an invalid `dataType` or `method`.

**Side effects** replaces `dataExcitationClusterParams` or `dataEmissionClusterParams` with `{'clusterBlocks', 'clusterSizesFreqs'}`; also replaces the level params that `find_data_levels` stores (`method='synced'` updates `dataExcitationLevelParams`, not `dataEmissionLevelParams`). Prints messages.

**Call order** `read_data()` → `cleanup_data()` → `find_clusters()`. `selected_emissions()` calls `find_clusters(dataType='emission', method='synced', recalculate=True, align=True)` when no clusters exist.

**Example**

```python
impd.find_clusters(dataType='emission', method='synced', recalculate=True, align=True)
blocks = impd.dataEmissionClusterParams['clusterBlocks'][298.15]['low']
print(blocks[0])      # e.g. [55, 375, 320]
```

### align_clusters(self, dataType='excitation', method='free')

Makes all blocks of one kind the same length so they can be stacked and averaged. Steps:

1. Calls `find_clusters(dataType, method)` (no-op if clusters exist).
2. Per temperature, shortens every `'high'` and `'low'` block to the shortest length in that temperature's frequency table.
3. Rebuilds `clusterSizesFreqs` as `[length, count]` pairs (in first-seen order, no longer sorted by count).
4. If a temperature has more than one distinct `'low'` length, deletes its last `'low'` block and last frequency entry.
5. Shortens blocks at every temperature to the shortest first-block length over all temperatures.

Only the end index and the length field change; start indices stay.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `dataType` | `str` | `'excitation'` | `'excitation'` or `'emission'`. |
| `method` | `str` | `'free'` | Passed to `find_clusters()` if clusters must be built. |

**Returns** `0`, or `-1` for an invalid `dataType`.

**Side effects** mutates `clusterBlocks` and `clusterSizesFreqs` of the chosen cluster set.

**Call order** after `find_clusters()`; usually invoked through `find_clusters(..., align=True)`.

**Example**

```python
impd.find_clusters(dataType='emission', method='synced', recalculate=True)
impd.align_clusters(dataType='emission')
```

### selected_emissions(self, emissionIndex=0, trimHead = 10, trimTail = 10, plot=False)

Cuts the emission transients out of `ImpedanceIm` using the `'low'` blocks of `dataEmissionClusterParams` and stores them in `dataEmissions`. Each block is sliced as `[start + trimHead : end + 1 - trimTail]`. `x` is the matching `timeStampImps` slice shifted to start at 0.

If `dataEmissionClusterParams` is `None`, it first runs `cleanup_data()` and `find_clusters(dataType='emission', method='synced', recalculate=True, align=True)`.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `emissionIndex` | `int` | `0` | `-1`: all blocks, stacked as columns of `y`, with `ymean`/`yerr` the mean and std over repeats (x from the first block). `0 … maxIndex-1`: that single block, `ymean = y`, `yerr` zeros. See limits below. |
| `trimHead` | `int` | `10` | Samples dropped after each block start. |
| `trimTail` | `int` | `10` | Samples dropped before each block end. |
| `plot` | `bool` | `False` | Unused. |

`maxIndex` is `count - 1` of the first entry in `clusterSizesFreqs[first T]['low']` (1 if that is 0). Index handling:

- `emissionIndex > maxIndex`: prints a warning and uses `maxIndex`.
- `emissionIndex == maxIndex` (including after that clamp): nothing is built; `dataEmissions` keeps its previous value (or stays `None`).
- `emissionIndex < -1`: prints "Using min index" but uses `0`.

**Returns** `0`.

**Side effects** replaces `dataEmissions` (dropping any `yFiltered`/`yRaw`); may run `cleanup_data()` and clustering; prints warnings.

**Call order** `read_data()` → `cleanup_data()` → (`find_clusters(...)`) → `selected_emissions()` → `filter_emissions()`.

**Example**

```python
impd.selected_emissions(emissionIndex=-1)
e = impd.dataEmissions[298.15]
print(e['y'].shape, e['ymean'].shape)    # (301, 542) (301,)
```

### filter_emissions(self, method='pca', emissionIndex=-1, recalculate=False, trimHead=10, trimTail=10, interactivePlot=True)

Denoises one trace per temperature from `dataEmissions` and stores it as `yFiltered`, with the input trace as `yRaw`. The settings per method are fixed:

| `method` | Call | Settings |
|---|---|---|
| `'pca'` | `_pca_denoise` | `window_size=100` |
| `'wavelet'` | `_wavelet_denoise` | `wavelet="db4", level=4, mode="soft"` |
| `'sgolay'` | `_savitzkyGolay_denoise` | `window_size=None` (automatic), `order=2` |
| `'lowess'` | `_lowess_denoise` | `fraction=None` (0.1) |

| Name | Type | Default | Meaning |
|---|---|---|---|
| `method` | `str` | `'pca'` | One of the four above (case-insensitive). Otherwise `ValueError`. |
| `emissionIndex` | `int` | `-1` | Which trace to denoise: `-1` uses `ymean`; `0 … R-2` uses column `emissionIndex` of `y`; a larger value uses the last column; `< -1` uses column 0. Also passed to `selected_emissions()` if `dataEmissions` is `None`. |
| `recalculate` | `bool` | `False` | `False` skips the work if `yFiltered` exists and `filterMethod` matches `method`. A changed `emissionIndex` alone does not trigger a recompute. |
| `trimHead` | `int` | `10` | Used only if `selected_emissions()` must run. |
| `trimTail` | `int` | `10` | Used only if `selected_emissions()` must run. |
| `interactivePlot` | `bool` | `True` | Opens a blocking plot of filtered (red line) vs raw (black points) per temperature; left/right arrows step through temperatures. |

**Returns** `0`. Raises `ValueError` if no emissions exist.

**Side effects** adds `yFiltered`, `yRaw`, `filterMethod`, `filterIndex` to each `dataEmissions[T]`; may call `selected_emissions()`; opens a matplotlib window by default. Pass `interactivePlot=False` in scripts and GUI code.

**Call order** after `selected_emissions()`.

**Example**

```python
impd.selected_emissions(emissionIndex=-1)
impd.filter_emissions(method='wavelet', emissionIndex=-1, recalculate=True, interactivePlot=False)
yF = impd.dataEmissions[298.15]['yFiltered']
```

### calculate_delC_normalized(self, t1=0.003, t2=0.203, emissionIndex=-1, denoiseEmission=False, denoiseMethod='pca', smoothCapacitance=True, plot=False)

Computes the double-boxcar DLTS signal for one rate window at every temperature: `deltaC = C(t2) - C(t1)` and `deltaC / C_inf`, where `C_inf` is the last sample of the trimmed emission window. Uncertainties from `yerr` are propagated with `uncertainties.ufloat`. The time constant is `tau = (t2 - t1) / ln(t2 / t1)`.

It always rebuilds the emissions first: `selected_emissions(emissionIndex, trimHead=10, trimTail=10)` then `filter_emissions(method=denoiseMethod, emissionIndex, recalculate=True, interactivePlot=False)`. `t1` is raised to `min(x)` and `t2` lowered to `max(x)` per temperature if they fall outside the window, without a warning.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `t1` | `float` | `0.003` | First gate, s after the start of the trimmed window. |
| `t2` | `float` | `0.203` | Second gate, s. |
| `emissionIndex` | `int` | `-1` | `-1` averages all repeats and gives meaningful errors; a single pulse (`0`) gives zero `yerr`, so all errors are 0. |
| `denoiseEmission` | `bool` | `False` | `True` reads C from `yFiltered`, `False` from `yRaw`. |
| `denoiseMethod` | `str` | `'pca'` | Filter used by `filter_emissions()`. The filter runs even when `denoiseEmission=False`. |
| `smoothCapacitance` | `bool` | `True` | `True` reads C and its error at `t1`, `t2`, `x[-1]` from cubic splines of C and `yerr`. `False` uses the nearest sample (and computes `tau` from those sample times). |
| `plot` | `bool` | `False` | Shows normalized ΔC vs T with error bars (blocking window). |

**Returns** `(delCNormalized, delCNormalizedErr)`: `(N, 4)` array `[T (K), tau (s), deltaC, deltaC/C_inf]` and `(N, 2)` array `[deltaC_err, (deltaC/C_inf)_err]`, both sorted by temperature.

**Side effects** replaces `dataEmissions` (and whatever `selected_emissions`/`filter_emissions` touch); may emit `uncertainties` warnings when errors are zero; opens a plot if `plot=True`.

**Call order** after `read_data()` and `cleanup_data()`. Clustering runs automatically if needed.

**Example**

```python
delC, delCErr = impd.calculate_delC_normalized(t1=0.001, t2=0.004, emissionIndex=-1,
                                               denoiseEmission=True, denoiseMethod='sgolay')
T, S, Serr = delC[:, 0], delC[:, 3], delCErr[:, 1]
```

### test(self, t1=None, t2=None, plot=True)

Experimental scan over rate-window pairs. For every pair with `t2[j] > t1[i]` it runs `calculate_delC_normalized(t1, t2, emissionIndex=0, denoiseEmission=False, smoothCapacitance=False)`, fits a cubic spline to normalized ΔC vs T, and runs `differential_evolution` on that spline over the temperature range.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `t1` | array of `float` | `None` → `[0.01, 0.02]` | First-gate values, s. |
| `t2` | array of `float` | `None` → `[0.01, 0.02]` | Second-gate values, s. |
| `plot` | `bool` | `True` | Draws two `tricontourf` maps over (t1, t2): peak T and peak ΔC. |

**Returns** array of rows `[t1, t2, T_at_extremum, -min_value]`, with `len(t1)*(len(t2)-1)//2` rows.

**Side effects** replaces `dataEmissions`; opens two blocking plots when `plot=True`.

`differential_evolution` minimizes the spline, so the third column is the temperature of the minimum and the fourth is the negated minimum value, not the maximum. The row count formula only matches the number of valid pairs when `t1` and `t2` are the same array. With the defaults there is one row, and `plot=True` fails with `ValueError: arange: cannot compute length`.

**Example**

```python
import numpy as np
C = impd.test(t1=np.array([0.001, 0.002, 0.003]), t2=np.array([0.001, 0.002, 0.003]), plot=False)
```

## Module-level functions

### read_h5_record(file_path, keys=None)

Reads one temperature step written by `ziDevice.writeDataH5()` into `{channel name: numpy array}`, the same layout a JSON step file gives. `uint64` datasets (tick stamps) are returned as `int64` so that `np.diff()` in `cleanup_data()` does not wrap around.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `file_path` | `str` | required | Path to a `.h5` step file. |
| `keys` | iterable of `str` or `None` | `None` | Channels to read. `None` reads all datasets. A missing key raises `KeyError`. |

**Returns** `dict[str, numpy.ndarray]`.

**Side effects** none (opens the file read-only and closes it).

**Example**

```python
rec = iaT.read_h5_record(r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5",
                         keys=('AuxInput1', 'ImpedanceIm'))
print(rec['ImpedanceIm'].shape)     # (262144,)
```

## Internal helpers

All are `@staticmethod`s of `impdData` unless noted.

### Loading and merging

- `_normalize_file_selection(file_selection)` returns `[]` for `None`, `[s]` for a string, otherwise `list(file_selection)`.
- `_load_record(file_path)` returns `read_h5_record(file_path)` for `.h5`, otherwise `json.load()` of the file (UTF-8).
- `_extract_txt_temperature(file_path)` matches the file name without extension against `_STEP_STEM_PATTERN` (optional sign letter `p`/`n` in either case, whole degrees, optional `p` + decimals, optional `C`, optional `_NNN`; no sign letter means positive) and returns the key from `_celsius_to_kelvin_key`, or `None` if the name encodes no temperature. `p25p0.h5` → 298.15, `n10p5.txt` → 262.65, `p25C_1.txt` → 298.15, `x25p0.txt` and `p-3.h5` → `None`.
- `_extract_csv_temperature(data_name)` matches a LabOne data name against `_CSV_NAME_PATTERN` (optional sign letter, whole degrees, optional `p` or `.` + decimals, then `C_`) and returns the key, or `None`. `25C_000` → 298.15, `n10C_000` → 263.15, `p25p5C_000` → 298.65.
- `_celsius_to_kelvin_key(sign, integerPart, fracPart)` turns the matched parts into `round(±T_C + 273.15, 6)`, so the same setpoint always gives the same float key.
- `_merge_nested_dict(existing, incoming, concatenate_arrays=False)` merges dicts recursively. With `concatenate_arrays=True`, same-key arrays are joined with `np.concatenate` and same-key lists with `+`; otherwise the incoming value wins. Returns `incoming` if either side is not a dict.
- `_append_records(existing_records, new_records)` merges per-temperature records: new temperatures are added, existing ones merged with `_merge_nested_dict(..., concatenate_arrays=True)`.
- `_append_unique_temps(existing_temps, new_temps)` appends temperatures not already in the list, keeping order.

### Time-axis repair

- `_is_seconds_axis(tick)` returns `True` when `tick` is a non-empty float array with at least one finite non-integer value, meaning a time axis in seconds. Integer arrays, and float arrays holding only whole numbers, count as clock ticks.
- `_ticks_per_second(tick)` returns `1.0` for a seconds axis, else `60 * 10**6`.
- `_zero_time_fill(signal=None)` fills zero entries of `tickStampImps` by interpolation or median-step extrapolation (keeping index 0 on a seconds axis), then recomputes `timeStampImps` and copies both into the `Demods` channels. Converts list channels to arrays. Returns the record, or `-1` if `signal` is `None`.
- `_zero_time_remove(signal=None)` deletes every sample whose `tickStampImps` is 0 from all channels. Not used; the call in `cleanup_data()` is commented out. Returns the record or `-1`.
- `_gap_remove(signal=None)` takes the typical step as the median of `|diff(tickStampImps)|`. Every step larger than `GAP_FACTOR` (100) typical steps, forward (dropped samples) or backward (a second record of the same temperature appended by `append_data`, whose clock restarts), is replaced by one typical step, and the axis is rebuilt from its first sample. The result is continuous and increasing; the data samples keep their order. It then recomputes `timeStampImps` (with `_ticks_per_second`) and copies both into the `Demods` channels. Unsigned ticks are converted to `int64` first so backward jumps don't wrap. A record without gaps is returned unchanged. Returns the record, or `-1` for `signal=None`.

### Clustering

- `_find_nearest(array, value)` returns the index of the element closest to `value`.
- `_find_signal_blocks(arr, val)` returns `[(start, end), ...]` inclusive index ranges of runs equal to `val`. Runs of −1 lying strictly between two `val` samples are counted as `val` first. Uses the nested helper `get_blocks_for_target(target)`.
- `_find_cluster_stats(dataLabels, classLabels)` builds `clusterBlocks` (label 0 → `'high'`, label 1 → `'low'`, entries `[start, end, end-start]`) and `clusterSizesFreqs` (`[length, count]` sorted by count, descending) for each temperature. For `'low'` it drops the last length added to the frequency table (`popitem()`), which removes the length of the final low block when that length is unique. Returns `(blocks, clusterSizesFreqs)`.

### Denoisers (also called directly by `detailedAnalysisTab.py`)

All four take `signal`, a `dataEmissions[T]`-style dict with `'x'`, `'y'`, `'ymean'`, and `index` which picks the trace: `-1` → `ymean`; `0 ≤ index < maxIndex` → column `index` (or the whole `y` if `maxIndex == 1`); `index > maxIndex` → last column; `index < -1` → column 0. `maxIndex` is `y.shape[1] - 1`, or 1 when `y` is 1-D. `index == maxIndex` leaves the trace undefined and raises `UnboundLocalError`. Each returns `(x, yDenoised, yRaw)`.

- `_wavelet_denoise(signal, index=-1, wavelet="db4", level=1, mode="soft")` decomposes with `pywt.wavedec`, estimates noise from the finest detail coefficients (MAD / 0.6745), applies the universal threshold `sigma * sqrt(2 ln n)` to all detail levels, and reconstructs.
- `_pca_denoise(signal, index=-1, window_size=None)` frames the trace into overlapping windows, keeps the first principal component, and averages the overlapping reconstructions. `window_size=None` → `max(2, n // 1000)` for n ≥ 1000, else `max(2, n // 20)`; it is capped at `n - 2`. The last sample is set to the mean of the two before it.
- `_savitzkyGolay_denoise(signal, index=-1, window_size=None, order=2)` applies `scipy.signal.savgol_filter`. `window_size=None` → `max(order + 2, n // 1000)` for n ≥ 1000, else `max(order + 2, n // 20)`; forced odd, capped at the trace length, and kept above `order`.
- `_lowess_denoise(signal, index=-1, fraction=None)` fits `fastlowess.Lowess(fraction, iterations=3, robustness_method="bisquare")` against `x`. `fraction=None` → 0.1.

### Peak finders (also called directly by `dataAnalysisTab.py` and `detailedAnalysisTab.py`)

Both return `(maxX, maxY, xf, yf, maxXErr, maxYErr)`, or `-1` (after printing) if `signalX` or `signalY` is `None`. Typical input is `x = delC[:, 0]` (T in K) and `y = delC[:, 3]`.

`_smoothingSpline_peakFinder(signalX = None, signalY = None, smoothingFactor = None, nBootstrap = 200, randomState = 0, signalYErr = None)` fits a cubic `UnivariateSpline` and returns the point of largest absolute value on a 100000-point grid, so negative peaks are found too.

| Name | Type | Default | Meaning |
|---|---|---|---|
| `signalX`, `signalY` | array | `None` | Data; sorted by x internally. |
| `smoothingFactor` | `float` | `None` | Spline `s`. `None` → `len(x)` when valid errors are given, otherwise `noiseVar * len(x)` with `noiseVar` estimated from second differences (plain variance for fewer than 5 points). |
| `nBootstrap` | `int` | `200` | Parametric bootstrap refits for the errors; `0` skips them. |
| `randomState` | `int` | `0` | Seed for the bootstrap. |
| `signalYErr` | array | `None` | Per-point errors; used as weights `1/err` and as bootstrap noise. Ignored unless all finite and > 0. |

`maxXErr`/`maxYErr` are the standard deviations of the bootstrap peaks (2000-point grid), or `None` if the bootstrap was skipped or fewer than `max(10, nBootstrap // 4)` refits succeeded.

`_curveFit_peakFinder(signalX = None, signalY = None, curveType = "pseudoVoigt", signalYErr = None)` fits an lmfit model after `model.guess()` and returns its `center` and `height` parameters with their `stderr` (which may be `None`). `curveType` is one of `pseudoVoigt`, `gaussian`, `lorenzian`/`lorentzian`, `voigt` (case-insensitive); anything else raises `ValueError`. `signalYErr` sets `weights = 1/err` when all finite and > 0. `xf`/`yf` is the fitted curve on 2000 points.

### Nested functions

- `_safe_ylim(values, pad_frac=0.1)` (inside `find_data_levels_scikit`) returns padded y-limits from the finite values, `(-1, 1)` if none.
- `update_cluster_plot(idx)` and `on_key(event)` (inside `find_data_levels_scikit`) redraw the K-Means / GMM / Hybrid panels for temperature `idx` and handle the arrow keys. `update_cluster_plot` refits both models for the displayed temperature.
- `update_filtered_plot(idx)` and `on_key(event)` (inside `filter_emissions`) redraw filtered vs raw traces and handle the arrow keys.
- `get_blocks_for_target(target)` (inside `_find_signal_blocks`) does the actual block search.

## Typical workflows

Run these outside the GUI with a non-interactive backend so no windows block:

```python
import os
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "8")
import matplotlib
matplotlib.use("Agg")
```

### 1. Load an HDF5 run, cut and average the emissions

```python
import glob
import numpy as np
import impedanceAnalysis_Tools as iaT

runFolder = r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655"
files = sorted(glob.glob(os.path.join(runFolder, "*.h5")))   # step files only; runParams.txt is read automatically

impd = iaT.impdData(fName=files)
assert impd.read_data() == 0
print("Temperatures (K):", impd.dataTemps)
print("Reps:", impd.dataParams["Number of Reps"])

impd.cleanup_data()
impd.find_clusters(dataType='emission', method='synced', recalculate=True, align=True)
impd.selected_emissions(emissionIndex=-1, trimHead=10, trimTail=10)

T = impd.dataTemps[0]
e = impd.dataEmissions[T]
print(e['x'].shape, e['y'].shape)          # (301,) (301, 542)
print("window length (s):", e['x'][-1])
```

### 2. Denoise with each method and compare

```python
methods = ['pca', 'wavelet', 'sgolay', 'lowess']
results = {}
for m in methods:
    impd.filter_emissions(method=m, emissionIndex=-1, recalculate=True, interactivePlot=False)
    results[m] = {T: impd.dataEmissions[T]['yFiltered'].copy() for T in impd.dataTemps}

T = impd.dataTemps[0]
raw = impd.dataEmissions[T]['yRaw']         # ymean, because emissionIndex=-1
for m in methods:
    print(m, "rms change:", np.sqrt(np.mean((results[m][T] - raw) ** 2)))
```

To denoise a single averaged trace without the class (as `detailedAnalysisTab.py` does):

```python
sig = {'x': e['x'], 'y': e['ymean'], 'ymean': e['ymean']}
x, ySG, yIn = iaT.impdData._savitzkyGolay_denoise(sig, index=-1, window_size=None, order=2)
```

### 3. Rate-window DLTS spectrum and peak temperature (JSON run)

```python
jsonFolder = r"C:\Users\spencer\Desktop\DATA\DLTS\092326\101901"
jfiles = sorted(glob.glob(os.path.join(jsonFolder, "*.json")))

run = iaT.impdData(fName=jfiles)
assert run.read_data() == 0                 # 47 temperatures
run.cleanup_data()

delC, delCErr = run.calculate_delC_normalized(t1=0.010, t2=0.050, emissionIndex=-1,
                                              denoiseEmission=True, denoiseMethod='sgolay',
                                              smoothCapacitance=True)
T, S, Serr = delC[:, 0], delC[:, 3], delCErr[:, 1]
tau = delC[0, 1]

yErr = Serr if np.all(np.isfinite(Serr)) and np.all(Serr > 0) else None
Tp, Sp, xf, yf, TpErr, SpErr = iaT.impdData._smoothingSpline_peakFinder(T, S, signalYErr=yErr)
print(f"tau = {tau:.4g} s, Tp = {Tp:.1f} K +/- {TpErr}")

# Parametric alternative:
Tp2, Sp2, xf2, yf2, TpErr2, SpErr2 = iaT.impdData._curveFit_peakFinder(T, S, curveType='gaussian', signalYErr=yErr)
```

### 4. Several rate windows and an Arrhenius plot

The module has no Arrhenius function; this combines its outputs with plain numpy.

```python
windows = [(0.005, 0.025), (0.010, 0.050), (0.020, 0.100), (0.040, 0.200)]   # s, must fit inside the emission window
taus, Tps = [], []
for t1, t2 in windows:
    delC, delCErr = run.calculate_delC_normalized(t1=t1, t2=t2, emissionIndex=-1,
                                                  denoiseEmission=True, denoiseMethod='sgolay')
    Tp, _, _, _, _, _ = iaT.impdData._smoothingSpline_peakFinder(delC[:, 0], delC[:, 3], nBootstrap=0)
    taus.append(delC[0, 1])
    Tps.append(Tp)

taus, Tps = np.array(taus), np.array(Tps)
kB = 8.617333e-5                                          # eV/K
slope, intercept = np.polyfit(1.0 / Tps, np.log(taus * Tps**2), 1)
print(f"Ea = {slope * kB:.3f} eV")
```

## Notes and limitations

- **tickStamp channels have two meanings.** Untriggered acquisitions store integer 60 MHz clock ticks; triggered acquisitions (used by runs) store the DAQ grid's float time axis in seconds under the same `tickStamp*` names. `cleanup_data()` detects this with `_is_seconds_axis` and uses `_ticks_per_second` (60e6 or 1.0) for conversion; on a seconds axis the leading t = 0 is kept rather than treated as a missing sample. A float axis that holds only whole numbers is treated as ticks.
- **Gap removal is continuous now.** Earlier versions shifted one segment by the wrong offset (the segments overlapped) and could apply both of their two shifts on a backward jump, leaving a non-monotonic axis; they also closed only the single largest gap and compared against the smallest step. Tests: `tests/test_temperatures_and_gaps.py`. The rebuilt axis starts at the record's first time stamp, so after a gap the later samples' absolute times change; only relative times matter to the analysis.
- **Temperature keys are exact kelvin** (`T_C + 273.15`, decimals kept). Earlier versions used `int(float(T_C)) + 273` (−10.5 °C → 263 K, 50.5 °C → 323 K), read any first character other than `p` as a minus sign (`25p0.txt` → 268 K), and raised `ValueError` for `p-3.h5` or `p25C.txt`. Code that indexed `dataValues` with integers (`dataValues[298]`) must use the float key (`dataValues[298.15]`).
- **Pass files, not a folder.** `fName` must be file paths. `read_data()` picks the loader from the first file's extension; `.h5`, `.txt` and `.json` can be mixed, CSV cannot. Files without a digit in the name are skipped.
- **`dataTemps` keeps load order.** With `sorted(glob(...))`, `p100p0` sorts before `p25p0`. Only `calculate_delC_normalized()` sorts its output by temperature.
- **`runParams.txt`** is read only for txt/h5/json loads, from `rootFolder` (the first file's folder). `append_data()` merges a new one over the old; CSV loads never read it.
- **CSV specifics.** Temperatures come from header column index 16, time is `timestamp / 60e6`, and `ImpedanceRe` is filled with zeros. Missing header/data files trigger extra file dialogs.
- **Rate-window gates are clipped silently.** `t1`/`t2` are forced into `[x.min(), x.max()]` of the trimmed emission window. In the sample HDF5 run the window is only about 5.6 ms (301 samples of 18.67 µs), so the default `t2=0.203` s becomes 5.6 ms, and `test()` with its defaults gives `t1 == t2`, `tau = NaN` and ΔC = 0. With `smoothCapacitance=False`, a gate at t = 0 gives `log(inf)` in `tau`.
- **`C_inf` is the last sample of the trimmed window**, not an extrapolated steady-state value. With short windows it can be far from the true steady-state capacitance.
- **`selected_emissions()` index quirks.** `maxIndex` is taken from the first temperature only. `emissionIndex == maxIndex`, including after clamping a too-large index, builds nothing and leaves `dataEmissions` unchanged (possibly `None`, so `filter_emissions()` then raises). `emissionIndex < -1` prints "Using min index" but uses 0. `plot` is unused.
- **Denoiser index quirks.** `index == maxIndex` raises `UnboundLocalError`. With exactly two repeats (`y` of shape `(n, 2)`) and `index=0`, `maxIndex == 1` and the whole 2-D `y` is passed to the filter instead of one column. The sample JSON run has two repeats per temperature (`y.shape == (26780, 2)`), so use `emissionIndex=-1` or build emissions with `emissionIndex=0` first. The `except:` fallback returns `-1`, which callers then fail to unpack.
- **`filter_emissions()`** uses fixed settings per method, ignores a change of `emissionIndex` unless `recalculate=True`, and opens a blocking plot by default (`interactivePlot=True`).
- **`_find_cluster_stats` drops a length with `popitem()`** from the `'low'` table. If every low block has the same length, the table ends up empty and `align_clusters()` fails on `np.min` of an empty array.
- **`find_data_levels()` edge trimming** raises `IndexError` if a record has no label-0 or no label-1 samples (for example a record marked unusable). It also mutates the stored labels.
- **`find_data_levels_scikit()`** always fits both GMM and K-Means, whatever `model` is. It divides by the record minimum, so a minimum of exactly 0 produces `inf`/`NaN`. All records must have the same length as the first. `dataType` values other than `'emission'`/`'excitation'` fail with `UnboundLocalError`.
- **Re-clustering after appends.** `selected_emissions()` only clusters when `dataEmissionClusterParams is None`; set it to `None` after `append_data()`. `selected_emissions()` also calls `cleanup_data()` again in that case.
- **`test()` is experimental.** It minimizes rather than maximizes, reports the negated minimum as "max ΔC", mis-sizes its output for unequal `t1`/`t2` arrays, and its plots fail with one row.
- **Interactive plots block.** `find_data_levels_scikit(interactivePlot=True)`, `filter_emissions(interactivePlot=True)`, `calculate_delC_normalized(plot=True)` and `test(plot=True)` call `plt.show()`. Do not use them from a worker thread.
- **Heavy imports.** The module imports hardware-control modules, `torch` and several unused packages at import time. The module creates no threads; `liveDataTab.py` runs it on a worker thread.
- **Units of `ImpedanceIm`** depend on the instrument's equivalent-circuit mode (code comment: imaginary impedance in Ohm or capacitance in F). The module does not check or convert them.

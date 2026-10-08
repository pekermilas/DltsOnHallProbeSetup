# Data formats

This page describes the files the application writes and reads: the run folder layout, the step file names, `runParams.txt`, JSON step files, HDF5 step files, and the Zurich Instruments MFIA CSV exports that the analysis tabs also accept. The last section shows how to open HDF5 step files in HDFView, MATLAB and Python.

All examples come from real files on the lab PC unless marked otherwise. The main example run is `C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\`, a 25 to 50 °C scan in 5 °C steps, 2^18 points per step, 100 repetitions, written as HDF5.

## Run folder layout

`runDlts_Tools.dltsRun.init_experiment()` creates one folder per run:

```text
<Data Root Folder>\
    MMDDYY\              date the run started, e.g. 092826 = 28 Sep 2026
        HHMMSS\          time the run started, 24 h, e.g. 114655 = 11:46:55
            p25p0.h5     one step file per temperature setpoint
            p30p0.h5
            ...
            runParams.txt
```

The real example folder:

```text
C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\
    p25p0.h5        8,658,758 bytes
    p30p0.h5        8,679,853 bytes
    p35p0.h5        8,677,551 bytes
    p40p0.h5        8,671,607 bytes
    p45p0.h5        8,676,121 bytes
    p50p0.h5        8,694,667 bytes
    runParams.txt       1,148 bytes
```

Details from the code:

- **Data Root Folder** comes from the Input Parameters tab. The run folder is `os.path.join(root, MMDDYY, HHMMSS)` (date and time from one `datetime.now()` call) and is created if missing.
- Data Root Folder is empty by default. A run with it empty, or set to a relative path, does not start: `init_experiment()` logs `Error: Data Root Folder is not set` and the GUI logs `Error: Failed to initialize the experiment.` Earlier versions wrote such a run to `\MMDDYY\HHMMSS\` at the root of the current drive, and older run folders have a doubled backslash in their recorded paths.
- The file extension follows **Data File Format**: `HDF5` gives `.h5`, `TXT` gives `.txt`. The code also maps `JSON` (and any unknown value) to `.json`, but the GUI dropdown offers only `TXT` and `HDF5`. `TXT` and `JSON` both write JSON content.
- Step files are written one at a time as each temperature finishes. Redo overwrites a step's file; Remove & Retake deletes it first and then writes it again.
- `runParams.txt` is written by `finish_experiment()`, which runs only when the main sequence completes. A run that stops with an error, or is aborted by closing the GUI, has step files but no `runParams.txt`. HDF5 step files still carry the parameters in their `run_params` attribute.

Older data on the lab PC also has other layouts, for example step files directly in a date folder (`DLTS\062626\n10p0.txt`) or `.json` step files (`DLTS\091526\133851\p25p0.json`). Folders converted with `convert_json_to_h5.py` also hold a `json_originals\` subfolder with the original JSON files.

## Step file names

`init_experiment()` builds each name from the setpoint `T` in `tempGrid`:

```python
prefix = 'n' if '-' in str(T) else 'p'
name = prefix + str(np.abs(T)).replace('.', 'p') + ext
```

| Setpoint (°C) | File name |
|---|---|
| `25.0` | `p25p0.h5` |
| `-10.0` | `n10p0.h5` |
| `50.5` | `p50p5.h5` |
| `300.0` | `p300p0.txt` (real, `DLTS\092526\114016`) |

The name is built from `str()` of the number. `instecTempStage_Control.build_temp_grid()` returns a float numpy array (`Tinit + step * np.arange(n)`), so whole-degree setpoints give `p25p0`. Fractional steps can give floating-point artifacts in the name. Checked with the same expression: a 0 to 1 °C grid in 0.1 °C steps gives `p0p30000000000000004`, `p0p6000000000000001`, `p0p7000000000000001`, and a grid starting at -1 °C gives `n0p3999999999999999` and similar. The readers still parse these names (the fraction is just a long digit string).

The readers accept a wider pattern. `liveDataTab._LEGACY_FILENAME_PATTERN`, used by the folder scans of the Quick Analysis tab (Offline Data), the Live Tools tab (Qualitative Analysis, live run folder), and the Detailed Analysis tab:

```python
re.compile(r'^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt|csv|h5)$')
```

| Part | Meaning |
|---|---|
| `[npNP]` | `p` = positive, `n` = negative |
| `(\d+)` | integer part |
| `(?:[pP](\d+))?` | optional `p` + fraction digits (`p5` = .5) |
| `[cC]?` | optional `C` |
| `(?:_\d+)?` | optional `_<n>` suffix, ignored |
| `(txt\|csv\|h5)` | extension |

`convert_json_to_h5.STEP_FILE_PATTERN` is the same pattern with the extensions `txt|json` instead. Note that `.json` step files are not picked up by these folder scans.

`impedanceAnalysis_Tools.impdData.read_data()` (Live Tools, Offline Run) applies the same name rule (`_STEP_STEM_PATTERN`, which also accepts a name without the sign letter as positive) and keys each file by its exact setpoint in kelvin, `T_C + 273.15`: `p25p0` gives 298.15, `p50p5` 323.65, `n10p5` 262.65, `p25C` 298.15. Earlier versions truncated to whole degrees and added 273 (`p50p5` gave 323), and failed on names with a `C`.

## runParams.txt

A JSON object with every run parameter: the MFIA parameters, then the temperature-controller parameters, then the output parameters (`dltsRun._current_run_params()`). It is written with `ziDevice.writeDataJson()` (`json.dump(..., indent=4)`), despite the `.txt` extension. The real file from `092826\114655`:

```json
{
    "Oscillation Amplitude": 0.3,
    "Oscillation Frequency": 501000.0,
    "Oscillation ON/OFF": 1,
    "Max bandwidth": 10000.0,
    "Input Control": 0,
    "Current Range": 0.01,
    "Voltage Range": 3.0,
    "Omega Suppression": 80.0,
    "Filter Harmonic": 1,
    "Filter Bandwidth": 2,
    "Data Transfer Rate": 60000,
    "Equivalent Circuit Mode": 0,
    "Threshold Input Signal": 59,
    "State Enable Time": 0.006,
    "State Disable Time": 0.003,
    "Logic Unit Not": 1,
    "Aux Output Signal": 13,
    "Aux Output Scale": -1.0,
    "Aux Output Offset": -0.5,
    "Aux Output Lower Limit": -10.0,
    "Aux Output Upper Limit": 0.0,
    "Signal Output Add": 1,
    "Trigger Source Signal": 36,
    "Initial Temperature (C)": 25.0,
    "Final Temperature (C)": 50.0,
    "Temperature Step (C)": 5.0,
    "Temperature Ramp (C/min)": 5.0,
    "Stability Delay (s)": 0,
    "Room Temperature (C)": 30.0,
    "Room Ramp (C/min)": 10.0,
    "Number of Points (power of 2)": 18,
    "Number of Reps": 100,
    "Data File Format": "HDF5",
    "Data Root Folder": "C:\\Users\\spencer\\Desktop\\DATA\\DLTS"
}
```

The meaning and units of each parameter are described in [runParamsTab.md](runParamsTab.md). Two are used by the readers:

- `State Enable Time` (s) is the reverse-bias duration and `State Disable Time` (s) the fill-pulse duration. `liveDataTab._legacy_run_timing()` reads them to preset the timing fields of the Quick Analysis Offline Data column and of the Qualitative Analysis frame (here 6 ms and 3 ms).
- `Number of Points (power of 2)` sets the samples per step: 2^18 = 262144 here.

`impdData.read_data()` looks for `runParams.txt` in the folder of the first selected file and prints a warning if it is missing.

## The 8 channels

Every step file, JSON or HDF5, holds the same 8 channels. They come from `zurichInstruments_Control.ziDevice.pull_data()`. Runs always call it with `trigger=True`: a triggered acquisition with the MFIA DAQ module in grid mode, `Number of Points` columns and `Number of Reps` repetitions, subscribed to the averaged (`.avg`) sample nodes.

| Channel | Source in a run (`trigger=True`) | Units |
|---|---|---|
| `timeStampImps` | Copy of `tickStampImps` | s |
| `timeStampDemods` | Copy of `tickStampDemods` | s |
| `tickStampImps` | The DAQ grid's time axis, taken from the `/dev32271/imps/0/sample.param1.avg` result | s (float), despite the name |
| `tickStampDemods` | The same `param1.avg` time axis as `tickStampImps` | s (float), despite the name |
| `ImpedanceRe` | `/dev32271/imps/0/sample.param0.avg` (impedance parameter 0) | see below |
| `ImpedanceIm` | `/dev32271/imps/0/sample.param1.avg` (impedance parameter 1) | see below |
| `AbsZ` | Computed as `sqrt(ImpedanceRe**2 + ImpedanceIm**2)` | see below |
| `AuxInput1` | `/dev32271/demods/0/sample.auxin0.avg` (Aux Input 1) | V |

In a triggered run all four time channels are therefore identical. In the example file they run from `0.0` to `4.893336` s in steps of `1.8666666666666665e-05` s (about 53.6 kSa/s), 262144 samples.

The comments in `impedanceAnalysis_Tools.impdData.read_data()` give the intended meaning:

| Channel | Meaning per `read_data()` comments |
|---|---|
| `tickStampImps`, `tickStampDemods` | Impedance / demodulator time stamps in hardware clock ticks |
| `timeStampImps`, `timeStampDemods` | Impedance / demodulator time stamps in seconds |
| `ImpedanceRe` | Real part of the impedance, Ω |
| `ImpedanceIm` | Imaginary part of the impedance, or capacitance, F |
| `AuxInput1` | Demodulation signal or excitation (the fill-pulse / reverse-bias waveform), V |
| `AbsZ` | Absolute value of the impedance, Ω |

What `param0` and `param1` actually are depends on how the MFIA impedance module's display parameters are set on the instrument. This software does not set them. The analysis code treats `ImpedanceIm` as capacitance in farads (it multiplies by 1e12 to get pF). In older runs `ImpedanceIm` is about `2.4e-10` (240 pF, `DLTS\062626\n10p0.txt`); in the example HDF5 run it is about `5e-6`. Because `AbsZ` is computed from `param0` and `param1`, it is the magnitude of the impedance only if those two are the real and imaginary parts. With `param1` a capacitance, `AbsZ` is effectively `abs(ImpedanceRe)` (see the export excerpt in [convert_h5_to_text.md](convert_h5_to_text.md#real-example)).

With `trigger=False` (not used by runs), `pull_data()` polls the device instead: the tick stamps are then the integer 60 MHz clock ticks, the time stamps are `ticks / 60e6` minus the first value, `AbsZ` is the device's own `abs(z)`, and the Imps and Demods channels can differ in length.

## JSON step files (.txt, .json)

Written by `ziDevice.writeDataJson(data, fName)`: one JSON object, `indent=4`, numpy arrays converted to lists. The parent folder is created if needed. The keys are the 8 channels in the order `pull_data()` created them:

```json
{
    "tickStampImps": [
        0.0,
        1.8666666666666665e-05,
        3.733333333333333e-05,
        ...
    ],
    "tickStampDemods": [ ... ],
    "timeStampImps": [ ... ],
    "timeStampDemods": [ ... ],
    "ImpedanceRe": [ ... ],
    "ImpedanceIm": [ ... ],
    "AuxInput1": [ ... ],
    "AbsZ": [ ... ]
}
```

(Start of the real file `DLTS\091526\133851\p25p0.json`, a 16-point test run. All values are floats.)

Properties:

- One value per line, so the files are large: `DLTS\062626\n10p0.txt` (131072 points) is 28.9 MB. The same data in HDF5 is about 8 times smaller (see `benchmarks/bench_results.json`).
- There is no metadata in the file: no setpoint (only the file name), no measured stage temperature, no time stamp (only the file modification time). The run parameters are only in `runParams.txt`.
- The file is written in place, not through a temporary file.

`convert_json_to_h5.py` converts these files to HDF5 without loss.

## HDF5 step files (.h5)

Written by `ziDevice.writeDataH5(data, fName, setpoint_C=None, stage_temperature_C=None, runParams=None, acquired_at=None, extraAttrs=None)`, one file per temperature step.

### Datasets

One 1-D dataset per channel, at the root of the file, named like the JSON keys.

| Channel | dtype |
|---|---|
| `tickStampImps`, `tickStampDemods` | `uint64` if the values are integers (clock ticks); `float64` if they are floats, as in every triggered run |
| all other channels | `float64` |

Every non-empty dataset is chunked and compressed with gzip level 4 plus the shuffle filter. An empty channel is stored as an empty, uncompressed dataset (gzip needs a chunked layout, which an empty dataset cannot have). The chunk size is chosen by h5py; in the example file it is 2048 elements.

### Root attributes

| Attribute | Type | Meaning |
|---|---|---|
| `format_version` | `int64` | Layout version, `ziDevice.H5_FORMAT_VERSION`, currently `1`. Bumped whenever the layout changes. |
| `acquired_at` | string | Local time the file was written (or `acquired_at` if given), ISO 8601 to the second, no time zone, e.g. `2026-09-28T11:48:02`. |
| `setpoint_C` | `float64` | Temperature setpoint in °C, or `NaN` if not given. |
| `stage_temperature_C` | `float64` | Measured stage temperature in °C: the mean of one controller reading before and one after the acquisition (either one if the other failed), or `NaN` if neither could be read. |
| `run_params` | string | `json.dumps()` of the run parameters (the same dictionary as `runParams.txt`, on one line). Absent if no parameters were passed. |
| `converted_from` | string | Only in files made by `convert_json_to_h5.py`: the name of the source JSON file. |

### Writing and crash safety

The file is first written as `<name>.h5.tmp` and then renamed to `<name>.h5` with `os.replace()`. The live watcher waits for `<name>.h5` to appear, so it never sees a half-written file. If the target is locked (for example the watcher is reading the previous version during a Redo), the rename is retried 10 times, 0.5 s apart, before the `PermissionError` is raised. A crash can only cost the step being written.

### Real example: `092826\114655\p25p0.h5`

Inspected with h5py:

```python
import h5py
with h5py.File(r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5", "r") as f:
    for k, v in f.attrs.items():
        print(k, repr(v)[:100])
    for k in f:
        d = f[k]
        print(k, d.shape, d.dtype, d.chunks, d.compression, d.compression_opts, d.shuffle)
```

Output (the `run_params` string is cut):

```text
acquired_at '2026-09-28T11:48:02'
format_version np.int64(1)
run_params '{"Oscillation Amplitude": 0.3, "Oscillation Frequency": 501000.0, "Oscillation ON/OFF": 1, "Max ...
setpoint_C np.float64(25.0)
stage_temperature_C np.float64(25.06325)
AbsZ (262144,) float64 (2048,) gzip 4 True
AuxInput1 (262144,) float64 (2048,) gzip 4 True
ImpedanceIm (262144,) float64 (2048,) gzip 4 True
ImpedanceRe (262144,) float64 (2048,) gzip 4 True
tickStampDemods (262144,) float64 (2048,) gzip 4 True
tickStampImps (262144,) float64 (2048,) gzip 4 True
timeStampDemods (262144,) float64 (2048,) gzip 4 True
timeStampImps (262144,) float64 (2048,) gzip 4 True
```

Value ranges in this file:

| Channel | First value | Min | Max |
|---|---|---|---|
| `AbsZ` | 0.08808 | 0.000867 | 3.037 |
| `AuxInput1` | -0.49956 | -1.50072 | -0.49919 |
| `ImpedanceIm` | 5.1616e-06 | 4.5715e-06 | 5.6927e-06 |
| `ImpedanceRe` | 0.08808 | -1.345 | 3.037 |
| all four time channels | 0.0 | 0.0 | 4.893336 |

`AuxInput1` switches between about -0.5 V and -1.5 V: the GUI's default Aux Output Offset (-0.5 V) and Scale (-1 V). The tick-stamp channels are `float64` because this was a triggered run.

To get a readable copy of a step file, use `convert_h5_to_text.py` or **Export HDF5 File...** on the Input Parameters tab.

## Zurich Instruments MFIA CSV exports

The Offline Data column of the Quick Analysis tab and the Detailed Analysis tab also load data exported with the Zurich Instruments LabOne software instead of this application. When you pick a folder, both tabs (`liveDataTab._scan_folder()`, run by `dataAnalysisTab._scan_quick_folder_async()`, and `detailedAnalysisTab._load_detailed_data()`) try these formats in order and use the first that matches:

1. single combined ZI export,
2. subfolder-per-temperature ZI export,
3. legacy per-temperature files (JSON `.txt`, `.h5`, or `.csv`).

No ZI CSV export is present in the lab data folder, so the descriptions below come from the reader code only.

### 1. Single combined ZI export

The folder directly holds:

| File (regex, case-insensitive) | Content |
|---|---|
| `...imps_0_sample_param1_avg_header...` ending `.csv` | Header table, `;`-separated, one row per chunk. Columns used: `chunk_number`, `history_name`, and from the first row `grid_col_offset` (s), `grid_col_delta` (s), `chunk_size`. |
| `...imps_0_sample_param1_avg_<digits>.csv` (without `header`) | Data table, `;`-separated. Columns used: `chunk` and `value`. |

Each header row whose `history_name` starts with `<digits>C_` (for example `25C_...`) becomes one temperature, mapped to its `chunk_number`. Only positive whole-degree names are recognized; there is no `n` prefix in this format. The first data file found is used for all chunks.

For each temperature, the `value` rows of its chunk (up to `chunk_size`) form the averaged transient. The time axis is `(grid_col_offset + k * grid_col_delta) * 1000` ms, so t = 0 is the start of the reverse bias when `grid_col_offset` is minus the fill-pulse length. Defaults when the header cannot be read: `grid_col_offset = -0.001`, `grid_col_delta = 1.86667e-05`, `chunk_size = 32768`. If the largest absolute value is below 1e-3, the values are taken as farads and multiplied by 1e12 (pF).

The folder name can preset the timing fields: `FP...<number>ms` sets the fill pulse and `RB...<number>ms` the reverse bias, for example `..._FP0V1ms_RB-5V500ms_...`.

### 2. Subfolder-per-temperature ZI export

The folder holds one subfolder per temperature, named like `0C`, `100C`, `n10C` (negative) or `120C_000`, matching `^(n?)(\d+)C(?:_\d+)?$`. Each subfolder holds its own `...imps_0_sample_param1_avg_<digits>.csv` data file and optionally its own `..._header...csv`. The data file is read with columns `chunk;timestamp;value`, and only chunk `0` is used. Grid parameters come from that subfolder's header (same defaults as above). This is the convention of the standalone `DLTS_APP.py`, which the Detailed Analysis tab was ported from. `DLTS_APP.py` itself only looks for the exact name `dev32271_imps_0_sample_param1_avg_00000.csv` and skips subfolders with fewer than 100 rows.

### 3. Legacy CSV files

In the legacy branch, each `.csv` file whose name matches `_LEGACY_FILENAME_PATTERN` is classified by its first line:

| First line | Treatment |
|---|---|
| Contains `;` and `chunk` | Chunked ZI-style CSV. With more than one chunk (or `p120C-p160C` in the name) the chunks are mapped to fixed temperatures: chunk 0..8 = 120, 125, ..., 160 °C. With one chunk, the temperature comes from the file name. The last column whose name contains `value`, `smoothed`, `cap` or `impedance` is the transient; F is converted to pF as above; the time axis is `k` times the sampling interval (`dltsc.manual_samplingRate`, default `1.8666666666666665e-05` s; Detailed Analysis always uses the default). |
| Contains `;` and `smoothed_value` or `timestamp` | Same, without chunk filtering. |
| Anything else | Read as a plain comma-separated table: column 0 = time in ms, column 1 = capacitance, used as is (no unit conversion). |

The chunk-to-temperature map for multi-chunk files is fixed in the code (from `DrKayisScript.py`); it is correct only for the one data set it was written for.

### CSV input to impdData.read_data()

`impedanceAnalysis_Tools.impdData.read_data()` (Live Tools, Offline Run) has a separate CSV reader for a set of LabOne export files selected together. Files are classified by substrings of their names: `_imps_0` = capacitance (header files contain `_header_`), `_auxin0_` = excitation, `_r_avg_` = demodulator R. Missing files are asked for in a file dialog. Temperatures come from column 16 of the capacitance header (names like `p25C_...` or `n10C_...`). Data files are `;`-separated with `chunk`, `timestamp` and `value` columns; `timestamp` is taken as 60 MHz clock ticks. `ImpedanceRe` is filled with zeros.

## Opening HDF5 step files

### HDFView

Open the `.h5` file with **File > Open**. The tree shows the 8 datasets under the root group `/`. Select `/` to see the root attributes (setpoint, stage temperature, acquisition time, `run_params`). Double-click a dataset to see its values in a table. gzip and shuffle are standard HDF5 filters, so HDFView reads the files without plugins.

Do not open a step file while a run is writing to the same folder, and never save changes from HDFView into a run's files.

### MATLAB

```matlab
f = 'C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5';

h5disp(f)                                  % layout and attributes
cap  = h5read(f, '/ImpedanceIm');          % column vector, double
t    = h5read(f, '/timeStampImps');        % seconds
aux  = h5read(f, '/AuxInput1');            % volts
Tset = h5readatt(f, '/', 'setpoint_C');
Tmea = h5readatt(f, '/', 'stage_temperature_C');   % NaN if not measured
p    = jsondecode(h5readatt(f, '/', 'run_params'));
```

`jsondecode` turns the parameter names into valid MATLAB field names (spaces and brackets are removed), so use `fieldnames(p)` to see them. If a file stores integer tick stamps, `h5read` returns them as `uint64`; convert with `double()` before arithmetic, or subtract the first value first to keep precision.

### Python

With the application's own reader:

```python
import os
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "8")
import impedanceAnalysis_Tools as iaT

rec = iaT.read_h5_record(r"C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5")
rec["ImpedanceIm"][:5]
rec = iaT.read_h5_record(path, keys=("AuxInput1", "ImpedanceIm"))   # only two channels
```

`read_h5_record(file_path, keys=None)` returns the same `{channel: values}` dictionary a JSON step file gives, with numpy arrays instead of lists. `uint64` tick stamps are returned as `int64`, the dtype numpy gives JSON integers, because `cleanup_data()` takes `np.diff()` of them. It does not return the attributes. Importing `impedanceAnalysis_Tools` also imports `zhinst`, `torch`, `sklearn`, `lmfit` and other heavy packages.

With h5py only, including the attributes:

```python
import json, h5py

with h5py.File(path, "r") as f:
    cap = f["ImpedanceIm"][()]
    setpoint = f.attrs["setpoint_C"]
    params = json.loads(f.attrs["run_params"])
```

`convert_h5_to_text.read_h5_file(path)` returns both the attributes (with `run_params` decoded) and the channels.

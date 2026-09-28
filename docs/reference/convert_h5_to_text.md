# convert_h5_to_text

## What it's for

`convert_h5_to_text.py` exports one HDF5 step file (written by `zurichInstruments_Control.ziDevice.writeDataH5()`) to a human-readable file for inspection. Two output formats exist:

| Format | Content |
|---|---|
| `.txt` | `#` header lines with the file's root attributes (setpoint, measured stage temperature, acquisition time, run parameters), then a tab-separated table with one column per channel. Opens in Notepad, Excel or Origin. |
| `.json` | `{"source": ..., "attributes": {...}, "channels": {name: [values]}}`, indented by 2 spaces. |

Values are written at full precision (Python `repr()` of each float, which round-trips exactly). Every export is read back and compared with the `.h5` data before it is kept. If the comparison fails, no output file is left behind.

The export is a copy for people to read. The analysis tabs do not read it. To keep it that way, the tool refuses output names that look like a step file (`p25p0.txt`, `n10p0.json`, ...), and the default output name is `<name>_export.txt` or `<name>_export.json`.

The same function is used by the **Export HDF5 File...** button on the Input Parameters tab (see [GUI button](#gui-button-export-hdf5-file) below).

## Command line

```text
python convert_h5_to_text.py FILE.h5 [FILE.h5 ...] [--format txt|json]
python convert_h5_to_text.py FILE.h5 -o OUTPUT.txt
```

| Option | Meaning |
|---|---|
| `files` (positional, one or more) | `.h5` step files to export. |
| `--format {txt,json}` | Output format. Default: taken from the `-o` extension (`.json` gives JSON, anything else gives the text table); without `-o`, `txt`. |
| `-o`, `--output OUTPUT` | Output file. Allowed only with a single input file; otherwise the script stops with `-o/--output takes a single input file` (exit code 2). Without `-o`, each file goes to `<stem>_export.<format>` next to its `.h5` file. |

For each input file the script prints one line, either

```text
<input> -> <output> (<rows> rows x <channels> channels, <size> MB)
```

or `<input>: failed: <reason>`. The exit code is `1` if any file failed, else `0`. A failure does not stop the remaining files.

### Real example

The command below exports the 25 °C step of the run `092826\114655` (a 2^18-point HDF5 run, 8.7 MB `.h5` file):

```text
python convert_h5_to_text.py "C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5" -o "%TEMP%\p25p0_export.txt"
```

It printed:

```text
C:\Users\spencer\Desktop\DATA\DLTS\092826\114655\p25p0.h5 -> C:\Users\spencer\AppData\Local\Temp\p25p0_export.txt (262144 rows x 8 channels, 35.9 MB)
```

and took about 3 s. The first lines of the output file (lines longer than about 160 characters are cut here and marked `...`):

```text
# DLTS step exported from p25p0.h5
# acquired_at: 2026-09-28T11:48:02
# format_version: 1
# run_params: {"Oscillation Amplitude": 0.3, "Oscillation Frequency": 501000.0, "Oscillation ON/OFF": 1, "Max bandwidth": 10000.0, "Input Control": 0, "Current  ...
# setpoint_C: 25.0
# stage_temperature_C: 25.06325
# 262144 rows; columns are tab-separated, empty cells mean a shorter channel
timeStampImps	timeStampDemods	tickStampImps	tickStampDemods	ImpedanceRe	ImpedanceIm	AbsZ	AuxInput1
0.0	0.0	0.0	0.0	0.08808358165588324	5.1615895110309485e-06	0.08808358180711465	-0.4995596262122852
1.8666666666666665e-05	1.8666666666666665e-05	1.8666666666666665e-05	1.8666666666666665e-05	0.08546414090096481	5.091041104975873e-06	0.08546414105259975	-0.499 ...
3.733333333333333e-05	3.733333333333333e-05	3.733333333333333e-05	3.733333333333333e-05	0.08363013272873036	5.1797908965950025e-06	0.08363013288914045	-0.499503 ...
```

The text export is about 4 times larger than the `.h5` file (35.9 MB against 8.7 MB here). In this triggered run all four time columns hold the same seconds axis; see [data_formats.md](data_formats.md#the-8-channels).

## GUI button: Export HDF5 File...

The button sits next to **Apply + Push Params** in the output-parameter group of the **Input Parameters** tab (`runParamsTab.export_h5_file()`). It:

1. Opens a file dialog for a `.h5` file, starting in the **Data Root Folder** if one is set.
2. Opens a save dialog in the same folder, with `<stem>_export.txt` as the suggested name. The file types are "Text table, tab-separated (*.txt)" and "JSON (*.json)". The format follows the extension of the name you save as.
3. Disables the button, runs `export_h5(h5Path, outPath)` on a background thread, then re-enables the button and writes one line to the log box: `Exported <file> -> <output> (TXT, <rows> rows x <channels> channels, <size> MB).` or `Export of <file> failed: <reason>`.

The refusal of step-file-like names applies here too. Choosing `p25p0.txt` in the save dialog gives a "failed" log line, not a file.

## Import

```python
import convert_h5_to_text as h5txt

result = h5txt.export_h5(r"C:\data\092826\114655\p25p0.h5")   # -> p25p0_export.txt
attrs, channels = h5txt.read_h5_file(r"C:\data\092826\114655\p25p0.h5")
```

The module needs only `h5py` and `numpy` (plus the standard library); it no longer imports `convert_json_to_h5` or any instrument module.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `FORMATS` | `('txt', 'json')` | Accepted output formats. |
| `_STEP_NAME` | regex `^[npNP]\d+(?:[pP]\d+)?[cC]?(?:_\d+)?\.(txt\|json\|csv\|h5)$`, case-insensitive | Output names refused because the analysis tabs would read them as run steps. |
| `CHANNEL_ORDER` | `('timeStampImps', 'timeStampDemods', 'tickStampImps', 'tickStampDemods', 'ImpedanceRe', 'ImpedanceIm', 'AbsZ', 'AuxInput1')` | Column order in exports: time axes first. HDF5 lists datasets alphabetically, so without this the table would start with `AbsZ`. Datasets not in this tuple follow, in alphabetical order. |

## Functions

### read_h5_file(path)

Read one step file into plain Python values.

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `str` | `.h5` step file. |

**Returns** `(attrs, channels)`:

- `attrs`: `dict` of the root attributes, in the order h5py lists them (alphabetical in the files the app writes). Numpy scalars become Python scalars (`.item()`), `bytes` are decoded as UTF-8, and `run_params` is parsed from its JSON string into a `dict` (left as a string if it is not valid JSON).
- `channels`: `dict` of channel name to numpy array in the file's own dtype (`uint64` tick stamps stay `uint64`), ordered by `CHANNEL_ORDER` and then alphabetically.

**Side effects** Opens the file read-only.

**Example**

```python
attrs, ch = h5txt.read_h5_file('p25p0.h5')
attrs['setpoint_C'], attrs['run_params']['Number of Reps'], ch['ImpedanceIm'][:3]
```

Unlike `impedanceAnalysis_Tools.read_h5_record()`, this function also returns the attributes and does not cast `uint64` to `int64`.

### default_output_path(h5Path, fmt='txt')

The default export name.

| Parameter | Type | Meaning |
|---|---|---|
| `h5Path` | `str` | Input path. |
| `fmt` | `str` | `'txt'` or `'json'`. Not checked. |

**Returns** `<h5Path without extension>_export.<fmt>`, for example `C:\run\p25p0_export.txt`.

**Side effects** None.

**Example**

```python
h5txt.default_output_path(r'C:\run\p25p0.h5', 'json')   # 'C:\\run\\p25p0_export.json'
```

### format_from_path(path)

**Returns** `'json'` if the extension of `path` is `.json` (any case), else `'txt'`.

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `str` | Output path. |

**Side effects** None.

**Example**

```python
h5txt.format_from_path('out.JSON')   # 'json'
h5txt.format_from_path('out.csv')    # 'txt'
```

### write_txt(path, attrs, channels, source)

Write the tab-separated text table.

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `str` | File to write (overwritten). |
| `attrs` | `dict` | Attributes from `read_h5_file()`. |
| `channels` | `dict` | Channels from `read_h5_file()`. |
| `source` | `str` | Name written in the first header line. |

Layout, UTF-8 with `\n` line ends:

1. `# DLTS step exported from <source>`
2. One `# <key>: <value>` line per attribute. A `dict` value (the run parameters) is written as one line of JSON, with `NaN` as `null`. Other values: floats as `repr()` (`nan` for NaN), everything else as `str()`.
3. `# <rows> rows; columns are tab-separated, empty cells mean a shorter channel`, where `rows` is the length of the longest channel.
4. The header row of channel names, tab-separated.
5. One row per sample. Floats as `repr()` (`nan` for NaN), integers as `str()`. A channel shorter than the longest one gets empty cells at the end.

**Returns** `None`.

**Side effects** Writes `path`.

**Example**

```python
attrs, ch = h5txt.read_h5_file('p25p0.h5')
h5txt.write_txt('p25p0_export.txt', attrs, ch, 'p25p0.h5')
```

### read_txt(path)

Read the channel table back from a `write_txt()` file, for verification.

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `str` | A file written by `write_txt()`. |

**Returns** `dict` of column name to `list[str]` of the non-empty cells. Lines starting with `#` are ignored; the first remaining line is the header row.

**Side effects** None.

**Example**

```python
cols = h5txt.read_txt('p25p0_export.txt')
float(cols['ImpedanceIm'][0])
```

### write_json(path, attrs, channels, source)

Write the JSON export: `{"source": source, "attributes": attrs, "channels": {name: [values]}}`, indented by 2, UTF-8, non-ASCII characters kept. Non-finite floats (NaN, ±inf) become `null`, both in attributes and in channels.

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `str` | File to write (overwritten). |
| `attrs` | `dict` | Attributes from `read_h5_file()`. |
| `channels` | `dict` | Channels from `read_h5_file()`. |
| `source` | `str` | Stored under `"source"`. |

**Returns** `None`.

**Side effects** Writes `path`.

**Example**

```python
h5txt.write_json('p25p0_export.json', attrs, ch, 'p25p0.h5')
```

A step without a measured stage temperature (for example a file made by `convert_json_to_h5.py`) therefore has `"stage_temperature_C": null` in JSON and `# stage_temperature_C: nan` in the text table.

### verify(path, fmt, channels)

Check that an export holds exactly the `.h5` channel values.

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `str` | The written export. |
| `fmt` | `'txt'` or `'json'` | How to read it back. Anything other than `'json'` is read as text. |
| `channels` | `dict` | The channels from `read_h5_file()`. |

**Returns** `None` when everything matches.

**Side effects** Reads `path`. Raises `ValueError` if the channel names or their order differ, if a channel has a different number of values, or if any value differs. Integer channels are parsed with `int()` into the original dtype. Float channels are parsed with `float()` (`null` becomes NaN) and compared with NaN equal to NaN.

**Example**

```python
h5txt.verify('p25p0_export.txt', 'txt', ch)
```

### export_h5(h5Path, outPath=None, fmt=None)

Export one file. This is what the command line and the GUI button call.

| Parameter | Type | Meaning |
|---|---|---|
| `h5Path` | `str` | `.h5` step file. |
| `outPath` | `str` or `None` | Output file. `None`: `default_output_path(h5Path, fmt)`. |
| `fmt` | `'txt'`, `'json'` or `None` | `None`: `format_from_path(outPath)` if `outPath` is given, else `'txt'`. |

Checks, in order, before anything is read:

1. `fmt` must be in `FORMATS`, else `ValueError: unknown format ...`.
2. If both `fmt` and an output ending in `.txt`/`.json` are given, they must agree, else `ValueError: format 'json' doesn't match the output extension of 'x.txt'`.
3. The output must not be the input file (compared by absolute path).
4. The output must not end in `.h5`, else `ValueError: the output must be a text file (.txt or .json), not .h5: that would replace data`.
5. The output's file name must not look like a step file (`_STEP_NAME`: `p25p0.txt`, `n10p0.json`, `p30p0.csv`, `p120C.h5`, `p25p0_1.txt`, any letter case). Otherwise: `ValueError: 'p25p0.txt' is named like a run's step file, so the analysis tabs would read it as data; choose another name, e.g. p25p0_export.txt`.

The export is then written to `<outPath>.tmp`, verified, and renamed to `outPath` with `os.replace()` (an existing file is overwritten). The `.tmp` file is removed in every case.

**Returns** `dict`:

| Key | Meaning |
|---|---|
| `'output'` | Output path. |
| `'format'` | `'txt'` or `'json'`. |
| `'channels'` | Number of channels. |
| `'rows'` | Length of the longest channel. |
| `'bytes'` | Size of the output file. |

**Side effects** Writes `outPath`. Raises on any failure; no partial output is left.

**Example**

```python
r = h5txt.export_h5(r'C:\run\p25p0.h5', fmt='json')
print(r['output'], r['rows'], r['bytes'])
```

### main(argv=None)

The command-line entry point.

| Parameter | Type | Meaning |
|---|---|---|
| `argv` | `list[str]` or `None` | Arguments without the program name. `None` uses `sys.argv[1:]`. |

**Returns** `int`: `1` if any file failed, else `0`.

**Side effects** Calls `export_h5()` for each file and prints one line per file.

**Example**

```python
h5txt.main([r'C:\run\p25p0.h5', r'C:\run\p30p0.h5', '--format', 'json'])
```

## Internal helpers

### _plain(value)

Makes a value JSON-safe: a non-finite Python `float` becomes `None`; `dict` and `list` are converted recursively; anything else is returned unchanged.

### _values(arr)

`arr.tolist()`: a numpy array as Python ints or floats. `repr()` of those floats round-trips exactly.

### _cell(value)

Text for one table cell or header value: `'nan'` for a NaN float, `repr(value)` for other floats, `str(value)` for everything else.

## Notes and limitations

- The step-name refusal covers `.txt`, `.json`, `.csv` and `.h5` in any letter case, and no output may end in `.h5`, so an export can neither be taken for run data nor replace a step file. (Earlier versions only refused `.txt`/`.json` step names; fixed, with tests in `tests/test_convert_h5_to_text.py`.)
- `--format` must agree with a `.txt`/`.json` output extension. With another extension (for example `-o out.dat`), `--format` decides the content.
- The output folder must exist; it is not created.
- The whole step is held in memory, twice (arrays and Python lists). A 2^18-point step exports in a few seconds.
- `read_h5_file()` calls `.item()` on array-valued attributes too. The app writes only scalar and string attributes, so this is not a problem for its own files. An array attribute with more than one element would raise `ValueError`.
- Tests: `tests/test_convert_h5_to_text.py` (see [other_scripts.md](other_scripts.md)).

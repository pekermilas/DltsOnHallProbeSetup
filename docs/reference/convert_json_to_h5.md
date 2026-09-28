# convert_json_to_h5

## What it's for

`convert_json_to_h5.py` converts existing DLTS run folders from JSON step files (`p25p0.txt`, `n10p0.txt`, `p25p0.json`, ...) to HDF5 step files (`p25p0.h5`, ...). It is a batch tool you run from the command line. It does not talk to any instrument.

Each converted file is written with the same writer a run uses when **Data File Format** is `HDF5` (`zurichInstruments_Control.ziDevice.writeDataH5()`). The GUI therefore reads a converted run exactly like a run that was recorded in HDF5. See [data_formats.md](data_formats.md) for both file layouts.

What goes into each `.h5` file:

| HDF5 content | Taken from |
|---|---|
| The 8 channel datasets | The JSON step file, value for value |
| `setpoint_C` attribute | The file name (`p25p0.txt` gives `25.0`, `n10p0.txt` gives `-10.0`) |
| `run_params` attribute | `runParams.txt` in the same folder (left out if that file is missing) |
| `acquired_at` attribute | The JSON file's modification time |
| `stage_temperature_C` attribute | Always `NaN`: JSON runs never recorded the measured stage temperature |
| `converted_from` attribute | The JSON file name, for example `p25p0.txt` |
| `format_version` attribute | `ziDevice.H5_FORMAT_VERSION` (currently `1`) |

Every `.h5` file is read back and compared value by value with its JSON source before the JSON file is touched. Only then is the JSON file moved, deleted, or left in place, depending on the options. If anything fails, the `.h5` file (and its `.tmp` file) is removed and the JSON file stays where it was.

By default a verified JSON file is moved into a `json_originals\` subfolder of the run folder. Leaving it next to the new `.h5` file would put two copies of the same temperature in the folder, and the folder scans in the analysis tabs would pick up both. `runParams.txt` is never moved, because the analysis code reads it from the run folder.

## Command line

```text
python convert_json_to_h5.py RUN_FOLDER [RUN_FOLDER ...]
python convert_json_to_h5.py --recursive DATA_ROOT_FOLDER
```

| Option | Meaning |
|---|---|
| `folders` (positional, one or more) | Run folders to convert. With `--recursive`, folders to search below. Each must be an existing folder, or the script stops with a usage error (exit code 2). |
| `--recursive` | Also convert every folder below the given folders that directly holds at least one step file. `json_originals` folders are skipped. |
| `--delete-json` | Delete each verified JSON file instead of moving it to `json_originals\`. This is the only option that frees disk space right away. |
| `--keep-json` | Leave each verified JSON file where it is. Cannot be combined with `--delete-json`. |
| `--overwrite` | Reconvert steps that already have a `.h5` file. Without it such steps are skipped. |
| `--dry-run` | Only list what would be converted. Nothing is written, moved, or deleted. |

The exit code is `1` if any file failed and `0` otherwise (also `0` when no step files were found).

Typical use:

```text
python convert_json_to_h5.py --dry-run --recursive "C:\Users\spencer\Desktop\DATA\DLTS"
python convert_json_to_h5.py --recursive "C:\Users\spencer\Desktop\DATA\DLTS"
```

Real dry-run output for a JSON run folder (shortened):

```text
C:\Users\spencer\Desktop\DATA\DLTS\091526\133851: 21 step file(s)
  p100p0.json: would convert
  p105p0.json: would convert
  ...
  p95p0.json: would convert
Dry run: 21 file(s) (0.1 MB) would be converted, 0 skipped.
```

A real conversion prints one header line per folder, one line per skipped or failed file, and a summary. This is the real output for a temporary copy of the run folder `092526\114016` (three 32768-point `.txt` step files, no `runParams.txt`):

```text
C:\Users\spencer\AppData\Local\Temp\convtest_run: 3 step file(s) (no runParams.txt: run_params not stored)
Converted 3 file(s): 21.0 MB of JSON -> 3.1 MB of HDF5. Skipped 0, failed 0.
Originals were moved to json_originals/ in each run folder; delete those folders to free the space.
```

Afterwards the folder held `p300p0.h5`, `p304p0.h5`, `p308p0.h5` (about 1.0 to 1.2 MB each) and `json_originals\p300p0.txt` etc. (about 7.3 MB each).

To get the disk space back after checking the converted runs in the GUI, delete the `json_originals` folders, or run with `--delete-json` in the first place.

## Import

```python
import convert_json_to_h5 as conv

stats = conv.convert_folder(r"C:\Users\spencer\Desktop\DATA\DLTS\091526\133851", jsonAction='keep')
print(stats)
```

Importing the module imports `zurichInstruments_Control`, which imports `zhinst.core`, `zhinst.toolkit`, `matplotlib` and `dltsConfig`. Those packages must be installed even though no instrument is used.

## Module constants and globals

| Name | Value / type | Meaning |
|---|---|---|
| `STEP_FILE_PATTERN` | `re.compile(r'^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt\|json)$')` | A JSON step file name: sign letter `p`/`n`, integer part, optional `p` + fraction digits, optional `C`, optional `_<n>` suffix, extension `.txt` or `.json`. Matches `p25p0.txt`, `n10p0.txt`, `p120.txt`, `p25C.txt`, `p25p0_1.txt`, `p25p0.json`. Does not match `runParams.txt`, `notes.txt`, `.h5` or `.csv` files. |
| `ORIGINALS_DIR` | `'json_originals'` | Subfolder that receives verified JSON files in the default mode. |
| `PARAMS_FILE` | `'runParams.txt'` | Name of the run-parameter file read from each run folder. |

## Functions

### setpoint_from_name(fileName)

The setpoint in °C encoded in a step file name.

| Parameter | Type | Meaning |
|---|---|---|
| `fileName` | `str` | A bare file name, not a path. |

**Returns** `float`, or `None` if the name does not match `STEP_FILE_PATTERN`. The value is `integer.fraction`, negated for an `n` prefix. The fraction digits are read as decimal digits: `p50p5` is `50.5`, `p25p05` is `25.05`.

**Side effects** None.

**Example**

```python
>>> conv.setpoint_from_name('n10p0.txt')
-10.0
>>> conv.setpoint_from_name('p25p0.h5') is None
True
```

`convert_h5_to_text.py` also uses this function to refuse output names that look like step files.

### step_files(folder)

The JSON step files directly inside one folder.

| Parameter | Type | Meaning |
|---|---|---|
| `folder` | `str` | Folder to list. |

**Returns** `list[str]` of bare file names that match `STEP_FILE_PATTERN` and are regular files, sorted as strings (so `p100p0.txt` comes before `p25p0.txt`).

**Side effects** None.

**Example**

```python
names = conv.step_files(r"C:\data\091526\133851")   # ['p100p0.json', 'p105p0.json', ...]
```

### find_run_folders(roots, recursive)

The folders to convert.

| Parameter | Type | Meaning |
|---|---|---|
| `roots` | iterable of `str` | Folders given on the command line. |
| `recursive` | `bool` | `False`: return `roots` unchanged. `True`: walk each root with `os.walk()` and return every folder (the root included) that directly holds at least one step file. Subfolders named `json_originals` are not entered. Subfolders are visited in sorted order. |

**Returns** `list[str]`.

**Side effects** None.

**Example**

```python
folders = conv.find_run_folders([r"C:\Users\spencer\Desktop\DATA\DLTS"], recursive=True)
```

Without `recursive`, a folder with no step files is still returned. It then prints `0 step file(s)` and converts nothing.

### verify(jsonData, h5Path)

Check that an `.h5` file holds exactly the values of a JSON step file.

| Parameter | Type | Meaning |
|---|---|---|
| `jsonData` | `dict` | The parsed JSON step file: channel name to list of values. |
| `h5Path` | `str` | The `.h5` file to check. |

**Returns** `None` when everything matches.

**Side effects** Opens `h5Path` read-only. Raises `ValueError` if:

- the set of datasets differs from the set of JSON keys (`channels differ: ...`);
- a `uint64` dataset's JSON source has a negative value (`negative tick stamps can't be stored as uint64`);
- any channel's shape or values differ (`<name>: values changed on conversion`). `NaN` equals `NaN` for float datasets.

`uint64` datasets are cast to `int64` before the comparison, so the JSON integers compare directly.

**Example**

```python
import json
with open('p25p0.txt') as f:
    conv.verify(json.load(f), 'p25p0.h5')
```

### load_run_params(folder)

Read the folder's `runParams.txt`.

| Parameter | Type | Meaning |
|---|---|---|
| `folder` | `str` | Run folder. |

**Returns** the parsed JSON (normally a `dict`), or `None` if the file does not exist. A file that exists but is not valid JSON raises `json.JSONDecodeError`, which is not caught in `convert_folder()`.

**Side effects** None.

**Example**

```python
params = conv.load_run_params(r"C:\data\092826\114655")
```

### convert_file(dev, folder, name, runParams, jsonAction, overwrite, dryRun)

Convert one step file.

| Parameter | Type | Meaning |
|---|---|---|
| `dev` | `zurichInstruments_Control.ziDevice` | Used only for its `writeDataH5()` method. It need not be connected. |
| `folder` | `str` | Run folder. |
| `name` | `str` | Step file name inside `folder`. |
| `runParams` | `dict` or `None` | Stored as the `run_params` attribute; `None` leaves the attribute out. |
| `jsonAction` | `'move'`, `'delete'` or `'keep'` | What to do with the JSON file after verification. |
| `overwrite` | `bool` | Reconvert even if the `.h5` file exists. |
| `dryRun` | `bool` | Only report what would happen. |

The output path is the JSON path with its extension replaced by `.h5`.

**Returns** a tuple `(status, message, bytesBefore, bytesAfter)`:

| `status` | When | `message` | Byte counts |
|---|---|---|---|
| `'skipped'` | The `.h5` exists and `overwrite` is `False` | `'<name>.h5 already exists'` | `0, 0` |
| `'skipped'` | `jsonAction == 'move'` and `json_originals\<name>` already exists | `'json_originals/<name> already exists'` | `0, 0` |
| `'converted'` | `dryRun` is `True` (and neither skip applies) | `'would convert'` | JSON size, `0` |
| `'failed'` | Reading, writing or verification raised | The exception text | `0, 0` |
| `'converted'` | Success | `''` | JSON size, `.h5` size |

The skip checks run before the dry-run check, so a dry run reports skips correctly. A dry run does not open the JSON files, so a file that would fail is still listed as `would convert`.

**Side effects** Writes `<stem>.h5` (through `<stem>.h5.tmp`). On failure, deletes `<stem>.h5` and `<stem>.h5.tmp` if present. On success, moves the JSON file to `json_originals\` (creating the folder), deletes it, or leaves it, as `jsonAction` says. A JSON file whose top level is not a non-empty object fails with `not a DLTS step file (expected an object of channels)`.

**Example**

```python
import zurichInstruments_Control as ziC
dev = ziC.ziDevice()
status, msg, before, after = conv.convert_file(dev, r"C:\data\run", 'p25p0.txt', None, 'keep', False, False)
```

### convert_folder(folder, jsonAction='move', overwrite=False, dryRun=False, log=print)

Convert every step file in one run folder.

| Parameter | Type | Meaning |
|---|---|---|
| `folder` | `str` | Run folder. |
| `jsonAction` | `'move'`, `'delete'` or `'keep'` | See `convert_file()`. |
| `overwrite` | `bool` | See `convert_file()`. |
| `dryRun` | `bool` | See `convert_file()`. |
| `log` | callable taking one `str` | Receives the progress lines. |

**Returns** `dict` with keys `'converted'`, `'skipped'`, `'failed'` (counts) and `'bytesBefore'`, `'bytesAfter'` (sums in bytes).

**Side effects** Creates one `ziDevice()` (no connection), reads `runParams.txt`, calls `convert_file()` for each name from `step_files()`. Logs `<folder>: <n> step file(s)`, with ` (no runParams.txt: run_params not stored)` appended when that file is missing. In a dry run it logs every file; otherwise it logs only skipped and failed files.

**Example**

```python
lines = []
stats = conv.convert_folder(r"C:\data\run", jsonAction='keep', log=lines.append)
```

### main(argv=None)

The command-line entry point.

| Parameter | Type | Meaning |
|---|---|---|
| `argv` | `list[str]` or `None` | Arguments without the program name. `None` uses `sys.argv[1:]`. |

**Returns** `int` exit code: `1` if any file failed, else `0`. Argument errors raise `SystemExit(2)` from `argparse`.

**Side effects** Everything `convert_folder()` does, for each folder from `find_run_folders()`, plus the summary printed to stdout.

**Example**

```python
conv.main(['--dry-run', '--recursive', r"C:\Users\spencer\Desktop\DATA\DLTS"])
```

## Internal helpers

None. All functions are listed above.

## Notes and limitations

- Converting twice is safe. The second pass finds no JSON step files (they were moved) or skips every step whose `.h5` exists.
- `--overwrite` only helps while the JSON file is still in the run folder. After a default (`move`) conversion the JSON file is in `json_originals\`, so there is nothing left to reconvert. Move the files back first. With `--overwrite` and the default `move`, a step is still skipped if `json_originals\<name>` already exists.
- If a folder holds both `p25p0.txt` and `p25p0.json`, both map to `p25p0.h5`. The first one in sorted order (`p25p0.json`) is converted and the other is skipped as `p25p0.h5 already exists`.
- `acquired_at` is the JSON file's modification time. If the file was copied or unzipped, that can be the copy time, not the acquisition time.
- Files in the older layout, directly in a date folder (for example `DLTS\062626\n10p0.txt`), convert fine. They have no `runParams.txt` next to them, so `run_params` is not stored.
- The step file pattern accepts `.json`, but the Live Tools folder scan (`liveDataTab._LEGACY_FILENAME_PATTERN`) accepts only `.txt`, `.csv` and `.h5`. Converting old `.json` runs to `.h5` makes them visible to that scan.
- A failure in one file does not stop the others. Check the summary line and the exit code.
- Tests: `tests/test_convert_json_to_h5.py` (see [other_scripts.md](other_scripts.md)).

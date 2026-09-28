"""Export one HDF5 step file (written by ziDevice.writeDataH5()) to a human-readable
text file for inspection: a tab-separated .txt table or an indented .json file.

  .txt   '#' header lines with the file's attributes (setpoint, measured stage
         temperature, acquisition time, run parameters), then one column per
         channel -- opens in Notepad, Excel or Origin.
  .json  {"source": ..., "attributes": {...}, "channels": {name: [values]}}.

Values are written at full precision (shortest exact form), and every export is
read back and compared with the .h5 file before it is kept. An output name like
p25p0.txt is refused: the analysis tabs would take it for a JSON step file of a
run, so exports default to <name>_export.txt / .json.

The GUI's Input Parameters tab has an "Export HDF5 File..." button for this.

Usage:
    python convert_h5_to_text.py FILE.h5 [FILE.h5 ...] [--format txt|json]
    python convert_h5_to_text.py FILE.h5 -o OUTPUT.txt
"""
import argparse
import json
import math
import os
import sys

import h5py
import numpy as np

from convert_json_to_h5 import setpoint_from_name

FORMATS = ('txt', 'json')
# Column order in exports: time axes first (HDF5 lists channels alphabetically).
CHANNEL_ORDER = ('timeStampImps', 'timeStampDemods', 'tickStampImps', 'tickStampDemods',
                 'ImpedanceRe', 'ImpedanceIm', 'AbsZ', 'AuxInput1')


def read_h5_file(path):
    """(attributes, channels) of one step file: plain Python attribute values
    (run_params decoded from its JSON string) and {channel: numpy array}."""
    with h5py.File(path, 'r') as f:
        attrs = {}
        for key, value in f.attrs.items():
            value = value.item() if hasattr(value, 'item') else value
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            if key == 'run_params' and isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            attrs[key] = value
        names = [k for k in CHANNEL_ORDER if k in f] + sorted(k for k in f.keys() if k not in CHANNEL_ORDER)
        channels = {key: f[key][()] for key in names}
    return attrs, channels


def default_output_path(h5Path, fmt='txt'):
    stem = os.path.splitext(h5Path)[0]
    return f"{stem}_export.{fmt}"


def format_from_path(path):
    return 'json' if os.path.splitext(path)[1].lower() == '.json' else 'txt'


def _plain(value):
    """JSON-safe value: NaN/inf become null (JSON has no NaN)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _values(arr):
    """Channel as Python ints/floats (exact: repr of a float round-trips)."""
    return arr.tolist()


def _cell(value):
    if isinstance(value, float):
        return 'nan' if math.isnan(value) else repr(value)
    return str(value)


def write_txt(path, attrs, channels, source):
    names = list(channels)
    columns = [_values(channels[n]) for n in names]
    nRows = max((len(c) for c in columns), default=0)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"# DLTS step exported from {source}\n")
        for key, value in attrs.items():
            text = json.dumps(_plain(value), ensure_ascii=False) if isinstance(value, dict) else _cell(value)
            f.write(f"# {key}: {text}\n")
        f.write(f"# {nRows} rows; columns are tab-separated, empty cells mean a shorter channel\n")
        f.write('\t'.join(names) + '\n')
        for i in range(nRows):
            f.write('\t'.join(_cell(c[i]) if i < len(c) else '' for c in columns) + '\n')


def read_txt(path):
    """Channels back from write_txt()'s table, for verification."""
    with open(path, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f if not line.startswith('#')]
    names = lines[0].split('\t')
    columns = {n: [] for n in names}
    for line in lines[1:]:
        for name, cell in zip(names, line.split('\t')):
            if cell != '':
                columns[name].append(cell)
    return columns


def write_json(path, attrs, channels, source):
    doc = {'source': source, 'attributes': _plain(attrs),
           'channels': {name: _plain(_values(arr)) for name, arr in channels.items()}}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)


def verify(path, fmt, channels):
    """Raise ValueError unless the export holds exactly the .h5 channel values."""
    if fmt == 'json':
        with open(path, 'r', encoding='utf-8') as f:
            stored = json.load(f)['channels']
    else:
        stored = read_txt(path)
    if list(stored) != list(channels):
        raise ValueError(f"channels differ: {list(stored)} vs {list(channels)}")
    for name, arr in channels.items():
        values = stored[name]
        if len(values) != arr.size:
            raise ValueError(f"{name}: {len(values)} values written, {arr.size} expected")
        if arr.dtype.kind in 'iu':
            back = np.array([int(v) for v in values], dtype=arr.dtype)
        else:
            back = np.array([np.nan if v is None else float(v) for v in values], dtype=np.float64)
        if not np.array_equal(back, arr, equal_nan=arr.dtype.kind == 'f'):
            raise ValueError(f"{name}: values changed on export")


def export_h5(h5Path, outPath=None, fmt=None):
    """Export h5Path to outPath (default <name>_export.<fmt>). fmt defaults to
    the output's extension ('.json' -> json, anything else -> txt). Returns
    {'output', 'format', 'rows', 'channels', 'bytes'}; raises on failure,
    leaving no partial output behind."""
    if fmt is None:
        fmt = format_from_path(outPath) if outPath else 'txt'
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; use one of {', '.join(FORMATS)}")
    outPath = outPath or default_output_path(h5Path, fmt)
    if os.path.abspath(outPath) == os.path.abspath(h5Path):
        raise ValueError("the output file can't be the .h5 file itself")
    if setpoint_from_name(os.path.basename(outPath)) is not None:
        raise ValueError(f"'{os.path.basename(outPath)}' is named like a run's step file, so the analysis "
                         f"tabs would read it as data; choose another name, e.g. "
                         f"{os.path.basename(default_output_path(h5Path, fmt))}")

    attrs, channels = read_h5_file(h5Path)
    source = os.path.basename(h5Path)
    tmpPath = outPath + '.tmp'
    try:
        (write_json if fmt == 'json' else write_txt)(tmpPath, attrs, channels, source)
        verify(tmpPath, fmt, channels)
        os.replace(tmpPath, outPath)
    finally:
        if os.path.exists(tmpPath):
            os.remove(tmpPath)
    return {'output': outPath, 'format': fmt, 'channels': len(channels),
            'rows': max((a.size for a in channels.values()), default=0), 'bytes': os.path.getsize(outPath)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export HDF5 DLTS step files to readable .txt or .json.")
    parser.add_argument('files', nargs='+', help=".h5 step file(s)")
    parser.add_argument('--format', choices=FORMATS, help="output format (default: from -o, else txt)")
    parser.add_argument('-o', '--output', help="output file (only with a single input file)")
    args = parser.parse_args(argv)
    if args.output and len(args.files) > 1:
        parser.error("-o/--output takes a single input file")

    failed = 0
    for path in args.files:
        try:
            result = export_h5(path, args.output, args.format)
            print(f"{path} -> {result['output']} ({result['rows']} rows x {result['channels']} channels, "
                  f"{result['bytes'] / 1024 ** 2:.1f} MB)")
        except Exception as exc:
            failed += 1
            print(f"{path}: failed: {exc}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

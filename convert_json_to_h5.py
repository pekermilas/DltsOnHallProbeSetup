"""Convert DLTS run folders from per-temperature JSON .txt files to HDF5.

Each step file (p25p0.txt, n10p0.txt, ...) becomes a .h5 file next to it, in the
same format a run with Data File Format = HDF5 writes (ziDevice.writeDataH5()),
so every part of the GUI reads converted runs exactly like new ones. The
setpoint comes from the file name, the run parameters from runParams.txt, and
acquired_at from the JSON file's modification time. The measured stage
temperature was never recorded in JSON, so it is stored as NaN.

Every .h5 file is read back and compared value by value with its JSON file
before the JSON file is touched. By default a verified JSON file is then moved
into a json_originals/ subfolder: leaving it beside the new file would put two
copies of the same temperature in the folder. runParams.txt stays where it is,
since the analysis code reads it from the run folder.

Usage:
    python convert_json_to_h5.py RUN_FOLDER [RUN_FOLDER ...]
    python convert_json_to_h5.py --recursive DATA_ROOT_FOLDER

Options:
    --recursive    also convert every run folder below the given folders
    --delete-json  delete verified JSON files instead of moving them aside
                   (this is what actually frees the disk space)
    --keep-json    leave verified JSON files where they are
    --overwrite    reconvert steps that already have a .h5 file
    --dry-run      only list what would be converted
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

import h5py
import numpy as np

import zurichInstruments_Control as ziC

# A per-temperature step file as init_experiment() names it (p25p0.txt,
# n10p0.txt), also allowing the older 'C' and _<n> suffixes liveDataTab accepts.
STEP_FILE_PATTERN = re.compile(r'^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt|json)$')
ORIGINALS_DIR = 'json_originals'
PARAMS_FILE = 'runParams.txt'


def setpoint_from_name(fileName):
    """The setpoint in C encoded in a step file name, or None if it isn't one."""
    match = STEP_FILE_PATTERN.match(fileName)
    if match is None:
        return None
    sign, integerPart, fracPart, _ = match.groups()
    value = float(f"{integerPart}.{fracPart or 0}")
    return -value if sign.lower() == 'n' else value


def step_files(folder):
    """The JSON step files directly inside folder, sorted by name."""
    return sorted(name for name in os.listdir(folder)
                  if STEP_FILE_PATTERN.match(name) and os.path.isfile(os.path.join(folder, name)))


def find_run_folders(roots, recursive):
    folders = []
    for root in roots:
        if not recursive:
            folders.append(root)
            continue
        for dirPath, dirNames, _ in os.walk(root):
            dirNames[:] = sorted(d for d in dirNames if d != ORIGINALS_DIR)
            if step_files(dirPath):
                folders.append(dirPath)
    return folders


def verify(jsonData, h5Path):
    """Raise ValueError unless h5Path holds exactly the values in jsonData."""
    with h5py.File(h5Path, 'r') as f:
        if set(f.keys()) != set(jsonData):
            raise ValueError(f"channels differ: {sorted(f.keys())} vs {sorted(jsonData)}")
        for key, values in jsonData.items():
            expected = np.asarray(values)
            stored = f[key][()]
            if stored.dtype == np.uint64:
                if expected.size and expected.min() < 0:
                    raise ValueError(f"{key}: negative tick stamps can't be stored as uint64")
                stored = stored.astype(np.int64)
            if stored.shape != expected.shape or not np.array_equal(
                    stored, expected, equal_nan=stored.dtype.kind == 'f'):
                raise ValueError(f"{key}: values changed on conversion")


def load_run_params(folder):
    path = os.path.join(folder, PARAMS_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def convert_file(dev, folder, name, runParams, jsonAction, overwrite, dryRun):
    """Convert one step file. Returns (status, message, bytesBefore, bytesAfter),
    status being 'converted', 'skipped' or 'failed'."""
    jsonPath = os.path.join(folder, name)
    h5Path = os.path.join(folder, os.path.splitext(name)[0] + '.h5')
    jsonSize = os.path.getsize(jsonPath)

    if os.path.exists(h5Path) and not overwrite:
        return 'skipped', f"{os.path.basename(h5Path)} already exists", 0, 0
    if jsonAction == 'move' and os.path.exists(os.path.join(folder, ORIGINALS_DIR, name)):
        return 'skipped', f"{ORIGINALS_DIR}/{name} already exists", 0, 0
    if dryRun:
        return 'converted', 'would convert', jsonSize, 0

    try:
        with open(jsonPath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or not data:
            raise ValueError("not a DLTS step file (expected an object of channels)")

        dev.writeDataH5(data, h5Path, setpoint_C=setpoint_from_name(name), runParams=runParams,
                        acquired_at=datetime.fromtimestamp(os.path.getmtime(jsonPath)),
                        extraAttrs={'converted_from': name})
        verify(data, h5Path)
    except Exception as exc:
        # Never leave a .h5 that doesn't match its source: the GUI would read it.
        for path in (h5Path, h5Path + '.tmp'):
            if os.path.exists(path):
                os.remove(path)
        return 'failed', str(exc), 0, 0

    if jsonAction == 'move':
        os.makedirs(os.path.join(folder, ORIGINALS_DIR), exist_ok=True)
        shutil.move(jsonPath, os.path.join(folder, ORIGINALS_DIR, name))
    elif jsonAction == 'delete':
        os.remove(jsonPath)
    return 'converted', '', jsonSize, os.path.getsize(h5Path)


def convert_folder(folder, jsonAction='move', overwrite=False, dryRun=False, log=print):
    """Convert every step file in one run folder. Returns counts and sizes."""
    dev = ziC.ziDevice()
    runParams = load_run_params(folder)
    names = step_files(folder)
    stats = {'converted': 0, 'skipped': 0, 'failed': 0, 'bytesBefore': 0, 'bytesAfter': 0}
    log(f"{folder}: {len(names)} step file(s)"
        + ("" if runParams is not None else f" (no {PARAMS_FILE}: run_params not stored)"))
    for name in names:
        status, message, before, after = convert_file(dev, folder, name, runParams,
                                                      jsonAction, overwrite, dryRun)
        stats[status] += 1
        stats['bytesBefore'] += before
        stats['bytesAfter'] += after
        if dryRun:
            log(f"  {name}: {message}")
        elif status != 'converted':
            log(f"  {name}: {status}: {message}")
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert DLTS run folders from JSON .txt step files to HDF5 (.h5).")
    parser.add_argument('folders', nargs='+', help="run folder(s), or data root folder(s) with --recursive")
    parser.add_argument('--recursive', action='store_true',
                        help="also convert every run folder below the given folders")
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--delete-json', dest='jsonAction', action='store_const', const='delete',
                        help="delete verified JSON files instead of moving them to json_originals/")
    action.add_argument('--keep-json', dest='jsonAction', action='store_const', const='keep',
                        help="leave verified JSON files in place")
    parser.add_argument('--overwrite', action='store_true',
                        help="reconvert steps that already have a .h5 file")
    parser.add_argument('--dry-run', action='store_true', help="only list what would be converted")
    parser.set_defaults(jsonAction='move')
    args = parser.parse_args(argv)

    missing = [f for f in args.folders if not os.path.isdir(f)]
    if missing:
        parser.error(f"not a folder: {', '.join(missing)}")

    folders = find_run_folders(args.folders, args.recursive)
    if not folders:
        print("No run folders with JSON step files found.")
        return 0

    total = {'converted': 0, 'skipped': 0, 'failed': 0, 'bytesBefore': 0, 'bytesAfter': 0}
    for folder in folders:
        for key, value in convert_folder(folder, args.jsonAction, args.overwrite, args.dry_run).items():
            total[key] += value

    mb = 1024 ** 2
    if args.dry_run:
        print(f"Dry run: {total['converted']} file(s) ({total['bytesBefore'] / mb:.1f} MB) would be converted, "
              f"{total['skipped']} skipped.")
    else:
        print(f"Converted {total['converted']} file(s): {total['bytesBefore'] / mb:.1f} MB of JSON -> "
              f"{total['bytesAfter'] / mb:.1f} MB of HDF5. Skipped {total['skipped']}, failed {total['failed']}.")
        if total['converted'] and args.jsonAction == 'move':
            print(f"Originals were moved to {ORIGINALS_DIR}/ in each run folder; "
                  f"delete those folders to free the space.")
    return 1 if total['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())

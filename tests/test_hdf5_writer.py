"""ziDevice.writeDataH5() and impedanceAnalysis_Tools.read_h5_record()."""
import json
import os

import h5py
import numpy as np
import pytest

import zurichInstruments_Control as ziC
import impedanceAnalysis_Tools as iaT
from conftest import make_step


def test_round_trip_is_lossless_with_native_types(zi_device, tmp_path):
    data = make_step(25.0)
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(data, str(path), setpoint_C=25.0)

    with h5py.File(path, 'r') as f:
        assert set(f.keys()) == set(data)
        for key, values in data.items():
            ds = f[key]
            assert ds.dtype == (np.uint64 if key.startswith('tickStamp') else np.float64), key
            assert ds.compression == 'gzip' and ds.shuffle, key
            assert np.array_equal(ds[()], values), key


def test_tick_stamps_survive_exactly_beyond_float_precision(zi_device, tmp_path):
    # float64 can't represent 2**62 + 1, and float32 (the old writer's type)
    # loses thousands of ticks at realistic 60 MHz counts.
    data = make_step(25.0, n=16)
    data['tickStampImps'] = np.uint64(2**62 + 1) + np.arange(16, dtype=np.uint64)
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(data, str(path))

    with h5py.File(path, 'r') as f:
        assert np.array_equal(f['tickStampImps'][()], data['tickStampImps'])


def test_attributes(zi_device, tmp_path):
    params = {'Number of Reps': 500, 'Data File Format': 'HDF5', 'Data Root Folder': 'C:\\data'}
    path = tmp_path / 'n10p0.h5'
    zi_device.writeDataH5(make_step(-10.0, n=64), str(path), setpoint_C=-10.0,
                          stage_temperature_C=-9.97, runParams=params)

    with h5py.File(path, 'r') as f:
        assert f.attrs['format_version'] == ziC.ziDevice.H5_FORMAT_VERSION
        assert f.attrs['setpoint_C'] == -10.0
        assert f.attrs['stage_temperature_C'] == -9.97
        assert json.loads(f.attrs['run_params']) == params
        assert isinstance(f.attrs['acquired_at'], str) and 'T' in f.attrs['acquired_at']


def test_missing_temperatures_are_stored_as_nan(zi_device, tmp_path):
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(make_step(25.0, n=64), str(path))

    with h5py.File(path, 'r') as f:
        assert np.isnan(f.attrs['setpoint_C']) and np.isnan(f.attrs['stage_temperature_C'])
        assert 'run_params' not in f.attrs


def test_empty_channel_can_be_written(zi_device, tmp_path):
    data = make_step(25.0, n=64)
    data['AbsZ'] = np.array([])
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(data, str(path))

    assert iaT.read_h5_record(str(path))['AbsZ'].size == 0


def test_creates_missing_parent_folder(zi_device, tmp_path):
    path = tmp_path / 'run' / '093000' / 'p25p0.h5'
    zi_device.writeDataH5(make_step(25.0, n=64), str(path))
    assert path.exists()


def test_reader_matches_json_types(zi_device, tmp_path):
    """read_h5_record() must hand back what np.asarray() of a JSON record gives,
    so the analysis code can't tell the formats apart."""
    data = make_step(25.0, n=256)
    h5_path, txt_path = tmp_path / 'p25p0.h5', tmp_path / 'p25p0.txt'
    zi_device.writeDataH5(data, str(h5_path))
    zi_device.writeDataJson(data, str(txt_path))

    from_h5 = iaT.read_h5_record(str(h5_path))
    with open(txt_path) as f:
        from_json = {k: np.asarray(v) for k, v in json.load(f).items()}

    assert set(from_h5) == set(from_json)
    for key in from_json:
        assert from_h5[key].dtype == from_json[key].dtype, key
        assert np.array_equal(from_h5[key], from_json[key]), key


def test_reader_can_read_only_some_channels(zi_device, tmp_path):
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(make_step(25.0, n=64), str(path))

    record = iaT.read_h5_record(str(path), keys=('AuxInput1', 'ImpedanceIm'))
    assert set(record) == {'AuxInput1', 'ImpedanceIm'}


# --- Redo/Retake overwrite and failures part-way through a write -------------

def test_overwrite_replaces_contents(zi_device, tmp_path):
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(make_step(25.0, n=64, seed=1), str(path), setpoint_C=25.0)
    second = make_step(25.0, n=128, seed=2)
    zi_device.writeDataH5(second, str(path), setpoint_C=25.0)

    record = iaT.read_h5_record(str(path))
    assert np.array_equal(record['ImpedanceIm'], second['ImpedanceIm'])
    assert os.listdir(tmp_path) == ['p25p0.h5']


def test_final_file_only_appears_once_complete(zi_device, tmp_path, monkeypatch):
    """The live watcher starts reading as soon as the final name exists, so it
    must not exist until the file is complete and closed."""
    path = tmp_path / 'p25p0.h5'
    realReplace = os.replace
    seen = {}

    def checking_replace(src, dst):
        seen['finalExisted'] = os.path.exists(dst)
        with h5py.File(src, 'r') as f:  # complete and closed: another reader can open it
            seen['keys'] = set(f.keys())
        realReplace(src, dst)

    monkeypatch.setattr(ziC.os, 'replace', checking_replace)
    zi_device.writeDataH5(make_step(25.0, n=64), str(path))

    assert seen['finalExisted'] is False
    assert len(seen['keys']) == 8


def _bad_step():
    """A step that fails part-way through writing: its last channel can't be
    converted to float64, after several channels are already in the file."""
    data = make_step(25.0, n=64)
    data['AuxInput1'] = ['not', 'a', 'number']
    return data


def test_failed_first_write_leaves_no_data_file(zi_device, tmp_path):
    path = tmp_path / 'p25p0.h5'
    with pytest.raises(ValueError):
        zi_device.writeDataH5(_bad_step(), str(path))
    assert not path.exists()


def test_failed_redo_keeps_previous_file(zi_device, tmp_path):
    path = tmp_path / 'p25p0.h5'
    first = make_step(25.0, n=64, seed=1)
    zi_device.writeDataH5(first, str(path))

    with pytest.raises(ValueError):
        zi_device.writeDataH5(_bad_step(), str(path))

    record = iaT.read_h5_record(str(path))
    assert np.array_equal(record['ImpedanceIm'], first['ImpedanceIm'])


def test_next_write_after_a_failure_cleans_up_the_temp_file(zi_device, tmp_path):
    path = tmp_path / 'p25p0.h5'
    with pytest.raises(ValueError):
        zi_device.writeDataH5(_bad_step(), str(path))
    zi_device.writeDataH5(make_step(25.0, n=64), str(path))
    assert os.listdir(tmp_path) == ['p25p0.h5']


def test_rename_is_retried_while_target_is_locked(zi_device, tmp_path, monkeypatch):
    """On Windows, os.replace() fails while a reader has the old file open."""
    realReplace = os.replace
    calls = []

    def locked_twice(src, dst):
        calls.append(dst)
        if len(calls) <= 2:
            raise PermissionError('file in use')
        realReplace(src, dst)

    monkeypatch.setattr(ziC.os, 'replace', locked_twice)
    monkeypatch.setattr(ziC.time, 'sleep', lambda s: None)
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(make_step(25.0, n=64), str(path))

    assert len(calls) == 3 and path.exists()


def test_rename_gives_up_if_target_stays_locked(zi_device, tmp_path, monkeypatch):
    def always_locked(src, dst):
        raise PermissionError('file in use')

    monkeypatch.setattr(ziC.os, 'replace', always_locked)
    monkeypatch.setattr(ziC.time, 'sleep', lambda s: None)
    with pytest.raises(PermissionError):
        zi_device.writeDataH5(make_step(25.0, n=64), str(tmp_path / 'p25p0.h5'))

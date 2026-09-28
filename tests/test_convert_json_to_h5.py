"""convert_json_to_h5.py: converting existing JSON run folders to HDF5."""
import json
import os
from datetime import datetime

import h5py
import numpy as np
import pytest

import convert_json_to_h5 as conv
import impedanceAnalysis_Tools as iaT
import liveDataTab as ldT
import zurichInstruments_Control as ziC
from conftest import step_file_name, write_run

TEMPS = [-10.0, 25.0, 50.5]
PARAMS = {'Number of Reps': 1}  # what write_run() puts in runParams.txt


@pytest.fixture
def json_run(zi_device, tmp_path):
    """A JSON run folder as the GUI wrote them before HDF5 output existed."""
    folder = tmp_path / 'run'
    folder.mkdir()
    write_run(zi_device, str(folder), TEMPS, '.txt', n=512)
    (folder / 'notes.txt').write_text('sample B, second cooldown')
    return folder


def listing(folder):
    return sorted(os.listdir(folder))


@pytest.mark.parametrize('name,setpoint', [
    ('p25p0.txt', 25.0), ('n10p0.txt', -10.0), ('p50p5.txt', 50.5), ('p120.txt', 120.0),
    ('p25C.txt', 25.0), ('p25p0_1.txt', 25.0), ('p25p0.json', 25.0),
    ('runParams.txt', None), ('notes.txt', None), ('p25p0.h5', None), ('p25p0.csv', None)])
def test_setpoint_from_name(name, setpoint):
    assert conv.setpoint_from_name(name) == setpoint


def test_converts_folder_and_moves_originals_aside(json_run):
    originals = {}
    for T in TEMPS:
        with open(json_run / step_file_name(T, '.txt')) as f:
            originals[T] = json.load(f)

    assert conv.main([str(json_run)]) == 0

    assert listing(json_run) == sorted(
        [step_file_name(T, '.h5') for T in TEMPS] + ['json_originals', 'notes.txt', 'runParams.txt'])
    assert listing(json_run / 'json_originals') == sorted(step_file_name(T, '.txt') for T in TEMPS)
    for T in TEMPS:
        record = iaT.read_h5_record(str(json_run / step_file_name(T, '.h5')))
        for key, values in originals[T].items():
            assert np.array_equal(record[key], np.asarray(values)), key


def test_attributes_of_converted_files(json_run):
    mtime = os.path.getmtime(json_run / 'p50p5.txt')
    assert conv.main([str(json_run)]) == 0

    with h5py.File(json_run / 'p50p5.h5', 'r') as f:
        assert f.attrs['setpoint_C'] == 50.5
        assert np.isnan(f.attrs['stage_temperature_C'])
        assert json.loads(f.attrs['run_params']) == PARAMS
        assert f.attrs['converted_from'] == 'p50p5.txt'
        assert f.attrs['acquired_at'] == datetime.fromtimestamp(mtime).isoformat(timespec='seconds')
        assert f.attrs['format_version'] == ziC.ziDevice.H5_FORMAT_VERSION
        assert f['tickStampImps'].dtype == np.uint64


def test_converted_run_reads_like_the_original(json_run):
    before = iaT.impdData(fName=[str(json_run / step_file_name(T, '.txt')) for T in TEMPS])
    assert before.read_data() == 0
    assert conv.main([str(json_run)]) == 0
    after = iaT.impdData(fName=[str(json_run / step_file_name(T, '.h5')) for T in TEMPS])
    assert after.read_data() == 0

    assert after.dataTemps == before.dataTemps and after.dataParams == before.dataParams
    for T in before.dataTemps:
        for key, values in before.dataValues[T].items():
            assert np.array_equal(after.dataValues[T][key], np.asarray(values)), key

    # The Qualitative folder scan sees each temperature once, from the .h5.
    registry = ldT._compute_legacy_dataset(str(json_run), [])
    assert sorted(registry) == TEMPS
    assert all(path.endswith('.h5') for path in registry.values())


def test_converts_triggered_run_with_float_tick_stamps(zi_device, tmp_path):
    """Real runs store the grid's time axis (seconds) under the tickStamp names;
    those must convert and verify, not be truncated to integers."""
    folder = tmp_path / 'run'
    t = (np.arange(512) * 1.8666666666666665e-05).tolist()
    data = {'tickStampImps': t, 'tickStampDemods': t, 'timeStampImps': t,
            'timeStampDemods': t, 'ImpedanceIm': np.linspace(1e-10, 2e-10, 512)}
    zi_device.writeDataJson(data, str(folder / 'p25p0.txt'))

    assert conv.main([str(folder)]) == 0
    record = iaT.read_h5_record(str(folder / 'p25p0.h5'))
    assert np.array_equal(record['tickStampImps'], np.asarray(t))


def test_delete_json(json_run):
    assert conv.main([str(json_run), '--delete-json']) == 0
    assert listing(json_run) == sorted(
        [step_file_name(T, '.h5') for T in TEMPS] + ['notes.txt', 'runParams.txt'])


def test_keep_json(json_run):
    assert conv.main([str(json_run), '--keep-json']) == 0
    for T in TEMPS:
        assert (json_run / step_file_name(T, '.txt')).exists()
        assert (json_run / step_file_name(T, '.h5')).exists()


def test_dry_run_changes_nothing(json_run, capsys):
    before = listing(json_run)
    assert conv.main([str(json_run), '--dry-run']) == 0
    assert listing(json_run) == before
    assert '3 file(s)' in capsys.readouterr().out


def test_existing_h5_is_skipped_unless_overwrite(json_run, zi_device):
    existing = json_run / 'p25p0.h5'
    zi_device.writeDataH5({'AbsZ': np.array([1.0])}, str(existing))

    assert conv.main([str(json_run), '--keep-json']) == 0
    assert set(iaT.read_h5_record(str(existing))) == {'AbsZ'}

    assert conv.main([str(json_run), '--keep-json', '--overwrite']) == 0
    assert len(iaT.read_h5_record(str(existing))) == 8


def test_running_twice_converts_nothing_new(json_run, capsys):
    assert conv.main([str(json_run)]) == 0
    capsys.readouterr()
    assert conv.main([str(json_run)]) == 0
    assert 'Converted 0 file(s)' in capsys.readouterr().out


def test_recursive_finds_run_folders_and_skips_originals(zi_device, tmp_path, capsys):
    root = tmp_path / 'data'
    runs = [root / '092526' / '093000', root / '092526' / '141500', root / '092626' / '101010']
    for run in runs:
        run.mkdir(parents=True)
        write_run(zi_device, str(run), TEMPS[:2], '.txt', n=64)

    assert conv.main(['--recursive', str(root)]) == 0
    for run in runs:
        assert (run / step_file_name(25.0, '.h5')).exists()
        assert (run / 'json_originals' / step_file_name(25.0, '.txt')).exists()

    # A second pass must not descend into json_originals/ and convert those.
    capsys.readouterr()
    assert conv.main(['--recursive', str(root)]) == 0
    assert 'No run folders' in capsys.readouterr().out


def test_unreadable_file_fails_without_touching_it(json_run):
    bad = json_run / 'p75p0.txt'
    bad.write_text('{"AbsZ": [1.0, 2.0')  # truncated, as a crash mid-write left it

    assert conv.main([str(json_run)]) == 1

    assert bad.read_text() == '{"AbsZ": [1.0, 2.0'
    assert not (json_run / 'p75p0.h5').exists()
    assert not (json_run / 'p75p0.h5.tmp').exists()
    # The good steps in the same folder are still converted.
    assert (json_run / 'p25p0.h5').exists()


def test_failed_verification_removes_the_h5_and_keeps_the_json(json_run, monkeypatch):
    realWrite = ziC.ziDevice.writeDataH5

    def corrupting_write(self, data, fName, **kwargs):
        data = dict(data, ImpedanceIm=np.asarray(data['ImpedanceIm']) * 2)
        return realWrite(self, data, fName, **kwargs)

    monkeypatch.setattr(ziC.ziDevice, 'writeDataH5', corrupting_write)
    assert conv.main([str(json_run)]) == 1

    assert not any(name.endswith('.h5') for name in os.listdir(json_run))
    for T in TEMPS:
        assert (json_run / step_file_name(T, '.txt')).exists()


def test_missing_run_params_is_not_an_error(json_run):
    os.remove(json_run / 'runParams.txt')
    assert conv.main([str(json_run)]) == 0
    with h5py.File(json_run / 'p25p0.h5', 'r') as f:
        assert 'run_params' not in f.attrs


def test_not_a_folder_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit):
        conv.main([str(tmp_path / 'missing')])

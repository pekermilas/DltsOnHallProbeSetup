"""convert_h5_to_text.py: readable .txt / .json copies of HDF5 step files."""
import json
import os

import numpy as np
import pytest

import convert_h5_to_text as h5txt
import liveDataTab as ldT
from conftest import make_step


@pytest.fixture
def step_h5(zi_device, tmp_path):
    data = make_step(25.0, n=512)
    data['timeStampImps'][3] = np.nan       # JSON has no NaN; must survive as null
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(data, str(path), setpoint_C=25.0, stage_temperature_C=25.06,
                          runParams={'Number of Reps': 100, 'Data File Format': 'HDF5'})
    return path, data


def test_txt_table_is_exact_and_readable(step_h5):
    path, data = step_h5
    result = h5txt.export_h5(str(path))

    assert result['output'].endswith('p25p0_export.txt') and result['format'] == 'txt'
    text = open(result['output'], encoding='utf-8').read().splitlines()
    assert '# setpoint_C: 25.0' in text and '# stage_temperature_C: 25.06' in text
    assert any(line.startswith('# run_params: {"Number of Reps": 100') for line in text)
    header = [l for l in text if not l.startswith('#')][0].split('\t')
    assert header == list(h5txt.CHANNEL_ORDER)   # time axes first, not alphabetical
    table = h5txt.read_txt(result['output'])
    assert [int(v) for v in table['tickStampImps']] == data['tickStampImps'].tolist()
    assert np.array_equal(np.array(table['ImpedanceIm'], dtype=float), data['ImpedanceIm'])
    assert table['timeStampImps'][3] == 'nan'


def test_json_is_exact(step_h5, tmp_path):
    path, data = step_h5
    out = tmp_path / 'inspect.json'
    result = h5txt.export_h5(str(path), str(out))

    assert result['format'] == 'json'
    doc = json.load(open(out, encoding='utf-8'))
    assert doc['source'] == 'p25p0.h5'
    assert doc['attributes']['run_params'] == {'Number of Reps': 100, 'Data File Format': 'HDF5'}
    assert doc['channels']['tickStampImps'] == data['tickStampImps'].tolist()
    assert doc['channels']['timeStampImps'][3] is None
    assert doc['channels']['AuxInput1'] == data['AuxInput1'].tolist()


def test_missing_stage_temperature_is_null_in_json(zi_device, tmp_path):
    path = tmp_path / 'p30p0.h5'
    zi_device.writeDataH5(make_step(30.0, n=16), str(path))
    h5txt.export_h5(str(path), fmt='json')
    doc = json.load(open(tmp_path / 'p30p0_export.json', encoding='utf-8'))
    assert doc['attributes']['stage_temperature_C'] is None


def test_float_tick_stamps_from_triggered_runs(zi_device, tmp_path):
    data = make_step(25.0, n=64)
    data['tickStampImps'] = np.arange(64) * 1.8666666666666665e-05
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(data, str(path))
    result = h5txt.export_h5(str(path))
    assert np.array_equal(np.array(h5txt.read_txt(result['output'])['tickStampImps'], dtype=float),
                          data['tickStampImps'])


def test_unequal_channel_lengths(zi_device, tmp_path):
    data = make_step(25.0, n=32)
    data['AbsZ'] = np.array([])
    path = tmp_path / 'p25p0.h5'
    zi_device.writeDataH5(data, str(path))
    result = h5txt.export_h5(str(path))
    assert h5txt.read_txt(result['output'])['AbsZ'] == [] and result['rows'] == 32


@pytest.mark.parametrize('name', ['p25p0.txt', 'p25p0.json', 'n10p0.txt'])
def test_refuses_names_the_analysis_tabs_would_read_as_data(step_h5, tmp_path, name):
    path, _ = step_h5
    with pytest.raises(ValueError, match='named like a run'):
        h5txt.export_h5(str(path), str(tmp_path / name))
    assert not (tmp_path / name).exists()


def test_export_next_to_the_run_is_ignored_by_the_folder_scan(step_h5, tmp_path):
    path, _ = step_h5
    h5txt.export_h5(str(path))
    h5txt.export_h5(str(path), fmt='json')
    registry = ldT._compute_legacy_dataset(str(tmp_path), [])
    assert registry == {25.0: str(path)}


def test_failed_verification_leaves_nothing(step_h5, monkeypatch):
    path, _ = step_h5
    monkeypatch.setattr(h5txt, '_cell', lambda v: '0')
    with pytest.raises(ValueError, match='values changed'):
        h5txt.export_h5(str(path))
    assert sorted(os.listdir(path.parent)) == ['p25p0.h5']


def test_cli(step_h5, tmp_path, capsys):
    path, _ = step_h5
    assert h5txt.main([str(path), '--format', 'json']) == 0
    assert (tmp_path / 'p25p0_export.json').exists()
    assert h5txt.main([str(tmp_path / 'missing.h5')]) == 1
    with pytest.raises(SystemExit):
        h5txt.main([str(path), str(path), '-o', 'x.txt'])

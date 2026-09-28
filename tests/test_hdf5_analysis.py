"""Reading HDF5 runs in the analysis code: impdData (Live Tools offline load and
live ingest), the Qualitative folder scan + extractor, and Detailed Analysis.
Each is checked to give exactly the same results as the same run in JSON .txt."""
import os
import shutil
from types import SimpleNamespace

import numpy as np
import pytest

import dltsConfig as dltsc
import impedanceAnalysis_Tools as iaT
import liveDataTab as ldT
import detailedAnalysisTab as daT
from conftest import SAMPLE_DT_S, step_file_name, write_run

TEMPS = [-10.0, 25.0, 50.5]


@pytest.fixture(scope='module')
def run_folders(tmp_path_factory):
    """One synthetic run stored both ways: {'.txt': [paths], '.h5': [paths]}.
    A 50 ms reverse bias gives the clustering several full cycles in 2**14 points."""
    import zurichInstruments_Control as ziC
    dev = ziC.ziDevice.__new__(ziC.ziDevice)
    root = tmp_path_factory.mktemp('run')
    files = {}
    for ext in ('.txt', '.h5'):
        folder = root / ext.strip('.')
        folder.mkdir()
        files[ext] = write_run(dev, str(folder), TEMPS, ext, rb_ms=50.0)
    return files


def assert_same(a, b, path='root'):
    """Deep equality for the nested dict/list/array structures impdData builds."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), path
        for key in a:
            assert_same(a[key], b[key], f'{path}/{key}')
    elif isinstance(a, (list, tuple)) and a and not np.isscalar(a[0]):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            assert_same(x, y, f'{path}[{i}]')
    elif isinstance(a, str) or a is None:
        assert a == b, path
    else:
        A, B = np.asarray(a), np.asarray(b)
        assert A.shape == B.shape, path
        assert np.array_equal(A, B, equal_nan=A.dtype.kind == 'f'), path


def run_offline_pipeline(files):
    """What Live Tools -> Load Existing Run does (liveDataTab._load_offline_run)."""
    impd = iaT.impdData(fName=list(files))
    assert impd.read_data() == 0
    impd.cleanup_data()
    impd.selected_emissions(emissionIndex=0)
    impd.filter_emissions(method='pca', emissionIndex=0, recalculate=True, interactivePlot=False)
    return impd


def test_offline_pipeline_gives_identical_results(run_folders):
    fromTxt = run_offline_pipeline(run_folders['.txt'])
    fromH5 = run_offline_pipeline(run_folders['.h5'])

    assert fromTxt.dataTemps == fromH5.dataTemps
    assert fromH5.dataParams == fromTxt.dataParams
    assert_same(fromTxt.dataValues, fromH5.dataValues, 'dataValues')
    assert_same(fromTxt.dataEmissions, fromH5.dataEmissions, 'dataEmissions')


def test_live_ingest_gives_identical_results(run_folders):
    """Live ingest reads the first file and then append_data()s each new one."""
    results = []
    for ext in ('.txt', '.h5'):
        paths = run_folders[ext]
        impd = iaT.impdData(fName=[paths[0]])
        assert impd.read_data() == 0
        for path in paths[1:]:
            assert impd.append_data(fName=[path]) == 0
        impd.cleanup_data()
        impd.selected_emissions(emissionIndex=0)
        results.append(impd)

    assert results[0].dataTemps == results[1].dataTemps
    assert_same(results[0].dataValues, results[1].dataValues, 'dataValues')
    assert_same(results[0].dataEmissions, results[1].dataEmissions, 'dataEmissions')


def test_read_data_accepts_mixed_txt_and_h5(run_folders):
    mixed = [run_folders['.txt'][0], run_folders['.h5'][1], run_folders['.txt'][2]]
    impd = iaT.impdData(fName=mixed)
    assert impd.read_data() == 0
    assert impd.dataTemps == [int(T) + 273 for T in TEMPS]

    reference = iaT.impdData(fName=run_folders['.txt'])
    assert reference.read_data() == 0
    impd.cleanup_data()
    reference.cleanup_data()
    assert_same(reference.dataValues, impd.dataValues)


@pytest.mark.parametrize('firstExt,appendExt', [('.h5', '.txt'), ('.txt', '.h5')])
def test_append_data_across_formats(run_folders, firstExt, appendExt):
    impd = iaT.impdData(fName=[run_folders[firstExt][0]])
    assert impd.read_data() == 0
    assert impd.append_data(fName=[run_folders[appendExt][1]]) == 0
    assert impd.dataTemps == [int(T) + 273 for T in TEMPS[:2]]


def test_appending_same_temperature_across_formats_concatenates(run_folders):
    impd = iaT.impdData(fName=[run_folders['.txt'][0]])
    assert impd.read_data() == 0
    n = len(impd.dataValues[impd.dataTemps[0]]['ImpedanceIm'])
    assert impd.append_data(fName=[run_folders['.h5'][0]]) == 0
    assert len(impd.dataValues[impd.dataTemps[0]]['ImpedanceIm']) == 2 * n


# --- Qualitative Analysis (folder scan + Extract & Average) and Detailed ------

@pytest.fixture(scope='module')
def long_run_folders(tmp_path_factory):
    """Long enough for several full 500 ms reverse-bias cycles, which the
    Extract & Average step needs to find any transients at all."""
    import zurichInstruments_Control as ziC
    dev = ziC.ziDevice.__new__(ziC.ziDevice)
    root = tmp_path_factory.mktemp('longrun')
    folders = {}
    for ext in ('.txt', '.h5'):
        folder = root / ext.strip('.')
        folder.mkdir()
        write_run(dev, str(folder), TEMPS, ext, n=2**17)
        folders[ext] = str(folder)
    return folders


def test_folder_scan_finds_h5_steps_and_ignores_partial_files(long_run_folders, tmp_path):
    folder = tmp_path / 'scan'
    shutil.copytree(long_run_folders['.h5'], folder)
    (folder / 'p99p0.h5.tmp').write_bytes(b'')  # a step still being written

    errors = []
    registry = ldT._compute_legacy_dataset(str(folder), errors)

    assert errors == []
    assert sorted(registry) == TEMPS
    assert all(path.endswith('.h5') for path in registry.values())
    assert 'legacy per-temperature' in ldT._describe_folder_contents(str(folder))


def extract_and_average(folder):
    """Qualitative Analysis' Extract & Average, minus the process pool."""
    errors = []
    registry = ldT._compute_legacy_dataset(folder, errors)
    transients, extractErrors = ldT._compute_legacy_transients(
        sorted(registry), 500.0, 450.0, registry, SAMPLE_DT_S)
    return transients, errors + extractErrors


def test_extract_and_average_gives_identical_transients(long_run_folders):
    fromTxt, txtErrors = extract_and_average(long_run_folders['.txt'])
    fromH5, h5Errors = extract_and_average(long_run_folders['.h5'])

    assert txtErrors == [] and h5Errors == []
    assert sorted(fromH5) == TEMPS
    assert_same(fromTxt, fromH5)


def test_detailed_analysis_load_gives_identical_data(long_run_folders):
    args = (None, None, None, 500.0, 0.2, 0.9)  # grid/chunk (ZI only), rb_ms, C_inf range
    txtData, txtTemps, txtErrors = daT._load_detailed_data(long_run_folders['.txt'], *args)
    h5Data, h5Temps, h5Errors = daT._load_detailed_data(long_run_folders['.h5'], *args)

    assert txtErrors == [] and h5Errors == []
    assert txtTemps == h5Temps == TEMPS
    assert_same(txtData, h5Data)


def test_detailed_analysis_loads_mixed_folder(long_run_folders, tmp_path):
    shutil.copy(os.path.join(long_run_folders['.txt'], step_file_name(-10.0, '.txt')), tmp_path)
    shutil.copy(os.path.join(long_run_folders['.h5'], step_file_name(50.5, '.h5')), tmp_path)

    _, temps, errors = daT._load_detailed_data(str(tmp_path), None, None, None, 500.0, 0.2, 0.9)
    assert errors == [] and temps == [-10.0, 50.5]


# --- Live watcher ------------------------------------------------------------

def test_live_watcher_ingests_h5_files_once_renamed_into_place(tmp_path, monkeypatch):
    finalName = str(tmp_path / 'p25p0.h5')
    (tmp_path / 'p25p0.h5.tmp').write_bytes(b'')  # still being written
    ingested = []
    token = object()
    for name, value in {'livePlot_liveRunToken': token, 'run_outputFileType': 'hdf5',
                        'livePlot_activeMode': 'live', 'livePlot_statusLabel': None,
                        'run_dataFileNames': [finalName], 'livePlot_processedFiles': set(),
                        'livePlot_liveIngestBusy': False, 'livePlot_pollAfterId': None,
                        'root': SimpleNamespace(after=lambda ms, fn: 'after-id')}.items():
        monkeypatch.setattr(dltsc, name, value, raising=False)
    monkeypatch.setattr(ldT, '_ingest_files_async', lambda paths, tok: ingested.append(paths))

    ldT._schedule_live_poll(token)
    assert ingested == []                   # only the .tmp exists: nothing to read yet
    assert dltsc.livePlot_pollAfterId == 'after-id'  # and it keeps polling

    os.replace(tmp_path / 'p25p0.h5.tmp', finalName)
    ldT._schedule_live_poll(token)
    assert ingested == [[finalName]]

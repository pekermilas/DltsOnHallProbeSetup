"""Quick Analysis' Offline Data column: the saved-folder scan it runs
(liveDataTab._scan_folder) and how its 'Loaded Folder' transients take part in
Rate Window Analysis' Data Source choice (dataAnalysisTab)."""
import json
import os
from types import SimpleNamespace

import numpy as np
import pytest

import dltsConfig as dltsc
import dataAnalysisTab as daT
import liveDataTab as ldT
from conftest import write_run


def test_scan_folder_indexes_steps_and_reads_the_run_timing(zi_device, tmp_path):
    write_run(zi_device, str(tmp_path), [10.0, 20.0], '.h5')
    with open(tmp_path / 'runParams.txt', 'w') as f:
        json.dump({'State Enable Time': 1.0, 'State Disable Time': 0.002}, f)

    scan = ldT._scan_folder(str(tmp_path))

    assert scan['errors'] == []
    assert sorted(scan['registry']) == [10.0, 20.0]
    assert (scan['fpMs'], scan['rbMs']) == (2.0, 1000.0)
    assert scan['ziParamsByFile'] == {}


def test_scan_folder_reports_an_unreadable_folder(tmp_path):
    scan = ldT._scan_folder(str(tmp_path / 'missing'))
    assert scan['registry'] == {} and scan['errors']


def transients(*temps):
    t = np.linspace(0, 500, 50)
    return {T: {'time_ms': t, 'avg_cap_pf': 100 + np.exp(-t / 50), 'C_infinity': 100.0} for T in temps}


@pytest.fixture
def sources(monkeypatch):
    for name in ('quickData_processedTransients', 'manual_processedTransients',
                 'livePlot_liveAllEmissionsData', 'livePlot_offlineAllEmissionsData',
                 'quickData_paramVars', 'manual_paramVars'):
        monkeypatch.setattr(dltsc, name, None, raising=False)


def test_auto_prefers_the_loaded_folder_over_the_live_run(sources, monkeypatch):
    monkeypatch.setattr(dltsc, 'manual_processedTransients', transients(30.0))
    data, label, _ = daT._get_processed_transients_for_source(daT.DATA_SOURCE_AUTO)
    assert label == daT.DATA_SOURCE_QUALITATIVE

    monkeypatch.setattr(dltsc, 'quickData_processedTransients', transients(10.0, 20.0))
    data, label, _ = daT._get_processed_transients_for_source(daT.DATA_SOURCE_AUTO)
    assert label == daT.DATA_SOURCE_LOADED and sorted(data) == [10.0, 20.0]


def test_loaded_folder_without_an_extraction_says_what_to_do(sources):
    data, label, reason = daT._get_processed_transients_for_source(daT.DATA_SOURCE_LOADED)
    assert data is None and 'Extract & Average' in reason
    assert daT._resolve_impd_for_source(daT.DATA_SOURCE_LOADED) == (None, None)


def test_loaded_folder_uses_its_own_reverse_bias(sources, monkeypatch):
    monkeypatch.setattr(dltsc, 'quickData_paramVars', {'rb_ms': SimpleNamespace(get=lambda: '1000')})
    monkeypatch.setattr(dltsc, 'manual_paramVars', {'rb_ms': SimpleNamespace(get=lambda: '6')})
    assert daT._rb_ms_for_source(daT.DATA_SOURCE_LOADED, transients(10.0)) == 1000.0
    assert daT._rb_ms_for_source(daT.DATA_SOURCE_QUALITATIVE, transients(10.0)) == 6.0

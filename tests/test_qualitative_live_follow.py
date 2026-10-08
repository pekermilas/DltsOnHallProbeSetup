"""Qualitative Analysis' 'Follow live run': the Averaged Capacitance Transients
Profile re-extracts by itself as a run writes (or Redo/Retake rewrites) step
files (liveDataTab._qualitative_live_update)."""
import os
from types import SimpleNamespace

import pytest

import dltsConfig as dltsc
import liveDataTab as ldT
from conftest import step_file_name


class FakeListbox:
    """The bits of tk.Listbox the follow step uses."""
    def __init__(self):
        self.items, self.selected = [], set()

    def curselection(self):
        return tuple(sorted(self.selected))

    def delete(self, first, last):
        self.items, self.selected = [], set()

    def insert(self, index, text):
        self.items.append(text)

    def select_set(self, index):
        self.selected.add(index)


def touch(path, mtime):
    with open(path, 'w') as f:
        f.write('{}')
    os.utime(path, (mtime, mtime))


@pytest.fixture
def run(tmp_path, monkeypatch):
    """A run folder with three planned steps, none written yet, and the
    Qualitative frame's state stubbed out; records extractions."""
    folder = str(tmp_path)
    files = [os.path.join(folder, step_file_name(T, '.txt')) for T in (10.0, 20.0, 30.0)]
    calls = SimpleNamespace(extracts=0)

    def fake_extract():
        calls.extracts += 1

    for name, value in {'run_dataFolder': folder, 'run_dataFileNames': files,
                        'manual_liveFollowVar': SimpleNamespace(get=lambda: True),
                        'manual_liveRunFolder': None, 'manual_liveFileMtimes': {},
                        'manual_datasetRegistry': {}, 'manual_processingBusy': False,
                        'manual_tempListbox': FakeListbox(), 'manual_folderLabel': None,
                        'manual_paramVars': None,
                        'log_to_textbox': lambda msg: None}.items():
        monkeypatch.setattr(dltsc, name, value, raising=False)
    monkeypatch.setattr(ldT, '_process_raw_transients', fake_extract)
    return SimpleNamespace(folder=folder, files=files, calls=calls)


def test_nothing_happens_before_the_first_step_is_written(run):
    assert ldT._qualitative_live_update() is False
    assert dltsc.manual_liveRunFolder is None and run.calls.extracts == 0


def test_first_step_adopts_the_run_folder_then_extracts(run):
    touch(run.files[0], 1000)
    assert ldT._qualitative_live_update() is True
    assert dltsc.manual_liveRunFolder == run.folder
    assert sorted(dltsc.manual_datasetRegistry) == [10.0]
    assert dltsc.manual_tempListbox.curselection() == (0,)
    assert run.calls.extracts == 1


def test_new_step_is_added_selected_and_keeps_the_users_selection(run):
    touch(run.files[0], 1000)
    touch(run.files[1], 1000)
    ldT._qualitative_live_update()                       # adopt: 10 and 20 C, both selected
    dltsc.manual_tempListbox.selected.discard(0)          # user unticks 10 C

    touch(run.files[2], 2000)
    assert ldT._qualitative_live_update() is True
    assert sorted(dltsc.manual_datasetRegistry) == [10.0, 20.0, 30.0]
    assert dltsc.manual_tempListbox.curselection() == (1, 2)   # 20 C kept, 30 C added
    assert run.calls.extracts == 2


def test_rewritten_step_is_re_extracted_and_unchanged_files_are_not(run):
    touch(run.files[0], 1000)
    ldT._qualitative_live_update()
    assert ldT._qualitative_live_update() is False       # nothing changed
    assert run.calls.extracts == 1

    touch(run.files[0], 3000)                             # Redo / Retake rewrote it
    assert ldT._qualitative_live_update() is True
    assert run.calls.extracts == 2


def test_waits_while_an_extraction_is_running(run, monkeypatch):
    touch(run.files[0], 1000)
    monkeypatch.setattr(dltsc, 'manual_processingBusy', True)
    assert ldT._qualitative_live_update() is True         # retried next tick
    assert dltsc.manual_liveRunFolder is None

    monkeypatch.setattr(dltsc, 'manual_processingBusy', False)
    ldT._qualitative_live_update()
    assert dltsc.manual_liveRunFolder == run.folder and run.calls.extracts == 1


def test_a_new_run_folder_is_adopted(run, tmp_path_factory, monkeypatch):
    touch(run.files[0], 1000)
    ldT._qualitative_live_update()

    other = str(tmp_path_factory.mktemp('next_run'))
    nextFile = os.path.join(other, step_file_name(50.0, '.txt'))
    monkeypatch.setattr(dltsc, 'run_dataFolder', other)
    monkeypatch.setattr(dltsc, 'run_dataFileNames', [nextFile])
    touch(nextFile, 4000)
    assert ldT._qualitative_live_update() is True
    assert dltsc.manual_liveRunFolder == other
    assert sorted(dltsc.manual_datasetRegistry) == [50.0]


def test_unticking_follow_stops_updates(run, monkeypatch):
    monkeypatch.setattr(dltsc, 'manual_liveFollowVar', SimpleNamespace(get=lambda: False))
    touch(run.files[0], 1000)
    assert ldT._qualitative_live_update() is False
    assert run.calls.extracts == 0


def test_tick_keeps_polling_until_the_run_ends_and_nothing_is_pending(run, monkeypatch):
    scheduled = []
    monkeypatch.setattr(dltsc, 'root', SimpleNamespace(after=lambda ms, fn: scheduled.append(fn)), raising=False)
    monkeypatch.setattr(dltsc, 'app_closing', False, raising=False)
    monkeypatch.setattr(dltsc, 'manual_livePollActive', True, raising=False)

    monkeypatch.setattr(dltsc, 'run_busy', True, raising=False)
    ldT._qualitative_live_tick()
    assert scheduled == [ldT._qualitative_live_tick]

    monkeypatch.setattr(dltsc, 'run_busy', False, raising=False)
    touch(run.files[0], 1000)                             # the last step lands as the run ends
    ldT._qualitative_live_tick()
    assert len(scheduled) == 2 and run.calls.extracts == 1

    ldT._qualitative_live_tick()                          # nothing left: the loop stops
    assert len(scheduled) == 2 and dltsc.manual_livePollActive is False

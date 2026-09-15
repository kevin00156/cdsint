# -*- coding: utf-8 -*-
"""A backup that did not happen has to say so.

engine/backup.py answered every kind of trouble with the same None: no
project open, project never saved to disk, save refused, copy refused. The
caller read that None as "no backup was asked for" and went on to change the
project, which is the one thing a safety backup exists to prevent.

So the cases that used to collapse into one are the cases here: each is asked
for by itself, and each has to come back saying which one it was.
"""
import os
import sys
import time
import types

import pytest

from engine import backup, entry_export, entry_import
from tests.fakes import DeafSystem, Project, Projects

from cds.core import settings as core_settings


# What settings.prepare hands the backup functions. Only the keys they read.
SETTINGS = {
    "safety_backup": True,
    "backup_binary": False,
    "backup_name": "",
    "backup_retention_count": 10,
    "save_after_import": True,
    "save_after_export": True,
}

ONE_ITEM = [{"path": "POUs/Main.st"}]

# A fixed clock, so the name a test asks for is a name it can spell out.
A_MOMENT = time.struct_time((2026, 3, 25, 14, 30, 22, 2, 84, -1))

PROJECT_PATH = os.path.join("C:\\p", "Soft.project")


def settings(**overrides):
    values = dict(SETTINGS)
    values.update(overrides)
    return values


class RefusingProject(Project):
    """A project whose save() fails the way a read-only .project does."""

    def save(self):
        raise IOError("The process cannot access the file")


@pytest.fixture
def copies(monkeypatch):
    """Every copy backup.py asks for, and none of them actually made."""
    made = []
    monkeypatch.setattr(backup.shutil, "copy2",
                        lambda src, dst: made.append((src, dst)))
    return made


def test_a_copy_that_fails_comes_back_as_an_error(tmp_path, monkeypatch):
    def refuse(src, dst):
        raise IOError("Permission denied")

    monkeypatch.setattr(backup.shutil, "copy2", refuse)
    name, error = backup.create_safety_backup(
        str(tmp_path), Projects(Project()), ONE_ITEM, settings())
    assert name is None
    assert "Permission denied" in error


def test_the_setting_being_off_is_not_an_error(tmp_path, copies):
    assert backup.create_safety_backup(
        str(tmp_path), Projects(Project()), ONE_ITEM,
        settings(safety_backup=False)) == (None, None)
    assert copies == []


def test_nothing_to_import_is_not_an_error(tmp_path, copies):
    assert backup.create_safety_backup(
        str(tmp_path), Projects(Project()), [], settings()) == (None, None)
    assert copies == []


def test_a_project_never_saved_to_disk_is_an_error(tmp_path, copies):
    name, error = backup.create_safety_backup(
        str(tmp_path), Projects(Project(path="")), ONE_ITEM, settings())
    assert name is None
    assert "never been saved" in error
    assert copies == []


def test_a_backup_that_worked_hands_back_the_name_it_wrote(tmp_path, copies):
    name, error = backup.create_safety_backup(
        str(tmp_path), Projects(Project(path=PROJECT_PATH)), ONE_ITEM,
        settings())
    assert error is None
    assert name.endswith("_Soft.project.bak")
    assert len(copies) == 1


def test_a_safety_backup_whose_save_fails_copies_nothing(tmp_path, copies):
    # A copy taken after a failed save is a copy of the state before the last
    # edits, which is not the state this import is about to overwrite. The
    # caller cannot be handed a filename for that.
    name, error = backup.create_safety_backup(
        str(tmp_path), Projects(RefusingProject()), ONE_ITEM, settings())
    assert name is None
    assert "cannot access the file" in error
    assert copies == []


def test_a_save_that_fails_stops_the_copy(tmp_path, copies):
    error = backup.finalize_sync_operation(
        str(tmp_path), Projects(RefusingProject()),
        settings(backup_binary=True), is_import=True)
    assert "cannot access the file" in error
    assert copies == []


def test_the_project_is_saved_once_and_then_copied(tmp_path, copies):
    project = Project()
    error = backup.finalize_sync_operation(
        str(tmp_path), Projects(project), settings(backup_binary=True),
        is_import=True)
    assert error is None
    assert project.saves == 1
    assert len(copies) == 1


def test_saving_without_the_binary_backup_copies_nothing(tmp_path, copies):
    project = Project()
    error = backup.finalize_sync_operation(
        str(tmp_path), Projects(project),
        settings(backup_binary=False, save_after_import=True), is_import=True)
    assert error is None
    assert project.saves == 1
    assert copies == []


def test_a_timestamped_name_carries_the_moment_and_the_project():
    assert backup.target_name(PROJECT_PATH, "", True, A_MOMENT) == \
        "20260325_143022_Soft.project.bak"


def test_a_custom_name_gets_the_extension_it_is_missing():
    assert backup.target_name(PROJECT_PATH, "nightly", False,
                              A_MOMENT) == "nightly.project"


def test_a_custom_name_that_already_has_the_extension_keeps_one():
    assert backup.target_name(PROJECT_PATH, "nightly.project", False,
                              A_MOMENT) == "nightly.project"


def test_no_custom_name_means_the_project_keeps_its_own():
    assert backup.target_name(PROJECT_PATH, "", False,
                              A_MOMENT) == "Soft.project"


@pytest.fixture
def importer(monkeypatch, tmp_path):
    """entry_import with one file to import, and the two backup calls faked.

    `run` takes what create_safety_backup and finalize_sync_operation should
    answer, and reports whether perform_import_items was reached: those two
    answers and that one fact are the whole of what this file is about at the
    entry point.
    """
    sync = tmp_path / "sync"
    sync.mkdir()
    (sync / "PLC_PRG.st").write_text(u"PROGRAM PLC_PRG\n", encoding="utf-8")
    on_disk = [{"name": "PLC_PRG", "path": "PLC_PRG.st",
                "file_path": str(sync / "PLC_PRG.st")}]
    imported = []

    monkeypatch.setattr(entry_import, "find_all_changes",
                        lambda base_dir, projects_obj, export_xml=False: {
                            "different": [], "new_in_ide": [],
                            "new_on_disk": list(on_disk),
                            "unchanged_count": 0})
    said_yes = types.ModuleType("engine.codesys_ui")
    said_yes.ask_yes_no = lambda title, message: True
    monkeypatch.setitem(sys.modules, "engine.codesys_ui", said_yes)
    monkeypatch.setattr(entry_import, "timed_prompt",
                        lambda *args, **kwargs: True)
    monkeypatch.setattr(entry_import, "perform_import_items",
                        lambda *args: imported.append(args) or (1, 0, 0, 0, 0))

    projects = Projects(Project({}, [], str(tmp_path / "Fake.project")))
    monkeypatch.setattr(entry_import, "projects", projects, raising=False)
    monkeypatch.setattr(entry_import, "system", DeafSystem(), raising=False)

    def run(backup_answer=(None, None), finalize_answer=None):
        monkeypatch.setattr(entry_import, "create_safety_backup",
                            lambda *args: backup_answer)
        monkeypatch.setattr(entry_import, "finalize_sync_operation",
                            lambda *args, **kwargs: finalize_answer)
        return entry_import.import_project(str(sync),
                                           core_settings.resolve({}), projects)

    return {"run": run, "imported": imported}


def test_a_failed_safety_backup_stops_the_import(importer):
    """The reason the error exists at all, checked where it has to land.

    entry_import read the old None as "no backup was asked for" and went on to
    change the project. Anything can go wrong at the entry point; what may not
    go wrong is that the guard fires and the import runs anyway.
    """
    result = importer["run"](
        backup_answer=(None, "the .project folder is read-only"))
    assert result["ok"] is False
    assert "read-only" in result["summary"]
    assert importer["imported"] == []


def test_an_import_that_could_not_save_the_project_is_not_ok(importer):
    # The objects did land, so the import is not undone -- but the project
    # holding them was never written, and a run that says ok would send the
    # reader away believing it was.
    result = importer["run"](finalize_answer="the project file is read-only")
    assert result["ok"] is False
    assert "the project file is read-only" in result["summary"]
    assert len(importer["imported"]) == 1


def test_an_import_that_saved_is_ok(importer):
    # The other direction, so the assertion above is about the error and not
    # about this fixture never producing an ok run.
    assert importer["run"]()["ok"] is True


@pytest.fixture
def exporter(monkeypatch, tmp_path):
    """entry_export over an empty project, with finalize_sync_operation faked.

    Nothing in the project, because what is under test is what the entry does
    with the answer it gets at the end, not what it wrote on the way there.
    """
    export_dir = tmp_path / "sync"
    projects = Projects(Project({}, [], str(tmp_path / "Fake.project")))
    monkeypatch.setattr(entry_export, "projects", projects, raising=False)
    monkeypatch.setattr(entry_export, "system", DeafSystem(), raising=False)

    def run(finalize_answer=None):
        monkeypatch.setattr(entry_export, "finalize_sync_operation",
                            lambda *args, **kwargs: finalize_answer)
        return entry_export.export_project(str(export_dir),
                                           core_settings.resolve({}), projects)

    return run


def test_an_export_that_could_not_save_the_project_is_not_ok(exporter):
    # The .st files are on disk and correct. What did not happen is the save
    # the settings asked for, and the summary has to separate the two or the
    # reader goes looking for a bad export that is not there.
    result = exporter(finalize_answer="the project file is read-only")
    assert result["ok"] is False
    assert "the project file is read-only" in result["summary"]


def test_an_export_that_saved_is_ok(exporter):
    assert exporter()["ok"] is True

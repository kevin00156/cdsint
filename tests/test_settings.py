# -*- coding: utf-8 -*-
"""Tests for engine.settings — this run's settings, and the first-run setup.

Two jobs. Loading is the whole of what every command reads: the file beside
the project, resolved, with `--sync-dir` laid over the top for this run only.
The first-run flow is the one dialog left (SPEC 6.7), and the part of it
worth testing in CPython is which shape of path gets written down — that is
what decides whether the project still syncs after somebody opens it
somewhere else.
"""
import io
import json
import os

import pytest

from cds.core import settings as schema
from engine import settings


class FakeProject(object):
    def __init__(self, path):
        self.path = path


class FakeProjects(object):
    def __init__(self, primary):
        self.primary = primary


class Recorded(object):
    """system.ui, remembering what it was asked to show."""

    def __init__(self):
        self.shown = []

    def __getattr__(self, level):
        def show(text):
            self.shown.append((level, text))
        return show


class RecordedSystem(object):
    def __init__(self):
        self.ui = Recorded()


@pytest.fixture
def project(tmp_path):
    return FakeProject(os.path.join(str(tmp_path), "App.project"))


@pytest.fixture
def ide(project):
    """The globals an entry body has: the IDE's objects, and this run's flags."""
    return {"projects": FakeProjects(project), "system": RecordedSystem()}


def settings_file(project):
    return schema.path_for(project.path)


def write(project, values):
    schema.write(settings_file(project), values)


# -- load ------------------------------------------------------------------

def test_a_project_with_no_settings_file_gets_the_defaults(ide):
    values, error = settings.load(ide)
    assert error is None
    assert values["debug"] is False
    assert values["backup_retention_count"] == 10
    # Nobody has chosen a folder, so there is not one to report.
    assert "sync_folder" not in values


def test_what_the_file_says_wins_over_the_default(ide, project):
    write(project, {"debug": True, "backup_retention_count": 3})
    values, error = settings.load(ide)
    assert error is None
    assert values["debug"] is True
    assert values["backup_retention_count"] == 3
    assert values["safety_backup"] is True     # untouched keys still default


def test_a_file_that_cannot_be_read_stops_the_command(ide, project):
    with io.open(settings_file(project), "w", encoding="utf-8") as handle:
        handle.write(u'{"sync_folder": "./sync", "debgu": true}')
    values, error = settings.load(ide)
    assert values is None
    assert "debgu" in error
    # The whole table comes with the refusal, so the reader can see the name
    # they meant to type (SPEC 4.4).
    assert "debug" in error and "auto_delete_orphans" in error


def test_no_project_open_has_no_settings_to_read():
    values, error = settings.load({"projects": FakeProjects(None)})
    assert values is None
    assert "No project is open" in error


# -- the --sync-dir override -----------------------------------------------

def test_sync_dir_overrides_the_file_for_this_run(ide, project, tmp_path):
    write(project, {"sync_folder": "./from-the-file"})
    elsewhere = os.path.join(str(tmp_path), "just-this-run")
    ide["command_args"] = {"sync_dir": elsewhere}

    values, folder, error = settings.prepare(ide)

    assert error is None
    assert folder == elsewhere
    # Never written back: the copy this flag exists for must come out of the
    # run saying exactly what it said going in (SPEC 4.2).
    assert schema.read(settings_file(project)) == \
        {"sync_folder": "./from-the-file"}


def test_sync_dir_works_when_there_is_no_file_at_all(ide, tmp_path, project):
    ide["command_args"] = {"sync_dir": os.path.join(str(tmp_path), "out")}
    values, folder, error = settings.prepare(ide)
    assert error is None
    assert folder.endswith("out")
    assert not os.path.exists(settings_file(project))


# -- prepare ---------------------------------------------------------------

def test_prepare_resolves_a_relative_folder_and_creates_it(ide, project,
                                                           tmp_path):
    write(project, {"sync_folder": "./sync"})
    values, folder, error = settings.prepare(ide)
    assert error is None
    assert folder == os.path.join(str(tmp_path), "sync")
    assert os.path.isdir(folder)


def test_prepare_gives_the_new_folder_its_git_rules(ide, project):
    write(project, {"sync_folder": "./sync"})
    _values, folder, _error = settings.prepare(ide)
    assert os.path.isfile(os.path.join(folder, ".gitignore"))
    assert os.path.isfile(os.path.join(folder, ".gitattributes"))


def test_no_folder_yet_is_not_an_error(ide):
    # It stops a compare and it does not stop a build, so prepare() reports
    # it as an absent folder and each command decides. Reporting it as an
    # error is what let a misspelt key run a build to a clean finish.
    values, folder, error = settings.prepare(ide)
    assert error is None
    assert folder is None
    assert values["debug"] is False


def test_a_file_that_cannot_be_read_is_an_error(ide, project):
    with io.open(settings_file(project), "w", encoding="utf-8") as handle:
        handle.write(u'{"sync_folder": "./sync", "debgu": true}')
    values, folder, error = settings.prepare(ide)
    assert values is None and folder is None
    assert "debgu" in error


def test_the_sentence_for_a_command_that_needs_a_folder_names_the_file(ide,
                                                                       project):
    said = settings.folder_missing(ide)
    assert settings_file(project) in said
    assert "sync_folder" in said


def test_prepare_does_not_ask_anybody_anything(ide, monkeypatch):
    # compare, build and discover go through prepare(). A dialog opened from
    # one of those is a modal window on the IDE's message loop that nobody
    # was expecting (SPEC 6.7).
    def refuse(*args, **kwargs):
        raise AssertionError("prepare() must not open the first-run dialog")

    monkeypatch.setattr(settings, "choose_sync_folder", refuse)
    _values, folder, error = settings.prepare(ide)
    assert error is None and folder is None


# -- the first-run dialog --------------------------------------------------

def test_the_dialog_writes_one_key_and_only_one(ide, project, tmp_path,
                                                monkeypatch):
    monkeypatch.setattr(settings, "_ask",
                        lambda system, path: str(tmp_path / "sync"))
    values, folder, error = settings.prepare_asking(ide)

    assert error is None
    with io.open(settings_file(project), encoding="utf-8") as handle:
        assert json.loads(handle.read()) == {"sync_folder": "." + os.sep + "sync"}
    # Everything else is still the code's default, not a line in the file.
    assert values["safety_backup"] is True
    assert os.path.isdir(folder)


def test_cancelling_the_dialog_writes_nothing(ide, project, monkeypatch):
    monkeypatch.setattr(settings, "_ask", lambda system, path: None)
    values, folder, error = settings.prepare_asking(ide)
    assert values is None and folder is None
    assert "cancelled" in error
    assert not os.path.exists(settings_file(project))


def test_a_project_that_already_has_a_folder_is_not_asked(ide, project,
                                                          monkeypatch):
    write(project, {"sync_folder": "./sync"})

    def refuse(system, path):
        raise AssertionError("the folder is already set; nothing to ask")

    monkeypatch.setattr(settings, "_ask", refuse)
    _values, folder, error = settings.prepare_asking(ide)
    assert error is None and folder.endswith("sync")


# -- _as_written: the shape the dialog writes down -------------------------

def project_dir(project):
    return os.path.dirname(project.path)


def test_a_folder_inside_the_project_directory_is_written_relative(tmp_path,
                                                                   project):
    # Relative is what travels: cds.core.settings.folder resolves it against
    # the project file, so a copy taken with its settings still works.
    chosen = os.path.join(str(tmp_path), "src")
    assert settings._as_written(chosen, project_dir(project)) == "." + os.sep + "src"


def test_the_project_directory_itself_is_written_as_dot(tmp_path, project):
    assert settings._as_written(str(tmp_path), project_dir(project)) == "." + os.sep


def test_a_nested_folder_keeps_its_whole_path(tmp_path, project):
    chosen = os.path.join(str(tmp_path), "plc", "src")
    assert settings._as_written(chosen, project_dir(project)) == \
        "." + os.sep + os.path.join("plc", "src")


def test_a_folder_outside_the_project_directory_stays_absolute(tmp_path,
                                                               project):
    # "../../shared" is relative too, and worthless: it only resolves while
    # the project sits exactly where it sits today.
    chosen = os.path.join(os.path.dirname(str(tmp_path)), "shared")
    assert settings._as_written(chosen, project_dir(project)) == chosen


def test_a_path_the_user_typed_relative_is_left_alone(project):
    assert settings._as_written("./sync/", project_dir(project)) == \
        "." + os.sep + "sync" + os.sep


def test_no_project_directory_means_no_relative_form(tmp_path):
    # An unsaved project, or an IDE version with no path to offer.
    chosen = os.path.join(str(tmp_path), "src")
    assert settings._as_written(chosen, None) == chosen

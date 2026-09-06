# -*- coding: utf-8 -*-
"""Tests for engine.settings — the first-run setup flow (SPEC 6.7).

Only the path decision is testable here. The dialogs themselves are
WinForms, so they are verified by hand against a real IDE; what CPython can
check is which shape of path gets written into the project property, because
that is what decides whether the project still syncs after someone else
opens it on their own machine.
"""
import ast
import io
import os

import pytest

from engine import settings


class FakeProject(object):
    def __init__(self, path):
        self.path = path


@pytest.fixture
def project(tmp_path):
    return FakeProject(os.path.join(str(tmp_path), "App.project"))


def test_a_folder_inside_the_project_directory_is_written_relative(tmp_path,
                                                                   project):
    # Relative is what travels: load_base_dir resolves it against the
    # project file and skips the computer-mismatch dialog entirely.
    chosen = os.path.join(str(tmp_path), "src")
    assert settings._as_written(chosen, project) == "." + os.sep + "src"


def test_the_project_directory_itself_is_written_as_dot(tmp_path, project):
    assert settings._as_written(str(tmp_path), project) == "." + os.sep


def test_a_nested_folder_keeps_its_whole_path(tmp_path, project):
    chosen = os.path.join(str(tmp_path), "plc", "src")
    assert settings._as_written(chosen, project) == \
        "." + os.sep + os.path.join("plc", "src")


def test_a_folder_outside_the_project_directory_stays_absolute(tmp_path,
                                                               project):
    # "../../shared" is relative too, and worthless: it only resolves while
    # the project sits exactly where it sits today.
    chosen = os.path.join(os.path.dirname(str(tmp_path)), "shared")
    assert settings._as_written(chosen, project) == chosen


def test_a_path_the_user_typed_relative_is_left_alone(project):
    assert settings._as_written("./sync/", project) == "." + os.sep + "sync" + os.sep


def test_no_project_path_means_no_relative_form(tmp_path):
    # A project object with no .path — an unsaved project, or an IDE
    # version that does not offer one. Absolute still works.
    chosen = os.path.join(str(tmp_path), "src")
    assert settings._as_written(chosen, object()) == chosen


def test_every_setting_in_the_dialog_has_a_property_behind_it():
    # The dialog is built from a dict with these keys (codesys_ui
    # SettingsForm); a key here with no widget, or a widget with no key,
    # silently drops whatever the user changed.
    keys = [key for _prop, key, _default in settings.SETTINGS]
    assert len(set(keys)) == len(keys)
    assert all(prop.startswith("cds-sync-")
               for prop, _key, _default in settings.SETTINGS)


# --- the sync folder row in the settings dialog (SPEC 6.7) -----------------

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
def written(monkeypatch):
    """settings with the property writes recorded instead of reaching an IDE."""
    record = {}

    def set_prop(name, value):
        record[name] = value
        return True

    monkeypatch.setattr(settings, "set_project_prop", set_prop)
    # It counts the project's applications through the IDE; nothing here has
    # one, and the folder decision does not depend on the answer.
    monkeypatch.setattr(settings, "update_application_count_flag", lambda: None)
    return record


def test_a_changed_folder_writes_the_path_the_machine_and_the_version(
        written, tmp_path, project):
    wanted = os.path.join(str(tmp_path), "src")

    assert settings._apply_folder(RecordedSystem(), wanted, "", project) is True

    # Relative, because the folder sits under the project's own directory.
    assert written["cds-sync-folder"] == "." + os.sep + "src"
    assert written["cds-sync-pc"]
    assert written["cds-sync-version"]
    assert os.path.isdir(wanted)


def test_an_untouched_folder_writes_nothing_at_all(written, project):
    # _remember_who_and_what stamps this machine onto the project. Running it
    # every time somebody opens Settings would quietly claim a project that
    # was set up on somebody else's.
    assert settings._apply_folder(RecordedSystem(), "./src", "./src",
                                  project) is False
    assert written == {}


def test_clearing_the_box_is_refused_out_loud(written, project):
    system = RecordedSystem()

    assert settings._apply_folder(system, "", "./src", project) is False

    assert written == {}
    assert system.ui.shown and "blank" in system.ui.shown[0][1]


def test_a_folder_that_cannot_be_written_says_so_and_stamps_nothing(
        written, monkeypatch, tmp_path, project):
    # A read-only project, or one whose properties the IDE will not hand
    # over. Stamping the machine after that would describe a folder the
    # project does not have.
    monkeypatch.setattr(settings, "set_project_prop",
                        lambda name, value: False)
    system = RecordedSystem()

    assert settings._apply_folder(system, os.path.join(str(tmp_path), "src"),
                                  "", project) is False

    assert written == {}
    assert system.ui.shown[0][0] == "error"


def test_every_widget_in_the_dialog_is_read_back():
    """get_results() builds the dict edit() reads back key by key.

    A widget whose key edit() does not know about is a setting the user
    changes and the project never hears about. Read off the parsed source
    because importing codesys_ui needs clr, which only exists in the IDE.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "engine", "codesys_ui.py")
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    returned = [node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "get_results"]
    assert len(returned) == 1
    keys = set()
    for node in ast.walk(returned[0]):
        if isinstance(node, ast.Dict):
            keys.update(key.value for key in node.keys)

    expected = set(key for _prop, key, _default in settings.SETTINGS)
    expected.add("sync_folder")
    assert keys == expected

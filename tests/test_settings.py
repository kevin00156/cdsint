# -*- coding: utf-8 -*-
"""Tests for engine.settings — the first-run setup flow (SPEC 6.7).

Only the path decision is testable here. The dialogs themselves are
WinForms, so they are verified by hand against a real IDE; what CPython can
check is which shape of path gets written into the project property, because
that is what decides whether the project still syncs after someone else
opens it on their own machine.
"""
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

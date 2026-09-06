# -*- coding: utf-8 -*-
"""Tests for cds.ide.project — asking the IDE what it has open.

The happy paths are covered through the watcher; what matters here is that
every question answers None instead of raising when the IDE is not in a state
to answer it. A watcher that dies because nobody has a project open, or
because somebody is halfway through editing a settings file, is useless.
"""
import io
import os

import pytest

from cds.core import settings
from cds.ide import project
from tests.fakes import Project, Projects


@pytest.fixture
def opened(tmp_path):
    """A project open at a real path, so its settings file has somewhere to be."""
    return Projects(Project(path=os.path.join(str(tmp_path), "x.project")))


def write(opened, text):
    path = settings.path_for(project.path_of(opened))
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_no_project_open_answers_nothing():
    empty = Projects()
    assert project.path_of(empty) is None
    assert project.sync_dir(empty) is None


def test_a_project_with_no_settings_file_has_no_sync_folder(opened):
    assert project.sync_dir(opened) is None


def test_a_settings_file_with_no_sync_folder_answers_nothing(opened):
    write(opened, u'{"debug": true}')
    assert project.sync_dir(opened) is None


def test_an_absolute_sync_folder_comes_back_as_written(opened):
    settings.write(settings.path_for(project.path_of(opened)),
                   {"sync_folder": r"D:\work\sync"})
    assert project.sync_dir(opened) == r"D:\work\sync"


def test_a_relative_sync_folder_resolves_against_the_project(opened, tmp_path):
    write(opened, u'{"sync_folder": "./out/sync"}')
    answer = project.sync_dir(opened)
    assert answer.endswith("sync")
    assert answer.startswith(str(tmp_path))


def test_a_settings_file_nobody_can_parse_answers_nothing(opened):
    # The watcher asks this on every heartbeat. A half-saved file must not
    # take it down; the next command that needs the file reports the problem
    # in full (SPEC 4.4).
    write(opened, u'{"sync_folder": ')
    assert project.sync_dir(opened) is None


def test_a_setting_nobody_recognises_answers_nothing(opened):
    write(opened, u'{"sync_folder": "./sync", "debgu": true}')
    assert project.sync_dir(opened) is None


def test_the_ide_name_leads_with_the_executable():
    assert project.ide_name().endswith(")")
    assert "(" in project.ide_name()

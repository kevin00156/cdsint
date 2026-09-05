# -*- coding: utf-8 -*-
"""Reading and writing the project properties, through the engine's helpers.

These sit behind bare `except:` blocks that turn any mistake into a quiet
False, which is exactly how they went unwatched: the property-name constants
arrived under the name `props`, three functions here already had a local
variable called `props` holding the project's own property dictionary, and
`props.FOLDER` started resolving to an attribute lookup on that dictionary.
Everything kept returning False and nothing said why. Only a headless run
against a real IDE showed it, in a log line nobody was reading.

So the helpers get tests of their own now, asserting the return value and
not just the side effect.
"""
import pytest

from cds.core import props
from engine import codesys_utils as utils


class Info(object):
    def __init__(self, values):
        self.values = values


class Project(object):
    def __init__(self, values=None, children=()):
        self._info = Info(values if values is not None else {})
        self._children = list(children)

    def get_project_info(self):
        return self._info

    def get_children(self, recursive=False):
        return list(self._children)

    @property
    def written(self):
        return self._info.values


class Projects(object):
    def __init__(self, primary):
        self.primary = primary


@pytest.fixture
def project(monkeypatch):
    """One open project, reachable the way the engine reaches it."""
    primary = Project()
    projects = Projects(primary)
    monkeypatch.setattr(utils, "resolve_projects", lambda *a, **k: projects)
    monkeypatch.setattr(utils, "_resolve_primary_project", lambda: primary)
    return primary


def test_setting_a_property_says_it_worked(project):
    # The caller in engine/settings.py prints "Could not write
    # cds-sync-folder" when this comes back False, so a False that means
    # "written fine" is a lie the user reads on screen.
    assert utils.set_project_prop(props.FOLDER, r"C:\sync") is True
    assert project.written[props.FOLDER] == r"C:\sync"


def test_reading_a_property_back_gives_what_was_written(project):
    utils.set_project_prop(props.BACKUP_NAME, "nightly")
    assert utils.get_project_prop(props.BACKUP_NAME) == "nightly"


def test_turning_debug_on_takes_effect_in_the_same_run(project, monkeypatch):
    # is_debug() caches, and the cache is reset by set_project_prop when the
    # property it just wrote is the debug one. Without that, `cdsint config
    # set cds-sync-debug=true` does nothing until the IDE is restarted.
    utils.reset_debug_cache()
    assert utils.is_debug() is False
    utils.set_project_prop(props.DEBUG, True)
    assert utils.is_debug() is True


def test_one_application_records_the_flag_as_false(project):
    assert utils.set_application_count_flag(1) is True
    assert project.written[props.MULTIPLE_APPS] == "False"


def test_two_applications_record_it_as_true(project):
    assert utils.set_application_count_flag(2) is True
    assert project.written[props.MULTIPLE_APPS] == "True"


def test_counting_the_applications_writes_the_same_flag(project):
    class Obj(object):
        def __init__(self, type_guid):
            self.type = type_guid

    project._children = [Obj(utils.APPLICATION_GUID),
                         Obj(utils.APPLICATION_GUID),
                         Obj("something-else")]

    assert utils.update_application_count_flag() is True
    assert project.written[props.MULTIPLE_APPS] == "True"

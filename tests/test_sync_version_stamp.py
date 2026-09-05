# -*- coding: utf-8 -*-
"""cds-sync-version has to be in the project before the project is saved.

It lives in the .project file, not in git, so the only thing that makes it
survive a run is the save at the end of it. Writing it after that save meant
it never survived anything: a headless run's process ends and takes it with
it, and in the watcher the person has to save by hand before it sticks. The
visible cost was check_version_compatibility warning about a mismatch on
every single run, and a warning that is always wrong is a warning nobody
reads.
"""
import sys

import pytest

from tests.test_dirty_files import DeafSystem, Info, Pou, Projects


class RecordingProject(object):
    """A project that remembers what its properties said when it was saved."""

    def __init__(self, values, children, path):
        self._values = values
        self._children = children
        self.path = path
        self.saved = None

    def get_project_info(self):
        return Info(self._values)

    def get_children(self, recursive=False):
        return list(self._children)

    def get_name(self):
        return "FakeProject"

    def save(self):
        self.saved = dict(self._values)


@pytest.fixture
def a_project_with_no_version(load_engine, monkeypatch, tmp_path):
    for dep in ("codesys_constants", "codesys_utils", "codesys_managers",
                "codesys_compare_engine"):
        load_engine(dep)
    export = load_engine("entry_export")
    sync = tmp_path / "sync"
    sync.mkdir()
    project = RecordingProject({"cds-sync-folder": str(sync)}, [Pou()],
                               str(tmp_path / "Fake.project"))
    projects = Projects(project)
    monkeypatch.setattr(export, "projects", projects, raising=False)
    monkeypatch.setattr(export, "system", DeafSystem(), raising=False)
    export.export_project(str(sync), projects)
    return project


def test_the_version_reaches_the_project_before_it_is_saved(
        a_project_with_no_version):
    version = sys.modules["engine.codesys_constants"].SCRIPT_VERSION
    assert a_project_with_no_version.saved is not None
    assert a_project_with_no_version.saved["cds-sync-version"] == version

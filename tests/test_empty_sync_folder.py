# -*- coding: utf-8 -*-
"""A sync folder with no .st in it is not an empty project. It is no truth.

Disk wins (SPEC target 1), so an import reads the folder as the answer to
"what should the IDE contain". A folder with nothing in it therefore reads as
"nothing", and the import deletes every object in the project — which is what
happened to a 229-object copy when the supervisor pointed a headless verify at
a fresh empty --sync-dir: 178 objects gone, 51 more that only survived because
their parent was deleted first.

The fix is a precondition, not a threshold: the same shape as the check that
refuses to import while somebody is logged into a PLC. Either the source of
truth exists or the command has nothing to do its job with.
"""
import sys

import pytest

from engine import entry_import

from cds.core import settings

# Every setting at its default: these tests are about the engine's
# behaviour, not about what somebody wrote in a settings file.
DEFAULTS = settings.resolve({})

from tests.test_unhandled_objects import DeafSystem, Project, Projects


@pytest.fixture
def importer(monkeypatch, tmp_path):
    """entry_import lent a fake IDE, with the comparison engine watched.

    The spy stands where the first thing that reads the IDE tree stands, so a
    check that fires too late shows up as a call that should not have
    happened.
    """
    body = entry_import
    compared = []

    def spy(base_dir, projects_obj, export_xml=False):
        compared.append(base_dir)
        return {"different": [], "new_in_ide": [], "new_on_disk": [],
                "unchanged_count": 0}

    monkeypatch.setattr(body, "find_all_changes", spy)

    def run(sync_dir):
        project = Project({}, [], str(tmp_path / "Fake.project"))
        projects = Projects(project)
        monkeypatch.setattr(body, "projects", projects, raising=False)
        monkeypatch.setattr(body, "system", DeafSystem(), raising=False)
        return body.import_project(str(sync_dir), DEFAULTS, projects)

    return {"run": run, "compared": compared, "sync": tmp_path / "sync"}


def test_an_empty_sync_folder_is_refused_before_the_ide_is_read(importer):
    importer["sync"].mkdir()
    result = importer["run"](importer["sync"])
    assert result["ok"] is False
    assert importer["compared"] == []
    assert ".st" in result["summary"] and str(importer["sync"]) in result["summary"]


def test_the_refusal_says_what_to_do_about_it(importer):
    # The two ways to be here are "never exported" and "pointed at the wrong
    # folder", and the reader cannot tell which without being told both.
    importer["sync"].mkdir()
    said = importer["run"](importer["sync"])["summary"]
    assert "export" in said and "sync_folder" in said


def test_a_folder_that_does_not_exist_yet_is_the_same_refusal(importer):
    # The settings are resolved before this runs and that step creates the
    # folder it was pointed at, so a typo arrives here as a brand new empty
    # directory rather than as an error.
    result = importer["run"](importer["sync"])
    assert result["ok"] is False and importer["compared"] == []


def test_one_st_file_is_enough_to_go_on(importer):
    importer["sync"].mkdir()
    (importer["sync"] / "MC_Main.st").write_text(u"FUNCTION_BLOCK MC_Main\n",
                                                 encoding="utf-8")
    result = importer["run"](importer["sync"])
    assert result["ok"] is True and importer["compared"] == [str(importer["sync"])]


def test_an_st_in_a_subfolder_counts(importer):
    # The .st files mirror the IDE tree, so most of them are several folders
    # down and the top level of a real sync folder is often just directories.
    nested = importer["sync"] / "Device" / "Application"
    nested.mkdir(parents=True)
    (nested / "PLC_PRG.st").write_text(u"PROGRAM PLC_PRG\n", encoding="utf-8")
    assert importer["run"](importer["sync"])["ok"] is True


def test_an_st_the_disk_scan_would_skip_does_not_count(importer):
    # Dot-folders are where backups and git live, and the import's own disk
    # scan walks past them. Counting one here would let a folder holding
    # nothing importable pass for a source of truth.
    hidden = importer["sync"] / ".project"
    hidden.mkdir(parents=True)
    (hidden / "backup.st").write_text(u"PROGRAM Old\n", encoding="utf-8")
    result = importer["run"](importer["sync"])
    assert result["ok"] is False and importer["compared"] == []

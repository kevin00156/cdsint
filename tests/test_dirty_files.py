# -*- coding: utf-8 -*-
"""An edit on disk that was never imported must survive the next export.

Disk is the source of truth (SPEC 5, PRINCIPLES 5), so the one thing export
must never do is quietly write over somebody's work. Until now it did: the
sync cache noticed the file had changed, used that only to decide it could
not take the fast path, and then overwrote it anyway (SPEC 6.1).
"""
import sys

import pytest


class Text(object):
    def __init__(self, text):
        self.text = text


class Pou(object):
    """A POU whose declaration and implementation a test can rewrite."""

    has_textual_declaration = True
    has_textual_implementation = True
    parent = None

    def __init__(self, name="MC_Main"):
        from engine.codesys_constants import TYPE_GUIDS
        self._name = name
        self.type = TYPE_GUIDS["pou"]
        self.guid = "guid-" + name
        self.textual_declaration = Text(u"FUNCTION_BLOCK %s\nEND_VAR\n" % name)
        self.textual_implementation = Text(u"x := 1;\n")

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        return []


class Info(object):
    def __init__(self, values):
        self.values = values


class Project(object):
    def __init__(self, values, children, path):
        self._values = values
        self._children = children
        self.path = path

    def get_project_info(self):
        return Info(self._values)

    def get_children(self, recursive=False):
        return list(self._children)

    def get_name(self):
        return "FakeProject"

    def save(self):
        pass


class Projects(object):
    def __init__(self, primary):
        self.primary = primary


class DeafUI(object):
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class DeafSystem(object):
    ui = DeafUI()


class Synced(object):
    """One POU exported once, and the two ways to export it again."""

    def __init__(self, pou, path, export, from_dialog):
        self.pou = pou
        self.file = path
        self.export = export
        self.export_from_dialog = from_dialog


@pytest.fixture
def a_synced_project(load_engine, monkeypatch, tmp_path):
    """A project whose sync cache knows what the disk held at the last sync."""
    for dep in ("codesys_constants", "codesys_utils", "codesys_managers",
                "codesys_compare_engine"):
        load_engine(dep)
    export = load_engine("entry_export")
    compare = load_engine("entry_compare")

    sync = tmp_path / "sync"
    sync.mkdir()
    version = sys.modules["engine.codesys_constants"].SCRIPT_VERSION
    pou = Pou()
    project = Project({"cds-sync-folder": str(sync),
                       "cds-sync-version": version},
                      [pou], str(tmp_path / "Fake.project"))
    projects = Projects(project)
    for body in (export, compare):
        monkeypatch.setattr(body, "projects", projects, raising=False)
        monkeypatch.setattr(body, "system", DeafSystem(), raising=False)

    run = lambda: export.export_project(str(sync), projects)
    first = run()
    assert first["ok"] is True, first["summary"]
    written = [p for p in sync.rglob("*.st")]
    assert len(written) == 1, written
    chose_the_ide = lambda: compare.perform_export(
        str(sync), [{"obj": pou, "name": pou.get_name(),
                     "path": written[0].name}])
    return Synced(pou, written[0], run, chose_the_ide)


def edit_on_disk(path, text):
    """Write the file the way a person with an editor would.

    utime is not touched: the guard compares against what the last export
    recorded, and a real edit moves the timestamp forward on its own.
    """
    path.write_text(text, encoding="utf-8")


def test_an_unimported_edit_is_not_overwritten(a_synced_project):
    mine = u"FUNCTION_BLOCK MC_Main\nEND_VAR\n// === IMPLEMENTATION ===\nmine := 1;\n"
    edit_on_disk(a_synced_project.file, mine)
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    a_synced_project.export()

    assert a_synced_project.file.read_text(encoding="utf-8") == mine


def test_the_file_it_left_alone_is_reported_as_waiting_for_import(
        a_synced_project):
    edit_on_disk(a_synced_project.file, u"FUNCTION_BLOCK MC_Main\nEND_VAR\nmine := 1;\n")
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    result = a_synced_project.export()

    assert result["data"]["pending_import"] == ["MC_Main.st"]
    assert "MC_Main.st" in result["summary"]


def test_an_export_that_left_files_behind_is_not_ok(a_synced_project):
    # The disk no longer matches the IDE and export chose not to make it
    # match, so the caller that reads only the exit code must not read that
    # as a finished export.
    edit_on_disk(a_synced_project.file, u"FUNCTION_BLOCK MC_Main\nEND_VAR\nmine := 1;\n")
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    assert a_synced_project.export()["ok"] is False


def test_an_untouched_file_is_still_updated_from_the_ide(a_synced_project):
    # The guard is about the disk having moved. When only the IDE moved,
    # export does exactly what it always did.
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    result = a_synced_project.export()

    assert u"theirs := 2;" in a_synced_project.file.read_text(encoding="utf-8")
    assert result["ok"] is True and result["data"]["pending_import"] == []


def test_a_disk_edit_that_matches_the_ide_is_not_called_pending(
        a_synced_project):
    # A git checkout rewrites files it did not change, moving the timestamp
    # and nothing else. There is nothing to import, so the content check has
    # to settle it before the timestamp gets a say.
    a_synced_project.file.write_bytes(a_synced_project.file.read_bytes())

    result = a_synced_project.export()

    assert result["ok"] is True and result["data"]["pending_import"] == []


def test_the_compare_dialog_export_writes_what_the_person_chose(
        a_synced_project):
    # The guard is for the export nobody was watching. Here the person read
    # the difference in the compare dialog and picked the IDE side, so
    # refusing them would be refusing the answer they just gave. What
    # switches the guard off is that perform_export builds a context with no
    # sync cache in it; this test is what stops somebody adding one.
    edit_on_disk(a_synced_project.file,
                 u"FUNCTION_BLOCK MC_Main\nEND_VAR\nmine := 1;\n")
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    result = a_synced_project.export_from_dialog()

    assert u"theirs := 2;" in a_synced_project.file.read_text(encoding="utf-8")
    assert result["ok"] is True

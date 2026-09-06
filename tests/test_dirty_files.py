# -*- coding: utf-8 -*-
"""An edit on disk that was never imported must survive the next export.

Disk is the source of truth (SPEC 5, PRINCIPLES 5), so the one thing export
must never do is quietly write over somebody's work. Until now it did: the
sync cache noticed the file had changed, used that only to decide it could
not take the fast path, and then overwrote it anyway (SPEC 6.1).
"""
import sys
import types

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
    """One POU exported once, and the ways to look at it or export it again."""

    def __init__(self, pou, path, sync, export, look,
                 import_answering_no, compare_engine):
        self.pou = pou
        self.file = path
        self.sync = sync
        self.export = export
        self.look = look
        self.import_answering_no = import_answering_no
        self.compare_engine = compare_engine


@pytest.fixture
def a_synced_project(load_engine, monkeypatch, tmp_path):
    """A project whose sync cache knows what the disk held at the last sync."""
    for dep in ("codesys_constants", "codesys_utils", "codesys_managers",
                "codesys_compare_engine"):
        load_engine(dep)
    export = load_engine("entry_export")

    sync = tmp_path / "sync"
    sync.mkdir()
    version = sys.modules["engine.codesys_constants"].SCRIPT_VERSION
    pou = Pou()
    project = Project({"cds-sync-folder": str(sync),
                       "cds-sync-version": version},
                      [pou], str(tmp_path / "Fake.project"))
    projects = Projects(project)
    monkeypatch.setattr(export, "projects", projects, raising=False)
    monkeypatch.setattr(export, "system", DeafSystem(), raising=False)

    run = lambda: export.export_project(str(sync), projects)
    first = run()
    assert first["ok"] is True, first["summary"]
    written = [p for p in sync.rglob("*.st")]
    assert len(written) == 1, written

    engine_module = sys.modules["engine.codesys_compare_engine"]
    look = lambda: engine_module.find_all_changes(str(sync), projects,
                                                  export_xml=False)

    importer = load_engine("entry_import")
    monkeypatch.setattr(importer, "projects", projects, raising=False)
    monkeypatch.setattr(importer, "system", DeafSystem(), raising=False)
    said_no = types.ModuleType("engine.codesys_ui")
    said_no.ask_yes_no = lambda title, message: False
    said_no.ask_yes_no_cancel = lambda title, message: False
    monkeypatch.setitem(sys.modules, "engine.codesys_ui", said_no)
    refuse = lambda: importer.import_project(projects)

    return Synced(pou, written[0], sync, run, look, refuse,
                  engine_module)


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


def test_the_export_does_not_print_a_count_nothing_ever_counts(
        a_synced_project, capsys):
    # Suggestion 7. "Skipped: 0 objects (no textual content)" was printed by
    # every export ever run: nothing has incremented that counter since the
    # line was written. A number that is always zero is not a measurement,
    # it is a reader wondering which objects it means.
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    a_synced_project.export()

    assert "Skipped:" not in capsys.readouterr().out


def test_a_compare_between_the_edit_and_the_export_does_not_lose_the_guard(
        a_synced_project):
    # compare only looks, so it must not throw away what the guard reads.
    # It used to rewrite sync_cache.json with only the objects it found
    # unchanged, which dropped the entry for the very file that differed --
    # and without an entry the guard has nothing to compare against and the
    # next export writes straight over the edit.
    mine = u"FUNCTION_BLOCK MC_Main\nEND_VAR\n// === IMPLEMENTATION ===\nmine := 1;\n"
    edit_on_disk(a_synced_project.file, mine)
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    a_synced_project.look()
    result = a_synced_project.export()

    assert a_synced_project.file.read_text(encoding="utf-8") == mine
    assert result["data"]["pending_import"] == ["MC_Main.st"]


def test_an_import_nobody_confirmed_does_not_lose_the_guard(a_synced_project):
    # import runs the same compare before it opens the Confirm Import
    # dialog, so answering No -- or getting NeedsInput headlessly -- left
    # the cache in the same gutted state as a bare compare.
    mine = u"FUNCTION_BLOCK MC_Main\nEND_VAR\n// === IMPLEMENTATION ===\nmine := 1;\n"
    edit_on_disk(a_synced_project.file, mine)
    a_synced_project.pou.textual_implementation.text = u"theirs := 2;\n"

    refused = a_synced_project.import_answering_no()
    assert refused["ok"] is False

    result = a_synced_project.export()

    assert a_synced_project.file.read_text(encoding="utf-8") == mine
    assert result["data"]["pending_import"] == ["MC_Main.st"]


def test_an_object_compare_could_not_read_keeps_its_cache_entry(
        a_synced_project, monkeypatch):
    # An object whose plugin is missing lands in the unhandled register and
    # never reaches Pass 2, so it has no fresh entry to write. Dropping the
    # old one disarms the guard for a file nobody even looked at.
    mine = u"FUNCTION_BLOCK MC_Main\nEND_VAR\n// === IMPLEMENTATION ===\nmine := 1;\n"
    edit_on_disk(a_synced_project.file, mine)

    def unreadable(obj, *args, **kwargs):
        raise RuntimeError("plugin missing")

    monkeypatch.setattr(a_synced_project.compare_engine, "classify_object",
                        unreadable)
    a_synced_project.look()
    result = a_synced_project.export()

    assert a_synced_project.file.read_text(encoding="utf-8") == mine
    assert result["data"]["pending_import"] == ["MC_Main.st"]

# -*- coding: utf-8 -*-
"""Tests for cds.ide.config: the cds-sync-* properties from outside the IDE."""
import os
import sys
import types

import pytest

from cds.ide import config, entries
from tests.test_watcher import make_globals


@pytest.fixture
def ide():
    return make_globals()


def props(ide):
    return ide["projects"].primary.props


def run(ide, **args):
    return config.run(ide, args)


# --- reading ---------------------------------------------------------------

def test_reading_one_property_reports_its_value(ide):
    props(ide)["cds-sync-debug"] = "true"
    result = run(ide, key="cds-sync-debug")
    assert result["ok"] is True
    assert result["data"] == {"cds-sync-debug": "true"}


def test_a_property_that_was_never_set_is_an_answer_not_a_failure(ide):
    # Absence is what the caller asked about, the same way an empty `list` is
    # an answer rather than an error.
    result = run(ide, key="cds-sync-debug")
    assert result["ok"] is True
    assert result["data"] == {"cds-sync-debug": None}
    assert "not set" in result["summary"]


def test_reading_everything_leaves_out_what_has_no_value(ide):
    # "" and "never set" are different, and reporting both as "" hides which
    # one this is.
    props(ide)["cds-sync-folder"] = "./sync"
    result = run(ide)
    assert result["data"] == {"cds-sync-folder": "./sync"}
    assert "1 of" in result["summary"]


def test_the_plc_permission_can_be_read(ide):
    props(ide)["cds-sync-plc"] = "connect"
    assert run(ide, key="cds-sync-plc")["data"] == {"cds-sync-plc": "connect"}


# --- writing ---------------------------------------------------------------

def test_setting_a_property_writes_it_and_saves(ide):
    result = run(ide, key="cds-sync-debug", value="true")
    assert result["ok"] is True
    assert props(ide)["cds-sync-debug"] == "true"
    # Unsaved, the property is gone the moment the project closes, and
    # headless nobody closes it politely.
    assert ide["projects"].primary.saves == 1


def test_an_empty_value_is_a_write_not_a_read(ide):
    props(ide)["cds-sync-backup-name"] = "old"
    run(ide, key="cds-sync-backup-name", value="")
    assert props(ide)["cds-sync-backup-name"] == ""


def test_the_plc_permission_cannot_be_written(ide):
    # It means "a person decided this in the IDE"; a CLI that can write it
    # erases that meaning (SPEC 6.5).
    result = run(ide, key="cds-sync-plc", value="download")
    assert result["ok"] is False and "SPEC 6.5" in result["summary"]
    assert "cds-sync-plc" not in props(ide)


def test_an_unknown_property_is_refused_and_the_known_ones_named(ide):
    # Writing it would leave a property nothing ever reads, which is exactly
    # the silent failure D13 rules out.
    result = run(ide, key="cds-sync-dbeug", value="true")
    assert result["ok"] is False
    assert "cds-sync-debug" in result["summary"]
    assert props(ide) == {}


def test_reading_an_unknown_property_is_refused_too(ide):
    assert run(ide, key="cds-sync-nonsense")["ok"] is False


def test_a_project_that_will_not_save_says_so_rather_than_claiming_success(ide):
    def refuse():
        raise RuntimeError("Delta 1.10 after a storage-format upgrade")
    ide["projects"].primary.save = refuse
    result = run(ide, key="cds-sync-debug", value="true")
    assert result["ok"] is True                      # the property is written
    assert "could not be saved" in result["summary"]  # and it will not last


# --- nothing open ----------------------------------------------------------

def test_with_no_project_open_there_is_nothing_to_read(ide):
    ide["projects"].primary = None
    result = run(ide, key="cds-sync-debug")
    assert result["ok"] is False and "no project" in result["summary"]


# --- setting the folder is more than writing the property (SPEC 6.7) -------

@pytest.fixture
def fake_codesys_ui(monkeypatch):
    """The dialog module, which needs clr and so cannot be the real one.

    Only entries.run's engine tail needs it: cds/ide/silent.py refuses to
    press a body whose dialogs it cannot take over, and it takes them over
    by name on this module. Nothing below opens one.
    """
    module = types.ModuleType("engine.codesys_ui")

    def opened(*args, **kwargs):
        raise AssertionError("a real dialog was opened")

    for name in ("ask_yes_no", "ask_yes_no_cancel", "show_sync_folder_dialog"):
        setattr(module, name, opened)
    sys.modules["engine.codesys_ui"] = module
    # entries.run() empties sys.modules of the engine before pressing a body
    # so a watcher picks up edited engine code without the IDE restarting.
    # Right inside an IDE, wrong here: it would take this stand-in with it,
    # and the real module needs clr.
    monkeypatch.setattr(entries, "forget_engine", lambda: None)
    yield module
    sys.modules.pop("engine.codesys_ui", None)


def set_folder(tmp_path, folder, monkeypatch):
    """`cdsint config set cds-sync-folder=...` the way both forms reach it.

    Through entries.run, not config.run: the engine tail that finishes the
    job hangs off entries, because cds/ide may not import the engine.

    `projects` goes onto __main__ because that is where CODESYS puts it, and
    codesys_utils.get_project_prop() looks for it there.
    """
    import __main__
    ide = make_globals(str(tmp_path / "App.project"))
    monkeypatch.setattr(__main__, "projects", ide["projects"], raising=False)
    outcome = entries.run(ide, "config",
                          {"key": "cds-sync-folder", "value": folder})
    return ide, outcome


def test_setting_the_folder_stamps_the_machine_and_the_version(
        tmp_path, monkeypatch, fake_codesys_ui):
    # The dialog writes all three. A project set up from the CLI used to get
    # only the first, which left load_base_dir and
    # check_version_compatibility with nothing to compare against.
    wanted = str(tmp_path / "sync")

    ide, outcome = set_folder(tmp_path, wanted, monkeypatch)

    assert outcome.ok(), outcome.error_text()
    # Verbatim: `config set` writes the value it was given. Only the dialog
    # rewrites a browsed path into its relative form, because there nobody
    # typed it.
    assert props(ide)["cds-sync-folder"] == wanted
    assert props(ide)["cds-sync-pc"]
    assert props(ide)["cds-sync-version"]


def test_setting_the_folder_creates_it_with_its_git_rules(
        tmp_path, monkeypatch, fake_codesys_ui):
    _ide, _outcome = set_folder(tmp_path, str(tmp_path / "sync"), monkeypatch)

    assert (tmp_path / "sync").is_dir()
    assert (tmp_path / "sync" / ".gitignore").exists()
    assert (tmp_path / "sync" / ".gitattributes").exists()


def test_setting_any_other_property_does_not_touch_the_folder(
        tmp_path, fake_codesys_ui):
    ide = make_globals(str(tmp_path / "App.project"))

    entries.run(ide, "config", {"key": "cds-sync-debug", "value": "true"})

    assert "cds-sync-pc" not in props(ide)
    assert "cds-sync-version" not in props(ide)

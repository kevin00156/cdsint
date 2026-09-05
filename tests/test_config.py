# -*- coding: utf-8 -*-
"""Tests for cds.ide.config: the cds-sync-* properties from outside the IDE."""
import pytest

from cds.ide import config
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

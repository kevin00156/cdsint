# -*- coding: utf-8 -*-
"""Tests for cdsint.reminders: what is printed on stderr, and how often.

No test reaches GitHub or scans Program Files: latest_tag and
link.unlinked are replaced wherever they would be called.
"""
import io
import os

import pytest

from cdsint import cli, link, release, reminders
from engine.codesys_constants import SCRIPT_VERSION

DAY = reminders.CHECK_EVERY_S


def bumped():
    major, minor, patch = release.parse(release.tag_of(SCRIPT_VERSION))
    return "v%d.%d.%d" % (major, minor, patch + 1)


@pytest.fixture
def downloaded(tmp_path, monkeypatch):
    """This process, as if it ran from the body setup.ps1 installed."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    os.makedirs(release.body_root())
    monkeypatch.setattr(release, "REPO_ROOT", release.body_root())
    monkeypatch.setattr(link, "unlinked", lambda: [])
    return tmp_path


def asked(monkeypatch, answer):
    """Replace the query with one that counts its calls and gives answer."""
    calls = []

    def latest_tag(timeout):
        calls.append(timeout)
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(release, "latest_tag", latest_tag)
    return calls


def test_the_body_setup_installed_counts_as_downloaded(downloaded):
    assert release.is_downloaded()


def test_a_newer_release_is_named(downloaded, monkeypatch):
    asked(monkeypatch, bumped())
    assert reminders.due(DAY) == [reminders.release_line(bumped())]
    assert "cdsint update" in reminders.release_line(bumped())


def test_the_same_release_is_not(downloaded, monkeypatch):
    asked(monkeypatch, release.tag_of(SCRIPT_VERSION))
    assert reminders.due(DAY) == []


def test_github_is_asked_once_a_day(downloaded, monkeypatch):
    calls = asked(monkeypatch, bumped())
    for now in (DAY, DAY + 1, 2 * DAY - 1):
        assert reminders.due(now) == [reminders.release_line(bumped())]
    assert len(calls) == 1
    reminders.due(2 * DAY)
    assert len(calls) == 2


def test_a_failed_query_counts_as_the_days_check(downloaded, monkeypatch):
    calls = asked(monkeypatch, OSError("offline"))
    assert reminders.due(DAY) == []
    assert reminders.due(DAY + 1) == []
    assert len(calls) == 1


def test_a_failed_query_keeps_the_last_answer(downloaded, monkeypatch):
    asked(monkeypatch, bumped())
    reminders.due(DAY)
    asked(monkeypatch, OSError("offline"))
    assert reminders.due(3 * DAY) == [reminders.release_line(bumped())]


def test_a_missing_menu_is_named_on_the_day_it_is_checked(downloaded,
                                                         monkeypatch):
    asked(monkeypatch, release.tag_of(SCRIPT_VERSION))
    missing = [("CODESYS V3.5 SP21", False)]
    monkeypatch.setattr(link, "unlinked", lambda: missing)
    assert reminders.due(DAY) == [reminders.menu_line(missing)]
    assert reminders.due(DAY + 1) == []


def test_a_menu_under_program_files_says_elevated():
    line = reminders.menu_line([("Delta DIADesigner-AX 1.10", True),
                                ("CODESYS V3.5 SP21", False)])
    assert "Delta DIADesigner-AX 1.10, CODESYS V3.5 SP21" in line
    assert "cdsint link" in line and "elevated" in line
    assert "elevated" not in reminders.menu_line([("CODESYS", False)])


def test_the_reminder_goes_to_stderr(downloaded, monkeypatch, capsys):
    asked(monkeypatch, bumped())
    reminders.remind("installs", False)
    out, err = capsys.readouterr()
    assert out == ""
    assert bumped() in err


@pytest.mark.parametrize("command, want_json", [("installs", True),
                                                ("update", False),
                                                ("link", False)])
def test_quiet_under_json_and_after_update_or_link(downloaded, monkeypatch,
                                                   capsys, command,
                                                   want_json):
    calls = asked(monkeypatch, bumped())
    reminders.remind(command, want_json)
    assert capsys.readouterr() == ("", "")
    assert calls == []


def test_a_clone_never_asks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = asked(monkeypatch, bumped())
    reminders.remind("installs", False)
    assert calls == []
    assert capsys.readouterr() == ("", "")


def test_a_broken_state_file_is_asked_again(downloaded, monkeypatch):
    with io.open(os.path.join(release.home(), "update_check.json"), "w",
                 encoding="utf-8") as handle:
        handle.write(u"{not json")
    asked(monkeypatch, bumped())
    assert reminders.due(DAY) == [reminders.release_line(bumped())]


def test_an_unwritable_state_file_does_not_fail_the_command(
        downloaded, monkeypatch, capsys):
    os.makedirs(os.path.join(release.home(), "update_check.json"))
    asked(monkeypatch, bumped())
    reminders.remind("installs", False)
    assert capsys.readouterr() == ("", "")


def test_every_command_ends_with_the_reminder(downloaded, monkeypatch,
                                              capsys):
    asked(monkeypatch, bumped())
    monkeypatch.setattr(cli.installs, "find", lambda: [])
    assert cli.main(["installs"]) == 0
    assert bumped() in capsys.readouterr().err

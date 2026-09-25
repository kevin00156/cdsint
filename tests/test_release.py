# -*- coding: utf-8 -*-
"""Tests for cdsint.release: when a newer release is named, and when not.

No test reaches GitHub. latest_tag is replaced wherever it would be called,
and the one test that lets the real one run points it at a closed port.
"""
import io
import json
import os
import re

import pytest

from cdsint import cli, release
from engine.codesys_constants import SCRIPT_VERSION

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = release.CHECK_EVERY_S


def bumped():
    major, minor, patch = release.parse(release.tag_of(SCRIPT_VERSION))
    return "v%d.%d.%d" % (major, minor, patch + 1)


@pytest.fixture
def downloaded(tmp_path, monkeypatch):
    """This process, as if it ran from the body setup.ps1 installed."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    os.makedirs(release.body_root())
    monkeypatch.setattr(release, "REPO_ROOT", release.body_root())
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


def test_versions_compare_as_numbers_not_text():
    assert release.parse("v0.10.0") > release.parse("v0.9.0")


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1", "v0.1.0-rc1", "main"])
def test_parse_refuses_what_is_not_a_release_tag(tag):
    with pytest.raises(ValueError):
        release.parse(tag)


def test_a_clone_is_not_the_downloaded_body(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert not release.is_downloaded()


def test_off_windows_nothing_is_the_downloaded_body(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert release.body_root() == ""
    assert not release.is_downloaded()


def test_a_newer_release_is_named(downloaded, monkeypatch):
    asked(monkeypatch, bumped())
    assert release.newer_release(DAY) == bumped()


def test_the_same_release_is_not(downloaded, monkeypatch):
    asked(monkeypatch, release.tag_of(SCRIPT_VERSION))
    assert release.newer_release(DAY) is None


def test_github_is_asked_once_a_day(downloaded, monkeypatch):
    calls = asked(monkeypatch, bumped())
    for now in (DAY, DAY + 1, 2 * DAY - 1):
        assert release.newer_release(now) == bumped()
    assert len(calls) == 1
    release.newer_release(2 * DAY)
    assert len(calls) == 2


def test_a_failed_query_counts_as_the_days_check(downloaded, monkeypatch):
    calls = asked(monkeypatch, OSError("offline"))
    assert release.newer_release(DAY) is None
    assert release.newer_release(DAY + 1) is None
    assert len(calls) == 1


def test_a_failed_query_keeps_the_last_answer(downloaded, monkeypatch):
    asked(monkeypatch, bumped())
    release.newer_release(DAY)
    asked(monkeypatch, OSError("offline"))
    assert release.newer_release(3 * DAY) == bumped()


def test_the_reminder_goes_to_stderr(downloaded, monkeypatch, capsys):
    asked(monkeypatch, bumped())
    release.remind("installs", False)
    out, err = capsys.readouterr()
    assert out == ""
    assert bumped() in err and "cdsint update" in err


@pytest.mark.parametrize("command, want_json", [("installs", True),
                                                ("update", False)])
def test_no_reminder_under_json_or_after_update(downloaded, monkeypatch,
                                                capsys, command, want_json):
    calls = asked(monkeypatch, bumped())
    release.remind(command, want_json)
    assert capsys.readouterr() == ("", "")
    assert calls == []


def test_a_clone_never_asks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = asked(monkeypatch, bumped())
    release.remind("installs", False)
    assert calls == []
    assert capsys.readouterr() == ("", "")


def test_a_broken_state_file_is_asked_again(downloaded, monkeypatch):
    with io.open(os.path.join(release.home(), "update_check.json"), "w",
                 encoding="utf-8") as handle:
        handle.write(u"{not json")
    asked(monkeypatch, bumped())
    assert release.newer_release(DAY) == bumped()


def test_an_unwritable_state_file_does_not_fail_the_command(
        downloaded, monkeypatch, capsys):
    os.makedirs(os.path.join(release.home(), "update_check.json"))
    asked(monkeypatch, bumped())
    release.remind("installs", False)
    assert capsys.readouterr() == ("", "")


def test_an_unreachable_github_is_an_oserror(monkeypatch):
    monkeypatch.setattr(release, "LATEST_URL", "http://127.0.0.1:9/")
    with pytest.raises(OSError):
        release.latest_tag(0.5)


def test_every_command_ends_with_the_reminder(downloaded, monkeypatch,
                                              capsys):
    asked(monkeypatch, bumped())
    monkeypatch.setattr(cli.installs, "find", lambda: [])
    assert cli.main(["installs"]) == 0
    assert bumped() in capsys.readouterr().err


def test_setup_ps1_installs_where_release_looks():
    """The body's path and the query are written twice, once per language.

    setup.ps1 runs before any Python of ours is installed, so it cannot ask;
    this is what keeps the two copies the same.
    """
    with io.open(os.path.join(REPO_ROOT, "irm", "setup.ps1"),
                 encoding="utf-8") as handle:
        script = handle.read()
    assert '$LatestUrl = "%s"' % release.LATEST_URL in script
    assert re.search(r'\$root = Join-Path \$appDir "body"', script)
    assert re.search(r'\$appDir = Join-Path \$env:LOCALAPPDATA "cdsint"',
                     script)

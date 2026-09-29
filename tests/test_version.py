# -*- coding: utf-8 -*-
"""Tests for `cdsint version` and `cdsint --version`."""
import json

import pytest

from cds.core.exits import EXIT_OK
from cdsint import cli, release
from engine.codesys_constants import SCRIPT_VERSION


def test_version_names_this_release_and_where_it_runs(capsys):
    assert cli.main(["version", "--json"]) == EXIT_OK
    about = json.loads(capsys.readouterr().out)
    assert about["version"] == SCRIPT_VERSION
    assert about["body"] == release.REPO_ROOT
    assert about["downloaded"] == release.is_downloaded()
    assert set(about) == {"version", "body", "downloaded", "python", "os"}


def test_a_clone_says_it_can_be_ahead_of_its_number(tmp_path, monkeypatch,
                                                    capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    cli.main(["version"])
    assert "ahead of this number" in capsys.readouterr().out


def test_the_downloaded_body_says_setup_installed_it(tmp_path, monkeypatch,
                                                     capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(release, "REPO_ROOT", release.body_root())
    cli.main(["version"])
    out = capsys.readouterr().out
    assert "installed by irm/setup.ps1" in out
    assert "ahead" not in out


def test_version_never_reaches_the_network(monkeypatch, capsys):
    def refuse(timeout):
        raise AssertionError("asked GitHub")
    monkeypatch.setattr(release, "latest_tag", refuse)
    monkeypatch.setattr(release, "is_downloaded", lambda: False)
    assert cli.main(["version"]) == EXIT_OK


def test_dash_dash_version_is_the_first_line_of_version(capsys):
    cli.main(["version"])
    first = capsys.readouterr().out.splitlines()[0]
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--version"])
    assert stopped.value.code == 0
    printed = capsys.readouterr().out.strip()
    assert printed == first == "cdsint " + SCRIPT_VERSION


# -*- coding: utf-8 -*-
"""Tests for cdsint.release: tags, and which install counts as downloaded.

No test reaches GitHub; the one that lets latest_tag run points it at a
closed port.
"""
import io
import os
import re

import pytest

from cdsint import release

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def test_an_unreachable_github_is_an_oserror(monkeypatch):
    monkeypatch.setattr(release, "LATEST_URL", "http://127.0.0.1:9/")
    with pytest.raises(OSError):
        release.latest_tag(0.5)


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

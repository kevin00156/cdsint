# -*- coding: utf-8 -*-
"""Tests for cdsint.update: what it refuses, and the swap itself.

The download is replaced by a zip built here, shaped like a GitHub archive:
one directory at the top, the tree under it.
"""
import io
import json
import os
import subprocess
import zipfile

import pytest

from cds.core.exits import EXIT_FAILED
from cdsint import cli, link, release, update
from cdsint.exits import Failure
from engine.codesys_constants import SCRIPT_VERSION

NEWER = "v99.0.0"


def tree(root, marker):
    """A body with a stub folder, and one file saying which body it is."""
    os.makedirs(os.path.join(root, "stub"))
    with io.open(os.path.join(root, "which"), "w", encoding="utf-8") as f:
        f.write(marker)


def which(body):
    with io.open(os.path.join(body, "which"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A downloaded body holding "old", and a release holding "new"."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    body = release.body_root()
    tree(body, "old")
    monkeypatch.setattr(release, "REPO_ROOT", body)

    def download(tag, staging):
        os.makedirs(staging)
        archive = os.path.join(staging, tag + ".zip")
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("cdsint-99.0.0/which", "new")
            bundle.writestr("cdsint-99.0.0/stub/Project_watch.py", "")
        return archive
    monkeypatch.setattr(update, "_download", download)
    monkeypatch.setattr(release, "latest_tag", lambda timeout: NEWER)
    monkeypatch.setattr(update, "running_ides", lambda: [])
    reinstalled = []
    monkeypatch.setattr(update, "_reinstall", reinstalled.append)
    monkeypatch.setattr(link, "link_all", lambda: [])
    return body, reinstalled


def test_the_new_release_replaces_the_body(machine):
    body, _ = machine
    assert update.replace_body(NEWER, body) is None
    assert which(body) == "new"
    assert not os.path.exists(body + ".new")
    assert not os.path.exists(body + ".old")


def test_state_beside_the_body_survives(machine):
    body, _ = machine
    instances = os.path.join(release.home(), "instances")
    os.makedirs(instances)
    update.replace_body(NEWER, body)
    assert os.path.isdir(instances)


def test_a_failed_swap_puts_the_old_body_back(machine, monkeypatch):
    body, _ = machine
    real_rename = os.rename

    def rename(src, dst):
        if dst == body:
            if src.endswith(".old"):
                return real_rename(src, dst)
            raise PermissionError("in use")
        return real_rename(src, dst)
    monkeypatch.setattr(update.os, "rename", rename)
    with pytest.raises(Failure) as caught:
        update._replace(NEWER, body)
    assert "still at" in str(caught.value)
    assert which(body) == "old"


def test_a_failed_download_leaves_the_old_body_alone(machine, monkeypatch):
    body, _ = machine

    def download(tag, staging):
        raise OSError("connection reset")
    monkeypatch.setattr(update, "_download", download)
    with pytest.raises(Failure):
        update._replace(NEWER, body)
    assert which(body) == "old"


def test_leftovers_of_an_interrupted_run_are_cleared(machine):
    body, _ = machine
    tree(body + ".new", "half")
    tree(body + ".old", "older")
    update.replace_body(NEWER, body)
    assert which(body) == "new"
    assert not os.path.exists(body + ".old")


def test_update_through_the_cli(machine, capsys):
    body, reinstalled = machine
    assert cli.main(["update"]) == 0
    assert which(body) == "new"
    assert reinstalled == [body]
    assert NEWER in capsys.readouterr().out


def test_update_under_json(machine, capsys):
    assert cli.main(["update", "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record == {"from": release.tag_of(SCRIPT_VERSION),
                      "latest": NEWER, "updated": True, "left_behind": None,
                      "menus": []}


def test_nothing_to_do_on_the_newest_release(machine, monkeypatch, capsys):
    body, reinstalled = machine
    monkeypatch.setattr(release, "latest_tag",
                        lambda timeout: release.tag_of(SCRIPT_VERSION))
    assert cli.main(["update"]) == 0
    assert which(body) == "old"
    assert reinstalled == []
    assert "newest release" in capsys.readouterr().out


def test_an_ide_added_since_is_linked_even_without_a_release(
        machine, monkeypatch, capsys):
    monkeypatch.setattr(release, "latest_tag",
                        lambda timeout: release.tag_of(SCRIPT_VERSION))
    monkeypatch.setattr(link, "link_all", lambda: [
        {"ide": "Lenze 4.0", "state": link.LINKED, "detail": "X"},
        {"ide": "SP21", "state": link.ALREADY, "detail": "Y"}])
    assert cli.main(["update"]) == 0
    out = capsys.readouterr().out
    assert "Lenze 4.0" in out and "SP21" not in out


def test_refused_while_an_ide_runs(machine, monkeypatch, capsys):
    body, _ = machine
    monkeypatch.setattr(update, "running_ides", lambda: ["CODESYS.exe"])
    assert cli.main(["update"]) == EXIT_FAILED
    assert "CODESYS.exe" in capsys.readouterr().err
    assert which(body) == "old"


def test_refused_on_a_clone(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert cli.main(["update"]) == EXIT_FAILED
    assert "git pull" in capsys.readouterr().err


def test_github_unreachable_is_said(machine, monkeypatch, capsys):
    def latest_tag(timeout):
        raise OSError("offline")
    monkeypatch.setattr(release, "latest_tag", latest_tag)
    assert cli.main(["update"]) == EXIT_FAILED
    assert "offline" in capsys.readouterr().err


def test_running_ides_reads_tasklist(monkeypatch):
    listing = ('"System","4","Services","0","144 K"\n'
               '"CODESYS.exe","100","Console","1","900,000 K"\n'
               '"DIADesigner-AX.exe","200","Console","1","800,000 K"\n'
               '"CODESYS.exe","300","Console","1","900,000 K"\n')

    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=listing)
    monkeypatch.setattr(update.subprocess, "run", run)
    assert update.running_ides() == ["CODESYS.exe", "DIADesigner-AX.exe"]

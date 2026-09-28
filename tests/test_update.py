# -*- coding: utf-8 -*-
"""Tests for cdsint.update: what it refuses, and the swap itself.

The download is replaced by a zip built here, shaped like the release job's
archive -- one directory at the top, the tree under it -- and published with
its SHA-256 the way sha256sum writes it. The new body's `cdsint link` is a
subprocess, stood in for everywhere but the tests of it.
"""
import hashlib
import http.client
import io
import json
import os
import subprocess
import urllib.error
import zipfile

import pytest

from cds.core.exits import EXIT_FAILED
from cdsint import cli, link, release, update
from cdsint.exits import Failure
from engine.codesys_constants import SCRIPT_VERSION

NEWER = "v99.0.0"

# The real ones, kept before the fixture below stands them in.
FETCH = update._fetch
RELINK = update.relink


def tree(root, marker):
    """A body with a stub folder, and one file saying which body it is."""
    os.makedirs(os.path.join(root, "stub"))
    with io.open(os.path.join(root, "which"), "w", encoding="utf-8") as f:
        f.write(marker)


def which(body):
    with io.open(os.path.join(body, "which"), encoding="utf-8") as f:
        return f.read()


def archive_of(files):
    """A zip holding files, by name, in memory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, text in files.items():
            bundle.writestr(name, text)
    return buffer.getvalue()


def publish(tag, archive):
    """What GitHub serves for a release: the archive and sha256sum's line."""
    url = release.asset_url(tag)
    line = "%s  %s\n" % (hashlib.sha256(archive).hexdigest(),
                         release.ASSET % tag)
    return {url: archive, url + ".sha256": line.encode("ascii")}


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A downloaded body holding "old", and a release holding "new"."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    body = release.body_root()
    tree(body, "old")
    monkeypatch.setattr(release, "REPO_ROOT", body)

    published = publish(NEWER, archive_of({
        "cdsint-99.0.0/which": "new",
        "cdsint-99.0.0/stub/Project_watch.py": ""}))
    monkeypatch.setattr(update, "_fetch", lambda url: published[url])
    monkeypatch.setattr(release, "latest_tag", lambda timeout: NEWER)
    monkeypatch.setattr(update, "running_ides", lambda: [])
    reinstalled = []

    def reinstall(body):
        reinstalled.append(body)
    monkeypatch.setattr(update, "_reinstall", reinstall)
    monkeypatch.setattr(update, "relink", lambda body: [])
    return body, reinstalled, published


def test_the_new_release_replaces_the_body(machine):
    body, _, _ = machine
    assert update.replace_body(NEWER, body) == []
    assert which(body) == "new"
    assert not os.path.exists(body + ".new")
    assert not os.path.exists(body + ".old")


def test_state_beside_the_body_survives(machine):
    body, _, _ = machine
    instances = os.path.join(release.home(), "instances")
    os.makedirs(instances)
    update.replace_body(NEWER, body)
    assert os.path.isdir(instances)


def test_a_failed_swap_puts_the_old_body_back(machine, monkeypatch):
    body, _, _ = machine
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
    body, _, _ = machine

    def download(tag, staging):
        raise OSError("connection reset")
    monkeypatch.setattr(update, "_download", download)
    with pytest.raises(Failure):
        update._replace(NEWER, body)
    assert which(body) == "old"


@pytest.mark.parametrize("cut", [
    http.client.IncompleteRead(b"PK", 4096),
    zipfile.zlib.error("invalid stored block lengths")])
def test_a_download_cut_or_corrupt_is_said_not_a_traceback(machine,
                                                           monkeypatch, cut):
    body, _, _ = machine

    def download(tag, staging):
        raise cut
    monkeypatch.setattr(update, "_download", download)
    with pytest.raises(Failure) as caught:
        update._replace(NEWER, body)
    assert "still at" in str(caught.value)
    assert which(body) == "old"


def test_a_staging_folder_that_will_not_go_is_a_leftover(machine,
                                                         monkeypatch):
    """The swap is done by then; the update stands and the folder is named."""
    body, _, _ = machine
    real_rmtree = update.shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if path == body + ".new" and os.path.exists(body):
            raise PermissionError("held by a virus scanner")
        return real_rmtree(path, *args, **kwargs)
    monkeypatch.setattr(update.shutil, "rmtree", rmtree)
    assert update.replace_body(NEWER, body) == [body + ".new"]
    assert which(body) == "new"


def test_a_pip_failure_still_links_the_menus(machine, monkeypatch, capsys):
    """Without link the new tree has no stub\\body.path: every menu breaks."""
    body, _, _ = machine
    linked = []
    monkeypatch.setattr(update, "_reinstall", lambda body: "pip said no")
    monkeypatch.setattr(update, "relink", lambda body: linked.append(1) or [])
    assert cli.main(["update"]) == 0
    assert linked == [1]
    assert which(body) == "new"
    assert "pip said no" in capsys.readouterr().err


def test_the_archive_is_the_release_asset_ci_published():
    assert release.asset_url("v1.2.3") == (
        "https://github.com/kevin00156/cdsint/releases/download/v1.2.3/"
        "cdsint-v1.2.3.zip")


@pytest.mark.parametrize("checksum", [
    b"0" * 64 + b"  cdsint-v99.0.0.zip\n", b"", b"\xff\xfe"])
def test_an_archive_its_checksum_does_not_vouch_for_is_refused(
        machine, checksum):
    body, _, published = machine
    published[release.asset_url(NEWER) + ".sha256"] = checksum
    with pytest.raises(Failure) as caught:
        update._replace(NEWER, body)
    assert "SHA-256" in str(caught.value) and "still at" in str(caught.value)
    assert which(body) == "old"
    assert not os.path.exists(body + ".new")


def test_a_release_without_a_checksum_is_refused(machine, monkeypatch):
    """A 404 on the .sha256 names that file, and installs nothing."""
    body, _, published = machine
    missing = release.asset_url(NEWER) + ".sha256"

    def urlopen(url, timeout):
        if url == missing:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return io.BytesIO(published[url])
    monkeypatch.setattr(update, "_fetch", FETCH)
    monkeypatch.setattr(update.urllib.request, "urlopen", urlopen)
    with pytest.raises(Failure) as caught:
        update._replace(NEWER, body)
    assert missing + ": HTTP Error 404" in str(caught.value)
    assert which(body) == "old"


def test_the_menus_are_linked_by_the_new_body_not_this_process(
        machine, monkeypatch, capsys):
    """This process still holds the old release's link.py after the swap."""
    body, _, _ = machine
    monkeypatch.setattr(update, "relink", RELINK)
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(
            [{"ide": "SP21", "state": link.LINKED, "detail": "X"}]),
            stderr="")
    monkeypatch.setattr(update.subprocess, "run", run)
    assert cli.main(["update", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["menus"] == [
        {"ide": "SP21", "state": link.LINKED, "detail": "X"}]
    (argv, kwargs), = calls
    assert argv[1:] == ["-m", "cdsint.cli", "link", "--json"]
    assert kwargs["cwd"] == body
    assert kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0] == body


def test_a_link_that_did_not_answer_is_a_failed_row(machine, monkeypatch):
    """Never a silent success: the new tree may have no body.path yet."""
    body, _, _ = machine

    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="",
                                           stderr="ImportError: no engine")
    monkeypatch.setattr(update.subprocess, "run", run)
    rows = RELINK(body)
    assert [row["state"] for row in rows] == [link.FAILED]
    assert "ImportError: no engine" in rows[0]["detail"]


def test_leftovers_of_an_interrupted_run_are_cleared(machine):
    body, _, _ = machine
    tree(body + ".new", "half")
    tree(body + ".old", "older")
    update.replace_body(NEWER, body)
    assert which(body) == "new"
    assert not os.path.exists(body + ".old")


def test_update_through_the_cli(machine, capsys):
    body, reinstalled, _ = machine
    assert cli.main(["update"]) == 0
    assert which(body) == "new"
    assert reinstalled == [body]
    assert NEWER in capsys.readouterr().out


def test_update_under_json(machine, capsys):
    assert cli.main(["update", "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record == {"from": release.tag_of(SCRIPT_VERSION),
                      "latest": NEWER, "updated": True, "left_behind": [],
                      "pip": None, "menus": []}


def test_nothing_to_do_on_the_newest_release(machine, monkeypatch, capsys):
    body, reinstalled, _ = machine
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
    monkeypatch.setattr(update, "relink", lambda body: [
        {"ide": "Lenze 4.0", "state": link.LINKED, "detail": "X"},
        {"ide": "SP21", "state": link.ALREADY, "detail": "Y"}])
    assert cli.main(["update"]) == 0
    out = capsys.readouterr().out
    assert "Lenze 4.0" in out and "SP21" not in out


def test_refused_while_an_ide_runs(machine, monkeypatch, capsys):
    body, _, _ = machine
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

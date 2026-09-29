# -*- coding: utf-8 -*-
"""Tests for irm/setup.ps1, by reading it: CI has no PowerShell to run it in.

Each test pins down one property whose loss has cost somebody an install,
in a form a text search can check. What only running it can show -- that
the swap works on NTFS, that iex leaves the shell as it was -- is for a
person at a Windows machine.
"""
import io
import os
import re

import pytest

from cdsint import release

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*path):
    with io.open(os.path.join(REPO_ROOT, *path), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def script():
    return read("irm", "setup.ps1")


def function(script, name):
    """The text of one function, up to the next one or the end."""
    start = script.index("function %s {" % name)
    after = script.find("\nfunction ", start + 1)
    return script[start:after if after > 0 else len(script)]


def test_setup_ps1_is_ascii(script):
    """A release asset is served as application/octet-stream, which Windows
    PowerShell 5.1 decodes as Latin-1, and a BOM-less file run from disk is
    read in the ANSI code page. ASCII reads the same in all of them."""
    script.encode("ascii")


def test_the_download_is_the_asset_the_release_job_publishes(script):
    """The URL and the file name, the same in setup.ps1 and release.py."""
    assert '$DownloadUrl = "%s"' % release.DOWNLOAD_URL in script
    assert '"$DownloadUrl/$Version/%s"' % (release.ASSET % "$Version") in script


def test_the_release_job_publishes_what_is_downloaded():
    workflow = read(".github", "workflows", "ci.yml")
    asset = release.ASSET % "$GITHUB_REF_NAME"
    upload = workflow[workflow.index("gh release create"):]
    for published in (asset, asset + ".sha256", "irm/setup.ps1"):
        assert published in upload
    assert 'sha256sum "%s" > "%s.sha256"' % (asset, asset) in workflow


def test_a_release_is_checked_before_it_is_unpacked(script):
    save = function(script, "Save-Archive")
    assert "Get-FileHash -Path $zip -Algorithm SHA256" in save
    assert save.index("Get-FileHash") < save.index("throw \"$url does not")
    body = function(script, "Get-Body")
    assert body.index("Save-Archive") < body.index("Expand-Tree")


def test_only_main_goes_unverified(script):
    save = function(script, "Save-Archive")
    unchecked = save[:save.index("$url = ")]
    assert 'if ($Version -eq "main")' in unchecked
    assert "unverified" in unchecked
    assert "archive/refs/tags" not in script


def test_the_old_body_is_moved_aside_never_deleted_first(script):
    """Deleting it before the new tree is in place left a half-deleted body
    whenever the move failed or a shell had its directory open."""
    body = function(script, "Get-Body")
    assert not re.search(r"Remove-Item\s+(-Path\s+)?\$root\b", body)
    aside = body.index("Rename-Item -Path $root")
    swap = body.index("Move-Item -Path $inner -Destination $root")
    cleared = body.index("Remove-Leftover -Path $retired")
    assert body.index("Expand-Tree") < aside < swap < cleared


def test_a_failed_swap_puts_the_old_body_back(script):
    body = function(script, "Get-Body")
    swap = body[body.index("Move-Item -Path $inner"):]
    rollback = swap[swap.index("} catch {"):swap.index("throw")]
    assert "Rename-Item -Path $retired" in rollback


def test_nothing_is_unpacked_on_another_volume(script):
    """%TEMP% can be on another drive, where a directory cannot be renamed."""
    assert "$env:TEMP" not in script
    assert '$staging = "$root.new"' in function(script, "Get-Body")


def test_python_is_asked_its_version_before_anything_is_downloaded(script):
    """Being on PATH proves nothing: the Store alias is a python.exe too."""
    probe = function(script, "Test-Python")
    assert "sys.version_info >= (3, 11)" in probe
    assert "$LASTEXITCODE -eq 0" in probe
    install = function(script, "Install-Cdsint")
    assert install.index("Test-Python") < install.index("Find-Body")


def test_success_is_not_announced_when_link_failed(script):
    install = function(script, "Install-Cdsint")
    refused = install.index("if ($linked -ne 0)")
    assert refused < install.index("[+] 'cdsint --help' to start")
    assert "return $linked" in install[refused:]


def test_the_callers_shell_is_left_as_it_was(script):
    """Under iex a top-level assignment is an assignment in the user's shell."""
    top_level = [line for line in script.splitlines()
                 if re.match(r"(\$ErrorActionPreference|\[Console\]::"
                             r"OutputEncoding)\s*=", line)]
    assert top_level == []
    tail = script[script.index("$code = & {"):]
    assert "finally {\n        [Console]::OutputEncoding = $encoding" in tail


def test_exit_only_when_run_from_a_file(script):
    """`exit` under iex closes the user's window."""
    exits = [line.strip() for line in script.splitlines()
             if re.search(r"(^|[{;])\s*exit\b", line)]
    assert exits == ["if ($PSCommandPath) { exit $code }"]
    assert script.rstrip().endswith(
        'if ($code -ne 0) { throw "cdsint setup did not finish; the lines '
        'above say what failed." }')


def test_list_never_downloads_a_body(script):
    """Run from irm there is no checkout, and -List fell through to Get-Body,
    which replaced the installed body it promised to leave alone."""
    find = function(script, "Find-Body")
    assert find.count("Get-Body") == 1
    assert "if (-not $List) { return Get-Body -Version $Version }" in find
    assert 'cdsint\\body' in find


def test_no_body_is_swapped_under_a_running_ide(script):
    """cdsint update refuses to; the installer swapped regardless, and an IDE
    that had run a script mixed the old engine with the new."""
    body = function(script, "Get-Body")
    assert body.index("Assert-NoIdeRunning") < body.index(
        "Rename-Item -Path $root")
    assert "update.running_ides()" in function(script, "Assert-NoIdeRunning")


def test_the_flat_body_goes_only_once_the_new_one_is_in(script):
    """It was deleted before the move, so a move that failed left no body."""
    body = function(script, "Get-Body")
    assert body.index("Move-Item -Path $inner -Destination $root") < \
        body.index("Remove-FlatBody")

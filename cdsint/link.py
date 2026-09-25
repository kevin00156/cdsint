# -*- coding: utf-8 -*-
"""`cdsint link`: put this body's stubs in every IDE's Scripts menu.

The IDE scans its ScriptDir recursively and menus every .py it finds, so
ScriptDir\\cdsint becomes an NTFS junction onto this body's stub\\ directory
and nothing else of ours is reachable from there (SPEC 5.3). stub\\body.path
tells the stubs where the body is. Whichever body runs this is the one
linked: a downloaded one, or the clone somebody is editing.

This used to live in irm/setup.ps1, untested, which is why a newly installed
IDE could only be added by downloading the whole body again. setup.ps1 calls
this now, and so does `cdsint update`.

A ScriptDir under Program Files needs an elevated shell. Without one it is
reported and skipped, never attempted: the attempt fails with a bare "access
denied" that names neither the IDE nor the fix. A real directory where the
junction should be is not ours to delete, so it is reported and left.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import ctypes
import io
import os
import subprocess

from cds.core.exits import EXIT_FAILED, EXIT_OK
from cds.ide.entries import REPO_ROOT
from cdsint import installs, report

MENU_FOLDER = "cdsint"

LINKED = "linked"            # made or repointed just now
ALREADY = "already"          # pointed here before this ran
NEEDS_ADMIN = "needs_admin"  # skipped: run again from an elevated shell
OCCUPIED = "occupied"        # a real directory is in the way
FAILED = "failed"

_LONG_PATH = "\\\\?\\"


def stub_dir():
    return os.path.join(REPO_ROOT, "stub")


def targets(script_dir=None):
    """[(IDE names, ScriptDir, needs admin)], one per ScriptDir.

    Two IDEs of one generation share a directory; linking it twice would
    report two successes for one junction.
    """
    if script_dir:
        return [("(given on the command line)", script_dir, False)]
    grouped = {}
    for install in installs.find():
        entry = grouped.setdefault(install["script_dir"], [
            [], install["script_dir"], install["script_dir_needs_admin"]])
        entry[0].append(install["name"])
    return [(" + ".join(names), path, admin)
            for names, path, admin in grouped.values()]


def points_here(menu):
    """Is menu a junction onto this body's stub directory?"""
    try:
        target = os.readlink(menu)
    except OSError:
        return False
    if target.startswith(_LONG_PATH):
        target = target[len(_LONG_PATH):]
    return os.path.normcase(os.path.abspath(target)) == os.path.normcase(
        os.path.abspath(stub_dir()))


def unlinked():
    """The IDEs whose menu does not reach this body, as (names, admin)."""
    return [(names, admin) for names, path, admin in targets()
            if not points_here(os.path.join(path, MENU_FOLDER))]


def is_elevated():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def make_junction(link, target):
    """mklink /J, because the standard library has no public call for it."""
    done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                          capture_output=True, text=True, errors="replace")
    if done.returncode:
        raise OSError((done.stderr or done.stdout).strip())


def link_one(script_dir, needs_admin):
    """Point one ScriptDir at this body. Returns (state, detail)."""
    menu = os.path.join(script_dir, MENU_FOLDER)
    if points_here(menu):
        return ALREADY, menu
    if needs_admin and not is_elevated():
        return NEEDS_ADMIN, script_dir
    if os.path.lexists(menu):
        try:
            os.readlink(menu)
        except OSError:
            return OCCUPIED, menu
        os.unlink(menu)
    try:
        os.makedirs(script_dir, exist_ok=True)
        make_junction(menu, stub_dir())
    except OSError as error:
        return FAILED, "%s: %s" % (menu, error)
    return LINKED, menu


def write_body_path():
    """One line, no newline, no BOM: the stub puts it on sys.path verbatim."""
    with io.open(os.path.join(stub_dir(), "body.path"), "w",
                 encoding="utf-8", newline="") as handle:
        handle.write(REPO_ROOT)


def link_all(script_dir=None):
    """Link every ScriptDir found, or the one given. One row per ScriptDir."""
    write_body_path()
    rows = []
    for names, path, admin in targets(script_dir):
        state, detail = link_one(path, admin)
        rows.append({"ide": names, "state": state, "detail": detail})
    return rows


def run(ns):
    rows = link_all(ns.script_dir)
    report.show_links(rows, ns.json)
    bad = [row for row in rows if row["state"] not in (LINKED, ALREADY)]
    return EXIT_FAILED if bad or not rows else EXIT_OK

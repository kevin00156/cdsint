# -*- coding: utf-8 -*-
"""`cdsint update`: replace the downloaded body with the newest release.

Only the body irm/setup.ps1 installed. A clone belongs to whoever is editing
it and is updated with git; a body anywhere else was put there by hand and
nobody here knows what else depends on that.

The junctions in each IDE's ScriptDir and the editable pip install both name
the body by its path, and the path does not change, so replacing the
directory is the whole upgrade; then cdsint/link.py rewrites stubody.path
in the new tree and adds any IDE installed since, updated or not. The new tree is unpacked beside the old one
first and only then swapped in by two renames, so a failed download or a
full disk leaves the old body exactly as it was.

It refuses while any CODESYS-family IDE is running. An IDE that has run one
of the stubs holds the old engine in memory, and after the swap its next
menu click would mix the old modules it has loaded with the new ones it has
not. Which IDEs have done that is not visible from out here, so all of them
count.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import csv
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from cds.core.exits import EXIT_FAILED, EXIT_OK
from cds.ide.entries import REPO_ROOT
from cdsint import installs, link, release, report
from cdsint.exits import Failure
from engine.codesys_constants import SCRIPT_VERSION

# A GitHub archive of a release is a few megabytes.
DOWNLOAD_TIMEOUT_S = 60.0


def run(ns):
    _check_downloaded()
    try:
        tag = release.latest_tag(ns.timeout)
    except (OSError, ValueError, KeyError) as error:
        raise Failure("could not ask GitHub for the newest release: %s"
                      % error, EXIT_FAILED)
    record = {"from": release.tag_of(SCRIPT_VERSION), "latest": tag,
              "updated": release.is_newer(tag)}
    if record["updated"]:
        _check_no_ide_running()
        record["left_behind"] = _replace(tag, release.body_root())
        _reinstall(release.body_root())
    record["menus"] = link.link_all()
    report.show_update(record, ns.json)
    return EXIT_OK


def _check_downloaded():
    if release.is_downloaded():
        return
    raise Failure(
        "cdsint at %s was not installed by irm/setup.ps1, so update leaves "
        "it alone. A clone updates with `git pull`." % REPO_ROOT, EXIT_FAILED)


def running_ides():
    """The CODESYS-family executables running now, by image name."""
    wanted = set(vendor["exe"].lower() for vendor in installs.VENDORS)
    listing = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, errors="replace",
                             check=True).stdout
    return sorted(set(row[0] for row in csv.reader(io.StringIO(listing))
                      if row and row[0].lower() in wanted))


def _check_no_ide_running():
    running = running_ides()
    if running:
        raise Failure(
            "close every CODESYS-family IDE first (running: %s). One that has "
            "run a cdsint script keeps the old engine loaded, and would mix "
            "it with the new one." % ", ".join(running), EXIT_FAILED)


def _replace(tag, body):
    """replace_body, with a failure said in words and where the old body is."""
    try:
        return replace_body(tag, body)
    except (OSError, zipfile.BadZipFile) as error:
        where = ("still at " + body if os.path.isdir(body)
                 else "at " + body + ".old; rename it back")
        raise Failure("could not replace the body with %s: %s. The old one "
                      "is %s." % (tag, error, where), EXIT_FAILED)


def replace_body(tag, body):
    """Unpack tag beside body, then swap it in by two renames.

    The retired copy is deleted last and a failure to delete it does not undo
    the update: the new body is already the one in use. Its path comes back
    so the caller can say it is still there, or None when it is gone.
    """
    staging = body + ".new"
    retired = body + ".old"
    for leftover in (staging, retired):
        if os.path.exists(leftover):
            shutil.rmtree(leftover)
    fresh = _unpack(_download(tag, staging), staging)
    os.rename(body, retired)
    try:
        os.rename(fresh, body)
    except OSError:
        os.rename(retired, body)
        raise
    shutil.rmtree(staging)
    try:
        shutil.rmtree(retired)
    except OSError:
        return retired
    return None


def _download(tag, staging):
    os.makedirs(staging)
    archive = os.path.join(staging, tag + ".zip")
    with urllib.request.urlopen(release.ARCHIVE_URL % tag,
                                timeout=DOWNLOAD_TIMEOUT_S) as response:
        with open(archive, "wb") as handle:
            shutil.copyfileobj(response, handle)
    return archive


def _unpack(archive, staging):
    """The tree inside the archive. GitHub wraps it in one directory."""
    with zipfile.ZipFile(archive) as bundle:
        top = set(name.split("/")[0] for name in bundle.namelist())
        if len(top) != 1:
            raise Failure("%s does not hold one tree: %s"
                          % (archive, sorted(top)), EXIT_FAILED)
        bundle.extractall(staging)
    return os.path.join(staging, top.pop())


def _reinstall(body):
    """Refresh the editable install's metadata, so `pip show` has the new number.

    The body is already in place and working when this runs; a failure here
    leaves only the metadata behind, so it is reported, not rolled back.
    """
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                           "-e", body], capture_output=True, text=True,
                          errors="replace")
    if done.returncode:
        raise Failure(
            "the new release is in place, but pip could not refresh its "
            "record of it; run `%s -m pip install -e \"%s\"`. pip said:\n%s"
            % (sys.executable, body, done.stderr.strip()), EXIT_FAILED)

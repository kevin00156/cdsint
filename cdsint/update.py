# -*- coding: utf-8 -*-
"""`cdsint update`: replace the downloaded body with the newest release.

Only the body irm/setup.ps1 installed. A clone belongs to whoever is editing
it and is updated with git; a body anywhere else was put there by hand and
nobody here knows what else depends on that.

The junctions in each IDE's ScriptDir and the editable pip install both name
the body by its path, and the path does not change, so replacing the
directory is the whole upgrade; then the body on disk runs its own
`cdsint link`, which writes stub\\body.path into the tree and adds any IDE
installed since, updated or not. The release's archive is checked against
the SHA-256 published beside it, then unpacked beside the old tree and only
then swapped in by two renames, so a failed download, a mismatch or a full
disk leaves the old body exactly as it was. Once the swap is done nothing
undoes it: what fails after that is a leftover to report, not a reason to
stop before the menus are linked, because a new tree without its body.path
is a Scripts menu that fails on every click.

It refuses while any CODESYS-family IDE is running. An IDE that has run one
of the stubs holds the old engine in memory, and after the swap its next
menu click would mix the old modules it has loaded with the new ones it has
not. Which IDEs have done that is not visible from out here, so all of them
count.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
import zlib

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
    except release.QUERY_ERRORS as error:
        raise Failure("could not ask GitHub for the newest release: %s"
                      % error, EXIT_FAILED)
    record = {"from": release.tag_of(SCRIPT_VERSION), "latest": tag,
              "updated": release.is_newer(tag)}
    if record["updated"]:
        _check_no_ide_running()
        record["left_behind"] = _replace(tag, release.body_root())
        record["pip"] = _reinstall(release.body_root())
    record["menus"] = relink(release.body_root())
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
    try:
        listing = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                                 capture_output=True, text=True,
                                 errors="replace", check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        # Not knowing is not "none running": a swap under a running IDE is
        # the one thing this check is for.
        raise Failure("could not list the running programs to check that no "
                      "CODESYS-family IDE is open, so nothing was changed: %s"
                      % exc, EXIT_FAILED)
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
    except release.QUERY_ERRORS + (zipfile.BadZipFile, zlib.error) as error:
        where = ("still at " + body if os.path.isdir(body)
                 else "at " + body + ".old; rename it back")
        raise Failure("could not replace the body with %s: %s. The old one "
                      "is %s." % (tag, error, where), EXIT_FAILED)


def replace_body(tag, body):
    """Unpack tag beside body, then swap it in by two renames.

    The staging directory and the retired copy are deleted last, and a
    failure to delete either does not undo the update: the new body is
    already the one in use. The paths still there come back so the caller
    can say so.
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
    return [path for path in (staging, retired) if not _deleted(path)]


def _deleted(path):
    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return True


def _download(tag, staging):
    """The release's archive, written into staging once its SHA-256 matches.

    The checksum is the release job's, published beside the archive; a
    release without one is refused, not installed unchecked.
    """
    url = release.asset_url(tag)
    data = _fetch(url)
    expected = _fetch(url + ".sha256").decode("ascii", "replace").split()[:1]
    if expected != [hashlib.sha256(data).hexdigest()]:
        raise ValueError("%s does not match the SHA-256 published beside it"
                         % url)
    os.makedirs(staging)
    archive = os.path.join(staging, release.ASSET % tag)
    with open(archive, "wb") as handle:
        handle.write(data)
    return archive


def _fetch(url):
    """url's content. An HTTP error names the URL: a 404 alone does not say
    which of the two files is missing."""
    try:
        with urllib.request.urlopen(url,
                                    timeout=DOWNLOAD_TIMEOUT_S) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise OSError("%s: %s" % (url, error)) from error


def _unpack(archive, staging):
    """The tree inside the archive, which the release job wraps in one
    directory; anything else is not an archive of this repo."""
    with zipfile.ZipFile(archive) as bundle:
        top = set(name.split("/")[0] for name in bundle.namelist())
        if len(top) != 1:
            raise Failure("%s does not hold one tree: %s"
                          % (archive, sorted(top)), EXIT_FAILED)
        bundle.extractall(staging)
    return os.path.join(staging, top.pop())


def relink(body):
    """`cdsint link --json`, run by the body on disk rather than by this process.

    After a swap this process still has the old release's modules loaded, and
    the stubs, vendors and body.path it would write are the old release's
    idea of them. A link that did not answer comes back as one failed row, so
    the missing body.path is said rather than left for the menu to find.
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join(
                   filter(None, (body, os.environ.get("PYTHONPATH")))))
    done = subprocess.run([sys.executable, "-m", "cdsint.cli", "link",
                           "--json"], cwd=body, env=env, capture_output=True,
                          encoding="utf-8", errors="replace")
    try:
        rows = json.loads(done.stdout)
    except ValueError:
        rows = None
    if isinstance(rows, list):
        return rows
    return [{"ide": "every IDE", "state": link.FAILED,
             "detail": "`cdsint link` in %s did not run (exit %s); run it "
                       "by hand. It said:\n%s"
                       % (body, done.returncode, done.stderr.strip())}]


def _reinstall(body):
    """Refresh the editable install's metadata, so `pip show` has the new number.

    The body is already in place and working when this runs; a failure here
    leaves only the metadata behind, so it is reported, not rolled back. What
    to run by hand comes back, or None when pip managed.
    """
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                           "-e", body], capture_output=True, text=True,
                          errors="replace")
    if done.returncode:
        return ("run `%s -m pip install -e \"%s\"`; pip said:\n%s"
                % (sys.executable, body, done.stderr.strip()))
    return None

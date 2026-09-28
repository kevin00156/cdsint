# -*- coding: utf-8 -*-
"""The instance directory: where it lives, and how to write a file in it.

This is the ground floor of the protocol between the in-IDE watcher and the
external CLI. One directory per running IDE:

    <root>/
        <instance-id>.json      registration + heartbeat  (cds.core.instances)
        <instance-id>/
            cmd/<id>.json       written by the CLI        (cds.core.commands)
            result/<id>.json    written by the watcher    (cds.core.commands)

The other side of every file here is a different process that may read at any
moment, so every write goes to ``<path>.tmp`` first and is then renamed over
the real name. Readers only ever look at ``.json``.

Pure Python on purpose (PRINCIPLES.md 4): no CODESYS imports, so it runs in CI
under CPython 3 and inside the IDE under IronPython 2.7 from the same source.
"""
from __future__ import print_function

import errno
import io
import json
import ntpath
import os
import re
import time

ROOT_ENV = "CDS_INSTANCES_DIR"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def default_root():
    """Where instance directories live, unless CDS_INSTANCES_DIR overrides it."""
    override = os.environ.get(ROOT_ENV)
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA")
    if not base:  # not Windows: only ever hit by CI and by tests
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "cdsint", "instances")


def make_instance_id(project_path, pid):
    """Build "<project stem>-<pid>", the name that identifies one IDE.

    ntpath, not os.path: the project path comes from the IDE, which only runs
    on Windows, so it is always a Windows path. ntpath splits on both slashes,
    so it reads that path correctly wherever the CLI happens to run.
    """
    stem = ntpath.splitext(ntpath.basename(project_path or "unsaved"))[0]
    return "%s-%s" % (_UNSAFE.sub("_", stem) or "unsaved", pid)


def registration_path(root, instance_id):
    return os.path.join(root, instance_id + ".json")


def instance_dir(root, instance_id):
    return os.path.join(root, instance_id)


def command_dir(root, instance_id):
    return os.path.join(root, instance_id, "cmd")


def result_dir(root, instance_id):
    return os.path.join(root, instance_id, "result")


def ensure_dirs(root, instance_id):
    """Create the cmd/ and result/ directories for an instance."""
    makedirs(command_dir(root, instance_id))
    makedirs(result_dir(root, instance_id))


# --------------------------------------------------------------------------
# Files a second process may be reading
# --------------------------------------------------------------------------

def write_json(path, data):
    """Write data to path atomically, via <path>.tmp plus a rename.

    The rename can fail: on Windows a file another process has open cannot be
    replaced, and the reader on the other side of this protocol opens these
    files constantly. That raises, and the caller decides — the watcher just
    tries again on its next turn rather than dying over a heartbeat.
    """
    write_atomic(path, json.dumps(data, indent=2, sort_keys=True))


def write_atomic(path, text):
    """Write text to path via <path>.tmp plus a rename, so a reader, or the
    next run after a crash, sees the old file or the new one and never half
    of one. Raises as write_json does."""
    makedirs(os.path.dirname(path))
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    try:
        _replace(tmp, path)
    except EnvironmentError:
        _discard(tmp)  # never leave a half-written name lying around
        raise


def read_json(path):
    """Parse path, or return None if it is gone.

    A missing file is normal here (the other side deletes as it goes); a
    malformed one is not, and raises (PRINCIPLES.md 6).
    """
    try:
        with io.open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return None
        raise
    return json.loads(text)


def json_names(directory):
    """Sorted .json file names in directory; .tmp and anything else skipped."""
    try:
        names = os.listdir(directory)
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return []
        raise
    return sorted(n for n in names if n.endswith(".json"))


def remove_file(path):
    """Delete path, saying nothing if it was already gone."""
    try:
        os.remove(path)
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) != errno.ENOENT:
            raise


def makedirs(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)


def _discard(path):
    """Drop a temp file whose rename did not happen. The real error is being
    re-raised by the caller, so failing to tidy up is not worth reporting."""
    try:
        os.remove(path)
    except (IOError, OSError):
        pass


# Where _replace keeps the old file while the new one is renamed in.
ASIDE = ".old"


def _replace(src, dst):
    """Rename src over dst. os.rename cannot overwrite on Windows.

    Without os.replace -- IronPython 2.7, which is where the sync cache and
    the plc record are written -- the old file is renamed aside rather than
    deleted: a rename a virus scanner blocks puts it back, and a process that
    dies between the two renames leaves it for last_written() to find. Only
    a stale aside is ever deleted before a new one is made, never the only
    copy there is.
    """
    replace = getattr(os, "replace", None)  # CPython 3 only, atomic
    if replace is not None:
        replace(src, dst)
        return
    aside = dst + ASIDE
    if os.path.exists(dst):
        _discard(aside)
        os.rename(dst, aside)
    try:
        os.rename(src, dst)
    except EnvironmentError:
        if os.path.exists(aside) and not os.path.exists(dst):
            os.rename(aside, dst)
        raise
    _discard(aside)


def last_written(path):
    """path, or what _replace set aside when the process died between its
    two renames. For the files whose loss loses work -- the sync cache and
    the plc record -- not for this protocol's files, where a file the other
    side deleted is an answer and must not come back."""
    if not os.path.exists(path) and os.path.exists(path + ASIDE):
        return path + ASIDE
    return path


# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------

def now(value=None):
    """Epoch seconds: value when the caller pins one, the clock otherwise."""
    return time.time() if value is None else float(value)


def iso(epoch):
    """The human-readable stamp that sits beside every epoch field."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(epoch))

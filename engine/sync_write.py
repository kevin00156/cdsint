# -*- coding: utf-8 -*-
"""Put a file in the sync folder in one step: the old file or the new one,
never half of one.

The disk is the source of truth (PRINCIPLES.md 5), so a `.st` cut short by
a killed headless export or a crashed IDE is not a damaged copy -- it is
what the next import pushes into the project. Every write goes to
`<path>.tmp` beside the target, then replaces the target in one rename.
`.tmp` is in the sync folder's .gitignore (engine/git_configs.py) and is not
a sync suffix (engine/sync_dir.py), so a temp left by a killed run is
neither committed nor read as an object, and the next write truncates it.

cds.core.ipc.write_atomic does the same for the protocol files, but
cds/core may not reach .NET, so without os.replace it falls back to two
renames with a moment where the target is gone. For the protocol that is
survivable; for a `.st` the orphan sweep and import would read the gap as
an object with no file. Here the IronPython path uses .NET instead.
"""
from __future__ import print_function

import io
import os

TMP = ".tmp"


def write_text(path, text):
    """Write text to path as utf-8, newlines exactly as given, in one step."""
    tmp = path + TMP
    try:
        with io.open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        replace(tmp, path)
    finally:
        _discard(tmp)


def replace(src, dst):
    """Move src over dst in one step, whether dst exists or not.

    os.replace is CPython 3 only; IronPython 2.7, where the IDE runs this,
    has .NET: File.Replace swaps an existing target, File.Move places a new
    one (.NET Framework's Move cannot overwrite).
    """
    native = getattr(os, "replace", None)
    if native is not None:
        native(src, dst)
        return
    from System.IO import File
    if File.Exists(dst):
        File.Replace(src, dst, None)
    else:
        File.Move(src, dst)


def _discard(path):
    """Drop a temp the replace did not consume. Called on the way out of
    write_text, where any real error is already propagating, so failing to
    tidy up is not worth a second one: the next write truncates it."""
    if not os.path.exists(path):
        return
    try:
        os.remove(path)
    except (IOError, OSError):
        pass

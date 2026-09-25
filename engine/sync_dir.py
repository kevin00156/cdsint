# -*- coding: utf-8 -*-
"""What is in the sync folder, and what this tool is allowed to look at.

One walk, one set of skip rules. There were three walks with three different
answers: the orphan sweep skipped dot-folders but not `__pycache__` and did
not consult RESERVED_FILES, the new-file scan skipped both, and the "is there
anything here to import" check skipped folders but never looked at file names
at all. Nothing had gone wrong yet only because RESERVED_FILES happens to hold
no `.st` -- the day somebody adds one, the sweep would have offered to delete
a file the scan refuses to see.

Disk is the source of truth (PRINCIPLES 5), so which files count as "on disk"
is not a detail three callers may each decide for themselves.
"""
from __future__ import print_function

import os

from cds.core.device_text import SUFFIX as DEVICE_SUFFIX
from cds.core.library_list import SUFFIX as LIBRARY_SUFFIX
from engine.codesys_constants import RESERVED_FILES

# The extensions this tool writes and reads back: code, native XML, the
# Library Manager's list (SPEC 6.9) and EtherCAT devices' settings (6.10).
# Anything else in the folder belongs to whoever put it there.
SYNC_SUFFIXES = (".st", ".xml", LIBRARY_SUFFIX, DEVICE_SUFFIX)

# Where git and the backups keep their own copies, and where Python leaves its
# bytecode. Walking into any of them would offer their contents up as project
# objects.
SKIPPED_DIRS = ("__pycache__",)


def _is_skipped_dir(name):
    return name.startswith(".") or name in SKIPPED_DIRS


def _is_skipped_file(name):
    if name.startswith("."):
        return True
    if name in RESERVED_FILES:
        return True
    return not name.endswith(SYNC_SUFFIXES)


def sync_files(base_dir):
    """Yield (rel_path, abs_path) for every file in the sync folder that counts.

    rel_path is relative to base_dir with forward slashes, which is the form
    the IDE-side paths and the cache keys are already in, so callers never
    have to convert.
    """
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not _is_skipped_dir(d)]

        rel_root = os.path.relpath(root, base_dir)
        if rel_root == ".":
            rel_root = ""

        for name in sorted(files):
            if _is_skipped_file(name):
                continue
            if rel_root:
                rel_path = rel_root.replace("\\", "/") + "/" + name
            else:
                rel_path = name
            yield rel_path, os.path.join(root, name)


def has_st_files(base_dir):
    """Is there anything here an import could read as the truth?

    A .st the disk scan will not look at cannot be a source of truth either,
    which is why this asks the same walk rather than one of its own.
    """
    for rel_path, _abs_path in sync_files(base_dir):
        if rel_path.endswith(".st"):
            return True
    return False

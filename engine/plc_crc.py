# -*- coding: utf-8 -*-
"""Is the controller running this tree? The files that answer it, and the answer.

The compiler is what answers it. Building the boot application offline writes
a `.crc` beside the `.app`, the controller keeps the same file at
PlcLogic/Application/Application.crc, and bytes 5 to 8 of the two are the
identity to compare. Everything here is plain bytes and paths: nothing in
this module talks to an IDE or to a controller, which is why the comparison
can be tested without either.
"""
from __future__ import print_function

import os
import tempfile

from engine.codesys_utils import log_warning, safe_str

# The verdict, and what it is called in the report (SPEC 6.6).
MATCH = "MATCH"
DIFFERENT = "DIFFERENT"
UNKNOWN = "UNKNOWN"

# Bytes 5 to 8 of a .crc file are the identity; the first four are a header.
# The test for that split is that those four bytes are identical in files
# built from two different projects.
CRC_FIELD = (4, 8)

REMOTE_APP_DIR = "PlcLogic/Application"
REMOTE_CRC = REMOTE_APP_DIR + "/Application.crc"

# The boot application is always written under the same name, so each run
# overwrites the last one rather than leaving a pile nobody reads, and no
# code here ever deletes a directory it did not create.
BOOT_NAME = "cdsint.app"
BOOT_CRC_NAME = "cdsint.crc"
PLC_CRC_NAME = "plc_Application.crc"
SOURCE_ARCHIVE_NAME = "plc_source.projectarchive"


# --------------------------------------------------------------------------
# The bytes
# --------------------------------------------------------------------------

def read_bytes(path):
    """The whole of a file, or None when it is not there."""
    if not os.path.isfile(path):
        return None
    handle = open(path, "rb")
    try:
        return handle.read()
    finally:
        handle.close()


def crc_field(raw):
    """The identity bytes of a .crc file as hex, or None if there are none.

    A file too short to hold the field is not a CRC of anything, so it reads
    as "no answer" rather than as a shorter answer that would then compare
    equal to another truncated file.
    """
    start, end = CRC_FIELD
    if raw is None or len(raw) < end:
        return None
    return "".join("%02X" % _byte(value) for value in raw[start:end])


def compare_crc(local, plc):
    """MATCH, DIFFERENT, or UNKNOWN when either side is missing.

    UNKNOWN is not a third shade of the same answer, it is the absence of
    one, and it is kept apart from DIFFERENT because the two call for
    different things: DIFFERENT means download, UNKNOWN means find out why
    there was nothing to compare.
    """
    if not local or not plc:
        return UNKNOWN
    return MATCH if local == plc else DIFFERENT


# --------------------------------------------------------------------------
# Saying what it came to
# --------------------------------------------------------------------------

def verdict_line(action, found):
    """The one line a person reads, for each of the three answers."""
    verdict = found["crc"]
    if verdict == MATCH:
        return ("%s: the controller is running this project (CRC %s)"
                % (action, found["plc_crc"]))
    if verdict == DIFFERENT:
        return ("%s: the controller is NOT running this project. Its CRC is "
                "%s and this project builds to %s"
                % (action, found["plc_crc"], found["local_crc"]))
    return ("%s: the controller and this project could not be compared. %s"
            % (action, why_unknown(found)))


def why_unknown(found):
    """Which half of the comparison is missing. Both is a real case."""
    missing = []
    if not found["local_crc"]:
        missing.append("this project produced no boot application CRC")
    if not found["plc_crc"]:
        missing.append("the controller has no %s" % REMOTE_CRC)
    return "; ".join(missing) or "no reason was recorded, which is a bug"


# --------------------------------------------------------------------------
# Where the files go
# --------------------------------------------------------------------------

def workspace(project_path):
    """Make and return where this run's .app, .crc and archive go.

    Named after the project rather than made fresh each time, so a second run
    overwrites the first instead of leaving a numbered trail in TEMP, and so
    the path in the report is one a reader can go and look at.
    """
    path = os.path.join(tempfile.gettempdir(), "cdsint", "plc",
                        _safe_name(_project_stem(project_path)))
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def forget(path):
    """Remove the file this run is about to write, and hand back the path.

    The workspace is named after the project so that runs overwrite each
    other rather than pile up, and that is exactly what makes a stale file
    dangerous: a call that returns without writing would otherwise be read
    as last week's answer to this week's question.
    """
    try:
        if os.path.isfile(path):
            os.remove(path)
    except (IOError, OSError) as exc:
        log_warning("plc: could not clear %s before writing it: %s"
                    % (path, safe_str(exc)))
    return path


def _byte(value):
    """One byte as an int, whether iterating gave us an int or a character."""
    return value if isinstance(value, int) else ord(value)


def _project_stem(project_path):
    if not project_path:
        return "unsaved"
    return os.path.splitext(os.path.basename(safe_str(project_path)))[0]


def _safe_name(stem):
    """A directory name from a project name: these have spaces and Chinese."""
    kept = [c if (c.isalnum() or c in "._-") else "_" for c in stem]
    return "".join(kept) or "unsaved"

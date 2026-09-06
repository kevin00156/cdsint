# -*- coding: utf-8 -*-
"""Is the controller running what cdsint put on it? The files, and the answer.

The obvious instrument is the wrong one, and it took a bench to see it. The
IDE will build a boot application offline and write a `.crc` beside it, and
the controller keeps a file of the same name and layout at
PlcLogic/Application/Application.crc. Holding those two against each other is
what this module used to do, and it answered DIFFERENT every time.

Two separate reasons, both measured on the WSL bench on 2026-09-06 with
CODESYS 3.5.21.40 (ScriptEngine 4.2.0.0):

  They are not the same artefact. The controller's `.app` came back 2118764
  bytes against the offline one's 2098340, with 1.68 million bytes different.
  Two files that unalike never agree; their CRCs were never going to either.

  The offline value is not a property of the source. A four-byte identity is
  stamped into every 64 KB block of the boot application, and the compiler
  mints a new one whenever the project has been written to: aiming the device
  at a gateway moved it, so did logging in, and so does setting a project
  property -- and the --project form sets cds-sync-folder on every run, so
  two identical `plc connect` runs a minute apart built 128DBA21 and
  59B20109. It is stable only for an untouched working copy, and not even the
  same for a byte-identical copy at another path, because it comes from the
  .compileinfo and .bootinfo files the IDE keeps beside the project file.

So there is exactly one stable, meaningful quantity in reach: the CRC the
controller itself holds. It changes when, and only when, something is
downloaded. That gives the comparison this module makes -- a download writes
down what it left there, and a later connect holds the controller against
that record.

MATCH therefore means "this controller still holds what cdsint downloaded to
it from this project", not "the controller is running this source". The
narrower claim is the true one, and it is the one the message says. Whether
the project has moved on since is a different question with its own commands:
compare and verify answer it by reading every object, which is the only way
to answer it that cannot silently miss an edit nobody saved.

Everything here is plain bytes, paths and JSON: nothing talks to an IDE or a
controller, which is why the comparison can be tested without either.
"""
from __future__ import print_function

import os
import tempfile

from cds.core import ipc
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

# What a run pulls off the controller, under names of its own so a reader who
# goes and looks in the workspace knows which side each file came from. Each
# run overwrites the last rather than leaving a pile nobody reads, and no code
# here ever deletes a directory it did not create.
PLC_CRC_NAME = "plc_Application.crc"
SOURCE_ARCHIVE_NAME = "plc_source.projectarchive"

# The record lives beside the project rather than in a machine-wide store,
# because it is a fact about one working copy: it says what a download made
# from these files put on a machine. Copy the project elsewhere and the copy
# rightly starts out knowing nothing.
RECORD_SUFFIX = ".cdsint-plc.json"

# The record is keyed by the controller a download went to, so one working
# copy can serve two benches without either answer overwriting the other.
# This is the key for a run that was given no --gateway and used whatever
# address the project already carried.
PROJECT_GATEWAY = "project"


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


# --------------------------------------------------------------------------
# What the last download left behind
# --------------------------------------------------------------------------

def record_path(project_path):
    """Where this project's record of its downloads lives, or None.

    None when there is no project on disk to sit beside, which is the one
    case where there is nowhere to put it and nothing sensible to invent.
    """
    if not project_path:
        return None
    return os.path.splitext(safe_str(project_path))[0] + RECORD_SUFFIX


def controller_key(address, port):
    """The name a controller is filed under: "host:port", or PROJECT_GATEWAY.

    A run given no --gateway used whatever the project carried, and this
    module has no way to find out what that was -- so it is filed under a
    name that says exactly that, rather than under a guess.
    """
    if not address:
        return PROJECT_GATEWAY
    return "%s:%s" % (address, port)


def read_records(path):
    """Every controller this project has been downloaded to. {} when none.

    A file that will not parse is not a reason to fail a bench command, but
    it is a reason to say so: the run goes on and answers UNKNOWN, which is
    what "there is no usable record" means.
    """
    if not path:
        return {}
    try:
        found = ipc.read_json(path)
    except (IOError, OSError, ValueError) as exc:
        log_warning("plc: %s could not be read, so this run has nothing to "
                    "compare against: %s" % (path, safe_str(exc)))
        return {}
    return found if isinstance(found, dict) else {}


def remember(path, key, entry):
    """Add one controller's entry to the record. True when it was written.

    Merged rather than replaced: downloading one copy to a second bench must
    not erase what it knows about the first, or a later connect to the first
    would answer UNKNOWN about a controller cdsint did load.
    """
    if not path:
        return False
    records = read_records(path)
    records[key] = entry
    try:
        ipc.write_json(path, records)
    except (IOError, OSError) as exc:
        log_warning("plc: the download is done but %s could not be written, "
                    "so a later connect will have nothing to compare "
                    "against: %s" % (path, safe_str(exc)))
        return False
    return True


# --------------------------------------------------------------------------
# The answer
# --------------------------------------------------------------------------

def judge(recorded, plc):
    """The verdict and the reason for it. Three answers, and no fourth.

    UNKNOWN is not a third shade of DIFFERENT, it is the absence of an
    answer, and the two are kept apart because they call for different
    things: DIFFERENT means download, UNKNOWN means find out why there was
    nothing to compare.
    """
    if not plc:
        return UNKNOWN, ("the controller has no %s, so there is nothing on it "
                         "for this to be about" % REMOTE_CRC)
    if not recorded:
        return UNKNOWN, ("cdsint has not downloaded to this controller from "
                         "this project, so there is nothing to compare "
                         "against; run plc download -y")
    when = recorded.get("downloaded_at", "an unrecorded date")
    if plc != recorded.get("plc_crc"):
        return DIFFERENT, ("the controller holds %s and the download from "
                           "here on %s left %s, so it has been loaded with "
                           "something else since"
                           % (plc, when, recorded.get("plc_crc")))
    return MATCH, ("the controller still holds %s, which is what the download "
                   "from this project put there on %s" % (plc, when))


def verdict_line(action, found):
    """The one line a person reads: the reason, not just the verdict word."""
    return "%s: %s" % (action, found["why"])


# --------------------------------------------------------------------------
# Where the files go
# --------------------------------------------------------------------------

def workspace(project_path):
    """Make and return where this run's .crc and archive go.

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

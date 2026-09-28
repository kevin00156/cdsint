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
  property -- and the --project form used to set the sync folder as one on
  every run, so two identical `plc connect` runs a minute apart built
  128DBA21 and 59B20109. It is stable only for an untouched working copy, and not even the
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
import zlib

from cds.core import ipc
from engine.strings import safe_str
from engine.sync_log import log_warning

# The verdict, and what it is called in the report (SPEC 6.6).
MATCH = "MATCH"
DIFFERENT = "DIFFERENT"
UNKNOWN = "UNKNOWN"

# Bytes 5 to 8 of a .crc file are the identity; the first four are a header.
# The test for that split is that those four bytes are identical in files
# built from two different projects.
CRC_FIELD = (4, 8)

# What a run pulls off the controller goes into the workspace under a name
# of its own, so a reader who goes and looks knows which side each file came
# from. Each run overwrites the last rather than leaving a pile nobody reads,
# and no code here ever deletes a directory it did not create.
LOCAL_PREFIX = "plc_"
SOURCE_ARCHIVE_NAME = LOCAL_PREFIX + "source.projectarchive"

# The record lives beside the project rather than in a machine-wide store,
# because it is a fact about one working copy: it says what a download made
# from these files put on a machine. Copy the project elsewhere and the copy
# rightly starts out knowing nothing.
RECORD_SUFFIX = ".cdsint-plc.json"


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
    """The name a controller is filed under in the record: "host:port".

    Keyed by the address a download went to, so one working copy can serve
    two benches without either answer overwriting the other. Every plc
    command names its address (--gateway), so there is no other key; an
    entry under any other name, such as the "project" a download without
    --gateway once wrote, names no controller and is never read.
    """
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

def remote_files(application):
    """Where the controller keeps the application called `application`.

    {"dir", "crc", "app"}: PlcLogic/<name>/ and the <name>.crc and <name>.app
    in it. That is the runtime's layout, but the bench has only ever held an
    application called Application, so it is the only name it was seen for.
    """
    folder = "PlcLogic/" + application
    return {"dir": folder, "crc": "%s/%s.crc" % (folder, application),
            "app": "%s/%s.app" % (folder, application)}


def file_name(remote):
    """The last part of a controller path: what a listing calls the file."""
    return remote.rsplit("/", 1)[-1]


def local_name(remote):
    """What a file fetched from `remote` is called in the workspace."""
    return LOCAL_PREFIX + file_name(remote)


def judge(recorded, plc, remote_crc):
    """The verdict and the reason for it. Three answers, and no fourth.

    UNKNOWN is not a third shade of DIFFERENT, it is the absence of an
    answer, and the two are kept apart because they call for different
    things: DIFFERENT means download, UNKNOWN means find out why there was
    nothing to compare.
    """
    if not plc:
        return UNKNOWN, ("the controller has no %s, so there is nothing on it "
                         "for this to be about" % remote_crc)
    if not recorded:
        return UNKNOWN, ("there is no record of a download from this "
                         "project to this controller, so there is nothing to "
                         "compare against; run plc download -y once")
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

class Stale(Exception):
    """An earlier run's file is where this run writes, and would not go."""


def workspace(project_path):
    """Make and return where this run's .crc and archive go.

    Named after the project rather than made fresh each time, so a second run
    overwrites the first instead of leaving a numbered trail in TEMP, and so
    the path in the report is one a reader can go and look at. The name alone
    is not enough: two working copies of one project share it, and a run of
    one would read the other's files as its own, so a hash of the full path
    follows it.
    """
    path = os.path.join(tempfile.gettempdir(), "cdsint", "plc",
                        _workspace_name(project_path))
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def forget(path):
    """Remove the file this run is about to write, and hand back the path.

    The workspace is named after the project so that runs overwrite each
    other rather than pile up, and that is exactly what makes a stale file
    dangerous: a call that returns without writing would otherwise be read
    as last week's answer to this week's question. So a file that will not
    go raises Stale, and the caller names the failure, rather than carrying
    on beside it.
    """
    try:
        if os.path.isfile(path):
            os.remove(path)
    except (IOError, OSError) as exc:
        raise Stale("%s is left from an earlier run and could not be "
                    "removed, so what this run fetches could not be told "
                    "from it: %s" % (path, safe_str(exc)))
    return path


def _byte(value):
    """One byte as an int, whether iterating gave us an int or a character."""
    return value if isinstance(value, int) else ord(value)


def _workspace_name(project_path):
    """The project's name, and a hash of where it is, as one directory name.

    normcase and abspath so one file reached two ways is one workspace; crc32
    because it is deterministic across runs and interpreters, which Python's
    own hash() is not.
    """
    if not project_path:
        return "unsaved"
    path = safe_str(project_path)
    where = os.path.normcase(os.path.abspath(path))
    return "%s-%08x" % (
        _safe_name(os.path.splitext(os.path.basename(path))[0]),
        zlib.crc32(where.encode("utf-8")) & 0xFFFFFFFF)


def _safe_name(stem):
    """A directory name from a project name: these have spaces and Chinese."""
    kept = [c if (c.isalnum() or c in "._-") else "_" for c in stem]
    return "".join(kept) or "unsaved"

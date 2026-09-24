# -*- coding: utf-8 -*-
"""Will the IDE agree the controller holds this working copy's download?

A CRC MATCH says the controller still holds what cdsint put there. It does
not say the IDE knows that. The IDE decides from two files it writes beside
the project on every download,
`<stem>.<device>.<application>.<guid>.bootinfo_guids` and the `.compileinfo`
with the same prefix; with them missing, a login with
OnlineChangeOption.Keep downloaded the whole application without asking
(bench, 2026-09-24), under a CRC record that said MATCH. So `plc trace`
checks those files too before it logs in (SPEC 6.8 step 2).

The `.bootinfo_guids` file is 32 bytes: the code identity, then the data
identity. The controller's Application.app carries the same 32 bytes in its
header, after the application name. Only one layout has been measured
(tests/data/plc_app_header_*.bin), so only that layout is read; anything
else is refused by name rather than read at a guessed offset, because a
guess that lands on the wrong 32 bytes would say DIFFER, or worse, agree.

Plain bytes and paths, like engine/plc_crc.py: no IDE, no controller.
"""
from __future__ import print_function

import os

from engine.strings import safe_str

# Where the application name starts in the .app header. Measured, not
# documented: the eight bytes before it were the same in every file seen.
NAME_AT = 8

# The four bytes between the padded name and the identities.
IDENTITY_TAG = bytearray(b"\x71\xa0\x80\x00")

# Code identity, then data identity, 16 bytes each.
IDENTITY_SIZE = 32
HALF = IDENTITY_SIZE // 2

GUIDS_SUFFIX = ".bootinfo_guids"
COMPILEINFO_SUFFIX = ".compileinfo"

# Every refusal here ends the same way, because every one of them is cured
# by the same thing: a download from this working copy rewrites both files
# and the controller's header together.
DOWNLOAD = "run plc download -y from this working copy"


def app_identity(header):
    """The 32 identity bytes of an Application.app header. (bytes, None) or
    (None, problem)."""
    raw = bytearray(header or b"")
    end = raw.find(bytearray(b"\x00"), NAME_AT)
    if end <= NAME_AT:
        return None, _unrecognised("no application name at offset %d"
                                   % NAME_AT)
    tag_at = _padded(end + 1)
    tag = raw[tag_at:tag_at + len(IDENTITY_TAG)]
    if tag != IDENTITY_TAG:
        return None, _unrecognised("%s after the name, where %s was expected"
                                   % (_hex(tag) or "nothing",
                                      _hex(IDENTITY_TAG)))
    start = tag_at + len(IDENTITY_TAG)
    identity = raw[start:start + IDENTITY_SIZE]
    if len(identity) != IDENTITY_SIZE:
        return None, _unrecognised("the header ends %d bytes into the "
                                   "identities" % len(identity))
    return bytes(identity), None


def local_identity(project_path, device_name, application_name):
    """The 32 bytes of this working copy's .bootinfo_guids. (bytes, None) or
    (None, problem)."""
    folder = os.path.dirname(safe_str(project_path))
    stem = os.path.splitext(os.path.basename(safe_str(project_path)))[0]
    prefix = "%s.%s.%s." % (stem, device_name, application_name)
    shown = os.path.join(folder, prefix + "<guid>" + GUIDS_SUFFIX)
    found = candidates(folder, prefix)
    if not found:
        return None, ("there is no %s. Without it and its %s the IDE "
                      "downloads the whole application on a Keep login, "
                      "without asking; %s" % (shown, COMPILEINFO_SUFFIX,
                                              DOWNLOAD))
    if len(found) > 1:
        return None, ("there are %d files matching %s: %s. Which one the IDE "
                      "goes by is not something cdsint guesses; %s"
                      % (len(found), shown, ", ".join(found), DOWNLOAD))
    return _guids_of(found[0])


def candidates(folder, prefix):
    """The .bootinfo_guids files in folder for this prefix, sorted.

    A directory listing rather than glob: device and application names may
    hold `[`, which glob reads as a pattern and IronPython 2.7 has no
    glob.escape for. normcase keeps glob's case rule on each platform.
    """
    if not os.path.isdir(folder):
        return []
    head = os.path.normcase(prefix)
    tail = os.path.normcase(GUIDS_SUFFIX)
    found = []
    for name in os.listdir(folder):
        folded = os.path.normcase(name)
        guid = folded[len(head):-len(tail)]
        # a guid has no dot; one with a dot is another application's file
        # whose name merely starts with this one's
        if (folded.startswith(head) and folded.endswith(tail) and guid
                and "." not in guid):
            found.append(os.path.join(folder, name))
    return sorted(found)


def differ(local, plc):
    """None when both identities agree, or the sentence saying they do not."""
    if local == plc:
        return None
    return ("this working copy's download info describes a different "
            "download than the controller holds: code %s data %s here, code "
            "%s data %s on the controller; %s"
            % (_hex(local[:HALF]), _hex(local[HALF:]), _hex(plc[:HALF]),
               _hex(plc[HALF:]), DOWNLOAD))


def judged(header, project_path, device_name, application_name):
    """The code identity as hex when the IDE will agree, or the problem.

    (hex, None) or (None, problem). The controller's side is read first:
    a header cdsint cannot read makes the local files moot.
    """
    plc, problem = app_identity(header)
    if problem:
        return None, problem
    local, problem = local_identity(project_path, device_name,
                                    application_name)
    if problem:
        return None, problem
    problem = differ(local, plc)
    if problem:
        return None, problem
    return _hex(plc[:HALF]), None


def _guids_of(path):
    """The identities in one .bootinfo_guids, with its .compileinfo there."""
    compileinfo = path[:-len(GUIDS_SUFFIX)] + COMPILEINFO_SUFFIX
    if not os.path.isfile(compileinfo):
        return None, ("%s is missing beside %s. Without it the IDE downloads "
                      "the whole application on a Keep login, without "
                      "asking; %s" % (compileinfo, path, DOWNLOAD))
    handle = open(path, "rb")
    try:
        raw = handle.read()
    finally:
        handle.close()
    if len(raw) != IDENTITY_SIZE:
        return None, ("%s holds %d bytes, not the %d of a code and a data "
                      "identity; %s" % (path, len(raw), IDENTITY_SIZE,
                                        DOWNLOAD))
    return bytes(bytearray(raw)), None


def _unrecognised(what):
    return ("the controller's Application.app header is in a layout cdsint "
            "does not recognise (%s), so it cannot tell which download the "
            "controller holds; %s" % (what, DOWNLOAD))


def _padded(offset):
    """offset rounded up to the next multiple of 4."""
    return (offset + 3) // 4 * 4


def _hex(raw):
    return "".join("%02X" % value for value in bytearray(raw))

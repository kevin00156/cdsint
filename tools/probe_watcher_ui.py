# -*- coding: utf-8 -*-
"""Acceptance launcher: put a watcher on a throwaway project, then get out.

For the real-input acceptance in docs/WATCHER.md 8. Start an IDE with

    <exe> --profile="<name>" --culture=en --runscript="<this file>"

and it builds a scratch project, writes a settings file pointing at a sync
folder beside it, arms the watcher exactly the way Project_watch.py does, and
returns. Once it has returned the IDE belongs to the user again, which is the
thing being measured: clicking File must open its menu on every attempt.

To drive an existing project instead, use tools/headless_watch.py.
Run either a second time in the same IDE and it stops the watcher.

Environment:
    CDS_PROBE_DIR        where to build (default %TEMP%\\cds-watcher-probe)
    CDS_PROBE_POUS       how many POUs to give it (default 3)
    CDS_PROBE_KEEPALIVE  "1" to park in system.delay() instead of returning.
                         Only for --noUI runs, which would otherwise exit the
                         moment the script ends. Never use it with a UI: it is
                         the very thing that makes the IDE unclickable, and
                         park() refuses when there is one.
"""
from __future__ import print_function

import os
import sys
import tempfile
import traceback

# The same three lines in every tool here: make sure this directory is
# somewhere the import system will look, then let tools/_root.py put the
# install root there. Run from a shell, `python tools/x.py` already puts this
# directory on sys.path and the check does nothing; run inside the IDE it is
# the only thing that does, because ScriptEngine hands IronPython the file and
# sys.path is the IDE's own search list. Checked rather than inserted flat, so
# one tool importing another does not stack a second copy of the same entry.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _root  # noqa: E402,F401

import headless_watch  # noqa: E402
from cds.core import settings
from cds.ide import session

PROBE_DIR = os.environ.get("CDS_PROBE_DIR",
                           os.path.join(tempfile.gettempdir(),
                                        "cds-watcher-probe"))
POU_COUNT = int(os.environ.get("CDS_PROBE_POUS", "3"))
KEEPALIVE = os.environ.get("CDS_PROBE_KEEPALIVE") == "1"

SYNC_DIR = os.path.join(PROBE_DIR, "sync")
PROJECT_PATH = os.path.join(PROBE_DIR, os.path.basename(PROBE_DIR) + ".project")


def open_or_create():
    """The scratch project, with a settings file pointing beside it."""
    for path in (PROBE_DIR, SYNC_DIR):
        if not os.path.isdir(path):
            os.makedirs(path)
    if os.path.exists(PROJECT_PATH):
        project = projects.open(PROJECT_PATH)
    else:
        project = projects.create(PROJECT_PATH)
    settings.write(settings.path_for(PROJECT_PATH),
                   {"sync_folder": SYNC_DIR})
    return project


def fill(project):
    """Give it a few POUs so export and compare have something to chew on."""
    have = set()
    for child in project.get_children():
        try:
            have.add(str(child.get_name()))
        except Exception:
            pass
    made = 0
    for index in range(POU_COUNT):
        name = "Probe%03d" % index
        if name in have:
            continue
        pou = project.create_pou(name)
        pou.textual_declaration.replace(
            "FUNCTION_BLOCK %s\nVAR\n\tcounter : INT;\nEND_VAR" % name)
        pou.textual_implementation.replace("counter := counter + %d;" % index)
        made += 1
    if made:
        project.save()
    return made


print("probe: project  " + PROJECT_PATH)
print("probe: sync dir " + SYNC_DIR)

if session.current() is not None:
    headless_watch.arm(globals())         # second run in this IDE: stop
else:
    try:
        print("probe: created %d POU(s)" % fill(open_or_create()))
    except Exception:
        print(traceback.format_exc())
    if headless_watch.arm(globals()) is not None and KEEPALIVE:
        headless_watch.park(globals())

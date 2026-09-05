# -*- coding: utf-8 -*-
"""plc connect and plc download: what the controller runs, and putting it there.

Both commands end in the same question, and it is the only one worth asking:
**is the machine running this tree?** `connect` asks it; `download` makes the
answer true first and then asks it anyway, because a download that reports
success without being read back is a claim, not a check.

This file is only the surface: the two names cds/ide/entries.py presses, the
question -y answers, and the order the steps run in. The steps themselves are
engine/plc_trip.py, reaching a controller is engine/plc_link.py, and how the
question is actually answered — the boot application, the two .crc files, the
three verdicts — is engine/plc_crc.py.

Two gates stand in front of both commands, and neither is here (SPEC D8,
6.5): the project property cds-sync-plc says whether this project allows the
action at all (cds/ide/permit.py), and -y says the caller means this call. By
the time a function in this file runs, both have been passed.

Only the headless form reaches this file, so it has no menu stub and its
flags arrive as `command_args` rather than as answers to dialogs
(cds/ide/silent.py). The exception is the download confirmation, which is a
question a person would have been asked and so goes through the same
ask_yes_no the import confirmation does.
"""
from __future__ import print_function

from engine import entry, plc_crc, unhandled
from engine.plc_trip import Trip

# The flags this run was given, put here by cds/ide/silent.py once this
# module's own code has run (silent.ARGS_GLOBAL). Defined so that importing
# the module directly — a test, a REPL — reads "no flags" instead of raising.
command_args = {}

DOWNLOAD_QUESTION = (
    "This will download the whole application to the controller: stop what "
    "is running, write the program, write the boot application so it "
    "survives a power cycle, and start it again. Online change is switched "
    "off, so the running state is lost and every init runs from the "
    "beginning.\n\nProceed?")


def connect():
    """Read the controller and compare what it holds against this project.

    Nothing here writes to the controller: the device-level connection
    (IScriptOnlineDevice) can list and fetch files, which is the whole of
    what this needs, whereas an application login downloads code.
    """
    unhandled.start()
    trip = a_trip("connect")
    problem = trip.reach_the_device()
    if problem:
        return trip.failed(problem)
    return trip.read_back()


def download():
    """Put this project on the controller, then read it back and check.

    The confirmation is first, before anything is resolved or connected, so
    a run without -y costs nothing and touches nothing.
    """
    unhandled.start()
    cancelled = confirm()
    if cancelled:
        return entry.result(False, cancelled, action="download",
                            crc=plc_crc.UNKNOWN)
    trip = a_trip("download")
    problem = trip.reach_the_device()
    if problem:
        return trip.failed(problem)
    problem = trip.send()
    if problem:
        return trip.failed(problem)
    return trip.read_back()


def confirm():
    """Ask the question -y answers. Returns the refusal text, or None.

    Routed through the engine's own dialog rather than reading the flag here
    because that is what makes it the same -y as import's: cds/ide/silent.py
    holds one table of dialog titles and the argument that answers each, and
    a flag read directly would not be in it (SPEC 4.2). With no -y at all
    that stand-in raises NeedsInput and this never returns; an explicit "no"
    is the case handled here.
    """
    from engine.codesys_ui import ask_yes_no
    if ask_yes_no("Confirm PLC Download", DOWNLOAD_QUESTION):
        return None
    return "PLC download cancelled: not confirmed."


def a_trip(action):
    """Both of this run's inputs from the IDE, handed to the trip.

    globals() is this body's namespace, which under cds/ide/silent.py is the
    one the stand-in `system` and the real `projects` were installed in, and
    command_args is set in it after this file has been exec'd. Read here,
    where they exist, rather than inside the trip, where they would resolve
    against an ordinary imported module and come back empty.
    """
    return Trip(action, command_args, globals())

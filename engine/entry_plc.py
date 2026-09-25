# -*- coding: utf-8 -*-
"""plc connect, download and trace: the commands that talk to a controller.

Both commands end in the same question, and it is the only one worth asking:
**is the machine running what cdsint put on it?** `download` makes the answer
true, reads it back — a download that reports success without being read back
is a claim, not a check — and writes down what it left there. `connect`
measures the same two things again and compares them with that record. The
one step that differs between the two is `remember`, and it is visible below
for that reason.

`trace` leans on the same answer: it records only from a controller that
MATCHes, because a recording of variables from a program that is not this
working copy's cannot be read against it (SPEC 6.8).

This file is only the surface: the three names cds/ide/entries.py presses,
the question -y answers, and the order the steps run in. The steps themselves
are engine/plc_trip.py and, for trace, engine/plc_trace_setup.py (offline)
and engine/plc_trace.py (online); reaching a controller is
engine/plc_link.py, and how the question is actually answered —
why the offline CRC alone cannot answer it, what the record holds, and the
three verdicts — is engine/plc_crc.py.

Gates stand in front of the commands, and none is here (SPEC D8, 6.5): the
`plc` list in the project's settings file says whether this project allows
the action at all (cds/ide/permit.py), and for download, -y says the caller
means this call. By the time a function in this file runs, they have been
passed. trace needs no -y: it changes nothing the caller would confirm.

Only the headless form reaches this file, so it has no menu stub and its
flags arrive as `command_args` rather than as answers to dialogs
(cds/ide/silent.py). The exception is the download confirmation, which is a
question a person would have been asked and so goes through the same
ask_yes_no the import confirmation does.
"""
from __future__ import print_function

from engine import entry, plc_crc, unhandled
from engine.plc_trace import TraceTrip
from engine.plc_trip import Trip, first_problem

from cds.core import dialogs

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
    """Read the controller and compare it with the last download from here.

    Nothing here writes to the controller: the device-level connection
    (IScriptOnlineDevice) can list and fetch files, which is the whole of
    what this needs, whereas an application login downloads code.

    Nothing here writes the record either. A connect that wrote one would
    turn "I have never put anything on this machine" into "whatever is on it
    is mine", which is the one answer this command must never invent.
    """
    unhandled.start()
    trip = a_trip("connect")
    return in_order(trip, [
        trip.reach_the_device,   # build the boot application, aim the device
        trip.read_back,          # what the controller holds, and its files
    ]) or trip.verdict()


def download():
    """Put this project on the controller, read it back, and write it down.

    The confirmation is first, before anything is resolved or connected, so
    a run without -y costs nothing and touches nothing.
    """
    unhandled.start()
    cancelled = confirm()
    if cancelled:
        return entry.result(False, cancelled, action="download",
                            crc=plc_crc.UNKNOWN)
    trip = a_trip("download")
    failed = in_order(trip, [
        trip.reach_the_device,   # build the boot application, aim the device
        trip.what_it_holds,      # the CRC on the controller before this run
        trip.send,               # put this project on it
        trip.read_back,          # the CRC, the files and the archive after
        trip.landed,             # and the two CRCs are not the same
    ])
    if failed:
        return failed
    trip.remember()
    return trip.verdict()


def record():
    """Record the job's variables from a controller holding this copy's program.

    Never downloads the application, never starts or stops it, never saves
    the project; what it puts on the controller is its own trace (SPEC 6.8).

    Not called trace(): this file is exec'd into the namespace CODESYS gives
    its scripts, and `trace` is that namespace's own trace plug-in object,
    which the trip borrows by that name. A function of the same name would
    shadow it, and did.
    """
    return traced(TraceTrip(command_args, globals()))


def traced(trip):
    """The trace steps, in SPEC 6.8's order, on a trip made by the caller.

    Split from trace() so a test can hand in a trip with a fake clock and a
    fake buffer setter; record() is the only other caller.
    """
    unhandled.start()
    return in_order(trip, [
        trip.may_run,             # --gateway given, and a wait lent to us
        trip.read_the_job,        # checked again: the wire is not trusted
        trip.reach_the_device,    # aim the device at --gateway
        trip.holds_our_download,  # CRC MATCH, or point at plc download -y
        trip.the_ide_agrees,      # the IDE's download info names it too
        trip.the_program_is_unchanged,  # or Keep would download the change
        trip.find_the_period,     # the task's period, from its configuration
        trip.no_trace_of_ours,    # nothing already called cdsint_trace
        trip.make_the_trace,      # in memory only; buffers wait for step 5
        trip.recording,           # log in, names, types, memory, run state,
                                  # buffers, record, save
    ]) or trip.verdict()


def in_order(trip, steps):
    """Run steps until one reports a problem. That failure, or None.

    A list rather than a run of `problem = step(); if problem: return`,
    because the commands differ only in which steps are in the list and
    that difference is the thing worth seeing.
    """
    problem = first_problem(steps)
    return trip.failed(problem) if problem else None


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
    if ask_yes_no(dialogs.CONFIRM_PLC_DOWNLOAD, DOWNLOAD_QUESTION):
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

# -*- coding: utf-8 -*-
"""plc connect, download, trace, login and logout: the commands that talk to
a controller.

`connect` and `download` end in the same question, and it is the only one
worth asking: **is the machine running what cdsint put on it?** `download`
makes the answer true, reads it back — a download that reports success
without being read back is a claim, not a check — and writes down what it
left there. `connect` measures the same things again and compares them with
that record. The steps only a download takes are listed in download()
below, beside connect()'s two, so that the difference between the commands
is the first thing a reader sees.

`trace` leans on the same answer: it records only from a controller that
MATCHes, because a recording of variables from a program that is not this
working copy's cannot be read against it (SPEC 6.8).

`login` and `logout` are the watcher's own session with the controller. A
plain login changes nothing on it: it logs in only when nothing would be
applied, and otherwise says which --method would. A login by --method makes
that change, after the same -y a download asks for.

This file is only the surface: the names cds/ide/entries.py presses, the
question -y answers, and the order the steps run in. The steps themselves
are engine/plc_trip.py, with download's own in engine/plc_download.py,
trace's in engine/plc_trace_setup.py (offline) and engine/plc_trace.py
(online), login's and logout's in engine/plc_session.py and a --method's in
engine/plc_method.py; reaching a controller is
engine/plc_link.py, and how the question is actually answered —
why the offline CRC alone cannot answer it, what the record holds, and the
three verdicts — is engine/plc_crc.py.

Gates stand in front of the commands, and none is here (SPEC D8, 6.5): the
`plc` list in the project's settings file says whether this project allows
the action at all (cds/ide/permit.py), and for download and login --method,
-y says the caller
means this call. By the time a function in this file runs, they have been
passed. trace needs no -y: it changes nothing the caller would confirm.

connect and download are reached only in the --project form; login and
logout only in the watcher; trace in both, the watcher's through
engine/plc_trace_watch.py. Neither form is the menu,
so there is no menu stub and the flags arrive as `command_args` rather than
as answers to dialogs (cds/ide/silent.py). The exception is the confirmation
of a download or a login by --method, which is a question a person would
have been asked and so goes through the same ask_yes_no the import
confirmation does.
"""
from __future__ import print_function

from engine import entry, plc_crc, unhandled
from engine.plc_download import DownloadTrip
from engine.plc_method import MethodTrip
from engine.plc_session import SessionTrip
from engine.plc_trace import TraceTrip
from engine.plc_trace_watch import WatchedTrip
from engine.plc_trip import Trip, first_problem

from cds.core import dialogs, trace_run

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

# What plc login --method asks. The download says where it parts from the
# --project one: it does not start the application again.
LOGIN_DOWNLOAD_QUESTION = (
    "This will log in and download the whole application to the controller "
    "the device node points at: stop what is running, write the program, and "
    "write the boot application so it survives a power cycle (unless "
    "--no-boot-app). Unlike plc download, it does not start the application "
    "again: it is left stopped until plc run -y. Online change is not used, "
    "so the running state is lost and every init runs from the beginning."
    "\n\nProceed?")

ONLINE_CHANGE_QUESTION = (
    "This will log in and apply what differs by online change: the "
    "application keeps running and keeps its state, then the boot "
    "application is written so the change survives a power cycle (unless "
    "--no-boot-app). If the IDE says an online change cannot carry the "
    "change, nothing is done; it never falls back to a full download."
    "\n\nProceed?")

# Each --method's question: the dialog title -y answers, the text, and what
# a "no" cancelled.
QUESTIONS = {
    "download": (dialogs.CONFIRM_PLC_DOWNLOAD, LOGIN_DOWNLOAD_QUESTION,
                 "PLC download"),
    "online_change": (dialogs.CONFIRM_PLC_ONLINE_CHANGE,
                      ONLINE_CHANGE_QUESTION, "PLC online change"),
}

STOP_HERE = ("plc trace --stop ends a recording a watcher is holding; this "
             "run records within its own process and ends by itself")


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
    trip = a_trip(Trip, "connect")
    return in_order(trip, [
        trip.reach_the_device,   # --gateway, the device, its application
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
    trip = a_trip(DownloadTrip, "download")
    return in_order(trip, [
        trip.reach_the_device,   # --gateway, the device, its application
        trip.what_it_holds,      # the CRC on the controller before this run
        trip.send,               # put this project on it
        trip.read_back,          # the CRC, the files and the archive after
        trip.landed,             # and the two CRCs are not the same
        trip.remember,           # what it left, for a later connect
        trip.left_running,       # after the record: it does hold this
    ]) or trip.verdict()


def log_in():
    """Log the IDE's active application in, changing nothing on the
    controller (watcher only; engine/plc_session.py).

    Not login(): the IDE's script namespace this file is exec'd into is no
    place to guess which plain names are free (see record()).
    """
    unhandled.start()
    if command_args.get("method"):
        return log_in_by_method()
    trip = a_trip(SessionTrip, "login")
    return trip.run([
        trip.find_the_project,      # the project and the online API
        trip.name_the_application,  # the active application
        trip.find_the_device,       # the node, and where it points
        trip.open_session,          # the online application
        trip.not_logged_in_yet,     # or done: already logged in
        trip.nothing_to_change,     # is_uptodate, or name the --method
        trip.the_ide_agrees,        # the controller holds this download
        lambda: trip.log_in_with("Keep"),  # which therefore applies nothing
        trip.read_state,            # logged in, and the state, read back
    ])


def log_in_by_method():
    """Log in by --method download or online_change, changing the controller
    as asked and in no other way (engine/plc_method.py).

    The question is asked here, before the script run and before anything is
    resolved or connected: a run without -y costs nothing, and the dialog
    stand-in raises a BaseException that the nested run would not park.
    """
    trip = a_trip(MethodTrip, "login")
    refused = trip.known_method() or confirm(*QUESTIONS[trip.method])
    if refused:
        return trip.failed(refused)
    return trip.run([
        trip.find_the_project,      # the project and the online API
        trip.name_the_application,  # the active application
        trip.find_the_device,       # the node, and where it points
        trip.open_session,          # the online application
        trip.logged_out_first,      # a method logs in itself
        trip.method_applies,        # what changes, or why it may not
        trip.forget_the_record,     # no MATCH for what is about to change
        trip.log_in_by_method,      # Never, or Force
        trip.write_boot_application,  # unless --no-boot-app or no change
        trip.read_state,            # logged in, and the state, read back
    ])


def log_out():
    """Log the IDE's active application out (watcher only)."""
    unhandled.start()
    trip = a_trip(SessionTrip, "logout")
    return trip.run([
        trip.find_the_project,      # the project and the online API
        trip.name_the_application,  # the active application
        trip.open_session,          # the online application
        trip.still_logged_in,       # or done: nothing to log out of
        trip.log_out,
        trip.read_state,            # logged out, read back
    ])


def record():
    """Record the job's variables from a controller holding this copy's program.

    Never downloads the application, never starts or stops it, never saves
    the project; what it puts on the controller is its own trace (SPEC 6.8).

    Not called trace(): this file is exec'd into the namespace CODESYS gives
    its scripts, and `trace` is that namespace's own trace plug-in object,
    which the trip borrows by that name. A function of the same name would
    shadow it, and did.

    Which form runs is told by the wait: the --project launcher lends one
    (cds/ide/hold.py), the watcher does not, because its timer may not wait
    (SPEC D5) and its ticks poll the recording instead. --stop never gets
    here in the watcher, which answers it itself (cds/ide/watcher.py).
    """
    if command_args.get("stop"):
        return entry.result(False, "trace: " + STOP_HERE, action="trace")
    if entry.borrowed(globals(), trace_run.HOLD_GLOBAL) is None:
        return watched(WatchedTrip(command_args, globals()))
    return traced(TraceTrip(command_args, globals()))


def watched(trip):
    """The watcher's form: every check and the start, then a Recording the
    watcher polls (engine/plc_trace_watch.py). Split from record() for the
    same reason traced() is."""
    unhandled.start()
    started = trip.start()
    if isinstance(started, dict):
        return started
    return entry.recording(started, "trace: recording %s for %s s"
                           % (trip.found["trace"], trip.job["duration_s"]))


def traced(trip):
    """The trace steps, in SPEC 6.8's order, on a trip made by the caller.

    Split from record() so a test can hand in a trip with a fake clock and a
    fake buffer setter; record() is the only other caller.
    """
    unhandled.start()
    if trip.named():
        the_trace = [
            trip.take_the_named_trace,  # --name: as the project has it
            trip.find_the_period]       # of the task the trace samples in
    else:
        the_trace = [
            trip.find_the_period,     # the task's period, from its configuration
            trip.no_trace_of_ours,    # nothing already called cdsint_trace
            trip.make_the_trace]      # in memory only; buffers wait for step 5
    return in_order(trip, [
        trip.may_run,             # a wait lent to us
        trip.can_script_traces,   # the CODESYS Trace package
        trip.read_the_job,        # checked again: the wire is not trusted
        trip.reach_the_device,    # --gateway, the device, its application
        trip.holds_our_download,  # CRC MATCH, or point at plc download -y
        trip.the_ide_agrees,      # the IDE's download info names it too
        trip.the_program_is_unchanged,  # or Keep would download the change
    ] + the_trace + [
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


def confirm(title=dialogs.CONFIRM_PLC_DOWNLOAD, question=DOWNLOAD_QUESTION,
            what="PLC download"):
    """Ask the question -y answers. Returns the refusal text, or None.

    Routed through the engine's own dialog rather than reading the flag here
    because that is what makes it the same -y as import's: cds/ide/silent.py
    holds one table of dialog titles and the argument that answers each, and
    a flag read directly would not be in it (SPEC 4.2). With no -y at all
    that stand-in raises NeedsInput and this never returns; an explicit "no"
    is the case handled here.
    """
    from engine.codesys_ui import ask_yes_no
    if ask_yes_no(title, question):
        return None
    return "%s cancelled: not confirmed." % what


def a_trip(kind, action):
    """Both of this run's inputs from the IDE, handed to the trip.

    globals() is this body's namespace, which under cds/ide/silent.py is the
    one the stand-in `system` and the real `projects` were installed in, and
    command_args is set in it after this file has been exec'd. Read here,
    where they exist, rather than inside the trip, where they would resolve
    against an ordinary imported module and come back empty.
    """
    return kind(action, command_args, globals())

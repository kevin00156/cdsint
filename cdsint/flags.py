# -*- coding: utf-8 -*-
"""What you may type: one table, and the parser built from it.

Every fact about a subcommand is one row of COMMANDS: what it does, which of
the two forms it has (SPEC D2), what flags it carries, and what it is called
on the wire. Adding a command means adding a row. It used to mean editing
seven places — a help string here, a tuple of names there, an if/elif in the
flag builder, a branch in the argument packer — and the failure that came of
missing one was never "unknown command", it was a flag that parsed and then
quietly did not reach the IDE.

cdsint/refusals.py turns the table into the refusals argparse cannot make
on its own; cdsint/cli.py is what becomes of a command line that passed.
"""
from __future__ import print_function

import argparse

from cds.core import settings
from cdsint.command_row import (  # noqa: F401  the table's vocabulary
    CONFIRM, CONFIRM_IMPORT, DEFAULT_TIMEOUT_S, DEFINITION, EITHER, HEADLESS,
    JOB, KINDS, METAVAR, NAME, NO_IDE, NUMBER, PAIRS, PATH, PROMPT_RESULTS,
    PROJECT_FLAGS, PROJECT_ONLY, SWITCH, WATCHER, WORDS, Command, _dest,
    format_words, key_value)
from engine.codesys_constants import SCRIPT_VERSION


ONLY_TRACE = "Only plc trace takes it."
ONLY_DOWNLOAD = ("Only plc download changes the controller, so only it has "
                 "anything to confirm.")
ONLY_CHANGES = ("Only trace apply and trace show change a trace object, so "
                "only they have anything to confirm.")
TRACE_NAMED = "Which trace object in the project is meant."
DATA_IN_THE_IDE = ("Recorded data lives only in the IDE that recorded it: an "
                   "IDE this command starts has none, and nobody would see "
                   "a trace loaded into it.")
NOT_FOR = "Only %s takes it."
CONTROLLER_LOGIN = ("The watcher runs inside an IDE somebody is using, and "
                    "logging into a controller would take their online "
                    "session away from them (SPEC D8).")
WATCHER_NAMES = ("In the watcher it records through the login already open "
                 "in that IDE, and CODESYS adds no object to an application "
                 "that is logged in, so the trace has to exist already: name "
                 "it, or make one with trace apply while logged out.")
THROUGH_THE_LOGIN = ("In the watcher it records through the login already "
                     "open in that IDE, which chose the controller; cdsint "
                     "does not aim it anywhere else.")
STOP_ALONE = ("--stop ends the recording a watcher is holding, and takes "
              "nothing else.")
STOP_IN_THE_WATCHER = ("--stop ends a recording a watcher is holding; a "
                       "--project run records within its own process and "
                       "ends by itself.")
TRACE_ACTIONS = ("list", "job", "apply", "save", "show")
LISTS_ONLY = "trace list names every trace and takes nothing else."
WRONG_CONTROLLER = ("A controller found by the project's device name can be "
                    "the wrong one, and %s (SPEC 6.6).")

COMMANDS = {
    "installs": Command(
        "list the IDEs on this machine, and what to call each one", NO_IDE),
    "list": Command("show the IDEs that are listening", NO_IDE),
    "version": Command(
        "show which cdsint this is, where it runs from, and on what Python "
        "and Windows", NO_IDE),
    "update": Command(
        "replace this install with the newest release and put it in the "
        "menu of any IDE added since; only one irm/setup.ps1 downloaded",
        NO_IDE),
    "link": Command(
        "put this install in the Scripts menu of every IDE on this machine",
        NO_IDE,
        flags=[("--script-dir", NAME,
                "link this ScriptDir only, instead of every one found")]),
    "unlink": Command(
        "take this install out of the Scripts menu of every IDE; "
        "irm/setup.ps1 -Uninstall runs it before removing the rest",
        NO_IDE,
        flags=[("--script-dir", NAME,
                "unlink this ScriptDir only, instead of every one found")]),
    "ping": Command("check that an IDE is answering", WATCHER),
    "status": Command("show what an IDE has open right now", WATCHER),
    "stop": Command("tell a watcher to shut down", WATCHER),
    "export": Command(
        "write the project out to the sync folder", EITHER,
        flags=[("--delete-orphans", SWITCH,
                "delete the sync files with no object behind them")]),
    "import": Command(
        "read the sync folder back into the project", EITHER,
        flags=[CONFIRM_IMPORT]),
    "compare": Command(
        "report how the project and the sync folder differ", EITHER),
    "discover": Command(
        "name every object and the kind it counted as; use it when a command "
        "reports failed_objects", EITHER),
    "build": Command(
        "build the application and report the error count", EITHER,
        flags=[("--app", NAME,
                "which application to build, when there are several")]),
    "verify": Command(
        "import (-y), export, compare and build, and pass only if all agree",
        EITHER,
        flags=[("-y/--yes", CONFIRM,
                "confirm the import step; without it verify only looks and "
                "says what the import would have done")]),
    "plc": Command(
        "talk to the controller: read what it runs, download to it, or "
        "record a trace from it",
        EITHER,
        # The words the settings file's plc list allows are the actions.
        action=settings.PLC_ACTIONS,
        action_help="connect reads what the controller holds; download "
                    "writes this project to it; trace records a trace "
                    "(--stop ends one a watcher is recording)",
        flags=[("-y/--yes", CONFIRM,
                "confirm the download; only plc download takes it"),
               ("--gateway", NAME,
                "reach the controller through this address; every --project "
                "plc action needs it", "IP"),
               ("--port", NUMBER,
                "device port behind --gateway; left out, the standard "
                "CODESYS device port is used"),
               ("--gateway-name", NAME,
                "which of the IDE profile's gateways reaches --gateway; "
                "needed when the profile has more than one"),
               ("--job", JOB, "the trace job file; only plc trace takes it"),
               ("--name", NAME,
                "plc trace: record this trace object as it is configured; "
                "the job then holds only duration_s, out, formats and the "
                "judging fields"),
               ("--stop", SWITCH,
                "plc trace --target: end the recording the watcher is "
                "holding")],
        needs={
            "connect": {"gateway": WRONG_CONTROLLER
                        % "the wrong controller can answer MATCH for a "
                          "download that went to it"},
            "download": {"gateway": WRONG_CONTROLLER
                         % "a download to the wrong controller passes its "
                           "own read-back"},
            "trace": {"job": "The job file says how long to record and "
                             "where to write (SPEC 6.8)."}},
        refuses={
            "connect": {"job": ONLY_TRACE, "yes": ONLY_DOWNLOAD,
                        "name": ONLY_TRACE, "stop": ONLY_TRACE},
            "download": {"job": ONLY_TRACE, "name": ONLY_TRACE,
                         "stop": ONLY_TRACE},
            "trace": {"yes": ONLY_DOWNLOAD},
            "trace --stop": dict((dest, STOP_ALONE) for dest in
                                 ("job", "name", "gateway", "port",
                                  "gateway_name", "yes"))},
        form_needs={
            WATCHER: {"trace": {"name": WATCHER_NAMES}},
            HEADLESS: {"trace": {"gateway": WRONG_CONTROLLER
                                 % "a trace recorded from the wrong "
                                   "controller looks exactly like a right "
                                   "one"}}},
        form_refuses={
            WATCHER: {"trace": dict((dest, THROUGH_THE_LOGIN) for dest in
                                    ("gateway", "port", "gateway_name"))},
            HEADLESS: {"trace --stop": {"stop": STOP_IN_THE_WATCHER}}},
        action_forms={"connect": (HEADLESS, CONTROLLER_LOGIN),
                      "download": (HEADLESS, CONTROLLER_LOGIN)},
        variant=("stop", "--stop")),
    "trace": Command(
        "list the project's traces, or move a trace's definition or its "
        "recorded data between the project and files; touches no PLC",
        EITHER,
        action=TRACE_ACTIONS,
        action_help="list names every trace, where it is and what it "
                    "records; job writes a trace's definition to a job file; "
                    "apply "
                    "makes a trace from one; save writes what a trace "
                    "recorded; show loads a saved trace into one for a person "
                    "to see",
        flags=[("-y/--yes", CONFIRM,
                "confirm trace apply or trace show; both change a trace "
                "object"),
               ("--name", NAME, "the trace object in the project"),
               ("--out", PATH,
                "trace job: the job file to write; trace save: the output "
                "path without extension"),
               ("--job", DEFINITION,
                "trace apply: the job file to take the definition from"),
               ("--file", PATH, "trace show: the saved .trace file to load"),
               ("--formats", WORDS,
                "trace save: comma-separated from trace, csv, txt; default "
                "trace,csv"),
               ("--folder", NAME,
                "trace apply: the folder a new trace goes in; it has to "
                "exist, and an existing trace is not moved")],
        needs={
            "job": {"name": TRACE_NAMED},
            "apply": {"name": TRACE_NAMED,
                      "job": "The job file says what the trace records."},
            "save": {"name": TRACE_NAMED,
                     "out": "Where the files go, without extension."},
            "show": {"file": "The .trace file a trace save or plc trace "
                             "wrote.",
                     "name": TRACE_NAMED}},
        refuses={
            "list": dict((dest, LISTS_ONLY) for dest in
                         ("yes", "name", "out", "job", "file", "formats",
                          "folder")),
            "job": {"yes": ONLY_CHANGES, "job": NOT_FOR % "trace apply",
                    "file": NOT_FOR % "trace show",
                    "formats": NOT_FOR % "trace save",
                    "folder": NOT_FOR % "trace apply"},
            "apply": {"out": NOT_FOR % "trace job or trace save",
                      "file": NOT_FOR % "trace show",
                      "formats": NOT_FOR % "trace save"},
            "save": {"yes": ONLY_CHANGES, "job": NOT_FOR % "trace apply",
                     "file": NOT_FOR % "trace show",
                     "folder": NOT_FOR % "trace apply"},
            "show": {"out": NOT_FOR % "trace job or trace save",
                     "job": NOT_FOR % "trace apply",
                     "formats": NOT_FOR % "trace save",
                     "folder": NOT_FOR % "trace apply"}},
        action_forms={"save": (WATCHER, DATA_IN_THE_IDE),
                      "show": (WATCHER, DATA_IN_THE_IDE)}),
}

# Every attribute a parsed command line can carry, worked out from the rows
# above rather than listed again. Each subparser is given the ones it does
# NOT define, as defaults, after its own arguments are added -- and only
# those, because set_defaults overwrites the default of a matching action
# rather than filling a gap. That is what lets cdsint/cli.py read ns.project
# the same way whichever subcommand ran, instead of asking with getattr
# whether the attribute is there at all.
EVERY_ATTRIBUTE = tuple(sorted(
    set(["target", "project", "action"]) | set(PROJECT_ONLY)
    | set(dest for row in COMMANDS.values() for dest in row.dests())))


class Parser(argparse.ArgumentParser):
    """argparse, minus the abbreviations.

    There was a flag spelled like the first half of `--force-lock` until the
    version and computer stamps went (SPEC 6.7). With abbreviations on, a
    script that still passes it does not get an error: argparse reads it as
    `--force-lock` and the run goes ahead against a project another IDE may
    have open. A flag that was deleted has to be refused by name.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        argparse.ArgumentParser.__init__(self, *args, **kwargs)


def build_parser():
    parser = Parser(prog="cdsint", description="Drive a CODESYS-family IDE.")
    # The spelling people and agents try first. `cdsint version` says more;
    # this is its first line.
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + SCRIPT_VERSION)
    sub = parser.add_subparsers(dest="command", required=True,
                                parser_class=Parser)
    # In the table's order, not sorted: the table reads life-cycle first,
    # then the commands that do work, and `cdsint --help` should too.
    for name, row in COMMANDS.items():
        _build_one(sub, name, row)
    return parser


def _build_one(sub, name, row):
    """One subparser, from one row. Nothing about a command is added later."""
    command = sub.add_parser(name, help=row.summary)
    if row.action is not None:
        command.add_argument("action", choices=row.action,
                             help=row.action_help)
    command.add_argument("--timeout", type=float,
                         default=DEFAULT_TIMEOUT_S,
                         help="seconds one command step may take (default "
                              "%(default)g); also how long a busy IDE counts "
                              "as alive. With --project the process deadline "
                              "is derived from it, so a four-step verify "
                              "waits longer than this number, and a plc trace "
                              "adds its job's duration_s")
    command.add_argument("--json", action="store_true",
                         help="print the raw record instead of a summary")
    if row.form != NO_IDE:
        _forms(command, row)
    _add_flags(command, row.flags)
    command.set_defaults(**dict((name, None) for name in EVERY_ATTRIBUTE
                                if name not in row.carries()))


def _forms(command, row):
    """--target, --project, and the flags that only fit the second one.

    --target is described once, whichever form the command has. It used to be
    added twice with two help texts, and two help texts for one flag is two
    places to say what it means.
    """
    form = command.add_mutually_exclusive_group()
    form.add_argument("--target", help="instance id, or a project name of a "
                                       "watcher that is already listening")
    if row.form == WATCHER:
        return
    form.add_argument("--project", help="a .project to open in an IDE of our "
                                        "own; needs --install")
    _add_flags(command, PROJECT_FLAGS)


def _add_flags(command, flags):
    """Add one row's flags. A fourth element names the value in the help."""
    for flag in flags:
        keywords = dict(KINDS[flag[1]], help=flag[2])
        if len(flag) > METAVAR:
            keywords["metavar"] = flag[METAVAR]
        command.add_argument(*flag[0].split("/"), **keywords)


def command_args(ns):
    """Turn the parsed flags back into the args the IDE side reads.

    Indexed, not getattr-with-a-default: every subparser carries every
    attribute (EVERY_ATTRIBUTE above), so a name that is not there is a row
    and a parser that disagree, and that should be a KeyError here rather
    than a None the IDE side reads as "not said".
    """
    given = vars(ns)
    return dict((dest, given[dest]) for dest in COMMANDS[ns.command].dests())


def blank_args(name):
    """Every arg this command takes, all unsaid. What a caller starts from."""
    return dict((dest, None) for dest in COMMANDS[name].dests())


def wire_name(ns):
    """What this invocation is called between the CLI and the IDE side."""
    if COMMANDS[ns.command].action is None:
        return ns.command
    return "%s %s" % (ns.command, ns.action)

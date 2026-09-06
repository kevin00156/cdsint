# -*- coding: utf-8 -*-
"""What you may type, and which combinations are refused.

The shape of the command line is one subject and what to do with a parsed
one is another, so this is the whole of the first: the subcommands, the
flags each carries, how a flag becomes an argument the IDE side reads, and
the three combinations that are answered with a reason instead of a run.

Every refusal here is a decision somebody made once, and the message says
which one. "unrecognized arguments" would be shorter and would send the
reader looking for a typo they did not make.

cdsint/cli.py is the other half.
"""
from __future__ import print_function

import argparse

from cdsint import target
from cdsint.exits import Failure

DEFAULT_TIMEOUT_S = target.DEFAULT_TIMEOUT_S

_HELP = {
    "installs": "list the IDEs on this machine, and what to call each one",
    "list": "show the IDEs that are listening",
    "ping": "check that an IDE is answering",
    "status": "show what an IDE has open right now",
    "export": "write the project out to the sync folder",
    "import": "read the sync folder back into the project",
    "compare": "report how the project and the sync folder differ",
    "discover": "name every object and the kind it counted as; use it when "
                "a command reports failed_objects",
    "build": "build the application and report the error count",
    "verify": "import (-y), export, compare and build, and pass only if all "
              "agree",
    "plc": "talk to the controller: read what it runs, or download to it",
    "stop": "tell a watcher to shut down",
}

# Commands that need an IDE with the project open, in either form.
BOTH_FORMS = ("export", "import", "compare", "discover", "build", "verify")
# Commands about a watcher's life, which only the --target form has.
WATCHER_ONLY = ("ping", "status", "stop")
# The one command with only the --project form. It gets --target anyway, so
# that asking for the other form is answered with the reason rather than
# with "unrecognized arguments" (SPEC D8).
PROJECT_ONLY_COMMAND = "plc"

# Extra flags per command, and how they become the command's args. A flag left
# out arrives as None so the watcher can tell "not said" from "said no".
FLAGS = {
    "export": [("--delete-orphans", "delete the sync files with no object behind them")],
    "import": [("--yes", "confirm the import; without it the watcher asks")],
    "build": [("--app", "which application to build, when there are several")],
    "verify": [("--yes", "confirm the import step; without it verify only "
                         "looks and says what the import would have done")],
    "plc": [("--yes", "confirm the download; connect never needs it")],
}

# Only meaningful when we start the IDE ourselves. --answer is among them
# because the prompts it answers are the IDE's own, and in the --target form
# there is a person sitting in front of that IDE to answer them.
PROJECT_ONLY = ("install", "profile", "report", "force_lock", "sync_dir",
                "answer")


class Parser(argparse.ArgumentParser):
    """argparse, minus the abbreviations.

    `--force` was a flag until the version and computer stamps went (SPEC
    6.7). With abbreviations on, a script that still passes it does not get
    an error -- argparse reads it as `--force-lock` and the run goes ahead
    against a project another IDE may have open. A flag that was deleted has
    to be refused by name.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        argparse.ArgumentParser.__init__(self, *args, **kwargs)


def build_parser():
    parser = Parser(prog="cdsint", description="Drive a CODESYS-family IDE.")
    sub = parser.add_subparsers(dest="command", required=True,
                                parser_class=Parser)
    _shared(sub.add_parser("installs", help=_HELP["installs"]))
    _shared(sub.add_parser("list", help=_HELP["list"]))
    for name in WATCHER_ONLY:
        _target_flag(_shared(sub.add_parser(name, help=_HELP[name])))
    for name in BOTH_FORMS + (PROJECT_ONLY_COMMAND,):
        command = _both_forms(_shared(sub.add_parser(name, help=_HELP[name])))
        for flag, help_text in FLAGS.get(name, []):
            _add_flag(command, flag, help_text)
    _plc_arguments(sub.choices[PROJECT_ONLY_COMMAND])
    return parser


def _shared(parser):
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="seconds one command step may take (default "
                             "120); also how long a busy IDE counts as alive. "
                             "With --project the process deadline is derived "
                             "from it, so a four-step verify waits longer "
                             "than this number")
    parser.add_argument("--json", action="store_true",
                        help="print the raw record instead of a summary")
    return parser


def _target_flag(parser):
    parser.add_argument("--target", help="instance id, or a project name")
    return parser


def _both_forms(parser):
    """The two forms, and the flags that only make sense in the second one."""
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--target", help="instance id, or a project name of a "
                                       "watcher that is already listening")
    form.add_argument("--project", help="a .project to open in an IDE of our "
                                        "own; needs --install")
    parser.add_argument("--install", help="which IDE to start; `cdsint "
                                          "installs` lists them")
    parser.add_argument("--profile", help="the IDE profile name, when the "
                                          "install has more than one")
    parser.add_argument("--report", help="where to write the run's report")
    parser.add_argument("--force-lock", action="store_true",
                        help="start even though the project looks open elsewhere")
    parser.add_argument("--sync-dir",
                        help="use this folder for this run instead of the "
                             "sync_folder in the project's settings file; "
                             "nothing is written back")
    parser.add_argument("--answer", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="answer one of the IDE's own prompts; repeatable")
    return parser


def _add_flag(command, flag, help_text):
    if flag == "--app":
        return command.add_argument(flag, default=None, help=help_text)
    if flag == "--yes":
        # -y is the spelling in SPEC 4.2, and the one every other tool that
        # asks "are you sure" uses.
        return command.add_argument("-y", flag, action="store_true",
                                    default=None, help=help_text)
    return command.add_argument(flag, action="store_true", default=None,
                                help=help_text)


def _plc_arguments(parser):
    parser.add_argument("action", choices=("connect", "download"),
                        help="connect reads what the controller holds; "
                             "download writes this project to it")
    parser.add_argument("--gateway", metavar="IP",
                        help="reach the controller through this address "
                             "instead of whatever the project already holds")
    parser.add_argument("--port", type=int, default=None, metavar="N",
                        help="device port behind --gateway; left out, the "
                             "standard CODESYS device port is used")


def command_args(ns):
    """Turn the parsed flags back into the args the IDE side reads."""
    args = dict((flag.lstrip("-").replace("-", "_"),
                 getattr(ns, flag.lstrip("-").replace("-", "_")))
                for flag, _ in FLAGS.get(ns.command, []))
    if ns.command == PROJECT_ONLY_COMMAND:
        args.update({"gateway": ns.gateway, "port": ns.port})
    return args


def wire_name(ns):
    """What this invocation is called between the CLI and the IDE side.

    `plc connect` rather than `plc` with an action inside args, so that the
    two halves are separate rows in cds/ide/entries.py — one is read-only and
    one downloads to a machine, and a table that tells them apart needs no
    dispatcher to read the difference back out (SPEC 4.2).
    """
    if ns.command == PROJECT_ONLY_COMMAND:
        return "%s %s" % (ns.command, ns.action)
    return ns.command


def _only_the_project_form(parser, ns):
    """plc has one form, and the reason is worth saying out loud (SPEC D8).

    argparse could simply not offer --target here, but then asking for it
    reads as a typo. The watcher runs inside an IDE somebody is using and a
    PLC login takes their online session away from them; that is a decision,
    so it gets a sentence rather than "unrecognized arguments".
    """
    if ns.command != PROJECT_ONLY_COMMAND:
        return
    if getattr(ns, "target", None):
        parser.error(
            "plc has no --target form. The watcher runs inside an IDE "
            "somebody is using, and logging into a controller would take "
            "their online session away from them, so a PLC command starts "
            "an IDE of its own: --project P --install I (SPEC D8).")
    if not getattr(ns, "project", None):
        parser.error(
            "plc needs --project P --install I. It is the only command with "
            "no --target form, because logging into a controller from the "
            "IDE somebody is using would take their online session away "
            "from them (SPEC D8).")


def refuse_project_flags(ns):
    """A --project flag with no --project is a caller who thinks it is headless.

    Ignoring it would run the command against somebody's open IDE while the
    caller believed it was driving one of its own.
    """
    given = [name for name in PROJECT_ONLY if getattr(ns, name, None)]
    if given:
        raise Failure("--%s only works with --project"
                      % given[0].replace("_", "-"))


def check(parser, ns):
    """Every refusal that belongs to the parser, in one call.

    Exit 2 rather than a Failure's exit 1: it says the flags do not go
    together, which is what argparse's own errors mean, and exit 1 is
    reserved for a command that ran and did not work.

    --sync-dir used to be refused here when it was missing, because a copy of
    a project carried the original's sync folder inside the .project. The
    settings now live in a file beside it, so a copy of the .project alone
    carries nothing and there is nothing to protect the caller from (SPEC
    4.2).
    """
    _only_the_project_form(parser, ns)

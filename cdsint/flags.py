# -*- coding: utf-8 -*-
"""What you may type: one table, and the refusals that come out of it.

Every fact about a subcommand is one row of COMMANDS: what it does, which of
the two forms it has (SPEC D2), what flags it carries, and what it is called
on the wire. Adding a command means adding a row. It used to mean editing
seven places — a help string here, a tuple of names there, an if/elif in the
flag builder, a branch in the argument packer — and the failure that came of
missing one was never "unknown command", it was a flag that parsed and then
quietly did not reach the IDE.

Every refusal here is a decision somebody made once, and the message says
which one. "unrecognized arguments" would be shorter and would send the
reader looking for a typo they did not make. All of them are exit 2, which
means "the command line itself is wrong" (SPEC 4.3): the caller's next move
is to change what they typed, not to run it again.

cdsint/cli.py is the other half.
"""
from __future__ import print_function

import argparse

# Seconds one command step may take (SPEC 4.2). The one number: the help text
# renders it with %(default)s, and both runners take it as their default, so
# there is nowhere for a second 120 to be written down and go stale.
DEFAULT_TIMEOUT_S = 120.0

# The two forms of every command (SPEC D2), plus the two that have neither.
#
#   NO_IDE     asks about this machine, not about a project: installs, list
#   WATCHER    only --target: the watcher's own life, which needs a watcher
#   EITHER     both forms, the ordinary case
#   HEADLESS   only --project, and the row says why (plc, SPEC D8). It is
#              still offered --target, so that asking for the other form is
#              answered with the reason rather than with "unrecognized"
NO_IDE = "none"
WATCHER = "target"
EITHER = "both"
HEADLESS = "project"


def key_value(text):
    """One --answer, as the (key, value) pair the IDE side wants.

    Checked here because here is where argparse checks every other flag, and
    a malformed one is a command line that will not run rather than a command
    that ran and failed: argparse answers it with exit 2, like every other
    refusal in this file (SPEC 4.3). It used to be parsed in cdsint/cli.py
    after the parser had finished, and a Failure's exit 1 said the opposite.
    """
    key, separator, value = text.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(
            "wants KEY=VALUE, not %r" % (text,))
    return (key, value)


# What shape a flag is. The kind decides both how argparse is told about it
# and what the IDE side receives; every one of them defaults to None rather
# than False or 0, so "not said" and "said no" stay different all the way
# through (cds/core/commands.py new_command). The one exception is --answer,
# whose default is an empty list because it is repeatable.
SWITCH = "switch"     # --delete-orphans
CONFIRM = "confirm"   # -y/--yes: the same flag wherever a step changes things
NAME = "name"         # --app NAME
NUMBER = "number"     # --port N
PAIRS = "pairs"       # --answer KEY=VALUE, and again for the next one

KINDS = {
    SWITCH: {"action": "store_true", "default": None},
    CONFIRM: {"action": "store_true", "default": None},
    NAME: {"default": None},
    NUMBER: {"type": int, "default": None, "metavar": "N"},
    PAIRS: {"action": "append", "default": [], "metavar": "KEY=VALUE",
            "type": key_value},
}

# A kind says how a flag is shaped; a flag may still name what its value is
# called in the help. Only --gateway does, and "IP" is what the readMe and
# SPEC 4.2 have always called it.
METAVAR = 3

def _dest(spelling):
    """What argparse calls a flag: its last long spelling, as an identifier."""
    return spelling.split("/")[-1].lstrip("-").replace("-", "_")


# -y is the spelling in SPEC 4.2 and the one every other tool that asks "are
# you sure" uses, so the flag carries both and argparse names it after the
# long one.
CONFIRM_IMPORT = ("-y/--yes", CONFIRM,
                  "confirm the import; without it the watcher asks")


class Command(object):
    """One subcommand, and everything the command line knows about it."""

    def __init__(self, summary, form, flags=(), action=None, one_form=None):
        self.summary = summary
        self.form = form
        self.flags = tuple(flags)
        # The positional argument, when the command has one. `plc` is the
        # only one: its two halves are separate rows in cds/ide/entries.py
        # because one is read-only and one writes to a machine, and a table
        # that tells them apart needs no dispatcher to read the difference
        # back out (SPEC 4.2).
        self.action = action
        # Why this command has only one form, in the words the refusal uses.
        self.one_form = one_form

    def dests(self):
        """What argparse will call each of this command's flags."""
        return [_dest(flag[0]) for flag in self.flags]

    def carries(self):
        """Every attribute this row's own subparser defines.

        Worked out from the row because the row is what _build_one reads.
        set_defaults does not fill a gap — it overwrites the default of any
        action with the same name — so a name in here that the parser also
        defines would have its declared default silently replaced, which is
        how --answer's empty list turned into None.
        """
        named = set(self.dests())
        if self.action is not None:
            named.add("action")
        if self.form != NO_IDE:
            named.add("target")
        if self.form in (EITHER, HEADLESS):
            named.add("project")
            named.update(PROJECT_ONLY)
        return named


COMMANDS = {
    "installs": Command(
        "list the IDEs on this machine, and what to call each one", NO_IDE),
    "list": Command("show the IDEs that are listening", NO_IDE),
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
        "talk to the controller: read what it runs, or download to it",
        HEADLESS,
        action=("connect", "download"),
        flags=[("-y/--yes", CONFIRM,
                "confirm the download; connect never needs it"),
               ("--gateway", NAME,
                "reach the controller through this address instead of "
                "whatever the project already holds", "IP"),
               ("--port", NUMBER,
                "device port behind --gateway; left out, the standard "
                "CODESYS device port is used")],
        one_form="The watcher runs inside an IDE somebody is using, and "
                 "logging into a controller would take their online session "
                 "away from them (SPEC D8)."),
}

# Flags that only mean something when we start the IDE ourselves. --answer is
# among them because the prompts it answers are the IDE's own, and in the
# --target form there is a person sitting in front of that IDE to answer them.
# One list, so that what the parser offers and what check() refuses without a
# --project cannot be two different sets of six names.
PROJECT_FLAGS = (
    ("--install", NAME, "which IDE to start; `cdsint installs` lists them"),
    ("--profile", NAME,
     "the IDE profile name, when the install has more than one"),
    ("--report", NAME, "where to write the run's report"),
    ("--force-lock", SWITCH,
     "start even though the project looks open elsewhere"),
    ("--sync-dir", NAME,
     "use this folder for this run instead of the sync_folder in the "
     "project's settings file; nothing is written back"),
    ("--answer", PAIRS, "answer one of the IDE's own prompts, as KEY=VALUE; "
                        "repeatable"),
)

PROJECT_ONLY = tuple(_dest(spelling)
                     for spelling, _kind, _help in PROJECT_FLAGS)

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
                             help="connect reads what the controller holds; "
                                  "download writes this project to it")
    command.add_argument("--timeout", type=float,
                         default=DEFAULT_TIMEOUT_S,
                         help="seconds one command step may take (default "
                              "%(default)g); also how long a busy IDE counts "
                              "as alive. With --project the process deadline "
                              "is derived from it, so a four-step verify "
                              "waits longer than this number")
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


def check(parser, ns):
    """Every refusal that belongs to the command line, in one call.

    All of them go through parser.error, so all of them are exit 2 (SPEC
    4.3). A Failure's exit 1 would say "the command ran and did not work",
    and nothing has run: the flags do not go together.
    """
    row = COMMANDS[ns.command]
    _one_form_only(parser, ns, row)
    _project_flags_need_a_project(parser, ns, row)


def _one_form_only(parser, ns, row):
    """A command with a single form, asked for the other one (SPEC D8).

    argparse could simply not offer --target here, but then asking for it
    reads as a typo. Which form a command has and why is a decision, so it
    gets a sentence, and the sentence is the row's.
    """
    if row.form != HEADLESS:
        return
    if ns.target:
        parser.error("%s has no --target form; it starts an IDE of its own, "
                     "so it wants --project P --install I. %s"
                     % (ns.command, row.one_form))
    if not ns.project:
        parser.error("%s needs --project P --install I. It is the only "
                     "command with no --target form. %s"
                     % (ns.command, row.one_form))


def _project_flags_need_a_project(parser, ns, row):
    """A --project flag with no --project is a caller who thinks it is headless.

    Ignoring it would run the command against somebody's open IDE while the
    caller believed it was driving one of its own.
    """
    if row.form == NO_IDE or ns.project:
        return
    said = vars(ns)
    given = [name for name in PROJECT_ONLY if said[name]]
    if given:
        parser.error("--%s only works with --project"
                     % given[0].replace("_", "-"))

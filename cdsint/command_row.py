# -*- coding: utf-8 -*-
"""What one row of the command table is: its forms, its flags' kinds, itself.

cdsint/flags.py holds the table and builds the parser from it; this is the
vocabulary the table is written in. Split off because the two change for
different reasons -- a new command is a row, a new kind of flag is here --
and together they ran past PRINCIPLES 2's limit.
"""
from __future__ import print_function

import argparse
import os

from cds.core import trace_job
from cdsint import job_file

# Seconds one command step may take (SPEC 4.2). The one number: the help text
# renders it with %(default)s, and both runners take it as their default, so
# there is nowhere for a second 120 to be written down and go stale.
DEFAULT_TIMEOUT_S = 120.0

# The two forms of every command (SPEC D2), plus the two that have neither.
#
#   NO_IDE     about this machine, not about a project: installs, list,
#              version, update, link, unlink
#   WATCHER    only --target: the watcher's own life, which needs a watcher,
#              and, through a row's action_forms, trace save and show,
#              whose data lives in the IDE somebody has open
#   EITHER     both forms, the ordinary case
#   HEADLESS   only --project, through a row's action_forms: plc connect
#              and download, which log in to a controller (SPEC D8). Still
#              offered --target, so that asking for the other form is
#              answered with the reason rather than with "unrecognized"
NO_IDE = "none"
WATCHER = "target"
EITHER = "both"
HEADLESS = "project"


# What an --answer may say: the members of the IDE's PromptResult enum, which
# are the WinForms DialogResult names. The IDE side looks the value up by
# exact name, so "yes" is not Yes -- and a name it cannot find used to be an
# exception after the IDE had started, with no report written at all.
PROMPT_RESULTS = ("OK", "Cancel", "Abort", "Retry", "Ignore", "Yes", "No")


def key_value(text):
    """One --answer, as the (key, value) pair the IDE side wants.

    Checked here because here is where argparse checks every other flag, and
    a malformed one is a command line that will not run rather than a command
    that ran and failed: argparse answers it with exit 2, like every
    refusal in cdsint/refusals.py (SPEC 4.3). It used to be parsed in
    cdsint/cli.py after the parser had finished, and a Failure's exit 1 said
    the opposite.
    """
    key, separator, value = text.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(
            "wants KEY=VALUE, not %r" % (text,))
    if value not in PROMPT_RESULTS:
        raise argparse.ArgumentTypeError(
            "%r is not a prompt answer; VALUE is one of %s"
            % (value, ", ".join(PROMPT_RESULTS)))
    return (key, value)


def format_words(text):
    """--formats, as the list of file kinds the IDE side saves.

    Checked by the same rule a job's `formats` is (cds/core/trace_job.py),
    so a word the IDE cannot save is a refused flag, exit 2, rather than a
    trace save that writes some of what was asked.
    """
    words = [word.strip() for word in text.split(",") if word.strip()]
    value, problem = trace_job.CHECKS[trace_job.FORMATS](words)
    if problem is not None:
        raise argparse.ArgumentTypeError(
            "wants %s, not %r%s" % (trace_job.FORMATS, text, problem))
    return value


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
JOB = "job"           # --job FILE: parsed here, checked once --name is known
DEFINITION = "definition"  # --job FILE, read as what to record only
PATH = "path"         # --out PATH: made absolute here, where the shell is
WORDS = "words"       # --formats csv,trace

KINDS = {
    SWITCH: {"action": "store_true", "default": None},
    CONFIRM: {"action": "store_true", "default": None},
    NAME: {"default": None},
    NUMBER: {"type": int, "default": None, "metavar": "N"},
    PAIRS: {"action": "append", "default": [], "metavar": "KEY=VALUE",
            "type": key_value},
    JOB: {"type": job_file.load, "default": None, "metavar": "FILE"},
    DEFINITION: {"type": job_file.read_definition, "default": None,
                 "metavar": "FILE"},
    # The IDE side writes and reads these, and its working directory is not
    # the shell's (cdsint/job_file.py says the same of a job's `out`).
    PATH: {"type": os.path.abspath, "default": None, "metavar": "PATH"},
    WORDS: {"type": format_words, "default": None, "metavar": "LIST"},
}

# A kind says how a flag is shaped; a flag may still name what its value is
# called in the help. Only --gateway does, and "IP" is what the reference and
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

    def __init__(self, summary, form, flags=(), action=None, needs=None,
                 refuses=None, action_forms=None, action_help=None,
                 form_needs=None, form_refuses=None, variant=None):
        self.summary = summary
        self.form = form
        self.flags = tuple(flags)
        # The positional argument, when the command has one: `plc` and
        # `trace`. Their actions are separate rows in cds/ide/entries.py
        # because each differs in its gate -- plc's in its word in the plc
        # list and whether it writes to a machine, trace's in its forms and
        # whether it changes the project -- and a table that tells them
        # apart needs no dispatcher to read the difference back out
        # (SPEC 4.2).
        self.action = action
        # {key: {dest: why}}: the flags one action cannot run without, and
        # the ones it will not take, each with the sentence that refuses.
        # The key is the action, or the action with its variant (key_of).
        self.needs = needs or {}
        self.refuses = refuses or {}
        # {action: (form, why)}: an action with fewer forms than its row,
        # and the sentence that refuses the other one.
        self.action_forms = action_forms or {}
        # What the positional says in --help: each action in a few words.
        self.action_help = action_help
        # {form: {key: {dest: why}}}: what one form adds to needs and
        # refuses. plc trace needs a --gateway headless and refuses one in
        # the watcher, which records through a login that already chose the
        # controller.
        self.form_needs = form_needs or {}
        self.form_refuses = form_refuses or {}
        # (dest, spelling): a switch that makes an action a different ask
        # with its own needs and refuses -- plc trace --stop takes nothing
        # else -- keyed "<action> <spelling>" in the tables above.
        self.variant = variant

    def form_of(self, action):
        """(this action's form, why it has only that one).

        A row with one form for all its actions is a watcher's own command,
        which is never offered --project, so there is no refusal to word.
        """
        return self.action_forms.get(action, (self.form, None))

    def key_of(self, action, said):
        """The needs/refuses key for this action as it was asked.

        Only an action whose tables name the variant has it: plc connect
        --stop is connect asked with a flag it refuses, not an ask of its
        own, and keying it "connect --stop" would find no table at all.
        """
        if not (self.variant and said.get(self.variant[0])):
            return action
        key = "%s %s" % (action, self.variant[1])
        tables = [self.needs, self.refuses] + list(
            self.form_needs.values()) + list(self.form_refuses.values())
        return key if any(key in table for table in tables) else action

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


# Flags that only mean something when we start the IDE ourselves. --answer is
# among them because the prompts it answers are the IDE's own, and in the
# --target form there is a person sitting in front of that IDE to answer them.
# One list, so that what the parser offers and what refusals.check refuses
# without a --project cannot be two different sets of six names.
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
    ("--answer", PAIRS, "answer one of the IDE's own prompts, as KEY=VALUE "
                        "with VALUE one of " + ", ".join(PROMPT_RESULTS)
                        + "; repeatable"),
)

PROJECT_ONLY = tuple(_dest(spelling)
                     for spelling, _kind, _help in PROJECT_FLAGS)

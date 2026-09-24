# -*- coding: utf-8 -*-
"""The command lines the parser accepts and cdsint still will not run.

Every refusal here is a decision somebody made once, and the message says
which one. "unrecognized arguments" would be shorter and would send the
reader looking for a typo they did not make. All of them are exit 2, which
means "the command line itself is wrong" (SPEC 4.3): the caller's next move
is to change what they typed, not to run it again. Each one is read off a
row of cdsint/flags.py COMMANDS, so a new command's refusals are part of its
row rather than a new branch here.
"""
from __future__ import print_function

from cdsint import flags


def check(parser, ns):
    """Every refusal that belongs to the command line, in one call.

    All of them go through parser.error, so all of them are exit 2 (SPEC
    4.3). A Failure's exit 1 would say "the command ran and did not work",
    and nothing has run: the flags do not go together.
    """
    row = flags.COMMANDS[ns.command]
    _one_form_only(parser, ns, row)
    _project_flags_need_a_project(parser, ns, row)
    _action_flags(parser, ns, row)


def _one_form_only(parser, ns, row):
    """A command with a single form, asked for the other one (SPEC D8).

    argparse could simply not offer --target here, but then asking for it
    reads as a typo. Which form a command has and why is a decision, so it
    gets a sentence, and the sentence is the row's.
    """
    if row.form != flags.HEADLESS:
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
    if row.form == flags.NO_IDE or ns.project:
        return
    said = vars(ns)
    given = [name for name in flags.PROJECT_ONLY if said[name]]
    if given:
        parser.error("--%s only works with --project"
                     % given[0].replace("_", "-"))


def _action_flags(parser, ns, row):
    """A flag one action cannot run without, or one it will not take.

    Refused rather than ignored: a -y the trace never reads would tell the
    caller it had confirmed something, and a --job on connect would read as
    a trace that silently did not happen.
    """
    said = vars(ns)
    for dest, why in row.needs.get(ns.action, {}).items():
        if not said[dest]:
            parser.error("%s %s needs --%s. %s"
                         % (ns.command, ns.action, dest, why))
    for dest, why in row.refuses.get(ns.action, {}).items():
        if said[dest]:
            parser.error("%s %s does not take --%s. %s"
                         % (ns.command, ns.action, dest, why))

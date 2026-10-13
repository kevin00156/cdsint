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

import argparse

from cdsint import flags, job_file


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
    _check_the_job(parser, ns)


def _one_form_only(parser, ns, row):
    """A command or action with a single form, asked for the other one.

    argparse could simply not offer the other form, but then asking for it
    reads as a typo. Which form a command has and why is a decision, so it
    gets a sentence, and the sentence is the row's: plc connect and download
    have only --project (SPEC D8), trace save and show only --target.
    """
    form, why = row.form_of(ns.action)
    shown = flags.wire_name(ns)
    if form == flags.WATCHER and ns.project:
        parser.error("%s has no --project form; it works on an IDE somebody "
                     "has open, so it wants --target. %s" % (shown, why))
    if form != flags.HEADLESS:
        return
    if ns.target:
        parser.error("%s has no --target form; it starts an IDE of its own, "
                     "so it wants --project P --install I. %s"
                     % (shown, why))
    if not ns.project:
        parser.error("%s needs --project P --install I. It is the only "
                     "command with no --target form. %s" % (shown, why))


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
    key = row.key_of(ns.action, said)
    form = flags.HEADLESS if ns.project else flags.WATCHER
    for dest, why in _merged(row.needs, row.form_needs, form, key).items():
        if not said[dest]:
            parser.error("%s %s needs --%s. %s"
                         % (ns.command, key, _spelled(dest), why))
    for dest, why in _merged(row.refuses, row.form_refuses, form,
                             key).items():
        if said[dest]:
            parser.error("%s %s does not take --%s. %s"
                         % (ns.command, key, _spelled(dest), why))


def _merged(table, by_form, form, key):
    """The row's table for `key`, with what this form adds to it.

    The key is the action as it was asked (Command.key_of), so plc trace
    --stop has a table of its own; the form is the one this command line
    runs in, since plc trace needs --gateway in one and refuses it in the
    other.
    """
    merged = dict(table.get(key, {}))
    merged.update(by_form.get(form, {}).get(key, {}))
    return merged


def _spelled(dest):
    return dest.replace("_", "-")


def _check_the_job(parser, ns):
    """plc trace's --job, checked now that --name is known.

    argparse only read the file (cdsint/job_file.py load): whether it may
    hold a definition depends on --name, which argparse had not seen yet.
    """
    if not isinstance(ns.job, job_file.Loaded):
        return
    try:
        ns.job = job_file.checked(ns.job, named=bool(ns.name))
    except argparse.ArgumentTypeError as exc:
        parser.error("argument --job: %s" % exc)

# -*- coding: utf-8 -*-
"""`verify`: the whole round trip in one command, with one verdict.

Four steps in the order that makes each one mean something (SPEC 4.2):

    import   the disk wins, so the IDE now holds what the text files say
    export   write it back out, so the text files hold what the IDE has
    compare  and now they must agree about every object
    build    and the result must compile

compare is the step that earns the other three. import and export each report
their own counts and each can be "ok" while quietly having done nothing; only
asking afterwards whether the IDE and the disk still differ turns the pair
into a round trip that was checked.

Without -y it stops before the first of them and runs compare alone, because
import is a step that changes the IDE and -y is how a caller says it means
that (SPEC 4.2). The supervisor found out what the other reading costs: a
verify pointed at an empty sync folder deleted 178 of a project's 229 objects
and would have gone on to export the emptiness, compare it against itself and
report a clean round trip.

Written once and given a runner, because a run through a watcher and a run
through an IDE of our own must reach the same verdict (SPEC D2).
"""
from __future__ import print_function

from cds.core import commands
from cdsint import flags

# The counts compare hands back. Any of them above zero means the IDE and the
# disk disagree about something after a full round trip, which is exactly
# what verify exists to catch.
DIFFERENCE_COUNTS = ("different", "new_in_ide", "new_on_disk", "moved")

# The order that makes each step mean something, as the docstring explains.
ORDER = ("import", "export", "compare", "build")

LOOK_ONLY = [("compare", {})]


def steps():
    """The four commands, with the answers the caller's flags already gave.

    Each step's args come from that command's own row in cdsint/flags.py, so
    a flag added to import or build arrives here unsaid rather than not at
    all. `yes` is the one this fills in, and it is not a guess on anyone's
    behalf: run() only builds these steps when the caller passed -y, so the
    engine's confirmation dialog would be asking a question already answered.
    """
    return [(name, _answered(name)) for name in ORDER]


def _answered(name):
    args = flags.blank_args(name)
    if "yes" in args:
        args["yes"] = True
    return args


# What compare calls each count, and what the import step would do with it.
PLAN = (("modified", "different"), ("new_on_disk", "new_on_disk"),
        ("delete", "new_in_ide"))


def run(runner, yes=None):
    """Run the round trip, or refuse it. Returns (results, problems).

    Empty problems is a pass. Without -y there is always a problem, because
    the run the caller asked for did not happen.
    """
    if not yes:
        return look(runner)
    results = runner.run(steps())
    return results, problems(results)


def look(runner):
    """No -y: find out what the import would have done, and do none of it.

    compare is the one step of the four that only reads, and its counts are
    the import's plan under other names — so the refusal can say what the
    caller would be agreeing to instead of just naming a missing flag.
    """
    results = runner.run(LOOK_ONLY)
    if not results or not results[-1]["ok"]:
        return results, problems(results, len(LOOK_ONLY))
    refusal = needs_yes(results[-1]["data"] or {})
    return results + [refusal], [refusal["error"]]


def needs_yes(counts):
    """The import step as it would have been, had it been allowed to run.

    Built by the same constructor every other result goes through, because
    cdsint/report.py and cdsint/cli.py read it the same way as the rest. The
    hand-written version carried seven of the twelve fields, so a reader that
    asked about `denied` got a KeyError on this one record alone.
    """
    plan = dict((name, counts.get(key) or 0) for name, key in PLAN)
    question = ("verify includes an import, so it needs -y like import does. "
                "This one would change %(modified)d object(s), create "
                "%(new_on_disk)d and delete %(delete)d from the IDE. Nothing "
                "was changed. Check those numbers against the sync folder you "
                "meant, then re-run with -y." % plan)
    return commands.new_result(
        commands.new_command("import", flags.blank_args("import")), False,
        error=question, data=plan,
        needs_input={"question": question, "arg": "yes"})


def problems(results, planned=None):
    """Everything wrong with this run, as sentences, most important first.

    A step that failed already carries its own error, so it is named once and
    briefly. The differences compare found are the finding this command is
    for, so they are spelled out.
    """
    found = []
    for result in results:
        if not result["ok"]:
            found.append("%s failed: %s" % (result["command"],
                                            result["error"]))
    ran = dict((r["command"], r) for r in results)
    if "compare" in ran and ran["compare"]["ok"]:
        found.extend(_differences(ran["compare"]["data"] or {}))
    planned = len(ORDER) if planned is None else planned
    if len(ran) < planned:
        found.append("stopped after %d of %d steps" % (len(ran), planned))
    return found


def _differences(data):
    """compare says "ok" when it finds differences — that is its job.

    For verify it is the opposite: import then export then any difference at
    all means the round trip lost or changed something, and which count it
    landed in says what kind of loss it was.
    """
    return ["the disk and the IDE still differ after the round trip: %s=%d"
            % (name, data[name])
            for name in DIFFERENCE_COUNTS if data.get(name)]

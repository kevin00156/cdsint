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

# The counts compare hands back. Any of them above zero means the IDE and the
# disk disagree about something after a full round trip, which is exactly
# what verify exists to catch.
DIFFERENCE_COUNTS = ("different", "new_in_ide", "new_on_disk", "moved")


def steps(force=None):
    """The four commands, with the answers the caller's flags already gave.

    `yes` here is not a guess on anyone's behalf: run() only builds these
    steps when the caller passed -y, so the engine's own confirmation dialog
    would be asking a question that has already been answered.
    """
    return [
        ("import", {"yes": True, "force": force}),
        ("export", {"delete_orphans": None}),
        ("compare", {}),
        ("build", {"app": None}),
    ]


LOOK_ONLY = [("compare", {})]

# What compare calls each count, and what the import step would do with it.
PLAN = (("modified", "different"), ("new_on_disk", "new_on_disk"),
        ("delete", "new_in_ide"))


def run(runner, force=None, yes=None):
    """Run the round trip, or refuse it. Returns (results, problems).

    Empty problems is a pass. Without -y there is always a problem, because
    the run the caller asked for did not happen.
    """
    if not yes:
        return look(runner)
    results = runner.run(steps(force))
    return results, problems(results)


def look(runner):
    """No -y: find out what the import would have done, and do none of it.

    compare is the one step of the four that only reads, and its counts are
    the import's plan under other names — so the refusal can say what the
    caller would be agreeing to instead of just naming a missing flag.
    """
    results = runner.run(LOOK_ONLY)
    if not results or not results[-1].get("ok"):
        return results, problems(results, len(LOOK_ONLY))
    refusal = needs_yes(results[-1].get("data") or {})
    return results + [refusal], [refusal["error"]]


def needs_yes(counts):
    """The import step as it would have been, had it been allowed to run."""
    plan = dict((name, counts.get(key) or 0) for name, key in PLAN)
    question = ("verify includes an import, so it needs -y like import does. "
                "This one would change %(modified)d object(s), create "
                "%(new_on_disk)d and delete %(delete)d from the IDE. Nothing "
                "was changed. Check those numbers against the sync folder you "
                "meant, then re-run with -y." % plan)
    return {"ok": False, "command": "import", "elapsed_s": 0.0, "messages": [],
            "data": plan, "error": question,
            "needs_input": {"question": question, "arg": "yes"}}


def problems(results, planned=None):
    """Everything wrong with this run, as sentences, most important first.

    A step that failed already carries its own error, so it is named once and
    briefly. The differences compare found are the finding this command is
    for, so they are spelled out.
    """
    found = []
    for result in results:
        if not result.get("ok"):
            found.append("%s failed: %s" % (result.get("command"),
                                            result.get("error")))
    ran = dict((r.get("command"), r) for r in results)
    if "compare" in ran and ran["compare"].get("ok"):
        found.extend(_differences(ran["compare"].get("data") or {}))
    planned = len(steps()) if planned is None else planned
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

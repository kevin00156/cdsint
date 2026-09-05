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

Written once and given a runner, because a run through a watcher and a run
through an IDE of our own must reach the same verdict (SPEC D2).
"""
from __future__ import print_function

# The counts compare hands back. Any of them above zero means the IDE and the
# disk disagree about something after a full round trip, which is exactly
# what verify exists to catch.
DIFFERENCE_COUNTS = ("different", "new_in_ide", "new_on_disk", "moved")


def steps(force=None):
    """The four commands, with the answers verify gives on the caller's behalf.

    `yes` is not a guess: importing is what verify means, and SPEC 4.2 lists
    verify without a -y of its own. Say so in the docs rather than asking a
    question whose only answer is the one that lets the command happen.
    """
    return [
        ("import", {"yes": True, "force": force}),
        ("export", {"delete_orphans": None}),
        ("compare", {}),
        ("build", {"app": None}),
    ]


def run(runner, force=None):
    """Run the four steps. Returns (results, problems); empty problems is a pass."""
    results = runner.run(steps(force))
    return results, problems(results)


def problems(results):
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
    if len(ran) < len(steps()):
        found.append("stopped after %d of %d steps" % (len(ran), len(steps())))
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

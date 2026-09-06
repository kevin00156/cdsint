# -*- coding: utf-8 -*-
"""Hold a headless IDE open with a watcher in it, so `--target` has a target.

An acceptance harness, not a product path. `cdsint <command> --project` is
how a pipeline drives an IDE nobody has open; this exists so the `--target`
half can be exercised on a machine where the only IDE anyone may start is one
this script started.

    set CDSINT_WATCH_PROJECT=<a copy of a .project>
    <exe> --profile="<name>" --noUI --runscript="<this file>"

Run it a second time in the same IDE and it stops the watcher instead.

**This is the one place system.delay() is allowed, and only under --noUI.**
SPEC D5 rules it out because it pumps repaints but not mouse and keyboard, so
a window stays on screen and cannot be clicked — that is the bug the timer
design fixed. With --noUI there is no window to freeze, and without something
holding the process the IDE exits the moment this script returns and the
watcher never gets a tick. park() refuses to run when there is a UI, so the
exception cannot escape the case that earns it.

Environment:
    CDSINT_WATCH_PROJECT   the .project to open (required)
    CDSINT_WATCH_SYNC      the sync folder (default: sync\\ beside the project).
                           It is written into the project's settings file,
                           overwriting whatever that file held.
    CDSINT_WATCH_ANSWERS   IDE prompts to pre-answer, "KEY=VALUE,KEY=VALUE".
                           A project saved by an older IDE needs
                           UpgradeProjectConfirmation=Yes, which rewrites its
                           storage format — only ever point this at a copy.
"""
from __future__ import print_function

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from cds.core import settings  # noqa: E402
from cds.ide import headless, session  # noqa: E402

POLL_MS = 200


def arm(ide_globals):
    """Start the watcher, or stop the one this IDE already has.

    Returns the watcher, or None when this run stopped one instead.
    """
    if session.current() is not None:
        session.main(ide_globals)
        print("harness: stopped the watcher")
        return None
    from engine.codesys_constants import SCRIPT_VERSION
    watcher = session.main(ide_globals, version=SCRIPT_VERSION)
    print("harness: armed as " + watcher.instance_id)
    return watcher


def park(ide_globals):
    """Hold the process open so the timer has somewhere to tick. --noUI only."""
    system = ide_globals["system"]
    if getattr(system, "ui_present", False):
        print("harness: not parking — this IDE has a UI, and parking would "
              "leave its window unclickable (SPEC D5). The watcher is armed "
              "and the script is returning, which is the whole point.")
        return False
    print("harness: parked; nothing else can use this process while it runs")
    while session.current() is not None:
        system.delay(POLL_MS)
    print("harness: watcher stopped, unparking")
    return True


def answers(raw):
    """"KEY=VALUE,KEY=VALUE" as a mapping, for headless.answer_prompts."""
    found = {}
    for pair in (raw or "").split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            found[key.strip()] = value.strip()
    return found


def main(ide_globals):
    path = os.environ.get("CDSINT_WATCH_PROJECT")
    if not path:
        print("headless_watch: set CDSINT_WATCH_PROJECT to the .project to open")
        return
    if session.current() is not None:
        arm(ide_globals)                    # second run: stop and get out
        return
    sync_dir = os.environ.get("CDSINT_WATCH_SYNC") or os.path.join(
        os.path.dirname(path), "sync")
    if not os.path.isdir(sync_dir):
        os.makedirs(sync_dir)
    # Written before the project is opened, because that is where the engine
    # reads it from: a settings file beside the .project, not a property
    # inside it (SPEC D10). It replaces whatever the project's own file said,
    # which is the point of pointing this at a throwaway copy.
    settings.write(settings.path_for(path), {"sync_folder": sync_dir})
    headless.answer_prompts(ide_globals,
                            answers(os.environ.get("CDSINT_WATCH_ANSWERS")))
    opened = headless.open_project(ide_globals, path)
    if opened is None:
        print("headless_watch: %s did not open; a prompt with no answer is "
              "the usual reason, and the keys are above" % path)
        return
    print("headless_watch: opened " + str(opened.path))
    print("headless_watch: sync dir " + sync_dir)
    if arm(ide_globals) is not None:
        park(ide_globals)


if __name__ == "__main__":
    main(globals())

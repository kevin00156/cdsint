# -*- coding: utf-8 -*-
"""The lines cdsint prints on stderr about its own install, and how often.

Two things earn a line: a release newer than this one, and an IDE whose
Scripts menu does not reach this install -- one installed after cdsint was,
usually. Both are offered, never acted on (SPEC D17): `cdsint update` and
`cdsint link` are what act.

Only an install irm/setup.ps1 downloaded is reminded. A clone is updated with
git, usually sits ahead of the newest release, and is where the tests run,
so it never reaches the network from here.

The checks run at most once a day. The newest release is kept, so its line
is printed on every command while it is true; the missing menus are printed
on the day they are checked, because an IDE somebody chose not to link would
otherwise be named on every command forever. Anything that goes wrong here
says nothing: factory machines are often offline, and a command that worked
must not fail or slow down because of a courtesy riding on it. `update` and
`link` report every failure of their own, so nothing is lost by being quiet.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import io
import json
import os
import sys
import time

from cdsint import link, release
from engine.codesys_constants import SCRIPT_VERSION

CHECK_EVERY_S = 24 * 60 * 60

# Long enough for a slow line, short enough that an offline machine whose
# firewall drops packets rather than refusing them loses little, once a day.
QUERY_TIMEOUT_S = 2.0

# The commands that have just said everything there is to say about this.
QUIET_AFTER = ("update", "link")


def _state_path():
    return os.path.join(release.home(), "update_check.json")


def _remembered():
    try:
        with io.open(_state_path(), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _remember(state):
    with io.open(_state_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def _newest(known):
    """The newest release's tag, or known when GitHub does not answer."""
    try:
        return release.latest_tag(QUERY_TIMEOUT_S)
    except (OSError, ValueError, KeyError):
        return known


def release_line(latest):
    if latest and release.is_newer(latest):
        return ("cdsint %s is out (this is %s); run `cdsint update`"
                % (latest, release.tag_of(SCRIPT_VERSION)))
    return None


def menu_line(missing):
    if not missing:
        return None
    line = ("cdsint is not in the Scripts menu of %s; run `cdsint link`"
            % ", ".join(names for names, _admin in missing))
    if any(admin for _names, admin in missing):
        line += " from an elevated shell"
    return line


def due(now):
    """The lines to print now. A failed query still counts as the day's check,
    so an offline machine pays the timeout once a day, not on every command.
    """
    state = _remembered()
    missing = []
    if now - state.get("checked", 0) >= CHECK_EVERY_S:
        state["checked"] = now
        state["latest"] = _newest(state.get("latest"))
        _remember(state)
        missing = link.unlinked()
    lines = (release_line(state.get("latest")), menu_line(missing))
    return [line for line in lines if line]


def remind(command, want_json):
    """Print what is due on stderr. Never fails the run.

    Not under --json, where a caller parses the output.
    """
    if want_json or command in QUIET_AFTER or not release.is_downloaded():
        return
    try:
        lines = due(time.time())
    except (OSError, ValueError):
        return
    for line in lines:
        print(line, file=sys.stderr)

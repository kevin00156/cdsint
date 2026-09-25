# -*- coding: utf-8 -*-
"""Whether a newer release than this one is out, and saying so.

Only an install that irm/setup.ps1 downloaded asks. A clone is updated with
git, usually sits ahead of the newest release, and is where the tests run, so
it never reaches the network from here.

The question goes to GitHub at most once a day and the answer is kept, so the
line naming a newer release is printed on every command while it is true
without a query on every command. A reminder that cannot reach GitHub says
nothing: factory machines are often offline, and a command that worked must
not fail or slow down because of a courtesy riding on it. `cdsint update`
asks the same question and reports every failure, so nothing is lost by
being quiet here.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import io
import json
import os
import re
import sys
import time
import urllib.request

from cds.ide.entries import REPO_ROOT
from engine.codesys_constants import SCRIPT_VERSION

REPO = "kevin00156/cdsint"
LATEST_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
ARCHIVE_URL = "https://github.com/%s/archive/refs/tags/%%s.zip" % REPO

CHECK_EVERY_S = 24 * 60 * 60

# Long enough for a slow line, short enough that an offline machine whose
# firewall drops packets rather than refusing them loses little, once a day.
REMIND_TIMEOUT_S = 2.0

# A release tag is "v" and SCRIPT_VERSION; the release job in
# .github/workflows/ci.yml refuses to publish any other.
_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def tag_of(version):
    return "v" + version


def parse(tag):
    """"v1.2.3" as (1, 2, 3), so that v0.10.0 sorts after v0.9.0."""
    match = _TAG.match(tag)
    if not match:
        raise ValueError("not a release tag: %r" % (tag,))
    return tuple(int(part) for part in match.groups())


def is_newer(tag):
    return parse(tag) > parse(tag_of(SCRIPT_VERSION))


def home():
    """%LOCALAPPDATA%\\cdsint: the body, and the state that outlives it.

    Read now rather than at import: tests move it. Empty off Windows, where
    there is no downloaded install to speak of.
    """
    base = os.environ.get("LOCALAPPDATA", "")
    return os.path.join(base, "cdsint") if base else ""


def body_root():
    """Where irm/setup.ps1 puts the body. setup.ps1 writes the same path.

    A directory of its own, not home() itself: home() also holds the
    registrations of the IDEs that are listening and the status window's
    position, and replacing the body must not take those with it.
    """
    return os.path.join(home(), "body") if home() else ""


def is_downloaded():
    """Is this process running from the body setup.ps1 installed?"""
    body = body_root()
    return bool(body) and (os.path.normcase(os.path.abspath(REPO_ROOT))
                           == os.path.normcase(os.path.abspath(body)))


def latest_tag(timeout):
    """The newest published release's tag. Raises OSError or ValueError."""
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "cdsint/" + SCRIPT_VERSION})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        tag = json.loads(response.read().decode("utf-8"))["tag_name"]
    parse(tag)
    return tag


def _state_path():
    return os.path.join(home(), "update_check.json")


def _remembered():
    try:
        with io.open(_state_path(), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _remember(state):
    with io.open(_state_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def newer_release(now):
    """The tag of a release newer than this one, or None. Asks once a day.

    A failed query still counts as the day's check, so an offline machine
    pays the timeout once a day rather than on every command.
    """
    state = _remembered()
    if now - state.get("checked", 0) >= CHECK_EVERY_S:
        state["checked"] = now
        try:
            state["latest"] = latest_tag(REMIND_TIMEOUT_S)
        except (OSError, ValueError, KeyError):
            pass
        _remember(state)
    latest = state.get("latest")
    return latest if latest and is_newer(latest) else None


def remind(command, want_json):
    """One line on stderr when a newer release is out. Never fails the run.

    Not under --json, where a caller parses the output, and not after
    `update`, which has just said everything there is to say.
    """
    if want_json or command == "update" or not is_downloaded():
        return
    try:
        tag = newer_release(time.time())
    except (OSError, ValueError):
        return
    if tag:
        print("cdsint %s is out (this is %s); run `cdsint update`"
              % (tag, tag_of(SCRIPT_VERSION)), file=sys.stderr)

# -*- coding: utf-8 -*-
"""Which release this is, which is newest, and where a downloaded one lives.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import json
import os
import re
import urllib.request

from cds.ide.entries import REPO_ROOT
from engine.codesys_constants import SCRIPT_VERSION

REPO = "kevin00156/cdsint"
LATEST_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
ARCHIVE_URL = "https://github.com/%s/archive/refs/tags/%%s.zip" % REPO

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

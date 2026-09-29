# -*- coding: utf-8 -*-
"""Which release this is, which is newest, and where a downloaded one lives.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import http.client
import json
import os
import re
import urllib.request

from cds.ide.entries import REPO_ROOT
from engine.codesys_constants import SCRIPT_VERSION

REPO = "kevin00156/cdsint"
LATEST_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
# The release job in .github/workflows/ci.yml archives the commit the tests
# passed on and publishes it with its SHA-256 beside it, as ASSET % tag and
# ASSET % tag + ".sha256". GitHub's own archive of a tag is whatever the tag
# points at when somebody asks, and comes with nothing to check it against.
DOWNLOAD_URL = "https://github.com/%s/releases/download" % REPO
ASSET = "cdsint-%s.zip"

# A release tag is "v" and SCRIPT_VERSION; the release job in
# .github/workflows/ci.yml refuses to publish any other.
_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# What asking GitHub can raise: a network that failed below HTTP, a response
# cut short or garbled above it (IncompleteRead is not an OSError), or an
# answer that is not a release.
QUERY_ERRORS = (OSError, ValueError, http.client.HTTPException)


def asset_url(tag):
    return "%s/%s/%s" % (DOWNLOAD_URL, tag, ASSET % tag)


def tag_of(version):
    return "v" + version


def parse(tag):
    """"v1.2.3" as (1, 2, 3), so that v0.10.0 sorts after v0.9.0."""
    match = _TAG.match(tag) if isinstance(tag, str) else None
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
    """The newest published release's tag. Raises one of QUERY_ERRORS."""
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "cdsint/" + SCRIPT_VERSION})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        answer = json.loads(response.read().decode("utf-8"))
    tag = answer.get("tag_name") if isinstance(answer, dict) else None
    parse(tag)
    return tag

# -*- coding: utf-8 -*-
"""Print one release's CHANGELOG section, after checking the tag is that release.

The release job in .github/workflows/ci.yml runs this on every pushed tag and
publishes what it prints. It refuses, and so nothing is published, when the
tag is not "v" plus SCRIPT_VERSION -- `cdsint update` compares tags against
that number, so a release whose tag says something else would be offered
forever or never -- and when the CHANGELOG has no dated section for it, which
is what an "Unreleased" heading still is.

Usage:
    python tools/release_notes.py v0.1.0 > notes.md
"""
from __future__ import print_function

import io
import os
import re
import sys

# The same three lines in every tool here; tools/cache_doctor.py says why.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _root  # noqa: E402,F401

from engine.codesys_constants import SCRIPT_VERSION  # noqa: E402

CHANGELOG = os.path.join(_root.INSTALL_ROOT, "CHANGELOG.md")

# "### 0.0.1 (2026-09-22) — moved into cdsint": the version, then its date.
_HEADING = re.compile(r"^### (\d+\.\d+\.\d+) \(\d{4}-\d{2}-\d{2}\)")


def section(text, version):
    """The lines under version's dated heading, up to the next heading."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(1) == version:
            break
    else:
        raise ValueError("CHANGELOG.md has no dated heading for %s" % version)
    body = []
    for line in lines[start + 1:]:
        if line.startswith("### ") or line == "---":
            break
        body.append(line)
    return "\n".join(body).strip() + "\n"


def notes(tag, text):
    if tag != "v" + SCRIPT_VERSION:
        raise ValueError("tag %s is not v%s, the version in "
                         "engine/codesys_constants.py" % (tag, SCRIPT_VERSION))
    return section(text, SCRIPT_VERSION)


def main(argv):
    with io.open(CHANGELOG, encoding="utf-8") as handle:
        text = handle.read()
    try:
        sys.stdout.write(notes(argv[1], text))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

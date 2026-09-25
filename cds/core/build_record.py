# -*- coding: utf-8 -*-
"""Which library list each application was last built with (SPEC 6.9, Build).

After a library changes, build() can answer "application is up to date, 0
errors" for code it did not compile (docs/library-manager-research.md 5.2).
So a build cleans first whenever an application's list differs from the one
recorded here. Local state, like sync_cache.json: losing it costs one clean
build and nothing else.
"""
from __future__ import print_function

import binascii
import io
import json
import os

SUFFIX = ".cdsint-build.json"


def path_for(project_path):
    """`Line.project` keeps its record in `Line.cdsint-build.json` beside it."""
    return os.path.splitext(project_path)[0] + SUFFIX


def digest(text):
    """Eight hex digits that change when the text does."""
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return "%08X" % (binascii.crc32(data) & 0xFFFFFFFF)


def read(path):
    """The record, or {} when there is none worth trusting.

    An unreadable record is not an error: the worst it causes is a clean
    build that was not needed.
    """
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            found = json.load(f)
    except (IOError, OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def write(path, record):
    text = json.dumps(record, indent=2, sort_keys=True)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)

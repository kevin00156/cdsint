# -*- coding: utf-8 -*-
"""Read a `plc trace` job file into the job the IDE side is handed.

Read out here, before any IDE starts, because a job that is wrong is a
command line that will not run (SPEC 6.8): argparse turns the refusal into
exit 2, as it does for every flag it checks (cdsint/flags.py key_value).
What a job may hold is cds/core/trace_job.py's to say; this only reads the
file and resolves the one path in it.
"""
from __future__ import print_function

import argparse
import json
import os

from cds.core import trace_job


def read(path):
    """The job at `path`, every default filled in and `out` made absolute.

    Raises ArgumentTypeError, never anything else: argparse reports that one
    as a refusal of the flag, and any other exception as a traceback.
    """
    shown = os.path.abspath(path)
    job, problem = trace_job.normalise(_load(shown))
    if problem is not None:
        raise argparse.ArgumentTypeError("%s: %s" % (shown, problem))
    # The IDE side writes the files, and its working directory is not the
    # shell's (cdsint/headless.py says the same of --sync-dir), so a relative
    # `out` would land somewhere neither of them meant.
    job["out"] = os.path.abspath(job["out"])
    return job


def _load(shown):
    """What the file says, as JSON. utf-8-sig: Notepad writes a BOM."""
    try:
        with open(shown, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except OSError as exc:
        raise argparse.ArgumentTypeError(
            "%s: cannot read the job file: %s" % (shown, exc.strerror or exc))
    except ValueError as exc:
        # JSONDecodeError and UnicodeDecodeError are both ValueErrors.
        raise argparse.ArgumentTypeError(
            "%s: the job file is not JSON: %s" % (shown, exc))

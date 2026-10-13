# -*- coding: utf-8 -*-
"""Read a trace job file into what the IDE side is handed.

For `plc trace`, load() reads the file while argparse parses, and checked()
checks it once the whole command line is known, because whether it may
hold a definition depends on --name. read_definition() is `trace apply`'s,
which needs only what to record. All of it runs before any IDE starts,
because a job that is wrong is a command line that will not run (SPEC
6.8): argparse turns the refusal into exit 2, as it does for every flag it
checks (cdsint/command_row.py key_value).

What a job may hold is cds/core/trace_job.py's to say; this only reads the
file and resolves the one path in it.
"""
from __future__ import print_function

import argparse
import collections
import json
import os

from cds.core import trace_job


# A job file as argparse hands it over: read and parsed, not yet checked
# (cdsint/refusals.py checks it once --name is known).
Loaded = collections.namedtuple("Loaded", "path job")


def load(path):
    """The job file at `path`, parsed but not checked: a Loaded.

    Raises ArgumentTypeError, never anything else: argparse reports that one
    as a refusal of the flag, and any other exception as a traceback.
    """
    shown = os.path.abspath(path)
    return Loaded(shown, _load(shown))


def checked(loaded, named):
    """The job a Loaded holds, every default filled in and `out` absolute.

    named: plc trace --name, whose job is only the run (cds/core/trace_job.py
    normalise). Raises ArgumentTypeError with the file's path in front.
    """
    job, problem = trace_job.normalise(loaded.job, named=named)
    if problem is not None:
        raise argparse.ArgumentTypeError("%s: %s" % (loaded.path, problem))
    # The IDE side writes the files, and its working directory is not the
    # shell's (cdsint/headless.py says the same of --sync-dir), so a relative
    # `out` would land somewhere neither of them meant.
    job["out"] = os.path.abspath(job["out"])
    return job


def read(path):
    """The whole job at `path`: load() and checked() without a --name."""
    return checked(load(path), named=False)


def waits_s(args):
    """Seconds a step waits on purpose, on top of --timeout (SPEC 6.8).

    A trace records for its job's duration_s: time the caller asked for, not
    time lost. Both forms add it: the headless process deadline, and the
    wait for the watcher's answer. trace apply hands over a definition with
    no duration_s, which waits for nothing.
    """
    return (args.get("job") or {}).get("duration_s", 0.0)


def read_definition(path):
    """The job at `path` read as what to record only, for `trace apply`.

    A file `trace job` wrote has no duration_s and no out, and that is the
    file apply most often gets; a full job is taken too and its run fields
    dropped (cds/core/trace_job.py normalise_definition).
    """
    shown = os.path.abspath(path)
    definition, problem = trace_job.normalise_definition(_load(shown))
    if problem is not None:
        raise argparse.ArgumentTypeError("%s: %s" % (shown, problem))
    return definition


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

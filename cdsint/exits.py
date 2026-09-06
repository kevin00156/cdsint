# -*- coding: utf-8 -*-
"""Stopping a command before it can produce a result at all.

The exit codes themselves are cds/core/exits.py, because the IDE side needs
the same numbers (SPEC 6.4). What lives here is the CLI's own exception: a
Failure is what the two forms raise when there is nothing to report — no
install, no watcher, a project somebody else has open — as opposed to a
command that ran and came back with an answer, which cdsint/cli.py turns into
an exit code instead.
"""
from __future__ import print_function

import sys

from cds.core.exits import EXIT_FAILED


class Failure(Exception):
    """Something stopped a command before it could produce a result.

    Carries the exit code because the reason and the code are one decision:
    splitting them lets a caller raise "no such install" and have it printed
    as a timeout.
    """

    def __init__(self, message, code=EXIT_FAILED, lines=()):
        Exception.__init__(self, message)
        self.code = code
        self.lines = list(lines)   # the candidates, when there were any

    def report(self):
        """Print the reason and hand back the code to exit with."""
        print(str(self), file=sys.stderr)
        for line in self.lines:
            print("  " + line, file=sys.stderr)
        return self.code

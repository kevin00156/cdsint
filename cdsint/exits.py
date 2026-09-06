# -*- coding: utf-8 -*-
"""What a command's outcome is worth as an exit code (SPEC 4.3).

Both forms end here: a caller reading only the exit code has to get the same
answer whether it drove a watcher or started an IDE of its own. 2 and 4 are
the same question — "is there a usable IDE for this project" — split by cause
because an agent can do something different about each.

5 is the odd one out: nothing went wrong. This command is not in the `plc`
list in the project's settings file, and no flag of ours can stand in for
that decision, which is why it is not folded into 1 (SPEC 6.5).
"""
from __future__ import print_function

import sys

EXIT_OK = 0
EXIT_FAILED = 1        # the command failed; a missing flag counts
EXIT_TARGET = 2        # no watcher matched, or more than one did
EXIT_TIMEOUT = 3       # nobody answered in time
EXIT_HEADLESS = 4      # the project is open elsewhere, or the IDE would not start
EXIT_DENIED = 5        # the settings file's plc list does not allow this


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

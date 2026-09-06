# -*- coding: utf-8 -*-
"""What a command's outcome is worth as an exit code (SPEC 4.3).

Here rather than beside the CLI because both sides of the IDE need the same
numbers. The IDE-side script writes down the code it means to exit with and
the launcher compares that against the code the shell actually saw (SPEC
6.4); with a copy of the table on each side that comparison can pass while
the two halves disagree about what 1 means.

2 and 4 are the same question — "is there a usable IDE for this project" —
split by cause, because an agent can do something different about each.

5 is the odd one out: nothing went wrong. The command is not in the `plc`
list in the project's settings file, and no flag of ours can stand in for
that decision, which is why it is not folded into 1 (SPEC 6.5).

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

EXIT_OK = 0
EXIT_FAILED = 1     # the command failed; a missing flag counts
EXIT_TARGET = 2     # the command line is wrong: flags that do not go
                    # together, or no single live IDE to talk to
EXIT_TIMEOUT = 3    # nobody answered in time
EXIT_HEADLESS = 4   # the project is open elsewhere, or the IDE would not start
EXIT_DENIED = 5     # the settings file's plc list does not allow this

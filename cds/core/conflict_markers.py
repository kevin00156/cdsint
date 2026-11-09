# -*- coding: utf-8 -*-
"""Does a text still hold a git merge conflict nobody resolved?

Import takes the disk as the truth, so a file left mid-merge by `git pull`
would land with its markers as the object's code, and the build would then
point at the markers rather than at the unfinished merge. Plain Python on
text, so the IDE side and CI share one copy.
"""
from __future__ import print_function

OPENING = u"<<<<<<<"
CLOSING = u">>>>>>>"


def _is_marker(line, marker):
    """Git writes a marker at the start of its line, followed by a label."""
    return line == marker or line.startswith(marker + u" ")


def has_conflict(text):
    """True when a line opening a conflict is followed by one closing it.

    Both ends are asked for, at the start of a line, because ST has no
    operator spelled with seven angle brackets and a line beginning with
    one end alone could still be somebody's drawing inside a comment. The
    `=======` between them is not asked about: a row of equals signs alone
    on a line is an ordinary divider in a (* *) block.
    """
    opened = False
    for line in text.splitlines():
        if _is_marker(line, OPENING):
            opened = True
        elif opened and _is_marker(line, CLOSING):
            return True
    return False

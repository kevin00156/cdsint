# -*- coding: utf-8 -*-
"""Watching stdout go past and keeping the last of it.

An engine body's real output is print()ed, and a caller who cannot see the
IDE has no other way to it. Passing the writes through rather than capturing
them is deliberate: under --noUI they are redirected to a file the launcher
keeps, and a person watching a headless run wants to see it happening.
"""
from __future__ import print_function

import collections

from cds.core.text import as_text

TAIL_LINES = 200


class Tee(object):
    """Passes writes through to the real stdout and keeps the last lines."""

    def __init__(self, stream, max_lines=TAIL_LINES):
        self.stream = stream
        self._lines = collections.deque(maxlen=max_lines)
        self._partial = u""

    def write(self, text):
        if self.stream is not None:
            self.stream.write(text)
        parts = (self._partial + as_text(text)).split(u"\n")
        self._partial = parts.pop()
        self._lines.extend(parts)

    def flush(self):
        if self.stream is not None:
            self.stream.flush()

    def tail(self):
        lines = list(self._lines)
        if self._partial:
            lines.append(self._partial)
        return u"\n".join(lines)

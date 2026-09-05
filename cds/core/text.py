# -*- coding: utf-8 -*-
"""One answer to "make this printable", for both sides of the IDE.

Lived in three places -- cds/ide/silent.py, engine/unhandled.py and
cds/ide/headless.py -- and the third one had the checks the other way round.
SPEC D12 forbids engine/ and cds/ide/ from importing each other, so the
shared copy belongs here, in the tier both already depend on.
"""
from __future__ import print_function


def as_text(value):
    """Bytes or unicode in, unicode out. IronPython 2.7 hands back both.

    The unicode check goes first and the order is the whole point. Under
    IronPython 2.7 `str`, `bytes` and `unicode` are one type, so
    `isinstance(value, bytes)` is true for every string there. Testing bytes
    first therefore sends real text down the decode branch, and decoding
    something that is already text encodes it with the default codec first --
    which raises on anything outside ASCII. A project path with Chinese in it
    is exactly what these callers hold.
    """
    if isinstance(value, type(u"")):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return type(u"")(value)

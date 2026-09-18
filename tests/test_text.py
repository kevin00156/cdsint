# -*- coding: utf-8 -*-
"""There is one as_text, and it asks whether this is already text first.

Under IronPython 2.7 `str`, `bytes` and `unicode` are the same type, so
`isinstance(value, bytes)` is true for every string. A copy that tests bytes
before unicode therefore calls .decode() on real text, and decoding text
encodes it with the default codec first -- which raises on a path with
Chinese in it, which is what cds/ide/headless.py was holding.

CPython cannot reproduce that type collapse, so the ordering cannot be
tested by behaviour here. What can be tested is that there is only one copy
to get the order wrong in, which is why these assertions are about identity.
"""
from cds.core.text import as_text
from cds.ide import headless, silent
from engine import unhandled


def test_the_ide_side_shares_one_implementation():
    assert silent._text is as_text
    assert unhandled._text is as_text


def test_text_that_is_already_text_comes_back_untouched():
    # The IronPython-safe property: nothing decodes a unicode string.
    path = u"P:/專案/客戶/產線/Shm.project"
    assert as_text(path) is path


def test_bytes_are_decoded_as_utf8():
    assert as_text(u"客戶".encode("utf-8")) == u"客戶"


def test_the_report_keeps_none_as_none():
    # headless wraps as_text rather than repeating it: a report field with
    # nothing in it should be null, not the word "None".
    assert headless._text(None) is None
    assert headless._text(u"客戶") == u"客戶"

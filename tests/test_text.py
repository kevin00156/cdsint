# -*- coding: utf-8 -*-
"""There is one as_text, and it asks whether this is already text first.

Under IronPython 2.7 `str`, `bytes` and `unicode` are the same type, so
`isinstance(value, bytes)` is true for every string. A copy that tests bytes
before unicode therefore calls .decode() on real text, and decoding text
encodes it with the default codec first -- which raises on a path with
Chinese in it, which is what cds/ide/headless.py was holding.

CPython cannot reproduce that type collapse for real. It can get close:
shadowing `bytes` with `str` in a module's globals makes every string answer
yes to the bytes question, as it does there, and text sent down a decode
branch then fails loudly, because CPython's str has no .decode(). The tests
named "as IronPython" run that way over each module that used to ask the
question in the wrong order.

The rest is structural: there is one copy to get the order wrong in, and the
last test reads the code to keep it that way -- nothing on the IDE side but
cds/core/text.py asks whether a value is bytes.
"""
import ast
import io
import os
import zlib

import pytest

from cds.core import build_record, text, trace_period
from cds.core.text import as_text
from cds.ide import headless, silent
from engine import unhandled

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDE_SIDE = ("engine", os.path.join("cds", "ide"), os.path.join("cds", "core"),
            "stub")
THE_ONE_THAT_ASKS = "cds/core/text.py"

A_PATH = u"P:/專案/客戶/產線/Shm.project"


@pytest.fixture
def as_ironpython(monkeypatch):
    """Every string is bytes, in the modules that turn strings into text."""
    for module in (text, build_record, trace_period):
        monkeypatch.setattr(module, "bytes", str, raising=False)


def test_the_ide_side_shares_one_implementation():
    assert silent._text is as_text
    assert unhandled._text is as_text


def test_text_that_is_already_text_comes_back_untouched():
    # The IronPython-safe property: nothing decodes a unicode string.
    assert as_text(A_PATH) is A_PATH


def test_bytes_are_decoded_as_utf8():
    assert as_text(u"客戶".encode("utf-8")) == u"客戶"


def test_the_report_keeps_none_as_none():
    # headless wraps as_text rather than repeating it: a report field with
    # nothing in it should be null, not the word "None".
    assert headless._text(None) is None
    assert headless._text(u"客戶") == u"客戶"


def test_as_ironpython_text_comes_back_untouched(as_ironpython):
    assert as_text(A_PATH) is A_PATH


def test_as_ironpython_a_task_period_reads_from_text(as_ironpython):
    # trace_period used to decode anything that said it was bytes, which
    # there is the export text itself, and a task named in Chinese raised.
    xml = (u'<ExportFile><Single><Single Name="MetaObject">'
           u'<Single Name="Name">主任務</Single></Single>'
           u'<Single Name="Object"><Single Name="Kindoftask">Cyclic</Single>'
           u'<Single Name="Interval"><Single Name="Time">t#4ms</Single>'
           u'<Single Name="Unit">ms</Single></Single></Single></Single>'
           u'</ExportFile>')
    assert trace_period.task_period_us(xml, u"主任務") == (4000, None)


def test_as_ironpython_the_build_record_digests_and_writes_text(
        as_ironpython, tmp_path):
    # digest used to hand text to crc32 unencoded because it looked like
    # bytes, and write to decode json's text output for the same reason.
    listed = u"library 工具, 3.5.19.0 (System)\n"
    expected = "%08X" % (zlib.crc32(listed.encode("utf-8")) & 0xFFFFFFFF)
    path = str(tmp_path / "Line.cdsint-build.json")
    build_record.write(path, {u"應用": build_record.digest(listed)})
    assert build_record.read(path) == {u"應用": expected}


def asks_whether_bytes(path):
    """Lines where this file calls isinstance(..., bytes) in any spelling."""
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "isinstance"
            and len(node.args) == 2
            and any(getattr(name, "id", None) == "bytes"
                    for name in ast.walk(node.args[1]))]


def ide_side_sources():
    for folder in IDE_SIDE:
        for where, _dirs, files in os.walk(os.path.join(REPO_ROOT, folder)):
            for name in sorted(files):
                if name.endswith(".py"):
                    full = os.path.join(where, name)
                    yield os.path.relpath(full, REPO_ROOT).replace("\\", "/")


def test_only_as_text_asks_whether_a_value_is_bytes():
    # Under IronPython that question is true of every string, so asking it
    # anywhere but after as_text's text check is the bug above, again.
    asking = ["%s:%d" % (rel, line)
              for rel in ide_side_sources() if rel != THE_ONE_THAT_ASKS
              for line in asks_whether_bytes(os.path.join(REPO_ROOT, rel))]
    assert asking == []


def test_the_bytes_check_can_actually_see_one(tmp_path):
    guilty = tmp_path / "guilty.py"
    guilty.write_text(u"def f(v):\n    return isinstance(v, (int, bytes))\n",
                      encoding="utf-8")
    assert asks_whether_bytes(str(guilty)) == [2]

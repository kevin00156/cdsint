# -*- coding: utf-8 -*-
"""Text the IDE refuses to take is a failed import of that file, by name.

update_object_code caught whatever the write raised, logged it, and answered
False, which every caller reads as "nothing to change". An object whose
editor was locked, or whose text the IDE would not accept, reported a
successful import with the IDE as it was (PRINCIPLES 6, SPEC D13).
"""
import pytest

from engine.object_content import update_object_code
from tests.sync_bench import Bench, folder, pou


class Locked(object):
    """A text document that refuses both ways of writing it."""

    def __init__(self, text):
        self._text = text

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        raise RuntimeError("the document is read-only")

    def replace(self, value):
        raise RuntimeError("the editor is locked")


class ReadOnly(Locked):
    """Read-only .text, as on the versions that take replace() instead."""

    def replace(self, value):
        self._text = value


def test_a_refused_write_fails_the_import_by_name(monkeypatch, tmp_path):
    foo = pou("Foo")
    bench = Bench(monkeypatch, tmp_path, folder("A", foo))
    assert bench.export()["ok"]
    bench.edit("A/Foo.st", u"x := 1;", u"x := 5;")
    foo.textual_implementation = Locked(u"x := 1;")

    result = bench.import_()

    assert result["ok"] is False
    assert result["data"]["failed"] == 1
    assert result["data"]["failed_objects"] == ["A/Foo.st"]


def test_a_read_only_text_is_still_written_through_replace():
    foo = pou("Foo")
    foo.textual_implementation = ReadOnly(u"x := 1;")

    assert update_object_code(foo, None, u"x := 5;") is True
    assert foo.textual_implementation.text == u"x := 5;"


def test_text_that_already_matches_is_not_written():
    foo = pou("Foo")
    foo.textual_implementation = Locked(u"x := 1;")

    assert update_object_code(foo, None, u"x := 1;") is False

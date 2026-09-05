# -*- coding: utf-8 -*-
"""Tests for cds.ide.messages — reading the IDE's build messages.

The module's one promise is that it never raises: it runs after a build that
already has a verdict, so an exception here throws that verdict away and the
caller gets a traceback instead of the errors it asked for. That is not
hypothetical — a project holding an object whose plugin is not installed has
messages that raise on the way out of the IDE.
"""
import pytest

from cds.ide import messages


class Severity(object):
    Error = 1
    Warning = 2
    FatalError = 4
    Information = 8


class Message(object):
    """One IScriptMessage, as much of it as this module reads."""

    def __init__(self, text, severity="error", obj=None, position=None):
        self.text = text
        self.severity = severity
        self._obj = obj
        self.position = position

    @property
    def object(self):
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


class Named(object):
    def __init__(self, name):
        self._name = name

    def get_name(self):
        return self._name


def ide(*found):
    class System(object):
        def get_message_objects(self, category, wanted=None):
            return list(found)
    return {"system": System(), "Severity": Severity}


def test_the_errors_come_back_with_object_and_position():
    report = messages.build_report(ide(
        Message("C0032: cannot convert", obj=Named("MC_Main"), position=41)))
    assert report == ["error    C0032: cannot convert  (MC_Main, at 41)"]


def test_errors_sort_ahead_of_warnings():
    report = messages.build_report(ide(
        Message("later", severity="warning"), Message("first")))
    assert [line.split()[0] for line in report] == ["error", "warning"]


def test_a_message_whose_object_cannot_be_read_is_still_reported():
    # The real one: "The object GUID '...' is not valid." off .object, from a
    # project with a device whose plugin this IDE does not have. getattr's
    # default only covers AttributeError, so this used to escape.
    report = messages.build_report(ide(
        Message("C0004: duplicate", obj=RuntimeError("GUID is not valid"))))
    assert report == ["error    C0004: duplicate"]


def test_one_unreadable_message_does_not_lose_the_others():
    class Hostile(object):
        def __getattr__(self, name):
            raise RuntimeError("nothing about this message can be read")

    report = messages.build_report(ide(Hostile(), Message("C0001: real")))
    assert any("C0001: real" in line for line in report)
    assert len(report) == 2  # the hostile one is described, not dropped


def test_an_ide_that_will_not_hand_over_its_messages_gives_an_empty_report():
    class Refusing(object):
        def get_message_objects(self, category, wanted=None):
            raise RuntimeError("no message store")

    assert messages.build_report({"system": Refusing(),
                                  "Severity": Severity}) == []


def test_the_report_is_capped():
    many = [Message("C0001: line %d" % i) for i in range(500)]
    assert len(messages.build_report(ide(*many))) == messages.MAX_LINES


@pytest.mark.parametrize("position", (None, "", "-1", "0"))
def test_a_position_that_says_nothing_is_left_off(position):
    report = messages.build_report(ide(
        Message("C0001: x", obj=Named("Main"), position=position)))
    assert report == ["error    C0001: x  (Main)"]

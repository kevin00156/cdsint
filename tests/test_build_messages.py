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


# --- asking the IDE for them (engine side) ---------------------------------

def test_the_severity_mask_covers_every_kind_of_build_message():
    # Delta 1.8/1.10 and Lenze 3.24 run ScriptEngine 4.0.0.0, where both
    # overloads of get_message_objects take a severity as well as a category.
    # Asking with only the category raises "Value cannot be null. Parameter
    # name: category" and loses the whole build — measured on Delta 1.10.
    from engine.entry_build import every_severity
    assert every_severity(Severity) == (Severity.FatalError | Severity.Error
                                        | Severity.Warning
                                        | Severity.Information)


def test_a_severity_this_engine_does_not_have_is_left_out_not_guessed():
    class Older(object):
        Error = 1
        Warning = 2
    from engine.entry_build import every_severity
    assert every_severity(Older) == 3


def test_no_severities_at_all_says_so_rather_than_asking_for_nothing():
    from engine.entry_build import every_severity
    with pytest.raises(AttributeError):
        every_severity(object())


class MessageStore(object):
    """A `system` that answers the two calls entry_build makes of it."""

    def __init__(self, active=(), messages=()):
        self.active = list(active)
        self.messages = list(messages)
        self.asked = []

    def get_message_categories(self, only_active):
        return self.active

    def get_message_objects(self, category, severities):
        self.asked.append((category, severities))
        return self.messages


BUILD = "97F48D64-A2A3-4856-B640-75C046E37EA9"


def test_a_build_that_said_nothing_reports_nothing_rather_than_raising():
    # Delta 1.10: a build that recompiled nothing leaves the category
    # registered but empty, and asking it for messages raises "Value cannot
    # be null. Parameter name: category" — which lost the whole build.
    from engine.entry_build import build_messages
    store = MessageStore(active=["some-other-category"])
    assert build_messages(store, BUILD, Severity) == []
    assert store.asked == []


def test_a_category_holding_messages_is_asked_with_the_full_mask():
    from engine.entry_build import build_messages
    store = MessageStore(active=[BUILD.lower()], messages=["one"])
    assert build_messages(store, BUILD, Severity) == ["one"]
    assert store.asked == [(BUILD, Severity.FatalError | Severity.Error
                            | Severity.Warning | Severity.Information)]


class BuildingApp(object):
    """An application whose build fills the message store on the Nth call."""

    def __init__(self, store, fills_on=1):
        self.store = store
        self.fills_on = fills_on
        self.builds = 0

    def build(self):
        self.builds += 1
        if self.builds >= self.fills_on:
            self.store.active = [BUILD.lower()]
            self.store.messages = ["Compile complete"]


def test_a_build_that_said_nothing_is_tried_once_more():
    # Delta 1.10's first build() in a process does not compile: 7.4s and no
    # messages, then 31.7s with 101 warnings. A headless run only ever gets a
    # first build, so without this it reports a clean build of code the IDE
    # never compiled.
    from engine.entry_build import run_build
    store = MessageStore()
    app = BuildingApp(store, fills_on=2)
    messages, _elapsed = run_build(app, store, BUILD, Severity)
    assert app.builds == 2 and messages == ["Compile complete"]


def test_a_build_that_spoke_first_time_is_not_repeated():
    from engine.entry_build import run_build
    store = MessageStore()
    app = BuildingApp(store, fills_on=1)
    run_build(app, store, BUILD, Severity)
    assert app.builds == 1


def test_two_silent_builds_hand_back_nothing_rather_than_a_third():
    # Silence twice over is an answer — "this IDE produced no build output" —
    # and the caller is told that instead of a count it cannot trust.
    from engine.entry_build import run_build
    store = MessageStore()
    app = BuildingApp(store, fills_on=99)
    messages, _elapsed = run_build(app, store, BUILD, Severity)
    assert app.builds == 2 and messages == []

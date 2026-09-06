# -*- coding: utf-8 -*-
"""Which application `build` compiles, and when it asks.

This used to be decided by a project property the last export had written:
build offered the chooser only when that flag already said "more than one",
and refreshed the flag afterwards. So the first build after a second
application appeared skipped the chooser, compiled the active one and
reported success with --app silently doing nothing (SPEC D10 retired the
flag). The tree is walked every build now, and these are the three answers
that walk has to give.
"""
import pytest

from tests.fakes import Project

from engine import entry_build


class App(object):
    def __init__(self, name, type_guid):
        self._name = name
        self.type = type_guid

    def get_name(self):
        return self._name


class Other(object):
    def __init__(self, type_guid):
        self.type = type_guid

    def get_name(self):
        return "not an application"


class Chooser(object):
    """system.ui, remembering whether it was asked to choose."""

    def __init__(self, answer=0):
        self.asked = []
        self.answer = answer

    def choose(self, caption, options):
        self.asked.append(list(options))
        return self.answer


class System(object):
    def __init__(self, answer=0):
        self.ui = Chooser(answer)


@pytest.fixture(scope="module")
def build():
    return entry_build


@pytest.fixture(scope="module")
def guids(build):
    import sys
    return sys.modules["engine.codesys_constants"].TYPE_GUIDS


def project_with(guids, names):
    children = [Other(guids["folder"])]
    children.extend(App(name, guids["application"]) for name in names)
    return Project(children=children)


def test_one_application_is_not_a_question(build, guids):
    system = System()
    app, refused = build.choose_application(project_with(guids, ["App"]),
                                            system, None)
    assert refused is None
    assert app.get_name() == "App"
    assert system.ui.asked == []


def test_two_applications_and_no_name_is_a_question(build, guids):
    system = System(answer=1)
    app, refused = build.choose_application(
        project_with(guids, ["AppA", "AppB"]), system, None)
    assert refused is None
    assert app.get_name() == "AppB"
    assert system.ui.asked == [["AppA", "AppB"]]


def test_a_name_that_is_there_is_used_without_asking(build, guids):
    system = System()
    app, refused = build.choose_application(
        project_with(guids, ["AppA", "AppB"]), system, "AppB")
    assert refused is None
    assert app.get_name() == "AppB"
    assert system.ui.asked == []


def test_a_name_that_is_not_there_is_refused_by_name(build, guids):
    # Not "build the active one instead": --app is the caller saying which
    # application the answer is about, so building a different one and
    # reporting success is the silent failure this replaced.
    system = System()
    app, refused = build.choose_application(
        project_with(guids, ["AppA", "AppB"]), system, "AppC")
    assert app is None
    assert "AppC" in refused and "AppA" in refused and "AppB" in refused
    assert system.ui.asked == []


def test_a_project_with_no_application_says_so(build, guids):
    app, refused = build.choose_application(project_with(guids, []), System(),
                                            None)
    assert app is None
    assert "No application" in refused


def test_a_cancelled_chooser_is_not_a_build(build, guids):
    system = System(answer=-1)
    app, refused = build.choose_application(
        project_with(guids, ["AppA", "AppB"]), system, None)
    assert app is None
    assert "cancelled" in refused


def test_the_chooser_answer_may_arrive_as_a_pair(build, guids):
    # Some IDE versions hand back (index, label) rather than a bare index.
    system = System(answer=(1, "AppB"))
    app, refused = build.choose_application(
        project_with(guids, ["AppA", "AppB"]), system, None)
    assert refused is None and app.get_name() == "AppB"

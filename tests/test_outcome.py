# -*- coding: utf-8 -*-
"""Outcome.said(): the messages a result record carries (SPEC 4.3).

A success ends them with its summary, once; a failure's summary is its error
and is not repeated among them.
"""
from cds.core import commands
from cds.ide.outcome import Outcome

SUMMARY = "login: already logged in, application run; nothing was done"


def outcome(ok, messages=()):
    return Outcome(list(messages), "", result={"ok": ok, "summary": SUMMARY})


def texts(said):
    return [m["text"] for m in said]


def test_a_success_ends_with_its_summary():
    said = outcome(True, [commands.message("info", "logged in")]).said()
    assert texts(said) == ["logged in", SUMMARY]
    assert said[-1]["level"] == "info"


def test_a_summary_already_said_is_not_said_again():
    already = [commands.message("info", SUMMARY)]
    assert texts(outcome(True, already).said()) == [SUMMARY]


def test_a_failure_s_summary_stays_out_of_the_messages():
    run = outcome(False, [commands.message("warning", "the link dropped")])
    assert texts(run.said()) == ["the link dropped"]
    assert run.error_text() == SUMMARY


def test_said_leaves_the_outcome_s_own_list_alone():
    run = outcome(True)
    run.said()
    assert run.messages == []

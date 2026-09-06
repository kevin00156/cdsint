# -*- coding: utf-8 -*-
"""The two gates in front of a controller (SPEC D8, 6.5).

`plc download` is the one command in cdsint that changes a machine, so it
is the one command with a permission layer in front of it: the `plc` list
in the project's settings file says whether this project allows the action
at all, and -y says the caller means this call. Neither can stand in for
the other, and both have to hold before anything logs in — a check that
runs inside the body it guards has already let the body start.
"""
import io

from cds.core import settings
from cds.ide import entries, permit, silent
import tests.plc_fakes as plc_fakes
from tests.plc_fakes import OnlineChangeOption, PLC_BODY, ide, press
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)


# --------------------------------------------------------------------------

def test_no_settings_file_allows_nothing():
    assert permit.granted(ide(allowed=None)["projects"]) == []


def test_one_word_allows_one_action():
    assert permit.granted(ide(allowed=["connect"])["projects"]) == ["connect"]


def test_both_words_allow_both_in_the_order_spec_lists_them():
    assert permit.granted(ide(allowed=["download", "connect"])["projects"])         == ["connect", "download"]


def test_case_is_a_persons_typing_not_a_decision():
    assert permit.granted(ide(allowed=["DOWNLOAD"])["projects"]) == ["download"]


def test_a_settings_file_that_cannot_be_read_is_a_failure_not_a_refusal():
    # exit 5 tells the caller to add a word to the `plc` list, and that is
    # the wrong instruction for a file with a typo in it -- following it
    # changes nothing, because the body never runs and nothing else ever
    # reads that file. So the refusal has to be the parse error itself, with
    # no `denied`, which is exit 1 (SPEC 4.3).
    ide_globals = ide(allowed=None)
    with io.open(settings.path_for(plc_fakes.PROJECT_PATH), "w",
                 encoding="utf-8") as handle:
        handle.write(u'{"plc": ["downlaod"]}')

    outcome = press(ide_globals, "connect", {})

    assert outcome.denied is None
    assert not outcome.ok()
    assert "downlaod" in outcome.error_text()
    # And it says the real problem rather than the refusal's wording: "the
    # plc list is empty" about a file with a typo three lines up sends the
    # reader to add a word that changes nothing.
    assert "does not allow" not in outcome.error_text()
    assert ide_globals["online"].session.calls == []


def test_the_refusal_says_which_file_and_what_to_write():
    said = permit.refusal(ide(allowed=["connect"])["projects"], "download")
    assert "plc" in said
    assert '["connect", "download"]' in said          # what to set it to
    assert settings.path_for(plc_fakes.PROJECT_PATH) in said    # where


# --------------------------------------------------------------------------
# The first gate: the engine is never reached
# --------------------------------------------------------------------------

def test_a_project_that_allows_nothing_refuses_download_before_any_login():
    ide_globals = ide(allowed=None)
    outcome = press(ide_globals, "download", {"yes": True})
    assert outcome.denied == {"file": settings.path_for(plc_fakes.PROJECT_PATH),
                              "key": "plc", "action": "download"}
    assert not outcome.ok()
    assert ide_globals["online"].session.calls == []


def test_the_refused_command_does_not_even_load_the_engine(monkeypatch):
    # Stronger than "login was not called": the body is never run at all, so
    # there is no path through the engine for a future edit to open up.
    ran = []
    monkeypatch.setattr(silent, "run",
                        lambda *args, **kwargs: ran.append(args))
    press(ide(allowed=None), "download", {"yes": True})
    assert ran == []


def test_allowing_download_does_not_allow_connect():
    # Two names, two decisions. Reading a controller and writing to one are
    # not the same permission, whichever way round somebody expects.
    outcome = press(ide(allowed=["download"]), "connect", {})
    assert outcome.denied["action"] == "connect"


def test_an_allowed_command_gets_through_to_the_engine(monkeypatch):
    ran = []
    monkeypatch.setattr(silent, "run",
                        lambda *args, **kwargs: ran.append(args[2]))
    press(ide(allowed=["connect"]), "connect", {})
    assert ran == ["connect"]


def test_the_other_commands_are_not_gated(monkeypatch):
    ran = []
    monkeypatch.setattr(silent, "run",
                        lambda *args, **kwargs: ran.append(args[2]))
    entries.run(ide(allowed=None), "export", {})
    assert ran == ["main"]

# The second gate: -y
# --------------------------------------------------------------------------

def test_without_yes_the_download_asks_and_nothing_logs_in():
    ide_globals = ide(allowed=["download"])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {})
    assert outcome.needs is not None and outcome.needs.arg == "yes"
    assert ide_globals["online"].session.calls == []


def test_the_question_says_what_the_download_will_do():
    outcome = silent.run(ide(allowed=["download"]), PLC_BODY, "download", {})
    asked = outcome.needs.question.lower()
    for promised in ("stop", "boot application", "start"):
        assert promised in asked


def test_connect_never_asks_for_yes():
    # Reading a controller changes nothing, so a confirmation would be a
    # question with one useful answer.
    outcome = silent.run(ide(allowed=["connect"]), PLC_BODY, "connect", {})
    assert outcome.needs is None


def test_with_yes_the_download_is_a_full_one_and_writes_a_boot_application():
    ide_globals = ide(allowed=["download"])
    silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    calls = ide_globals["online"].session.calls
    assert [name for name, _rest in [(c[0], c[1:]) for c in calls]] == [
        "login", "create_boot_application", "start", "logout"]
    # Never an online change: the point of a download from a pipeline is that
    # every initialisation runs again.
    assert calls[0][1:] == (OnlineChangeOption.Never, False)


def test_saying_no_outright_is_not_the_same_as_not_being_asked():
    ide_globals = ide(allowed=["download"])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": False})
    assert outcome.needs is None and not outcome.ok()
    assert "cancelled" in outcome.error_text().lower()
    assert ide_globals["online"].session.calls == []


# --------------------------------------------------------------------------

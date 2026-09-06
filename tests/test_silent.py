# -*- coding: utf-8 -*-
"""Tests for cds.ide.silent — running a script with nobody at the keyboard.

The scripts under test are stand-ins written into tmp_path, shaped like the
real Project_*.py: they reach for `system` from their own globals, and they
reach for ask_yes_no through sys.modules["engine.codesys_ui"] at call time. Running
the real ones needs a real IDE, which is the hand test in the plan.
"""
import codecs
import io
import os
import re
import sys
import types

import pytest

from cds.ide import silent


class FakeSystem(object):
    def __init__(self):
        self.ui = "the real ui, which must survive"
        self.abortable = False

    def delay(self, ms):
        pass


@pytest.fixture
def ide():
    return {"system": FakeSystem(), "projects": object()}


@pytest.fixture(autouse=True)
def fake_codesys_ui():
    """Stand in for the module the scripts reload on every run.

    Autouse because silent.run now refuses to drive a body it cannot take
    the dialogs away from, and the real module needs clr, which only exists
    inside the IDE. Inside the IDE it is always importable, so every test
    here runs with it present, the way a real command does.
    """
    module = types.ModuleType("engine.codesys_ui")

    def ask_yes_no(title, message):
        raise AssertionError("a real message box was opened")

    def ask_yes_no_cancel(title, message):
        raise AssertionError("a real message box was opened")

    def show_sync_folder_dialog(*args):
        raise AssertionError("a real folder dialog was opened")

    module.ask_yes_no = ask_yes_no
    module.ask_yes_no_cancel = ask_yes_no_cancel
    module.show_sync_folder_dialog = show_sync_folder_dialog
    sys.modules["engine.codesys_ui"] = module
    yield module
    del sys.modules["engine.codesys_ui"]


def write_script(tmp_path, body, name="Project_fake.py"):
    """A stand-in body. It ends by returning a result, as the real ones do.

    Tests that care about the verdict append their own `return` to the body;
    this trailing one keeps every other test off the "returned no result"
    path, which is not what they are about.
    """
    path = tmp_path / name
    path.write_text(
        u"# -*- coding: utf-8 -*-\n"
        u"import sys\n"
        u"RAN_AS_MAIN = False\n"
        u"def main():\n" + body + u"\n"
        u"    return {'ok': True, 'summary': 'done', 'data': {}}\n"
        u"if __name__ == '__main__':\n"
        u"    RAN_AS_MAIN = True\n"
        u"    main()\n",
        encoding="utf-8")
    return str(path)


# --- the namespace ---------------------------------------------------------

def test_the_script_does_not_run_itself(tmp_path, ide):
    path = write_script(tmp_path, u"    system.ui.info('ran')")
    outcome = silent.run(ide, path, "main", {})
    assert len(outcome.messages) == 1  # once, from our call, not twice


def test_the_script_sees_the_stand_in_ui(tmp_path, ide):
    path = write_script(tmp_path, u"    system.ui.info(u'hello')")
    outcome = silent.run(ide, path, "main", {})
    assert outcome.messages == [{"level": "info", "text": u"hello"}]
    assert outcome.ok()


def test_everything_but_ui_still_reaches_the_real_system(tmp_path, ide):
    path = write_script(tmp_path, u"    system.delay(1)\n"
                                  u"    system.ui.info(str(system.abortable))")
    assert silent.run(ide, path, "main", {}).messages[0]["text"] == "False"


def test_the_real_system_is_put_back_afterwards(tmp_path, ide):
    path = write_script(tmp_path, u"    system.ui.info('x')")
    silent.run(ide, path, "main", {})
    assert ide["system"].ui == "the real ui, which must survive"


def test_a_utf8_script_with_a_coding_line_compiles(tmp_path, ide):
    # IronPython 2.7 rejects a coding declaration in unicode source, so the
    # runner compiles from bytes. Keep a non-ASCII literal here to prove it.
    path = write_script(tmp_path, u"    system.ui.info(u'\u532f\u5165\u5b8c\u6210')")
    assert silent.run(ide, path, "main", {}).messages[0]["text"] == u"匯入完成"


# --- what the script printed -----------------------------------------------

def test_stdout_is_captured_and_still_printed(tmp_path, ide, capsys):
    path = write_script(tmp_path, u"    print('line one')\n    print('line two')")
    outcome = silent.run(ide, path, "main", {})
    assert outcome.stdout_tail == "line one\nline two"
    assert "line one" in capsys.readouterr().out


def test_only_the_tail_is_kept(tmp_path, ide):
    path = write_script(tmp_path,
                        u"    for i in range(500): print('line %d' % i)")
    tail = silent.run(ide, path, "main", {}).stdout_tail.splitlines()
    assert len(tail) == silent.STDOUT_TAIL_LINES
    assert tail[-1] == "line 499"


def test_stdout_is_restored_even_when_the_script_blows_up(tmp_path, ide):
    original = sys.stdout
    path = write_script(tmp_path, u"    raise ValueError('boom')")
    outcome = silent.run(ide, path, "main", {})
    assert sys.stdout is original
    assert "boom" in outcome.error and not outcome.ok()


# --- answering the dialogs -------------------------------------------------

def yes_no_script(tmp_path, title):
    return write_script(tmp_path,
                        u"    from engine.codesys_ui import ask_yes_no\n"
                        u"    system.ui.info('answered ' + "
                        u"str(ask_yes_no(%r, 'because')))" % str(title))


def test_a_yes_no_dialog_is_answered_from_the_arguments(tmp_path, ide,
                                                        fake_codesys_ui):
    path = yes_no_script(tmp_path, "Delete Orphaned Files?")
    outcome = silent.run(ide, path, "main", {"delete_orphans": True})
    assert outcome.messages[0]["text"] == "answered True"


def test_a_yes_no_dialog_with_no_argument_takes_its_default(tmp_path, ide,
                                                            fake_codesys_ui):
    path = yes_no_script(tmp_path, "Delete Orphaned Files?")
    outcome = silent.run(ide, path, "main", {})
    assert outcome.messages[0]["text"] == "answered False"


def test_confirm_import_has_no_default_and_asks(tmp_path, ide, fake_codesys_ui):
    # Importing without being told to is exactly what must never happen.
    path = yes_no_script(tmp_path, "Confirm Import")
    outcome = silent.run(ide, path, "main", {})
    assert outcome.needs.arg == "yes"
    assert not outcome.ok()


def test_an_unknown_dialog_is_refused_rather_than_guessed(tmp_path, ide,
                                                          fake_codesys_ui):
    path = yes_no_script(tmp_path, "Some New Question")
    outcome = silent.run(ide, path, "main", {"yes": True})
    assert outcome.needs is not None
    assert "Some New Question" in outcome.needs.question


def test_the_computer_mismatch_cancels_unless_forced(tmp_path, ide,
                                                     fake_codesys_ui):
    body = (u"    from engine.codesys_ui import ask_yes_no_cancel\n"
            u"    system.ui.info(ask_yes_no_cancel("
            u"'Computer Mismatch Detected', 'm'))")
    path = write_script(tmp_path, body)
    assert silent.run(ide, path, "main", {}).messages[0]["text"] == "cancel"
    assert silent.run(ide, path, "main", {"force": True}
                      ).messages[0]["text"] == "no"


def test_the_sync_folder_dialog_is_refused_rather_than_opened(tmp_path, ide,
                                                              fake_codesys_ui):
    # It is a modal WinForms window on the IDE's own message loop. Opened
    # from a command, it would freeze the IDE until someone walked over to
    # the machine — the exact hang the stand-in UI exists to prevent.
    body = (u"    from engine.codesys_ui import show_sync_folder_dialog\n"
            u"    show_sync_folder_dialog(system, '')")
    outcome = silent.run(ide, write_script(tmp_path, body), "main", {})
    assert outcome.needs is not None
    assert "cds-sync-folder" in outcome.needs.question
    assert not outcome.ok()


def test_codesys_ui_is_put_back_afterwards(tmp_path, ide, fake_codesys_ui):
    path = yes_no_script(tmp_path, "Delete Orphaned Files?")
    silent.run(ide, path, "main", {})
    with pytest.raises(AssertionError):
        sys.modules["engine.codesys_ui"].ask_yes_no("x", "y")


def test_a_body_is_not_run_at_all_when_the_dialogs_cannot_be_taken_over(
        tmp_path, ide, monkeypatch):
    """Nothing imports codesys_ui at module level, and forget_engine wipes
    sys.modules before every command, so the runner has to load it itself.
    When it cannot, running the body anyway would open a real message box on
    the IDE's message loop and freeze the IDE."""
    monkeypatch.setattr(silent, "UI_MODULE", "engine.no_such_dialog_module")
    path = write_script(tmp_path, u"    print('this must not run')")
    outcome = silent.run(ide, path, "main", {})
    assert not outcome.ok()
    assert "could not take over" in outcome.error
    assert outcome.stdout_tail == ""
    assert not hasattr(sys.modules["__main__"], "system")


# --- the shared .pyw modules reach __main__ --------------------------------

def test_a_module_that_looks_at_main_gets_the_stand_in(tmp_path, ide):
    # codesys_utils:517 finds `system` through __main__, not through the
    # calling script's globals, so __main__ has to be swapped too.
    body = (u"    import __main__\n"
            u"    __main__.system.ui.info('through __main__')")
    path = write_script(tmp_path, body)
    assert silent.run(ide, path, "main", {}).messages[0]["text"] == \
        "through __main__"


def test_main_is_put_back_afterwards(tmp_path, ide):
    before = getattr(sys.modules["__main__"], "system", "absent")
    path = write_script(tmp_path, u"    system.ui.info('x')")
    silent.run(ide, path, "main", {})
    assert getattr(sys.modules["__main__"], "system", "absent") == before


# --- choosing an application -----------------------------------------------

def choose_script(tmp_path):
    return write_script(tmp_path,
                        u"    try:\n"
                        u"        i = system.ui.choose('pick', ['App', 'Other'])\n"
                        u"        system.ui.info('chose %d' % i)\n"
                        u"    except Exception as e:\n"
                        u"        system.ui.info('swallowed')")


def test_choose_picks_the_named_application(tmp_path, ide):
    outcome = silent.run(ide, choose_script(tmp_path), "main", {"app": "Other"})
    assert outcome.messages[0]["text"] == "chose 1"


def test_choose_without_a_name_is_not_swallowed_by_except_exception(tmp_path, ide):
    # Project_Build.py wraps the chooser in `except Exception`, which would
    # otherwise turn "you did not say which app" into a silent wrong build.
    outcome = silent.run(ide, choose_script(tmp_path), "main", {})
    assert outcome.needs is not None and outcome.needs.arg == "app"
    assert [m["text"] for m in outcome.messages] == []


def test_choose_rejects_a_name_that_is_not_there(tmp_path, ide):
    outcome = silent.run(ide, choose_script(tmp_path), "main", {"app": "Ghost"})
    assert "Ghost" in outcome.needs.question


def test_any_other_dialog_says_it_needs_a_person(tmp_path, ide):
    path = write_script(tmp_path, u"    system.ui.query_string('name?', '')")
    outcome = silent.run(ide, path, "main", {})
    assert "query_string" in outcome.needs.question


# --- the verdict is the return value (SPEC D11) ----------------------------

def returning(tmp_path, expression, said=u""):
    """A body that says `said`, then returns `expression`."""
    path = tmp_path / "Project_verdict.py"
    path.write_text(u"# -*- coding: utf-8 -*-\n"
                    u"def main():\n" + said + u"    return " + expression
                    + u"\n", encoding="utf-8")
    return str(path)


def test_a_false_result_is_a_failure_and_its_summary_is_the_error(tmp_path, ide):
    path = returning(tmp_path,
                     u"{'ok': False, 'summary': 'sync folder not set'}")
    outcome = silent.run(ide, path, "main", {})
    assert not outcome.ok()
    assert outcome.error_text() == "sync folder not set"


def test_a_true_result_is_success(tmp_path, ide):
    path = returning(tmp_path, u"{'ok': True, 'summary': 'Export complete!'}")
    outcome = silent.run(ide, path, "main", {})
    assert outcome.ok() and outcome.error_text() is None


def test_a_warning_no_longer_condemns_a_run_that_worked(tmp_path, ide):
    # This is the whole point of D11: an author who writes a harmless
    # warning mid-export used to turn a good export into exit 1.
    path = returning(tmp_path, u"{'ok': True, 'summary': 'Export complete!'}",
                     said=u"    system.ui.warning('two objects were skipped')\n")
    assert silent.run(ide, path, "main", {}).ok()


def test_an_error_message_does_not_rescue_a_run_that_failed(tmp_path, ide):
    path = returning(tmp_path, u"{'ok': False, 'summary': 'no project open'}",
                     said=u"    system.ui.error('no project open')\n")
    assert not silent.run(ide, path, "main", {}).ok()


def test_a_failure_with_no_summary_still_says_something(tmp_path, ide):
    # commands.new_result refuses to write "it failed and I don't know why".
    outcome = silent.run(ide, returning(tmp_path, u"{'ok': False}"), "main", {})
    assert not outcome.ok() and outcome.error_text()


def test_the_counts_come_back_in_data(tmp_path, ide):
    path = returning(tmp_path,
                     u"{'ok': True, 'summary': 's', 'data': {'updated': 3}}")
    assert silent.run(ide, path, "main", {}).data() == {"updated": 3}


# --- a script that gives up quietly ----------------------------------------

def test_a_script_that_returns_nothing_is_a_failure(tmp_path, ide):
    # Project_import.py used to have two give-up paths that only print(), so
    # a cancelled import came back ok=True and the caller went on to build
    # code that was never imported.
    path = returning(tmp_path, u"None", said=u"    print('Import cancelled.')\n")
    outcome = silent.run(ide, path, "main", {})
    assert not outcome.ok()
    assert "returned no result" in outcome.error_text()
    assert outcome.stdout_tail == "Import cancelled."


def test_saying_it_is_complete_is_not_enough_on_its_own(tmp_path, ide):
    # An info popup is what a person reads, not the verdict.
    path = returning(tmp_path, u"None",
                     said=u"    system.ui.info('Export complete!')\n")
    assert not silent.run(ide, path, "main", {}).ok()


# --- the dialog titles are copies of literals in four other files ----------

DRIVEN_FILES = (
    # What the commands actually execute, relative to the repo root.
    # engine/settings.py is left out on purpose: every dialog it opens sits
    # behind show_sync_folder_dialog, which the stand-in UI refuses outright
    # (test_the_sync_folder_dialog_is_refused_rather_than_opened), so silent
    # mode never reaches them.
    "engine/entry_export.py", "engine/entry_import.py",
    "engine/entry_compare.py", "engine/entry_discover.py",
    "engine/entry_build.py", "engine/entry_plc.py",
    "engine/codesys_utils.py", "engine/codesys_managers.py",
    "engine/codesys_compare_engine.py", "engine/codesys_online.py",
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def titles_asked_for(function):
    """Every literal title passed to `function` anywhere the commands reach.

    Two call shapes: `ask_yes_no("Title", ...)` and the timed one,
    `timed_prompt(ask_yes_no, "Title", ...)`, which keeps the wait for a
    person out of the sync timings (codesys_utils.timed_prompt).
    """
    pattern = re.compile(function + r'\s*[(,]\s*"([^"]+)"')
    found = set()
    for name in DRIVEN_FILES:
        path = os.path.join(REPO_ROOT, *name.split("/"))
        with io.open(path, encoding="utf-8") as handle:
            found.update(pattern.findall(handle.read()))
    return found


def test_every_yes_no_dialog_has_an_answer():
    # Nothing else keeps these two in step. Rename a title in one of those
    # files and export or import starts failing with "unexpected dialog",
    # while every test here stays green because they use stand-in scripts.
    assert titles_asked_for("ask_yes_no") <= set(silent.YES_NO)


def test_every_yes_no_cancel_dialog_has_an_answer():
    assert titles_asked_for("ask_yes_no_cancel") <= set(silent.YES_NO_CANCEL)


def test_the_answer_tables_are_not_carrying_dead_titles():
    assert set(silent.YES_NO) == titles_asked_for("ask_yes_no")
    assert set(silent.YES_NO_CANCEL) == titles_asked_for("ask_yes_no_cancel")


def test_an_unknown_yes_no_cancel_dialog_is_refused(tmp_path, ide,
                                                    fake_codesys_ui):
    body = (u"    from engine.codesys_ui import ask_yes_no_cancel\n"
            u"    ask_yes_no_cancel('Brand New Question', 'm')")
    outcome = silent.run(ide, write_script(tmp_path, body), "main", {})
    assert "Brand New Question" in outcome.needs.question


# --- the real bodies keep the contract -------------------------------------

class DeafUI(object):
    """Swallows every popup, so what is left is the return value."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class NoProjectSystem(object):
    def __init__(self):
        self.ui = DeafUI()


# entry_build.py is missing: its first line is `from System import Guid`, and
# System is the .NET one, which only exists inside the IDE. Its give-up paths
# are covered by the headless acceptance run in the plan instead.
BODIES = ("entry_export.py", "entry_import.py", "entry_compare.py",
          "entry_discover.py")


@pytest.mark.parametrize("script", BODIES)
def test_a_body_that_gives_up_still_returns_a_result(script):
    """No project open is the give-up path every body can reach from here.

    The stand-in scripts above prove the runner reads a result; this proves
    the bodies hand one back. A body that grows a bare `return` fails here
    rather than six months later, as a command that reported success and
    changed nothing.
    """
    ide = {"system": NoProjectSystem(), "projects": None}
    outcome = silent.run(ide, os.path.join(REPO_ROOT, "engine", script),
                         "main", {})
    assert isinstance(outcome.result, dict), outcome.error
    assert outcome.result["ok"] is False
    assert outcome.result["summary"]
    assert not outcome.ok()


# --- the exec path ---------------------------------------------------------

def test_a_script_saved_with_a_bom_still_compiles(tmp_path, ide):
    # Python 2's compile() chokes on a BOM, and Windows editors add them.
    path = tmp_path / "Project_bom.py"
    body = (u"# -*- coding: utf-8 -*-\n"
            u"def main():\n"
            u"    system.ui.info('past the bom')\n")
    path.write_bytes(codecs.BOM_UTF8 + body.encode("utf-8"))
    outcome = silent.run(ide, str(path), "main", {})
    assert outcome.messages[0]["text"] == "past the bom"


def test_nothing_is_running_before_or_after_a_run(tmp_path, ide):
    assert silent.running() is False
    path = write_script(tmp_path, u"    system.ui.info(str(1))")
    silent.run(ide, path, "main", {})
    assert silent.running() is False


def test_the_running_flag_is_up_inside_the_script(tmp_path, ide):
    path = write_script(tmp_path,
                        u"    import cds.ide.silent as s\n"
                        u"    system.ui.info(str(s.running()))")
    assert silent.run(ide, path, "main", {}).messages[0]["text"] == "True"

# -*- coding: utf-8 -*-
"""The probe table is a list of promises, and this is what keeps them.

perf_probe.py measures the engine by name. When the engine renames or deletes
something, the row that named it stops matching anything, `_patch_function`
returns 0, `install_probes` adds 0 to its total, and the report comes out one
row shorter than it should be. Nobody sees a hole; they see a ranking that
does not mention the function, which reads as a function that cost nothing.

Two ways a row goes stale, so both are checked: the engine no longer has that
name at all, or the class named has the method only by inheritance --
`_patch_method` reads a class's own `__dict__`, and an inherited method is
not one it can wrap.

These tests read the tables against the real engine, so the next rename fails
here rather than in a report somebody is about to draw a conclusion from.
"""
import os
import sys

import pytest

# Every engine module the tables name has to be loaded before the lookup can
# find anything: perf_probe searches sys.modules, the way it does inside the
# IDE after the entry body has pulled its imports in. The two entry bodies
# between them import the rest of the engine.
import engine.entry_export  # noqa: F401
import engine.entry_import  # noqa: F401

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import perf_probe  # noqa: E402
import perf_tables  # noqa: E402

from cds.core import settings as core_settings  # noqa: E402
from tests.fakes import Project, Projects  # noqa: E402


def test_every_row_in_the_tables_names_something_the_engine_has():
    assert perf_probe.unresolved_probes() == []


@pytest.mark.parametrize("name", [row[0] for row in perf_tables.FUNCTIONS])
def test_each_function_row_names_one_engine_function(name):
    """Named one per row so a failure says which row, not just that one broke."""
    assert perf_probe._find_function(name) is not None


@pytest.mark.parametrize("row", perf_tables.METHODS,
                         ids=[row[1] + "." + row[2] for row in perf_tables.METHODS])
def test_each_method_row_names_a_method_that_class_defines_itself(row):
    """`__dict__`, not `getattr`: the wrapper goes on the class that owns the
    method, and putting it on a subclass that merely inherits one would wrap
    the same function twice."""
    module_name, class_name, method_name = row[0], row[1], row[2]
    cls = perf_probe._find_class(module_name, class_name)
    assert cls is not None, module_name + " has no " + class_name
    assert method_name in cls.__dict__


def test_a_name_the_engine_does_not_have_is_reported(monkeypatch):
    """The mechanism itself, so a table that goes stale cannot pass quietly."""
    monkeypatch.setattr(perf_probe, "FUNCTIONS",
                        [("no_such_engine_function", "x:gone")])
    monkeypatch.setattr(perf_probe, "METHODS", [])
    assert perf_probe.unresolved_probes() == ["no_such_engine_function"]


def test_install_probes_installs_nothing_when_a_row_is_stale(monkeypatch,
                                                             capsys):
    """Refusing beats a report three rows short: the rows that go missing are
    the ones nobody thinks to look for."""
    patched = []
    monkeypatch.setattr(perf_probe, "FUNCTIONS",
                        [("no_such_engine_function", "x:gone")])
    monkeypatch.setattr(perf_probe, "METHODS", [])
    monkeypatch.setattr(perf_probe, "_patch_function",
                        lambda *args, **kwargs: patched.append(args) or 1)

    assert perf_probe.install_probes() == (0, 0)
    assert patched == []
    assert "no_such_engine_function" in capsys.readouterr().out


def test_main_does_not_run_the_operation_when_no_probes_went_in(monkeypatch,
                                                                tmp_path,
                                                                capsys):
    """import mode performs a REAL import, so refusing has to reach main().

    install_probes() returning (0, 0) on a stale table only helped as far as
    the print: main() went on to announce "0 functions", create, update, move
    and delete objects in the open project, and write a report with no rows
    in it.
    """
    from engine import entry_import, settings as engine_settings

    ran = []
    monkeypatch.setattr(perf_probe, "unresolved_probes",
                        lambda: ["no_such_engine_function"])
    monkeypatch.setattr(entry_import, "import_project",
                        lambda *args, **kwargs: ran.append(args))
    monkeypatch.setattr(engine_settings, "prepare",
                        lambda caller_globals: (core_settings.resolve({}),
                                                str(tmp_path), None))
    monkeypatch.setattr(perf_probe, "projects",
                        Projects(Project(path=str(tmp_path / "Fake.project"))),
                        raising=False)
    monkeypatch.setattr(sys, "argv", ["perf_probe.py", "import"])

    perf_probe.main()

    assert ran == []
    said = capsys.readouterr().out
    assert "no_such_engine_function" in said
    assert "Stopping" in said

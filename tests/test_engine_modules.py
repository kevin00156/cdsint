# -*- coding: utf-8 -*-
"""Forgetting the engine so the next run re-reads it (cds/core/engine_modules).

A watcher and a Scripts menu both outlive any one command, so without this an
edit to engine code needs an IDE restart to take effect. Three callers do it —
cds/ide/entries.py and the two menu stubs — and this is what they all call.
"""
import sys

import pytest

from cds.core.engine_modules import forget_engine


@pytest.fixture(autouse=True)
def engine_modules_survive():
    """Put back whatever the rest of the suite had loaded.

    This is the one test file that empties the engine out of sys.modules on
    purpose, and other test modules hold references to what was there — a
    fixture loaded it once for the whole session.
    """
    before = dict((name, module) for name, module in sys.modules.items()
                  if name.split(".")[0] == "engine")
    yield
    for name in [n for n in sys.modules if n.split(".")[0] == "engine"]:
        del sys.modules[name]
    sys.modules.update(before)


@pytest.fixture
def loaded():
    """Pretend a command has just run and left the engine in sys.modules."""
    names = ["engine", "engine.entry_export", "engine.codesys_ui"]
    for name in names:
        sys.modules[name] = object()
    return names


def test_every_engine_module_goes(loaded):
    forget_engine()
    assert [name for name in loaded if name in sys.modules] == []


def test_nothing_else_goes(loaded):
    sys.modules["engineering_notes"] = object()
    try:
        forget_engine()
        # Not a prefix match: "engineering_notes" starts with "engine" and is
        # a different package. The split is on the dot for that reason.
        assert "engineering_notes" in sys.modules
        assert "cds.core.engine_modules" in sys.modules
    finally:
        del sys.modules["engineering_notes"]


def test_it_is_fine_when_nothing_is_loaded():
    forget_engine()
    forget_engine()   # must not raise on the second pass

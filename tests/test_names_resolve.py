# -*- coding: utf-8 -*-
"""Every name the engine uses resolves, except the ones the IDE injects.

Two NameErrors got through this ticket's stage 4 and stage 5. Both were in a
branch the fake-object tests never reach, so the first anybody knew was a real
IDE answering a traceback in the middle of an import. pyflakes had been
reporting both all along, and the reason nobody saw it is that its output for
this package is dominated by the IDE globals -- `system`, `Severity`,
`PouType` -- which are genuinely undefined here and genuinely fine. A filter
wide enough to hide those was wide enough to hide a typo.

So the filter lives here instead of in somebody's shell history: the IDE
globals are listed by name, and anything else that does not resolve is a bug.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The names CODESYS puts into a running script's namespace.
IDE_GLOBALS = frozenset((
    "system", "projects", "online", "PouType", "Severity",
    "OnlineChangeOption",
))

# ...and the only files allowed to read one as a bare global: the ones the IDE
# itself executes, whose namespace those names are actually in.
#
# Everything else is handed them (engine/entry.py's borrowed()). Letting the
# whole of engine/ off would let back exactly the bug this list was written
# after: codesys_managers.py read a bare `PouType` for years, and it could
# never have resolved, because entry.lend() copies the IDE's globals onto the
# entry body and not onto the modules it calls.
def _may_read_ide_globals(rel_path):
    return (rel_path.startswith("engine/entry_")
            or rel_path.startswith("stub/")
            or rel_path.startswith("tools/")
            or rel_path == "cds/ide/headless.py")

# Python 2 built-ins that are gone in 3. The IDE side runs on IronPython 2.7
# as well (SPEC D4), so these are load-bearing there and absent here.
PYTHON_2_BUILTINS = frozenset(("unicode", "basestring", "long", "unichr"))

SCANNED = ("engine", "cds", "cdsint", "stub", "tools")


def sources():
    for folder in SCANNED:
        for where, _dirs, files in os.walk(os.path.join(REPO_ROOT, folder)):
            if "__pycache__" in where:
                continue
            for name in sorted(files):
                if name.endswith(".py"):
                    full = os.path.join(where, name)
                    yield os.path.relpath(full, REPO_ROOT).replace("\\", "/")


def undefined_in(source, rel_path):
    """What does not resolve in this source, read as if it were `rel_path`.

    Source rather than a path, so the two tests below can ask about a line
    nobody has to write into the engine and take out again.
    """
    api = pytest.importorskip("pyflakes.api")
    reporter = pytest.importorskip("pyflakes.reporter")

    class Collect(reporter.Reporter):
        def __init__(self):
            reporter.Reporter.__init__(self, io.StringIO(), io.StringIO())
            self.found = []

        def flake(self, message):
            text = str(message)
            if "undefined name" in text:
                self.found.append(text)

    collected = Collect()
    api.check(source, rel_path, collected)

    allowed = set(PYTHON_2_BUILTINS)
    if _may_read_ide_globals(rel_path):
        allowed |= IDE_GLOBALS
    return [line for line in collected.found
            if not any("'%s'" % name in line for name in allowed)]


def undefined_names(rel_path):
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        return undefined_in(handle.read(), rel_path)


@pytest.mark.parametrize("rel_path", sorted(sources()))
def test_every_name_resolves(rel_path):
    left = undefined_names(rel_path)
    assert not left, (
        "%s uses a name that is not defined and is not one the IDE injects:\n"
        "  %s" % (rel_path, "\n  ".join(left)))


READS_AN_IDE_GLOBAL = "def make():\n    return %s\n"


@pytest.mark.parametrize("name", sorted(IDE_GLOBALS))
def test_an_engine_module_may_not_read_an_ide_global(name):
    """The allowance is for the files the IDE executes, and nowhere else.

    engine/codesys_managers.py read a bare `PouType` for years and it could
    never have resolved: entry.lend() copies the IDE's globals onto the entry
    body, not onto the modules it calls. A whitelist that covered all of
    engine/ would let that back in without a word.
    """
    left = undefined_in(READS_AN_IDE_GLOBAL % name,
                        "engine/codesys_pretend.py")
    assert left, ("a bare `%s` in an engine module went unreported" % name)


@pytest.mark.parametrize("name", sorted(IDE_GLOBALS))
def test_an_entry_body_may(name):
    """They are genuinely in an entry body's namespace: CODESYS puts them
    there, and that is the one place reading them bare is the truth."""
    assert undefined_in(READS_AN_IDE_GLOBAL % name,
                        "engine/entry_pretend.py") == []


def test_ast_parses_every_file():
    """Cheap, and it means the test above is reading real code rather than
    quietly skipping a file it could not parse."""
    for rel_path in sources():
        with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                     encoding="utf-8") as handle:
            ast.parse(handle.read(), filename=rel_path)

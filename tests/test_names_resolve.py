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

# The names CODESYS puts into a running script's namespace. The engine reads
# them as plain globals because that is what they are; engine/entry.py's
# borrowed() is how they reach anything that is not an entry body.
IDE_GLOBALS = frozenset((
    "system", "projects", "online", "PouType", "Severity",
    "OnlineChangeOption",
))

# Python 2 built-ins that are gone in 3. The IDE side runs on IronPython 2.7
# as well (SPEC D4), so these are load-bearing there and absent here.
PYTHON_2_BUILTINS = frozenset(("unicode", "basestring", "long", "unichr"))

ALLOWED = IDE_GLOBALS | PYTHON_2_BUILTINS

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


def undefined_names(rel_path):
    """What pyflakes says does not resolve in this file."""
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
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        api.check(handle.read(), rel_path, collected)
    return [line for line in collected.found
            if not any("'%s'" % name in line for name in ALLOWED)]


@pytest.mark.parametrize("rel_path", sorted(sources()))
def test_every_name_resolves(rel_path):
    left = undefined_names(rel_path)
    assert not left, (
        "%s uses a name that is not defined and is not one the IDE injects:\n"
        "  %s" % (rel_path, "\n  ".join(left)))


def test_the_allowed_list_is_not_a_way_to_hide_a_typo():
    """A guard on the guard: every name on the list has to be one a real IDE
    provides or a Python 2 built-in, not whatever made today's test pass."""
    assert ALLOWED == IDE_GLOBALS | PYTHON_2_BUILTINS
    assert not (IDE_GLOBALS & PYTHON_2_BUILTINS)


def test_ast_parses_every_file():
    """Cheap, and it means the test above is reading real code rather than
    quietly skipping a file it could not parse."""
    for rel_path in sources():
        with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                     encoding="utf-8") as handle:
            ast.parse(handle.read(), filename=rel_path)

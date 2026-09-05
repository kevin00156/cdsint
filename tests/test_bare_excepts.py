# -*- coding: utf-8 -*-
"""`except:` with nothing after it is banned, and the old ones only go down.

A bare except swallows the bug you have not thought of, along with Ctrl-C.
PRINCIPLES 6 has said so since before this repo existed, and the engine
arrived from kevin-cds-text-sync carrying a hundred of them anyway. Clearing
all of them in one pass would be a hundred guesses at what each one was
written to catch, in code that talks to an API this test cannot call.

So they come out a function at a time, whenever somebody is in there for
another reason, and this table is the ratchet: everything not listed must be
at zero, and a listed file must be at exactly its number. Clean some up and
the test tells you to lower the number, which is how the count in the commit
message stays honest. Nothing may go up.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNED = ("engine", "cds", "cdsint", "stub", "tools", "tests")

# What is left, 2026-09-05. Lower these; do not raise them.
ALLOWED = {
    "engine/codesys_compare_engine.py": 7,
    "engine/codesys_managers.py": 29,
    "engine/codesys_ui.py": 6,
    "engine/codesys_ui_diff.py": 3,
    "engine/codesys_utils.py": 34,
    "engine/entry_build.py": 6,
    "engine/entry_compare.py": 2,
    "tools/Project_discover.py": 5,
    "tools/Project_resources.py": 2,
}


def sources():
    for folder in SCANNED:
        for where, _dirs, files in os.walk(os.path.join(REPO_ROOT, folder)):
            if "__pycache__" in where:
                continue
            for name in sorted(files):
                if name.endswith(".py"):
                    full = os.path.join(where, name)
                    yield os.path.relpath(full, REPO_ROOT).replace("\\", "/")


def count(rel_path):
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=rel_path)
    return sum(1 for node in ast.walk(tree)
               if isinstance(node, ast.ExceptHandler) and node.type is None)


@pytest.mark.parametrize("rel_path", sorted(sources()))
def test_no_more_bare_excepts_than_it_started_with(rel_path):
    allowed = ALLOWED.get(rel_path, 0)
    found = count(rel_path)
    if found > allowed:
        pytest.fail("%s has %d bare except: (allowed %d). Catch the "
                    "exception you expect." % (rel_path, found, allowed))
    if found < allowed:
        pytest.fail("%s is down to %d bare except: from %d. Lower its number "
                    "in ALLOWED so the ratchet holds." % (rel_path, found,
                                                          allowed))


def test_the_table_has_no_entries_for_files_that_are_gone():
    assert set(ALLOWED) <= set(sources())

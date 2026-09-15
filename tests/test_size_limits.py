# -*- coding: utf-8 -*-
"""The hard size limits, and the two tables that say what is still over them.

PRINCIPLES 2 sets 400 lines for a file and 60 for a function, and says what
hard means: no new file starts over it, and no file already over it gets
longer. Nothing enforced that, so the sentence sat there while several engine
files went past a thousand lines and one export function grew to several
times the limit.

Same shape as tests/test_bare_excepts.py, for the same reason: a ratchet
beats a target. The tables below record what is over the limit today.
Anything not in a table must be inside the limit. Anything in one must be at
exactly its number -- go over and the test says so, come under and the test
tells you what to do about it: lower the entry, or, once the thing is inside
the limit, take the entry out so the table stops holding it to a number
stricter than the rule. These tables are the count; no other file carries a
number that has to be kept in step with them.

Only the hard limits are here. The soft ones (300 and 40) are a note to a
person reading their own diff, and a test that fires on them would be a test
everybody learns to ignore.

A function's length is `end_lineno - lineno + 1`: the `def` line through the
last line of its body. Decorators are not counted, because ast puts them
outside the node. A method is keyed `Class.method`, since two classes in one
file can both have an `export`. A function defined inside another function
is not an entry of its own: its lines are already part of the one that holds
it, and counting them twice would let a long function hide behind a closure.

tests/ is not scanned. These limits are about code somebody has to read
while changing behaviour; a test file is read one test at a time and grows
by one more independent case.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNED = ("engine", "cds", "cdsint", "stub", "tools")

FILE_LIMIT = 400
FUNCTION_LIMIT = 60

# What is over 400 lines. Lower these; do not raise them.
ALLOWED_FILE_LINES = {
    "engine/codesys_compare_engine.py": 1084,
    "engine/codesys_managers.py": 1384,
    "engine/codesys_utils.py": 1104,
    "tools/call_tree_resolve.py": 439,
    "tools/perf_probe.py": 444,
}

# What is over 60 lines, by file and then by function. Same rule.
ALLOWED_FUNCTION_LINES = {
    "engine/codesys_compare_engine.py": {
        "batch_import_native_xmls_with_children": 77,
        "build_device_remap": 75,
        "create_new_object": 141,
        "detect_moved_files": 81,
        "find_all_changes": 237,
    },
    "engine/codesys_managers.py": {
        "NativeManager.export": 67,
        "classify_object": 108,
    },
    "engine/codesys_utils.py": {
        "ensure_git_configs": 64,
        "get_quick_ide_hash": 68,
    },
    "engine/entry_compare.py": {
        "compare_project": 89,
    },
    "engine/entry_export.py": {
        "cleanup_orphaned_files": 96,
        "export_project": 213,
    },
    "engine/entry_import.py": {
        "import_project": 229,
    },
    "tools/cache_doctor.py": {
        "main": 176,
    },
    "tools/call_tree_parse.py": {
        "_blank_comments": 61,
    },
    "tools/call_tree_resolve.py": {
        "_resolve_calls": 104,
    },
    "tools/perf_probe.py": {
        "build_report": 104,
        "main": 90,
    },
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


def read(rel_path):
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        return handle.read()


def file_lines(rel_path):
    return len(read(rel_path).split("\n"))


def function_lines(rel_path):
    """Every function in the file, by name, with its length.

    A method carries its class so that two `export`s in one file stay two
    entries rather than one of them quietly winning.
    """
    found = {}
    tree = ast.parse(read(rel_path), filename=rel_path)
    for node in ast.walk(tree):
        prefix = node.name + "." if isinstance(node, ast.ClassDef) else ""
        if not isinstance(node, (ast.ClassDef, ast.Module)):
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[prefix + child.name] = (child.end_lineno
                                              - child.lineno + 1)
    return found


def complain(what, found, allowed, limit):
    """What to say about a length against its table entry, or None if it fits.

    Coming under the entry has two different answers, and telling somebody to
    lower the number when the thing is finally inside the limit would leave
    that file pinned to a number stricter than the rule for ever -- a ratchet
    with no way off it.
    """
    if found > allowed:
        return ("%s is %d lines (allowed %d, the hard limit is %d). Split it "
                "before the next thing goes in." % (what, found, allowed,
                                                    limit))
    if found < allowed and found <= limit:
        return ("%s is down to %d lines, inside the %d-line limit. Remove its "
                "entry from tests/test_size_limits.py -- it does not need one "
                "any more." % (what, found, limit))
    if found < allowed:
        return ("%s is down to %d lines from %d. Lower its number in "
                "tests/test_size_limits.py so the ratchet holds."
                % (what, found, allowed))
    return None


@pytest.mark.parametrize("rel_path", sorted(sources()))
def test_no_file_is_longer_than_it_was_allowed_to_be(rel_path):
    allowed = ALLOWED_FILE_LINES.get(rel_path, FILE_LIMIT)
    found = file_lines(rel_path)
    if rel_path not in ALLOWED_FILE_LINES:
        assert found <= FILE_LIMIT, (
            "%s is %d lines, over the %d-line hard limit, and it is not in "
            "ALLOWED_FILE_LINES. A new file does not get to start over it."
            % (rel_path, found, FILE_LIMIT))
        return
    problem = complain(rel_path, found, allowed, FILE_LIMIT)
    if problem:
        pytest.fail(problem)


@pytest.mark.parametrize("rel_path", sorted(sources()))
def test_no_function_is_longer_than_it_was_allowed_to_be(rel_path):
    allowed = ALLOWED_FUNCTION_LINES.get(rel_path, {})
    for name, found in sorted(function_lines(rel_path).items()):
        what = "%s's %s()" % (rel_path, name)
        if name not in allowed:
            assert found <= FUNCTION_LIMIT, (
                "%s is %d lines, over the %d-line hard limit, and it is not "
                "in ALLOWED_FUNCTION_LINES." % (what, found, FUNCTION_LIMIT))
            continue
        problem = complain(what, found, allowed[name], FUNCTION_LIMIT)
        if problem:
            pytest.fail(problem)


@pytest.mark.parametrize("rel_path", sorted(ALLOWED_FUNCTION_LINES))
def test_the_function_table_has_no_entries_for_functions_that_are_gone(rel_path):
    """A row naming a function somebody deleted or renamed passes for ever
    without measuring anything, which is the failure mode this test exists
    to prevent, one level up."""
    assert set(ALLOWED_FUNCTION_LINES[rel_path]) <= set(function_lines(rel_path))


def test_the_file_table_has_no_entries_for_files_that_are_gone():
    assert set(ALLOWED_FILE_LINES) <= set(sources())


def test_something_over_its_entry_is_told_to_split():
    said = complain("a.py", 500, 450, FILE_LIMIT)
    assert "Split it" in said and "500" in said


def test_something_still_over_the_limit_is_told_to_lower_its_entry():
    said = complain("a.py", 450, 500, FILE_LIMIT)
    assert "Lower its number" in said and "450" in said


def test_something_back_inside_the_limit_is_told_to_drop_its_entry():
    # Not "lower it to 380": that would hold the file at 380 for ever, which
    # is stricter than the rule and is a ratchet with no way off it.
    said = complain("a.py", 380, 500, FILE_LIMIT)
    assert "Remove its entry" in said
    assert "Lower its number" not in said


def test_something_at_its_entry_has_nothing_said_about_it():
    assert complain("a.py", 500, 500, FILE_LIMIT) is None

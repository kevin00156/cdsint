# -*- coding: utf-8 -*-
"""The exit codes, against SPEC 4.3's table and against the other side.

Two witnesses, for the reason SPEC 6.4 gives: the IDE-side script writes down
the code it means to exit with and the launcher compares that against what
the shell saw. While each side had a copy of the table, that comparison could
pass with both sides equally wrong, and a caller reading only `$?` would act
on a number the document never promised.

So there is one table (cds/core/exits.py) and this reads the document to
check it, the way tests/test_core_settings.py does for SPEC 4.4.
"""
import ast
import io
import os
import re

from cds.core import exits

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO_ROOT, "docs", "SPEC.md")

# The one module allowed to say what a number means.
HOME = "cds/core/exits.py"


def documented():
    """The exit codes SPEC 4.3's table lists, as a set of numbers."""
    with io.open(SPEC, encoding="utf-8") as handle:
        text = handle.read()
    section = text.split("### 4.3 Exit code", 1)[1].split("### 4.4", 1)[0]
    found = set()
    for row in section.splitlines():
        if row.startswith("|"):
            found.update(int(n) for n in re.findall(r"^\|\s*(\d)\s*\|", row))
    return found


def named_here():
    return dict((name, value) for name, value in vars(exits).items()
                if name.startswith("EXIT_"))


def test_the_code_and_the_spec_list_the_same_exit_codes():
    assert set(named_here().values()) == documented()


def test_every_code_has_exactly_one_name():
    codes = named_here()
    assert len(set(codes.values())) == len(codes)


def test_zero_is_the_only_one_that_means_it_worked():
    assert exits.EXIT_OK == 0
    assert all(value > 0 for name, value in named_here().items()
               if name != "EXIT_OK")


def defines_an_exit_code(rel_path):
    """The lines where this file assigns an EXIT_* of its own."""
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=rel_path)
    return [node.lineno for node in tree.body
            if isinstance(node, ast.Assign)
            for name in node.targets
            if getattr(name, "id", "").startswith("EXIT_")]


def sources():
    for folder in ("cds", "cdsint"):
        for where, _dirs, files in os.walk(os.path.join(REPO_ROOT, folder)):
            if "__pycache__" in where:
                continue
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.relpath(os.path.join(where, name),
                                          REPO_ROOT).replace("\\", "/")


def test_only_one_module_defines_an_exit_code():
    # The IDE side used to define EXIT_OK and EXIT_FAILED of its own, and a
    # second definition is the one thing SPEC 6.4's comparison cannot notice:
    # both sides can be equally wrong and still agree.
    offences = ["%s:%d" % (rel_path, line)
                for rel_path in sources() if rel_path != HOME
                for line in defines_an_exit_code(rel_path)]
    assert not offences, ("an exit code is defined outside %s: %s"
                          % (HOME, ", ".join(offences)))

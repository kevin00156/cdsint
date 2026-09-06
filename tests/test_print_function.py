# -*- coding: utf-8 -*-
"""Every file that runs inside the IDE says which print it means (PRINCIPLES 8).

Without `from __future__ import print_function`, IronPython 2.7 reads
`print("Error:", msg)` as the statement form printing one tuple, so the IDE
shows `('Error:', '...')`. It is not a crash, which is why two of them lived
in entry_export.py for as long as they did — nothing fails, the message just
stops being readable at the moment somebody needs to read it.

The rule has no exceptions, including the docstring-only `__init__.py` files
and the CPython-only instruments in `tools/`. Some of the instruments there
do run inside an IDE, and asking which ones per file is the carve-out that
somebody eventually gets wrong; the line costs a CPython-only file nothing,
because print is a function there anyway. A rule with a carve-out is one every
future author has to remember; a rule a test enforces over a whole directory
is one they can forget.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PRINCIPLES 8: the four directories that are inside the IDE at some point,
# plus tools/, where some of the instruments are.
IDE_SIDE = ("engine", os.path.join("cds", "ide"), os.path.join("cds", "core"),
            "stub", "tools")


def ide_side_sources():
    for folder in IDE_SIDE:
        root = os.path.join(REPO_ROOT, folder)
        for where, _dirs, files in os.walk(root):
            if "__pycache__" in where:
                continue
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(where, name)


def declares_print_function(path):
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "print_function" for alias in node.names):
                return True
    return False


@pytest.mark.parametrize("path", sorted(ide_side_sources()),
                         ids=lambda p: os.path.relpath(p, REPO_ROOT))
def test_an_ide_side_file_declares_print_function(path):
    assert declares_print_function(path), (
        os.path.relpath(path, REPO_ROOT) + " runs under IronPython 2.7 and "
        "needs `from __future__ import print_function`")

# -*- coding: utf-8 -*-
"""tools/py27_compile.py, the script the py27-grammar CI job runs.

That job is the only place it runs under 2.7, and a job that compiles the
wrong list of files, or none, is green either way. So its CPython 3 half is
held here: it walks the same files the rest of the suite calls IDE-side, and
it names a file that does not compile by path and line.
"""
import os
import sys

import pytest

from tests import test_py2_runtime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO_ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import py27_compile  # noqa: E402


def test_it_compiles_the_files_the_suite_calls_ide_side():
    assert sorted(py27_compile.ide_side_sources(REPO_ROOT)) == sorted(
        test_py2_runtime.ide_side_sources())


def test_every_ide_side_file_compiles_here(capsys):
    assert py27_compile.main(["py27_compile.py", REPO_ROOT]) == 0


def test_a_file_that_does_not_compile_is_named_with_its_line(tmp_path,
                                                            capsys):
    engine = tmp_path / "engine"
    engine.mkdir()
    (engine / "broken.py").write_text(u"x = 1\ndef f(:\n", encoding="utf-8")
    assert py27_compile.main(["py27_compile.py", str(tmp_path)]) == 1
    assert str(engine / "broken.py") + ":2: " in capsys.readouterr().err


@pytest.mark.parametrize("folder", ["", "somewhere_else"])
def test_no_files_is_a_failure_not_a_pass(tmp_path, folder):
    # A mount in the wrong place compiles nothing; that must not be green.
    (tmp_path / "somewhere_else").mkdir()
    assert py27_compile.main(["py27_compile.py",
                              str(tmp_path / folder)]) == 1

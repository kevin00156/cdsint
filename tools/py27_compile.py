# -*- coding: utf-8 -*-
"""Compile every IDE-side file with whatever Python runs this (PRINCIPLES 8).

Run under a real Python 2.7, it is the proof that the IDE side parses under
IronPython's grammar, which no amount of reading the code from CPython 3 can
give: the py27-grammar job in .github/workflows/ci.yml runs it that way, in a
python:2.7 container. Run under CPython 3 it asks the other half.

    python tools/py27_compile.py [repo root]

Written for both interpreters, so it uses nothing either lacks. It compiles
from bytes, as cds/ide/silent.py does, so the coding line in each file is
what decides how the file is read -- the same way the IDE reads it.
"""
from __future__ import print_function

import os
import sys

IDE_SIDE = ("engine", os.path.join("cds", "ide"), os.path.join("cds", "core"),
            "stub")


def ide_side_sources(root):
    for folder in IDE_SIDE:
        for where, dirs, files in os.walk(os.path.join(root, folder)):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(where, name)


def compile_error(path):
    """`path:line: message` if this file does not compile, else None."""
    handle = open(path, "rb")
    try:
        source = handle.read()
    finally:
        handle.close()
    try:
        compile(source, path, "exec")
    except SyntaxError as exc:
        return "%s:%s: %s" % (path, exc.lineno, exc.msg)
    return None


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    paths = list(ide_side_sources(root))
    errors = [e for e in (compile_error(p) for p in paths) if e is not None]
    for error in errors:
        print(error, file=sys.stderr)
    print("%d of %d IDE-side files compile under Python %d.%d"
          % (len(paths) - len(errors), len(paths),
             sys.version_info[0], sys.version_info[1]))
    return 1 if errors or not paths else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

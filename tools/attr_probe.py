# -*- coding: utf-8 -*-
"""Print what build_properties exposes on the objects of the open project.

Runs INSIDE an IDE: Tools > Scripting > Execute Script File, or --runscript.

CODESYS versions disagree about which compile attributes an object carries and
what they are called, and engine/codesys_constants.py keeps a table (ATTR_REGISTRY)
of the names it knows. When a version turns up whose names are different, the
symptom is an attribute that never round-trips and nothing said why. This is
how you find out what that version actually calls them.

It used to live inside read_ide_attrs() as a one-shot dump guarded by a flag
stored on the function object -- a probe sitting in the hottest path of an
unchanged export, where it cost a `getattr` per object forever to answer a
question somebody asked once.
"""
from __future__ import print_function

import os
import sys

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _root  # noqa: F401  (importing it is the whole of it)

from engine.strings import safe_str
from engine.ide_read import name_of  # noqa: E402

# Enough objects to see the pattern, few enough to read. A project has
# hundreds and they nearly all answer the same way.
HOW_MANY = 5


def _build_properties(obj):
    try:
        return obj.build_properties
    except Exception as exc:
        return exc


def _report(obj):
    """One object: its name, and every readable build_properties attribute."""
    props = _build_properties(obj)
    if isinstance(props, Exception):
        print("%s: no build_properties (%s)" % (name_of(obj), safe_str(props)))
        return False
    if props is None:
        print("%s: build_properties is None" % name_of(obj))
        return False

    names = [a for a in dir(props) if not a.startswith("_")]
    print("%s: %s" % (name_of(obj), ", ".join(names)))
    for attr in names:
        try:
            value = getattr(props, attr)
        except Exception as exc:
            print("    %s -> ERROR: %s" % (attr, safe_str(exc)))
            continue
        if not hasattr(value, "__call__"):
            print("    %s = %r" % (attr, value))
    return True


def main():
    import __main__
    projects = getattr(__main__, "projects", None)
    if projects is None or not projects.primary:
        print("No project open. Run this from inside an IDE with a project.")
        return 1

    shown = 0
    for obj in projects.primary.get_children(recursive=True):
        if _report(obj):
            shown += 1
        if shown >= HOW_MANY:
            break
    if not shown:
        print("Nothing in this project exposes build_properties.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

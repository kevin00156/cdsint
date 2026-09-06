# -*- coding: utf-8 -*-
"""Put the install root on sys.path, so a tool can import engine/ and cds/.

Importing this module is the whole of it; there is nothing to call.

A tool in here is run by absolute path — `python tools/cache_doctor.py` from a
shell, or **Execute Script File** inside the IDE — and neither of those puts
the *install root* anywhere the import system will look.

The two differ about tools/ itself, which is why each tool checks for it
before importing this rather than inserting it flat. From a shell it is
already sys.path[0], the directory the script came from. Inside the IDE it is
not there at all: ScriptEngine hands IronPython the file, not a package, and
sys.path is the IDE's own search list. That is why the stubs in stub/ carry
their own path insert too.

The leading underscore keeps this out of the tool list in the readMe: it is
not an instrument, it is what the instruments stand on.
"""
from __future__ import print_function

import os
import sys

# tools/ sits beside engine/, cds/ and profiles/, so the root is one up.
INSTALL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if INSTALL_ROOT not in sys.path:
    sys.path.insert(0, INSTALL_ROOT)

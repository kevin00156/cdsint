# -*- coding: utf-8 -*-
"""Scripts menu -> set the sync folder. The body lives outside ScriptDir (SPEC 5.3)."""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_here, "body.path")) as _f:
    _root = _f.read().strip()
if _root not in sys.path:
    sys.path.insert(0, _root)
for _name in [n for n in sys.modules.keys() if n.split(".")[0] == "engine"]:
    del sys.modules[_name]
from engine import entry, entry_directory
entry.run(entry_directory, globals(), "set_base_directory")

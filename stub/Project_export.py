# -*- coding: utf-8 -*-
"""Scripts menu -> export. The body lives outside ScriptDir (SPEC 5.3)."""
from __future__ import print_function

import codecs, os, sys

_here = os.path.dirname(os.path.abspath(__file__))
# utf-8-sig, not open(): an editor or an installer that adds a BOM would
# otherwise put "\ufeffC:\..." on sys.path and nothing would import.
with codecs.open(os.path.join(_here, "body.path"), "r", "utf-8-sig") as _f:
    _root = _f.read().strip()
if _root not in sys.path:
    sys.path.insert(0, _root)
for _name in [n for n in sys.modules.keys() if n.split(".")[0] == "engine"]:
    del sys.modules[_name]
from engine import entry, entry_export
entry.run(entry_export, globals())

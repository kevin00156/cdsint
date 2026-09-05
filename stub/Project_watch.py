# -*- coding: utf-8 -*-
"""Scripts menu -> start or stop the watcher. Run it again to stop it."""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_here, "body.path")) as _f:
    _root = _f.read().strip()
if _root not in sys.path:
    sys.path.insert(0, _root)
from cds.ide import session
from engine import settings
from engine.codesys_constants import SCRIPT_VERSION
session.main(globals(), version=SCRIPT_VERSION, settings=settings.edit)

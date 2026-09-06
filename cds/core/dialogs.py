# -*- coding: utf-8 -*-
"""The titles of the yes/no dialogs cdsint's own commands ask.

A title is a name used from both sides at once: engine/ hands it to
codesys_ui.ask_yes_no, and cds/ide/silent.py looks it up to find the flag
that answers it when nobody is there to click (SPEC D7). Written out as a
literal in both places, the two spellings are free to drift, and the run that
finds out is the one that stops with "unexpected dialog" against a title
somebody had every reason to think was harmless to reword.

Only cdsint's own dialogs. The IDE's own prompts are a different mechanism
with a different answer (--answer, SPEC 6.4), and they are keyed by the IDE.

Pure Python (PRINCIPLES.md 4): no CODESYS imports, so both layers may use it.
"""
from __future__ import print_function

DELETE_ORPHANS = "Delete Orphaned Files?"
CONFIRM_IMPORT = "Confirm Import"
CONFIRM_PLC_DOWNLOAD = "Confirm PLC Download"

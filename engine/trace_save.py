# -*- coding: utf-8 -*-
"""A trace editor's save, with nobody there to close what it shows.

A CSV save of a trace that records a name the IDE's symbols do not hold, a
direct address such as %QD3 among them, ends in an OK-only message box: "The
csv export encountered some problems with unknown variables/parameters"
(docs/trace-research.md 18). In an interactive IDE that box is modal, so a
watcher run stopped in it until someone walked over and pressed OK, once
before the recording and once after. The samples are recorded either way.

Logging simple prompts turns the box into a line in the IDE's message view,
but only inside a script run: from the watcher's timer tick the same setting
left the box modal (research 18), so the save is made inside one. The trace
editor's own lines, which name each variable, are handed back for
the caller to report, so the run says what the box would have said.
"""
from __future__ import print_function

import os

from engine import entry, ide_private, plc_crc
from engine.entry_build import every_severity
from engine.strings import safe_str

# The message category the trace editor writes its warnings to, by GUID: its
# description is the IDE's display language, the GUID is not. Read on
# CODESYS 3.5.21.40 (research 18).
TRACE_CATEGORY = "05263faf-c096-4326-bf22-4af1f5404f54"


def save(ide_globals, editor, path):
    """editor.save(path), the IDE's simple prompts logged and not shown.

    Hands back what the trace editor said while saving, each line once.
    prompt_handling is put back afterwards: in the watcher it is the
    person's IDE, and their own scripts are not this run's to change.
    """
    system = entry.borrowed(ide_globals, "system")
    severity = entry.borrowed(ide_globals, "Severity")
    logged = entry.borrowed(ide_globals, "PromptHandling").LogSimplePrompts
    seen = len(_trace_messages(system, severity))
    ensure_directory(path)
    before = system.prompt_handling
    system.prompt_handling = before | logged
    try:
        ide_private.in_script_run(entry.borrowed(ide_globals, "online"),
                                  lambda: editor.save(plc_crc.forget(path)))
    finally:
        system.prompt_handling = before
    said = []
    for text in _trace_messages(system, severity)[seen:]:
        if text not in said:
            said.append(text)
    return said


def ensure_directory(path):
    """The file's directory exists before the IDE is asked to write there."""
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)


def _trace_messages(system, severity):
    """The texts in the trace editor's category, oldest first.

    Only a category get_message_categories lists as active is asked, and
    with a severity mask: ScriptEngine 4.0.0.0 throws on an empty category
    and on a call without the mask (engine/entry_build.py build_messages).
    """
    for category in system.get_message_categories(True):
        if str(category).lower() == TRACE_CATEGORY:
            return [safe_str(found.text) for found in
                    system.get_message_objects(category,
                                               every_severity(severity))]
    return []

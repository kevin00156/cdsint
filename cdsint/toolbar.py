# -*- coding: utf-8 -*-
"""`cdsint toolbar`: the dropdown of ScriptDir scripts on every IDE's toolbar.

The IDE has a command that lists ScriptDir as a dropdown, but no vendor puts it
on a toolbar, so reaching Project_watch takes three menu levels until someone
adds it by hand in Customize, once per IDE version. No IDE script API is known
to do that, and none would help a closed IDE, so this edits the file Customize
writes: <vendor options>\\...\\<anything> (<profile>).opt.tbar.

That file is the IDE's and holds the user's layout, and its format is
undocumented. So the one thing inserted is the item, the original is kept
beside it the first time, and a file that is not the expected shape is
reported and left alone. An IDE that is open may hold its own idea of the
toolbars, so nothing is written while any of them runs.

The button goes first on the first toolbar. Measured on 2026-11-06: every
supported IDE has Standard there. Finding it by name would break if that name
is localised, and placing it beside another button would break for whoever
removed that button.

A closed IDE reads this at its next start, and an unchanged toolbar is not
written back when it closes. A first start writes the file before anything is
customised, so only an IDE that has never been opened has none, and this must
not invent one: the file holds every toolbar's whole layout.

irm/setup.ps1 runs this once, and `cdsint update` deliberately does not, or a
button somebody removed would come back with each release. Uninstalling leaves
it: nothing tells this button from one added by hand, and it is not cdsint's
alone, since it lists whatever is in ScriptDir.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import codecs
import os
import re
import xml.etree.ElementTree as ElementTree

from cds.core.exits import EXIT_FAILED, EXIT_OK
from cdsint import installs, report, update
from cdsint.exits import Failure

COMMAND_GUID = "a9b65152-0c1c-458c-bef7-655dc955aea8"
_ITEM_TYPE = "{d7c09fff-b12f-47d8-bd4f-3d60b8672b7f}"
BACKUP_SUFFIX = ".cdsint-backup"
_NEW_SUFFIX = ".cdsint-new"

ADDED = "button_added"
ALREADY = "button_already"
NO_FILE = "button_no_file"            # this IDE has never been opened
IDE_OPEN = "button_ide_open"
UNRECOGNISED = "button_unrecognised"
FAILED = "button_failed"

_DONE = (ADDED, ALREADY)

# The opening of the first toolbar's item list, up to its line end. It may not
# cross an earlier Items, and must not be self-closed: an empty first toolbar
# written as <List ... /> would otherwise send the button to the second one.
_FIRST_ITEMS = re.compile(
    r'<List Name="Toolbars"[^>]*>\s*<Single [^>]*>'
    r'(?:(?!<List Name="Items").)*'
    r'<List Name="Items"[^>]*(?<!/)>(\r?\n)', re.DOTALL)


def with_button(raw):
    """The file's bytes with the button first on the first toolbar.

    None when they are not the shape every supported IDE writes. The result is
    parsed back and checked, because a regex over XML is only trusted once the
    XML agrees with it.
    """
    if not raw.startswith(codecs.BOM_UTF16_LE):
        return None
    try:
        text = raw[len(codecs.BOM_UTF16_LE):].decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    match = _FIRST_ITEMS.search(text)
    if match is None:
        return None
    patched = text[:match.end()] + _item(match.group(1)) + text[match.end():]
    result = codecs.BOM_UTF16_LE + patched.encode("utf-16-le")
    return result if _first_command(result) == COMMAND_GUID else None


def _item(newline):
    lines = ('        <Single Type="%s" Method="IArchivable">' % _ITEM_TYPE,
             '          <Single Name="CommandGuid" Type="System.Guid">%s'
             '</Single>' % COMMAND_GUID,
             '        </Single>', '')
    return newline.join(lines)


def _first_command(raw):
    """The command of the first toolbar's first item, or None."""
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    first_bar = root.find("List[@Name='Toolbars']/Single")
    if first_bar is None:
        return None
    item = first_bar.find("List[@Name='Items']/Single"
                          "/Single[@Name='CommandGuid']")
    return None if item is None else item.text


def _replace(path, original, patched):
    """Keep the first original beside it, then swap the new bytes in whole."""
    backup = path + BACKUP_SUFFIX
    if not os.path.exists(backup):
        with open(backup, "wb") as handle:
            handle.write(original)
    new = path + _NEW_SUFFIX
    with open(new, "wb") as handle:
        handle.write(patched)
    os.replace(new, path)


def add_to_file(path):
    """Put the button in one .opt.tbar. Returns (state, detail)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        if COMMAND_GUID.encode("utf-16-le") in raw:
            return ALREADY, path
        patched = with_button(raw)
        if patched is None:
            return UNRECOGNISED, path
        _replace(path, raw, patched)
    except OSError as error:
        return FAILED, "%s: %s" % (path, error)
    return ADDED, path


def files_of(install):
    """Every .opt.tbar under this vendor's options that is this install's.

    The directory between them carries a hash nobody can compute, and an IDE
    upgraded across vendor layouts leaves one in each, so it is searched for.
    """
    wanted = tuple(" (%s).opt.tbar" % profile for profile in install["profiles"])
    return sorted(os.path.join(folder, name)
                  for root in install["user_options"]
                  for folder, _dirs, names in os.walk(root)
                  for name in names if name.endswith(wanted))


def _rows_for(install):
    files = files_of(install)
    if not files:
        return [{"ide": install["name"], "state": NO_FILE, "detail": ""}]
    rows = []
    for path in files:
        state, detail = add_to_file(path)
        rows.append({"ide": install["name"], "state": state, "detail": detail})
    return rows


def add_everywhere():
    """One row per file changed or considered, or one saying why none were."""
    try:
        running = update.running_ides()
    except Failure as error:
        return [{"ide": "every IDE", "state": FAILED, "detail": str(error)}]
    if running:
        return [{"ide": "every IDE", "state": IDE_OPEN,
                 "detail": ", ".join(running)}]
    return [row for install in installs.find() for row in _rows_for(install)]


def run(ns):
    """Exit 1 when any IDE is left without the button, or none was found.

    irm/setup.ps1 ignores this code, because a missing button is no reason to
    call an install failed. Asked for by name, it is the answer to the question.
    """
    rows = add_everywhere()
    report.show_toolbars(rows, ns.json)
    if rows and all(row["state"] in _DONE for row in rows):
        return EXIT_OK
    return EXIT_FAILED

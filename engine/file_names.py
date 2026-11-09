# -*- coding: utf-8 -*-
"""How an object's name becomes a file or folder name, and back.

The one place the mapping lives. Export writes every path segment through
clean_filename(); import names a new object, or a folder it has to make,
through name_from_file(); a lookup that holds a disk segment compares it
against clean_filename() of each IDE name, never against the raw name.

Two rules. A character Windows forbids in a file name becomes `_`; that
loses the character, so it does not come back, and a lookup finds the
object only by mapping its name the same way. A name Windows keeps for a
device (AUX, CON, COM1, ...) gets `_` after it: `AUX.st` is not a file on
Windows -- Windows 10 writes it to the device and git on Windows 11 refuses
to index it -- so an FB called AUX was exported "successfully" and was
missing from every clone. The `_` does come back, but only off a reserved
name: `MAIN_` stays `MAIN_`.
"""
from __future__ import print_function

FORBIDDEN_CHARS = ["<", ">", ":", "\"", "/", "\\", "|", "?", "*"]

# Windows reads a superscript digit as the same port, so those are taken too.
_PORT_DIGITS = [str(n) for n in range(1, 10)] + [u"¹", u"²", u"³"]
RESERVED_NAMES = frozenset(
    [u"CON", u"PRN", u"AUX", u"NUL"]
    + [u"COM" + digit for digit in _PORT_DIGITS]
    + [u"LPT" + digit for digit in _PORT_DIGITS])

RESERVED_MARK = "_"


def _stem(segment):
    """What Windows checks against the device names: the part before the
    first dot (`AUX.Main.st` is the device too), with trailing spaces off."""
    return segment.split(".", 1)[0]


def _is_reserved(stem):
    return stem.rstrip(" ").upper() in RESERVED_NAMES


def clean_filename(name):
    """The file or folder name an object called `name` is written under."""
    clean_name = name
    for char in FORBIDDEN_CHARS:
        clean_name = clean_name.replace(char, "_")
    stem = _stem(clean_name)
    if _is_reserved(stem):
        return stem + RESERVED_MARK + clean_name[len(stem):]
    return clean_name


def name_from_file(segment):
    """The object name a disk segment stands for, when nothing in the IDE
    has it yet. The inverse of clean_filename() as far as one exists."""
    stem = _stem(segment)
    if stem.endswith(RESERVED_MARK) and _is_reserved(stem[:-len(RESERVED_MARK)]):
        return stem[:-len(RESERVED_MARK)] + segment[len(stem):]
    return segment

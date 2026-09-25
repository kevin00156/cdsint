# -*- coding: utf-8 -*-
"""An EtherCAT device's settings file: its lines, how they read, what differs.

SPEC 6.10. One file per device under an EtherCAT master, holding every
ReadWrite leaf parameter and every mapped channel, keyed by connector and
parameter identifier, which are the same numbers on both IDEs
(docs/ethercat-research.md 7). Native XML is not the format: importing it
duplicates the tree (research 2.2). Plain Python on text, shared by the IDE
side and CI.
"""
from __future__ import print_function

import re

SUFFIX = ".device"
HEADER = ("# cdsint EtherCAT device settings. The device line is checked, "
          "never applied; '#' comments are for the reader.")
# c1/1610633216, c1/1627394048/Value, dev/42: a connector (or the device's
# own parameters) and a path of identifiers.
KEY = re.compile(r"^(c\d+|dev)(/[^/\s=]+)+$")
# A comment is a '#' with space before it; "16#6060" inside a value is not.
COMMENT = re.compile(r"\s+#(\s|$)")
COMMENT_COLUMN = 50


def _with_comment(text, comment):
    if not comment:
        return text
    return text.ljust(COMMENT_COLUMN) + "  # " + comment


def render(ident, values, maps):
    """The file. values and maps are (key, value, comment) triples."""
    lines = [HEADER, "device  " + ident]
    for key, value, comment in sorted(values):
        lines.append(_with_comment("%s = %s" % (key, value), comment).rstrip())
    for key, variable, comment in sorted(maps):
        lines.append(_with_comment("map %s = %s" % (key, variable), comment))
    return "\n".join(lines) + "\n"


def _strip_comment(text):
    found = COMMENT.search(text)
    return text[:found.start()] if found else text


def _assignment(text):
    """(key, value, None) or (None, None, why)."""
    key, sep, value = text.partition("=")
    key = key.strip()
    if not sep or not KEY.match(key):
        return None, None, "expected 'key = value', key like c1/1610633216"
    return key, value.strip(), None


def _read_line(stripped, doc):
    """Put one line into doc. None, or why it could not be read."""
    if stripped.startswith("device ") or stripped == "device":
        if doc["ident"] is not None:
            return "the device line is given twice"
        doc["ident"] = stripped[len("device"):].strip()
        return None
    table = "values"
    if stripped.startswith("map "):
        table, stripped = "maps", stripped[len("map "):]
    key, value, why = _assignment(stripped)
    if why:
        return why
    if key in doc[table]:
        return "%s is given twice" % key
    doc[table][key] = value
    return None


def parse(text):
    """(doc, problems). doc is {"ident", "values", "maps"}; a problem is
    "line N: why"."""
    doc = {"ident": None, "values": {}, "maps": {}}
    problems = []
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = _strip_comment(raw).strip()
        if not stripped or stripped.startswith("#"):
            continue
        why = _read_line(stripped, doc)
        if why:
            problems.append("line %d: %s" % (number, why))
    if doc["ident"] is None:
        problems.append("no 'device TYPE|ID|VERSION' line")
    return doc, problems


def diff(have, wanted):
    """What to write: changed values, changed mappings, and "" for every
    mapping `have` has that `wanted` does not (unmap it)."""
    values = dict((k, v) for k, v in wanted["values"].items()
                  if have["values"].get(k) != v)
    maps = dict((k, v) for k, v in wanted["maps"].items()
                if have["maps"].get(k) != v)
    for key in have["maps"]:
        if key not in wanted["maps"]:
            maps[key] = ""
    return {"values": values, "maps": maps}


def same(ide_text, disk_text):
    """Would importing disk_text change nothing? The same device, and no
    mismatch by import's rules: a value line left out is not managed."""
    disk, problems = parse(disk_text)
    if problems:
        return False
    ide, _ = parse(ide_text)
    return ide["ident"] == disk["ident"] and not mismatches(ide, disk)


def mismatches(after, wanted):
    """Each value or mapping the IDE does not hold as written, by key.

    A value line left out of the file is not managed, so only the file's
    values are checked; a map line left out means "no variable", so every
    mapping on either side is.
    """
    found = []
    for table, label in (("values", ""), ("maps", "map ")):
        keys = set(wanted[table])
        if table == "maps":
            keys |= set(after[table])
        for key in sorted(keys):
            want = wanted[table].get(key, "")
            have = after[table].get(key, "")
            if want != have:
                found.append("%s%s: written %s, the IDE has %s"
                             % (label, key, want or "(nothing)",
                                have or "(nothing)"))
    return found

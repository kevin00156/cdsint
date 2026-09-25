# -*- coding: utf-8 -*-
"""The Library Manager file: its lines, how they read, and what differs.

SPEC 6.9. One file per application, `Library Manager.libraries`, built from
the script API rather than the native XML, because importing the XML merges
and never removes, and exporting it reorders a hash table by itself
(docs/library-manager-research.md 4 and 6). Plain Python on text, so the IDE
side and CI share one copy.
"""
from __future__ import print_function

import re

SUFFIX = ".libraries"
KINDS = ("library", "placeholder", "redirect")
FLAGS = ("qualified_only", "optional", "hide_when_referenced",
         "publish_symbols")
HEADER = ("# cdsint library list. '# system' lines belong to the devices "
          "and are never applied.")
# "Util, 3.5.19.0 (System)": a name, a version or wildcard, a company. The
# IDE's own display string, which is also what add_library takes.
LIBRARY_NAME = re.compile(r"^.+, \S+ \(.+\)$")
KIND_WIDTH = 13
OPTIONS_COLUMN = 60


def entry(kind, name, value=None, options=None):
    return {"kind": kind, "name": name, "value": value,
            "options": dict(options or {})}


def squeeze(text):
    """One space wherever there were several: the IDE's names have single
    spaces, and a hand-typed double space is not a different library."""
    return " ".join(text.split())


def key(e):
    """How two entries are the same entry: kind and name, never the IDE's id,
    which changes every session (research 2). Case does not count."""
    return (KINDS.index(e["kind"]), e["name"].lower())


def _canonical(e):
    """What an entry says, with case taken out of its name and value."""
    return (key(e), (e["value"] or "").lower(), sorted(e["options"].items()))


def _options_text(options):
    words = [flag for flag in FLAGS if options.get(flag)]
    if options.get("namespace"):
        words.append("namespace=" + options["namespace"])
    return " ".join(words)


def _line(e):
    head = e["kind"].ljust(KIND_WIDTH) + e["name"]
    if e["kind"] != "library":
        return head + " = " + e["value"]
    options = _options_text(e["options"])
    if not options:
        return head
    return head.ljust(OPTIONS_COLUMN) + " " + options


def render(entries, system=()):
    """The file: the user's entries, then the devices' as comments."""
    lines = [HEADER]
    lines.extend(_line(e) for e in sorted(entries, key=key))
    for name, value, info in sorted(system, key=lambda s: s[0].lower()):
        comment = "# system".ljust(KIND_WIDTH) + name + " = " + value
        lines.append((comment.ljust(OPTIONS_COLUMN) + " " + info).rstrip())
    return "\n".join(lines) + "\n"


def _parse_library(rest):
    close = rest.rfind(")")
    name = squeeze(rest[:close + 1])
    if close < 0 or not LIBRARY_NAME.match(name):
        return None, ("a library needs 'Name, Version (Company)', not %r"
                      % rest)
    options = {}
    for word in rest[close + 1:].split():
        if word in FLAGS:
            options[word] = True
        elif word.startswith("namespace=") and word != "namespace=":
            options["namespace"] = word[len("namespace="):]
        else:
            return None, "unknown option %r" % word
    return entry("library", name, options=options), None


def _parse_pair(kind, rest):
    name, sep, value = rest.partition(" = ")
    if not sep or not name.strip() or not value.strip():
        return None, ("a %s needs 'Name = Library, Version (Company)'"
                      % kind)
    return entry(kind, squeeze(name), squeeze(value)), None


def _parse_line(text):
    kind, _, rest = text.partition(" ")
    if kind == "library":
        return _parse_library(rest.strip())
    if kind in ("placeholder", "redirect"):
        return _parse_pair(kind, rest.strip())
    return None, "unknown kind %r (expected %s)" % (kind, ", ".join(KINDS))


def parse(text):
    """(entries, problems). A problem is "line N: why"; comments are skipped."""
    entries, problems, seen = [], [], set()
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        found, why = _parse_line(stripped)
        if why:
            problems.append("line %d: %s" % (number, why))
            continue
        if key(found) in seen:
            problems.append("line %d: %s %s is listed twice"
                            % (number, found["kind"], found["name"]))
            continue
        seen.add(key(found))
        entries.append(found)
    return entries, problems


def diff(have, wanted):
    """What turns `have` into `wanted`: entries to remove, add and change."""
    old = dict((key(e), e) for e in have)
    new = dict((key(e), e) for e in wanted)
    return {
        "remove": [old[k] for k in sorted(old) if k not in new],
        "add": [new[k] for k in sorted(new) if k not in old],
        "change": [(old[k], new[k]) for k in sorted(new)
                   if k in old and _canonical(old[k]) != _canonical(new[k])],
    }


def same(ide_text, disk_text):
    """Equal as entries. A disk file that does not parse is never equal."""
    disk, problems = parse(disk_text)
    if problems:
        return False
    ide, _ = parse(ide_text)
    return (sorted(_canonical(e) for e in ide)
            == sorted(_canonical(e) for e in disk))


def mismatches(after, wanted):
    """Each entry of `wanted` the IDE does not hold as written, by name."""
    d = diff(after, wanted)
    found = ["%s %s: not in the IDE after import" % (e["kind"], e["name"])
             for e in d["add"]]
    found += ["%s %s: still in the IDE" % (e["kind"], e["name"])
              for e in d["remove"]]
    found += ["%s %s: the IDE has %r" % (new["kind"], new["name"], _line(old))
              for old, new in d["change"]]
    return found

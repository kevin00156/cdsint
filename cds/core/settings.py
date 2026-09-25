# -*- coding: utf-8 -*-
"""The settings file next to the project: what is in it, and how to read it.

One JSON file per project, named after it -- `Line.project` sits beside
`Line.cdsint.json` (SPEC D10). It replaces the project properties the
settings used to live in, which were inside the binary `.project` and so
could only be read or written by a running IDE.

The schema below is the only one. Both sides of the IDE boundary import it,
which is why it is here rather than in `engine/` or `cds/ide/` (SPEC D12),
and being pure Python it is tested in CI.

Validation happens in `read` and nowhere else. The file is edited by hand, so
a typo is not a possibility but a certainty, and a misspelt key that quietly
does nothing is worse than a command that refuses to run (SPEC 4.4).
"""
from __future__ import print_function

import io
import json
import os

# IronPython 2.7 has two string types and json hands back the unicode one;
# CPython 3 has one. The set collapses to whichever this interpreter has.
TEXT_TYPES = tuple(set([type(u""), type("")]))

# What a value may be. The name is what a refusal prints, so it reads as the
# thing a person would type into the file rather than as a Python type.
TEXT = "a string"
FLAG = "true or false"
COUNT = "a whole number"
# The only words the `plc` list recognises (SPEC 6.5), one per plc command
# that talks to a controller.
PLC_ACTIONS = ("connect", "download", "trace")
ACTIONS = "a list of the words " + ", ".join(PLC_ACTIONS)

# name, kind, default, what it is for. `sync_folder` is the one setting with
# no default -- there is no sensible guess for where somebody's files go, so
# the first export asks (SPEC 6.7) -- and NO_DEFAULT marks it so that
# `resolve` can leave it out rather than inventing an empty string.
NO_DEFAULT = object()

SCHEMA = (
    ("auto_delete_orphans", FLAG, False,
     "delete .st files with no object behind them, without asking"),
    ("backup_binary", FLAG, False,
     "copy the .project into the sync folder on export"),
    ("backup_name", TEXT, "", "what to call those backups"),
    ("backup_retention_count", COUNT, 10, "how many backups to keep"),
    ("debug", FLAG, False, "write sync_metadata.json and the *.log files"),
    ("devices", FLAG, False,
     "let import apply EtherCAT device settings (SPEC 6.10)"),
    ("export_xml", FLAG, False,
     "also export visualisations, alarms and text lists as XML"),
    ("plc", ACTIONS, (), "which PLC commands this project allows (SPEC 6.5)"),
    ("safety_backup", FLAG, True, "back the .project up before an import"),
    ("save_after_export", FLAG, True, "save the project after an export"),
    ("save_after_import", FLAG, True, "save the project after an import"),
    ("sync_folder", TEXT, NO_DEFAULT,
     "where the .st files live; './...' is relative to the project file"),
    ("trace_memory_mb", COUNT, 256,
     "the most controller memory one plc trace may ask for (SPEC 6.8)"),
)

KINDS = dict((name, kind) for name, kind, _d, _m in SCHEMA)
DEFAULTS = dict((name, default) for name, _k, default, _m in SCHEMA
                if default is not NO_DEFAULT)

SUFFIX = ".cdsint.json"


class Invalid(ValueError):
    """The settings file cannot be used, and the message says how to fix it.

    Every refusal carries the whole table, because the reader is looking at a
    file they wrote by hand and the next thing they need is the list of names
    that are actually spelled that way.
    """


def path_for(project_path):
    """The settings file that belongs to this .project."""
    directory, name = os.path.split(project_path)
    stem = os.path.splitext(name)[0]
    return os.path.join(directory, stem + SUFFIX)


def read(path):
    """What the file says, or None when there is no file.

    Only the keys the file actually holds come back, so a caller can still
    tell "nobody decided" from "somebody chose the default" -- which is what
    lets the first-run dialog write one key and leave the rest alone.
    """
    try:
        with io.open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (IOError, OSError):
        # Missing is the normal state of a project nobody has set up yet.
        # Unreadable for any other reason is not, and the caller sees it.
        if not os.path.exists(path):
            return None
        raise
    try:
        found = json.loads(text)
    except ValueError as exc:
        raise Invalid(_refusal(path, "it is not valid JSON: %s" % (exc,)))
    if not isinstance(found, dict):
        raise Invalid(_refusal(path, "the top level is not an object"))
    return dict((key, _checked(path, key, value))
                for key, value in found.items())


def resolve(written):
    """The file's keys plus every default, ready to use without converting.

    Callers read values straight out of this: the types are the schema's
    types, so nothing downstream wraps a setting in bool() or int() again.
    `sync_folder` is absent when nobody has set it, for the reason in SCHEMA.
    """
    values = dict(DEFAULTS)
    values["plc"] = list(DEFAULTS["plc"])
    values.update(written or {})
    return values


def write(path, values):
    """Replace the file with exactly these keys. Nothing else is kept.

    Not validated here: `read` is the only validator (SPEC 4.4), and adding a
    second one would be a second place for the rules to drift.
    """
    text = json.dumps(_plain(values), ensure_ascii=False, indent=2,
                      sort_keys=True)
    if not isinstance(text, type(u"")):  # IronPython 2.7 hands back bytes
        text = text.decode("utf-8")
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text + u"\n")


def is_relative(sync_folder):
    """Does this value resolve against the project's own directory?

    One predicate, because two would drift: the first-run dialog decides with
    it whether to write a relative path, and `folder` below decides with it
    whether to resolve one. "./..." and "." travel with a project; everything
    else -- another drive, a folder outside the project -- has no relative
    form worth keeping and is used as written (SPEC 6.7).
    """
    here = _separators(sync_folder)
    return here == "." or here.startswith("." + os.sep)


def folder(sync_folder, project_dir):
    """Where `sync_folder` points, absolute. None when there is nothing to point.

    None also when a relative path has no project directory to resolve
    against, which is a project the IDE could not give a path for.
    """
    raw = (sync_folder or "").strip()
    if not raw:
        return None
    if not is_relative(raw):
        return os.path.normpath(raw)
    if not project_dir:
        return None
    return os.path.normpath(os.path.join(project_dir, _separators(raw)))


def _separators(value):
    """The path with this platform's separator, whichever one was typed."""
    return (value or "").strip().replace("/", os.sep).replace("\\", os.sep)


def table():
    """The schema as lines a person can read, one setting per line."""
    lines = []
    for name, kind, default, meaning in SCHEMA:
        shown = ("no default; the first export asks"
                 if default is NO_DEFAULT
                 else "default " + json.dumps(_plain_value(default)))
        lines.append("  %-22s %-38s %s" % (name, kind + ", " + shown, meaning))
    return lines


# -- the checking ----------------------------------------------------------

def _checked(path, key, value):
    """One entry, or a refusal naming it. Returns the value in schema form."""
    kind = KINDS.get(key)
    if kind is None:
        raise Invalid(_refusal(path, "%s is not a setting cdsint knows"
                               % json.dumps(key)))
    if kind == FLAG:
        return _flag(path, key, value)
    if kind == COUNT:
        return _count(path, key, value)
    if kind == TEXT:
        return _text(path, key, value)
    return _actions(path, key, value)


def _flag(path, key, value):
    if not isinstance(value, bool):
        raise Invalid(_wrong_type(path, key, value))
    return value


def _count(path, key, value):
    # bool is an int in Python, and `"backup_retention_count": true` is a
    # mistake worth naming rather than reading as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise Invalid(_wrong_type(path, key, value))
    return value


def _text(path, key, value):
    if not isinstance(value, TEXT_TYPES):
        raise Invalid(_wrong_type(path, key, value))
    return value


def _actions(path, key, value):
    """The `plc` list. An unrecognised word is printed as written, not fixed.

    Guessing that "downlaod" meant "download" would make the gate on PLC
    downloads depend on a spelling correction; a typo the reader can see is a
    typo they can fix (SPEC 6.5).
    """
    if not isinstance(value, list):
        raise Invalid(_wrong_type(path, key, value))
    for word in value:
        if not isinstance(word, TEXT_TYPES):
            raise Invalid(_wrong_type(path, key, value))
        if word.strip().lower() not in PLC_ACTIONS:
            raise Invalid(_refusal(
                path, "%s is not one of %s, so plc %s allows nothing"
                % (json.dumps(word), ", ".join(PLC_ACTIONS),
                   json.dumps(value))))
    return [word.strip().lower() for word in value]


def _wrong_type(path, key, value):
    return _refusal(path, "%s wants %s, not %s"
                    % (key, KINDS[key], json.dumps(_plain_value(value))))


def _refusal(path, problem):
    return u"\n".join([u"cannot read %s: %s" % (path, problem), u"",
                       u"The settings cdsint knows:"]
                      + table())


def _plain(values):
    return dict((key, _plain_value(value)) for key, value in values.items())


def _plain_value(value):
    """Tuples become lists: the schema holds `plc`'s empty default immutable."""
    return list(value) if isinstance(value, tuple) else value

# -*- coding: utf-8 -*-
"""Read and write the cds-sync-* project properties from outside the IDE.

These live in the .project file, so only something running inside an IDE can
touch them. Until now the only way in was the Settings dialog, which needs a
person; this is the same properties for a caller who has no screen (SPEC 4.4,
6.7).

Reading and writing a named property is plumbing, not object-tree work, so it
belongs on this side of SPEC D12 rather than in the engine — cds/ide/project.py
already reads cds-sync-folder the same way.
"""
from __future__ import print_function

from cds.ide import project

# The properties a caller may read and write, and what each one is for. This
# is SPEC 4.4's table in the form a program can use: a name that is not here
# is a typo, and silently writing it would leave a property nothing reads.
PROPERTIES = {
    "cds-sync-folder": "where the .st files live, absolute or relative to the project",
    "cds-sync-pc": "the computer the sync folder was set up on",
    "cds-sync-version": "the tool version that last synced",
    "cds-sync-debug": "true to write sync_metadata.json and the *.log files",
    "cds-sync-export-xml": "true to also export visualisations and alarms as XML",
    "cds-sync-backup-binary": "true to copy the .project into the sync folder on export",
    "cds-sync-safety-backup": "true to back the .project up before an import",
    "cds-sync-backup-name": "what to call those backups",
    "cds-sync-backup-retention-count": "how many backups to keep",
    "cds-sync-save-after-import": "true to save the project after an import",
    "cds-sync-save-after-export": "true to save the project after an export",
    "cds-sync-auto-delete-orphans": "true to delete orphaned .st files on export",
}

# Readable, never writable from here. The property means "a person decided
# this in the IDE", and a CLI that can write it erases that meaning. It is a
# policy, not a wall: headless mode already runs arbitrary IronPython inside
# the IDE, so anyone who wants to get past it can (SPEC 6.5).
READ_ONLY = "cds-sync-plc"


def run(ide_globals, args):
    """Answer one config command. Returns the same record an entry body does.

    The shape is engine/entry.py's result(): ok, summary, data. Built by hand
    because cds/ide may not import the engine (SPEC D12).
    """
    args = args or {}
    key = args.get("key")
    value = args.get("value")
    projects_obj = ide_globals.get("projects")
    if getattr(projects_obj, "primary", None) is None:
        return _result(False, "no project is open, so there are no properties "
                              "to read or write")
    if value is not None:
        return _set(projects_obj, key, value)
    return _get(projects_obj, key)


def _get(projects_obj, key):
    if key is None:
        return _get_all(projects_obj)
    known = _reject_unknown(key, readable=True)
    if known is not None:
        return known
    found = project.prop(projects_obj, key)
    if found is None:
        return _result(True, "%s is not set" % key, **{key: None})
    return _result(True, "%s = %s" % (key, found), **{key: found})


def _get_all(projects_obj):
    """Every known property this project has a value for.

    The ones with no value are left out rather than reported as empty: a
    caller cannot tell "" from "never set" otherwise, and the count in the
    summary says how many are missing.
    """
    names = sorted(list(PROPERTIES) + [READ_ONLY])
    found = {}
    for name in names:
        value = project.prop(projects_obj, name)
        if value is not None:
            found[name] = value
    return _result(True, "%d of %d properties are set"
                   % (len(found), len(names)), **found)


def _set(projects_obj, key, value):
    if key is None:
        return _result(False, "config set needs a property; try KEY=VALUE")
    known = _reject_unknown(key, readable=False)
    if known is not None:
        return known
    if not project.set_prop(projects_obj, key, value):
        return _result(False, "could not write %s to Project Information > "
                              "Properties" % key)
    # Saving is the point. A property that lives only in the IDE's memory is
    # gone the next time the project is closed, and headless there is nobody
    # to close it politely — the process just ends. The cost is that an edit
    # the user had in flight is written out too, which is why the summary
    # says the project was saved.
    saved = project.save(projects_obj)
    return _result(True, "%s = %s%s" % (key, value,
                                        "; project saved" if saved else
                                        "; the project could not be saved, so "
                                        "this only lasts until it is closed"),
                   **{key: value})


def _reject_unknown(key, readable):
    """None when the key is usable, otherwise the refusal to hand back."""
    if key == READ_ONLY:
        if readable:
            return None
        return _result(False, "%s is set by a person in the IDE, not from "
                              "here (SPEC 6.5)" % READ_ONLY)
    if key not in PROPERTIES:
        return _result(False, "unknown property %r; the ones cdsint knows are "
                              "%s" % (key, ", ".join(sorted(PROPERTIES))))
    return None


def _result(ok, summary, **data):
    return {"ok": bool(ok), "summary": summary, "data": data}

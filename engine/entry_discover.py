# -*- coding: utf-8 -*-
"""discover - name every object in the project, and which kind it counted as.

The one diagnostic for "an object never reached the disk and nothing said
so". classify_object resolves an object's type GUID to a kind through the
guid_aliases table in profiles/default.json; a GUID no kind claims resolves
to nothing, and export then counts that object nowhere. This walks the same
tree, says what each object was recognised as, and names the GUIDs that
matched no kind so they can be appended to the right kind's alias list and
the export re-run.

`total` counts every node in the tree, not the objects export writes: the
ones export skips on purpose - property accessors, tasks, device modules,
anything a monolithic container owns - are exactly where a silently dropped
object hides, so leaving them out would remove the answer. On the softplc
project that is 407 against export's 229.

Read-only. It changes nothing in the IDE and writes nothing to the sync
folder except through log_info, which only reaches sync_debug.log when
the settings file turns debug on.
"""
from __future__ import print_function

from engine.codesys_constants import kind_of
from engine.strings import safe_str
from engine.sync_log import init_logging, log_info, log_warning
from engine import entry, settings, unhandled


def discover_project(projects_obj=None):
    """Survey the object tree and report what it is made of."""
    projects_obj = projects_obj or entry.borrowed(globals(), "projects")
    if projects_obj is None or not projects_obj.primary:
        msg = "Error: 'projects' object not found or no project open."
        system.ui.error(msg)
        return entry.result(False, msg)

    # No sync folder yet is not a reason to refuse: discover is what somebody
    # runs *because* the export did not work. Without one the log has nowhere
    # to go, and the tree on stdout is the whole answer. A settings file that
    # cannot be read is a different thing and does refuse (SPEC 4.4).
    values, base_dir, error = settings.prepare(globals())
    if error:
        system.ui.error(error)
        return entry.result(False, error)
    init_logging(base_dir, values["debug"])

    unhandled.start()
    survey = _survey(projects_obj.primary)
    # log_info prints as well as writing, so the tree goes out once: printing
    # it here and logging it too is how the old script put every line on
    # stdout twice.
    log_info("PROJECT TREE:\n" + "\n".join(_tree_lines(survey)))

    unknown = [{"name": record["name"], "guid": record["guid"]}
               for record in survey if record["kind"] is None
               and record["guid"]]
    by_kind = {}
    for record in survey:
        if record["kind"]:
            by_kind[record["kind"]] = by_kind.get(record["kind"], 0) + 1

    _report_unknown(unknown)
    return _verdict(len(survey), by_kind, unknown)


def _verdict(total, by_kind, unknown):
    """ok is False when anything went unrecognised (SPEC D13).

    A caller must not have to read `data` to find out that it needs to read
    `data`: an unknown GUID means the export it is about to run will drop
    those objects silently, which is the failure this command exists to
    catch.
    """
    failed = unhandled.names()
    summary = "%d objects, %d kinds, %d unknown type GUID(s)" % (
        total, len(by_kind), len(unknown))
    if unknown:
        summary += ": " + ", ".join(
            "%s (%s)" % (item["name"], item["guid"]) for item in unknown[:10])
    if failed:
        summary += " -- " + unhandled.summary()
    return entry.result(not unknown and not failed, summary,
                        total=total, by_kind=by_kind, unknown=unknown,
                        failed_objects=failed)


def _survey(project):
    """One record per object: name, type GUID, kind, and where it sits.

    get_children(recursive=True) is the enumeration export uses, so the two
    see the same objects. Each of the four IDE attributes is read once here
    and carried in the record rather than fetched again downstream
    (PRINCIPLES 3).
    """
    survey = []
    for obj in project.get_children(recursive=True):
        survey.append(_look_at(obj))
    return survey


def _look_at(obj):
    """What one object is, without letting a refused read end the walk.

    Reading .type raises when the plugin that owns the object is not
    installed in this IDE - a project opened in another vendor's product.
    classify_object survives that the same way, by naming the object rather
    than throwing (SPEC D13).
    """
    record = {"name": unhandled.name_of(obj), "guid": "", "kind": None,
              "own": "", "parent": ""}
    try:
        record["own"] = safe_str(obj.guid)
        record["parent"] = safe_str(obj.parent.guid) if obj.parent else ""
    except Exception as exc:
        log_warning("Could not place %s in the tree: %s"
                    % (record["name"], safe_str(exc)))
    try:
        record["guid"] = safe_str(obj.type).lower()
    except Exception as exc:
        unhandled.note(obj, exc)
        return record
    record["kind"] = kind_of(record["guid"])
    return record


def _tree_lines(survey):
    """The survey as an indented tree, parents before their children.

    An object whose parent is not in the survey hangs off the project root:
    get_children(recursive=True) returns everything under the project, so the
    only parent it can be missing is the project itself.
    """
    children_of = {}
    roots = []
    known = set(record["own"] for record in survey if record["own"])
    for record in survey:
        if record["parent"] in known:
            children_of.setdefault(record["parent"], []).append(record)
        else:
            roots.append(record)

    lines = []

    def walk(record, depth):
        lines.append("  " * depth + "|-- " + _describe(record))
        for child in children_of.get(record["own"], []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return lines


def _describe(record):
    if record["kind"]:
        return "%s (%s)" % (record["name"], record["kind"])
    return "[!] %s (UNKNOWN %s)" % (record["name"], record["guid"] or "?")


def _report_unknown(unknown):
    """Say what to do about the GUIDs no kind claimed.

    The fix is a JSON edit, not a code change, and saying so here is what
    stops the next reader going looking for the table in the engine.
    """
    if not unknown:
        return
    print("")
    print("UNKNOWN OBJECT TYPES -- these are missing from profiles/default.json:")
    for item in unknown:
        line = " - %s (example object: %s)" % (item["guid"], item["name"])
        print(line)
        log_warning("Unknown object type: " + line)
    print("Append each GUID to the matching kind's list under 'guid_aliases'")
    print("in profiles/default.json, then run discover again.")


def main():
    return discover_project()


if __name__ == "__main__":
    main()

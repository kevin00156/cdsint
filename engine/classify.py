# -*- coding: utf-8 -*-
"""What kind an object is, where its file goes, and who handles it.

One answer for both directions. Export and compare have to agree about every
object, and when they do not, compare sees "no disk file" for something export
never writes, marks it an orphan, and the next import deletes it from the IDE.
They used to agree by carrying the same thirty lines twice, with a comment in
one copy asking whoever edited it to remember the other.

This is the deciding half; codesys_managers.py is the doing half. It stayed
there until the shared answers outgrew it -- classify_object() and
build_expected_path() are still over there, because they read the IDE object
rather than decide anything about the command.
"""
from __future__ import print_function

import collections

from engine import unhandled
from engine.codesys_constants import TYPE_GUIDS, XML_TYPES, kind_allows_export
from engine.codesys_managers import (
    ConfigManager, FolderManager, NativeManager, POUManager, PropertyManager,
    build_expected_path, classify_object,
)
from engine.codesys_utils import log_info, log_warning, safe_str


# What resolve_object decided about one object.
#
# skip_reason is None when the object gets a file; otherwise it names the gate
# that stopped it, because the reasons are not interchangeable downstream: an
# unsupported kind has no path at all, while a kind the profile does not
# export has one that simply must not be written.
#
# cache says how the answer was reached -- "hit", "invalidated" or "miss".
# That is the number the compare pass reports, and it is the only way to tell
# a genuinely slow run from a cold cache.
Resolved = collections.namedtuple(
    "Resolved", "effective_type is_xml rel_path skip_reason cache")

SKIP_UNSUPPORTED = "unsupported"
SKIP_NO_PATH = "no_path"
SKIP_SYNC_DIRECTION = "sync_direction"
SKIP_XML_GATE = "xml_gate"

# The XML kinds written whether or not export_xml is on. A task configuration
# and the NVL lists are project structure, not the optional extras the flag is
# about (Library Manager, visualizations, alarm config, trace).
ALWAYS_EXPORTED_XML = (
    TYPE_GUIDS["task_config"],
    TYPE_GUIDS["nvl_sender"],
    TYPE_GUIDS["nvl_receiver"],
)


def collect_accessors(obj, obj_guid, effective_type, accessors):
    """Record this property's GET and SET children in `accessors`, keyed by GUID.

    A property's file is one text holding the declaration and both accessors,
    so whoever is about to build or compare that text needs the two children.
    Both the export loop and the compare pass gather them while they are
    already walking every object, because a second walk would be a second read
    of every name (PRINCIPLES 3) -- and both had written out the same fifteen
    lines to do it.

    Not a property: nothing happens. A property whose children will not be
    listed: an empty pair, so the text is built as if GET and SET were empty,
    and the object is named (SPEC D13) rather than quietly compared wrong.
    """
    if effective_type != TYPE_GUIDS["property"]:
        return
    guid = obj_guid
    if guid is None:
        return
    if guid not in accessors:
        accessors[guid] = {'get': None, 'set': None}
    try:
        children = obj.get_children()
    except Exception as exc:
        unhandled.note(obj, exc)
        log_warning("Could not read the accessors of %s: %s"
                    % (unhandled.name_of(obj), safe_str(exc)))
        return
    for child in children:
        try:
            name = child.get_name().upper()
        except Exception as exc:
            unhandled.note(child, exc)
            continue
        if name == "GET":
            accessors[guid]['get'] = child
        elif name == "SET":
            accessors[guid]['set'] = child


def resolve_object(obj, obj_guid, cached_types, export_xml, project):
    """Classify one object and say where its file goes. One answer, both ways.

    Export and compare have to agree about every object. When they do not,
    compare sees "no disk file" for something export never writes, marks it an
    orphan, and the next import deletes it from the IDE. They used to agree by
    carrying the same thirty lines twice, with a comment in one of them asking
    whoever edited it to remember the other.

    cached_types is the type cache from sync_cache.json, already reshaped by
    codesys_utils.cached_classification.

    obj_guid is passed in rather than read here. Every caller already has it,
    and reading it again crosses into .NET for an answer they are holding
    (PRINCIPLES 3) -- measured on the softplc sample, that second read cost
    two seconds across 407 objects.
    """
    cached = cached_types.get(obj_guid) if obj_guid else None
    cached_rel_path = cached[2] if cached else None

    if cached_rel_path:
        # The cache is trusted only for an object that had a real path last
        # time. A cached "skip" never is: the set of supported kinds changes
        # between versions, and a once-skipped object would stay buried
        # forever -- and on the compare side its file would be deleted as a
        # false orphan.
        effective_type, is_xml = cached[0], cached[1]
        fresh_path = build_expected_path(obj, effective_type, is_xml, obj_guid)
        if not fresh_path or fresh_path == cached_rel_path:
            return _gated(effective_type, is_xml, cached_rel_path,
                          export_xml, "hit")
        # The path disagrees, so the object moved or was renamed, or the
        # cached classification predates the current profile. Re-classify
        # rather than half-trusting (effective_type, is_xml): those decide
        # .st against .xml, and a stale pair yields a path that neither
        # export nor import agrees on.
        log_info("Path invalidated for GUID %s: '%s' -> re-classifying"
                 % (obj_guid, cached_rel_path))
        cache = "invalidated"
    else:
        cache = "miss"

    effective_type, is_xml, unsupported = classify_object(obj, project)
    if unsupported:
        return Resolved(effective_type, is_xml, None, SKIP_UNSUPPORTED, cache)
    return _gated(effective_type, is_xml,
                  build_expected_path(obj, effective_type, is_xml, obj_guid),
                  export_xml, cache)


def _gated(effective_type, is_xml, rel_path, export_xml, cache):
    """The gates that apply once a kind and a path are known."""
    if not rel_path:
        # A top-level folder resolves to the sync folder itself, which is not
        # a place to write anything.
        return Resolved(effective_type, is_xml, None, SKIP_NO_PATH, cache)
    if not kind_allows_export(effective_type):
        return Resolved(effective_type, is_xml, rel_path,
                        SKIP_SYNC_DIRECTION, cache)
    if (is_xml and not export_xml and effective_type in XML_TYPES
            and effective_type not in ALWAYS_EXPORTED_XML):
        # Export does not write these when the flag is off, so compare must
        # not look for their files. Without the same answer on both sides,
        # pass 2 calls them orphans and import removes them.
        return Resolved(effective_type, is_xml, rel_path, SKIP_XML_GATE, cache)
    return Resolved(effective_type, is_xml, rel_path, None, cache)


def create_import_managers(project, pou_type=None):
    """One manager per kind that needs its own, plus the two fallbacks.

    Export and import share this dict: they are the same objects, and a kind
    that needs special handling on the way out needs it on the way back.

    The project is handed to every one of them here, once. Six methods used
    to go looking for it themselves through a resolver that searched every
    loaded module; a command has exactly one project open and already knows
    which. pou_type goes the same way, and only the two managers that create
    a POU need it.
    """
    return {
        TYPE_GUIDS["folder"]: FolderManager(project),
        TYPE_GUIDS["property"]: PropertyManager(project, pou_type),
        TYPE_GUIDS["task_config"]: ConfigManager(project),
        TYPE_GUIDS["alarm_config"]: ConfigManager(project),
        TYPE_GUIDS["visu_manager"]: ConfigManager(project),
        TYPE_GUIDS["device"]: ConfigManager(project),
        TYPE_GUIDS["softmotion_pool"]: ConfigManager(project),
        "default": POUManager(project, pou_type),
        "native": NativeManager(project)
    }


def manager_for(managers, effective_type, is_xml):
    """Which manager handles this object. The only rule, for both directions.

    A kind with a manager of its own gets it; everything else goes to native
    when it is stored as XML and to the text manager when it is not.

    There were two rules. Export asked for a dedicated manager first; import
    saw the ".xml" suffix and went straight to native, so a device -- which
    has a dedicated ConfigManager -- was handled by one manager on the way out
    and another on the way back. That cost nothing only because ConfigManager
    inherits update() and create() unchanged from NativeManager, which is a
    fact about today's class body and not a rule anybody wrote down.
    """
    dedicated = managers.get(effective_type)
    if dedicated is not None:
        return dedicated
    return managers["native"] if is_xml else managers["default"]

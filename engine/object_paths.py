# -*- coding: utf-8 -*-
"""Where an IDE object sits in the tree, as the path its file takes on disk.

Every ancestor read crosses into .NET, so the container prefix and the
ancestor chain are memoized per object; clear_path_caches() starts a pass
fresh. build_expected_path() is the one answer to "which file is this
object" that export, compare and import all use.

Moved out of codesys_managers.py unchanged.
"""
from __future__ import print_function

from engine.codesys_utils import safe_str, clean_filename
from engine.codesys_constants import TYPE_GUIDS
from engine.ide_read import guid_of, parent_of


# ── Ancestor-chain memoization ──────────────────────────────────────────
# Both path helpers below walk from an object up towards the project root, and
# every step reads .type / .get_name() / .parent off a live IDE object -- a
# .NET round trip each. build_expected_path() calls both, so each object used
# to pay for two full root walks, and it is called for every object on every
# run (the type cache stores a path but the caller re-derives one to validate
# it, so the walk is never skipped).
#
# Objects in the same container share an ancestor chain, so the answer is
# cached per ancestor. A project with 150 objects across 44 folders goes from
# ~300 root walks to ~44.
_container_prefix_cache = {}

_object_path_cache = {}


def clear_path_caches():
    """Drop the memoized ancestor lookups.

    Call before computing paths in a fresh pass. The caches are keyed by
    object GUID, which survives a move, so anything that relocates objects in
    the IDE must clear them before paths are derived again.
    """
    _container_prefix_cache.clear()
    _object_path_cache.clear()


def _node_type(obj):
    """Type GUID of an IDE node, or None when it cannot be read.

    Replaces `hasattr(o,'type') and hasattr(o,'get_name')` followed by
    `safe_str(o.type)`: three crossings into .NET where one suffices. A node
    whose type is unreadable is treated as the end of the walk, exactly as the
    hasattr guards did.
    """
    try:
        value = getattr(obj, "type", None)
    except:
        return None
    if value is None:
        return None
    if not hasattr(obj, "get_name"):
        return None
    return safe_str(value)


def _container_names(obj, obj_guid=None):
    """(device_name, app_name) considering obj and every ancestor.

    The original walked upwards letting each higher ancestor overwrite what a
    lower one had set, so the OUTERMOST device/application wins. This collects
    the uncached part of the chain first, then fills it in from the top down,
    which reproduces that precedence while letting every node keep its own
    answer.
    """
    chain = []
    device_name = None
    app_name = None

    current = obj
    key = obj_guid if obj_guid is not None else guid_of(obj)
    while current is not None:
        if key is not None and key in _container_prefix_cache:
            device_name, app_name = _container_prefix_cache[key]
            break
        chain.append((key, current))
        current = parent_of(current)
        key = guid_of(current) if current is not None else None

    for key, node in reversed(chain):
        try:
            node_type = safe_str(node.type)
            # Only fill a slot that is still empty: whatever came from above
            # is the outer one and takes precedence.
            if node_type == TYPE_GUIDS.get("application"):
                if app_name is None:
                    app_name = clean_filename(node.get_name())
            elif node_type == TYPE_GUIDS.get("device"):
                if device_name is None:
                    device_name = clean_filename(node.get_name())
        except:
            pass
        if key is not None:
            _container_prefix_cache[key] = (device_name, app_name)

    return device_name, app_name


def _path_stop_types(stop_at_application):
    """Ancestor types that end a path walk and contribute no folder name."""
    stops = [TYPE_GUIDS["plc_logic"], TYPE_GUIDS["device"],
             # Tasks are exported inside the monolithic Task Configuration XML,
             # so they must not produce subfolders on disk.
             TYPE_GUIDS["task_config"], TYPE_GUIDS["task"]]
    if stop_at_application:
        stops.append(TYPE_GUIDS["application"])
    return stops


def _ancestor_path(node, stop_types):
    """Folder names for node and its ancestors, outermost first. Cached."""
    chain = []
    names = ()

    current = node
    while current is not None:
        key = guid_of(current)
        if key is not None and key in _object_path_cache:
            names = _object_path_cache[key]
            break
        current_type = _node_type(current)
        if current_type is None:
            break
        if current_type in stop_types:
            # A stop node contributes nothing, and nothing above it counts.
            if key is not None:
                _object_path_cache[key] = ()
            names = ()
            break
        chain.append((key, current))
        current = parent_of(current)

    for key, ancestor in reversed(chain):
        try:
            names = names + (clean_filename(ancestor.get_name()),)
        except:
            pass
        if key is not None:
            _object_path_cache[key] = names

    return names


def get_object_path(obj, stop_at_application=True, parent=None):
    """
    Build the path from object to Application root.
    Returns list of folder names from Application (exclusive) to object (exclusive).

    Pass `parent` when the caller already holds it; fetching it is a round trip.
    """
    if parent is None:
        parent = parent_of(obj)
    if parent is None:
        return []
    stop_types = _path_stop_types(stop_at_application)
    if not stop_at_application:
        # Rare enough not to be worth a second cache keyed on the flag.
        return list(_uncached_ancestor_path(parent, stop_types))
    return list(_ancestor_path(parent, stop_types))


def _uncached_ancestor_path(node, stop_types):
    names = []
    current = node
    while current is not None:
        current_type = _node_type(current)
        if current_type is None or current_type in stop_types:
            break
        try:
            names.insert(0, clean_filename(current.get_name()))
        except:
            break
        current = parent_of(current)
    return names


def get_container_prefix(obj, obj_guid=None):
    """Walk up from obj to find its Device and Application names.
    Returns list like ['PLC', 'ST_Application'] or [] for global objects.

    Pass `obj_guid` when the caller already has it; reading .guid is a round trip.
    """
    device_name, app_name = _container_names(obj, obj_guid)
    parts = []
    if device_name: parts.append(device_name)
    if app_name: parts.append(app_name)
    return parts


# Kinds that can own an action/method/property. Built once: the tuple was
# rebuilt on every call, and TYPE_GUIDS is fixed at import.
_MEMBER_PARENT_TYPES = (TYPE_GUIDS["pou"], TYPE_GUIDS["itf"])


def get_parent_pou_name(obj, parent=None):
    """Get parent POU/Interface name for nested objects (actions, methods, properties).

    Pass `parent` when the caller already has it. Every `obj.parent` is a .NET
    round trip, and this used to take six of them -- two to test it exists and
    is truthy, two more for hasattr checks, then one each for .type and
    .get_name() -- to read at most one name. hasattr() is a getattr() under the
    covers, so testing before reading doubled every lookup; try/except reads
    each property exactly once instead.
    """
    try:
        if parent is None:
            parent = getattr(obj, "parent", None)
        if not parent:
            return None
        try:
            parent_type = safe_str(parent.type)
        except:
            return None
        if parent_type in _MEMBER_PARENT_TYPES:
            return parent.get_name()
    except:
        pass
    return None


def build_expected_path(obj, effective_type, is_xml, obj_guid=None):
    """Build the expected rel_path for an IDE object.

    Pass obj_guid when the caller already has it. Every caller on the
    per-object path does, and reading .guid again is a .NET round trip for an
    answer somebody upstairs is holding (PRINCIPLES 3).
    """
    from engine.codesys_constants import TYPE_NAMES, TYPE_GUIDS, kind_of

    # obj.guid and obj.parent are each a .NET round trip, and this function is
    # on the per-object path for both export and compare. The helpers below
    # used to fetch them independently -- guid twice, parent twice, plus six
    # more parent reads inside get_parent_pou_name -- so read each once here
    # and hand them down.
    if obj_guid is None:
        obj_guid = guid_of(obj)
    parent = parent_of(obj)

    container = get_container_prefix(obj, obj_guid=obj_guid)
    path_parts = get_object_path(obj, parent=parent)
    obj_name = obj.get_name()
    clean_name = clean_filename(obj_name)

    if is_xml:
        # Special case: POUs exported as XML (graphical) use 'pou_xml' extension
        if effective_type == TYPE_GUIDS["pou"]:
            type_name = "pou_xml"
        else:
            type_name = TYPE_NAMES.get(effective_type, effective_type[:8])
        file_name = clean_name + "." + type_name + ".xml"
    else:
        # kind_of(effective_type), not kind_of(obj.type): they agree on this
        # branch, and the caller already has effective_type. classify_object
        # sets effective_type to the normalized GUID for the object's own kind,
        # and the two cases where it deviates -- an NVL masquerading as a GVL,
        # a graphical POU -- both set is_xml and so never reach here.
        obj_kind = kind_of(effective_type)
        parent_pou = get_parent_pou_name(obj, parent=parent)
        # Nested objects (Action, Method, Property) prefix filename with parent POU name
        if parent_pou and obj_kind in ("action", "method", "property", "itf_method"):
            file_name = clean_filename(parent_pou) + "." + clean_name + ".st"
            clean_parent_pou = clean_filename(parent_pou)
            # If the path already has the parent name as a folder, remove it to avoid redundancy
            if path_parts and path_parts[-1] == clean_parent_pou:
                path_parts = path_parts[:-1]
        elif obj_kind == "folder":
            # Folders use their own name as the last part of path
            file_name = ""
        else:
            file_name = clean_name + ".st"

    full_path_parts = container + path_parts
    if not file_name:
        return "/".join(full_path_parts)
    
    if full_path_parts:
        return "/".join(full_path_parts) + "/" + file_name
    return file_name

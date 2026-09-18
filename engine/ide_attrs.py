# -*- coding: utf-8 -*-
"""The build attributes an object carries in the IDE, read and written.

exclude_from_build, link_always and the rest live behind properties that
not every build exposes, so which ones are readable is probed once per
run. ide_flag() is the one-crossing boolean read.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

from engine.unhandled import name_of
from engine.strings import safe_str
from engine.sync_log import is_debug, log_info, log_warning


def ide_flag(obj, name):
    """Read a boolean property off an IDE object, treating any failure as False.

    Replaces the `hasattr(obj, name) and obj.name` idiom. hasattr() is itself a
    property read, so that form cost two .NET round trips per flag; this costs
    one while keeping the old behaviour exactly -- Python 2's hasattr swallows
    every exception, not just AttributeError, so a property that raises must
    still read as False rather than propagating.
    """
    try:
        return bool(getattr(obj, name, False))
    except:
        return False


_MISSING = object()

_attr_probe_cache = {}  # obj_type -> tuple of (attr_key, api_prop)


def clear_attr_probe_cache():
    """Forget which build properties apply to each object type."""
    _attr_probe_cache.clear()


def _readable_attr_props(obj_type, build_props):
    """(attr_key, api_prop) pairs worth reading for this object type.

    Discovering them costs up to four lookups per registry entry -- a hasattr
    and a read for '<prop>_is_valid', then the same for the property itself --
    and every one is a .NET round trip. Which members a build_properties object
    exposes follows from the object TYPE, which is already what ATTR_REGISTRY
    assumes by keying its 'types' on type GUIDs, so probe once per type rather
    than once per object.
    """
    cached = _attr_probe_cache.get(obj_type)
    if cached is not None:
        return cached

    from engine.codesys_constants import ATTR_REGISTRY
    pairs = []
    for key, spec in ATTR_REGISTRY.items():
        if obj_type not in spec["types"]:
            continue
        prop_name = spec["api_prop"]
        try:
            valid = getattr(build_props, prop_name + "_is_valid", _MISSING)
            if valid is not _MISSING and not valid:
                continue
            # Objects missing an ATTR_REGISTRY member are normal (older
            # CODESYS / other object flavors) - stay quiet about them.
            if getattr(build_props, prop_name, _MISSING) is _MISSING:
                continue
        except Exception:
            continue
        pairs.append((key, prop_name))

    pairs = tuple(pairs)
    _attr_probe_cache[obj_type] = pairs
    return pairs


def read_ide_attrs(obj, obj_type=None):
    """Read supported IDE attributes from live CODESYS object.

    Uses obj.build_properties (ScriptBuildProperties) to access build flags.
    Uses ATTR_REGISTRY to determine which attributes apply to this object type.
    Returns dict of {attr_key: True} for non-default attributes.

    Pass obj_type when the caller already read it; every caller on the
    per-object path had just done so, and re-reading .type is a round trip.
    """
    from engine.codesys_constants import ATTR_REGISTRY
    if obj_type is None:
        obj_type = safe_str(obj.type)
    attrs = {}

    if not any(obj_type in spec["types"] for spec in ATTR_REGISTRY.values()):
        return attrs

    # Access the build_properties sub-object (ScriptBuildProperties)
    build_props = None
    try:
        build_props = getattr(obj, "build_properties", None)
    except Exception as e:
        if is_debug():
            log_info("read_ide_attrs: %s has no build_properties: %s" % (name_of(obj), safe_str(e)))

    if build_props is None:
        return attrs

    for key, prop_name in _readable_attr_props(obj_type, build_props):
        try:
            if getattr(build_props, prop_name):
                attrs[key] = True
        except Exception as e:
            log_warning("Cannot read attr '%s' from %s: %s" % (key, name_of(obj), safe_str(e)))

    if attrs and is_debug():
        log_info("read_ide_attrs: %s -> %s" % (name_of(obj), list(attrs.keys())))
    return attrs


def write_ide_attrs(obj, attrs):
    """Apply parsed attributes to a CODESYS IDE object via build_properties.

    Only sets attributes that are supported for this object type per
    ATTR_REGISTRY. A missing pragma means False (unset), so clearing a pragma
    on disk clears the flag in the IDE.
    """
    from engine.codesys_constants import ATTR_REGISTRY
    obj_type = safe_str(obj.type)
    obj_name = safe_str(obj.get_name()) if hasattr(obj, "get_name") else "<unknown>"

    applicable = [key for key, spec in ATTR_REGISTRY.items() if obj_type in spec["types"]]
    if not applicable:
        return

    # Access the build_properties sub-object
    build_props = None
    try:
        build_props = getattr(obj, "build_properties", None)
    except Exception as e:
        log_warning("write_ide_attrs: %s has no build_properties: %s" % (obj_name, safe_str(e)))
        return

    if build_props is None:
        if attrs:
            log_warning("write_ide_attrs: %s -> build_properties is None, cannot apply attrs" % obj_name)
        return

    for key, spec in ATTR_REGISTRY.items():
        if obj_type not in spec["types"]:
            continue

        prop_name = spec["api_prop"]
        # Treat missing pragmas as False (unset)
        target_val = attrs.get(key, False)

        try:
            # Check if this property is valid for this object type
            valid_check = prop_name + "_is_valid"
            if hasattr(build_props, valid_check):
                if not getattr(build_props, valid_check):
                    continue

            # Only set it if it actually differs from target (to avoid dirtifying IDE unnecessarily)
            current_val = getattr(build_props, prop_name)
            if bool(current_val) != bool(target_val):
                setattr(build_props, prop_name, target_val)
                log_info("write_ide_attrs: updated %s.build_properties.%s = %s" % (obj_name, prop_name, target_val))
        except Exception as e:
            log_warning("Cannot write attr '%s' on %s: %s" % (key, obj_name, safe_str(e)))

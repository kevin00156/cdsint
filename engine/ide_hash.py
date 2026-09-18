# -*- coding: utf-8 -*-
"""A cheap hash of what an IDE object would export, without exporting it.

The cache compares this against what it remembered to skip an object
whose text has not changed, so it has to be built from exactly the parts
the export writes.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

from engine.unhandled import name_of
from engine.codesys_constants import TYPE_GUIDS, IMPLEMENTATION_TYPES
from engine.ide_attrs import ide_flag, read_ide_attrs
from engine.st_text import (
    build_state_hash,
    format_property_content,
    format_st_content,
)
from engine.strings import safe_str
from engine.sync_log import log_warning


def get_quick_ide_hash(obj, is_xml):
    """
    Quickly calculate identification hash from IDE object without full export.
    Includes build_properties (sync attributes) so attribute-only changes
    invalidate the cache.
    Returns None if full export is mandatory (e.g. XML types).
    """
    if is_xml:
        return None  # XML requires full export for stable comparison

    try:
        obj_type_guid = safe_str(obj.type)

        # Extract decl and impl. getattr-with-default rather than
        # hasattr()-then-read: hasattr() IS a read, so the guarded form fetched
        # every has_textual_* flag twice, and each fetch is a .NET round trip.
        # This runs for every object that takes the cache-skip path, so it is
        # the hottest function in an unchanged export.
        decl = obj.textual_declaration.text if ide_flag(obj, 'has_textual_declaration') else None

        if obj_type_guid == TYPE_GUIDS["property"]:
            # Special Case: Properties combine Get and Set children
            get_impl = None
            set_impl = None
            try:
                for child in obj.get_children():
                    c_name = child.get_name().lower()
                    if c_name not in ("get", "set"):
                        continue
                    c_decl = child.textual_declaration.text if ide_flag(child, 'has_textual_declaration') else ""
                    c_impl = child.textual_implementation.text if ide_flag(child, 'has_textual_implementation') else ""
                    if c_name == "get":
                        get_impl = format_st_content(c_decl, c_impl)
                    else:
                        set_impl = format_st_content(c_decl, c_impl)
            except Exception as exc:
                # No quick answer, rather than a quick wrong one. Swallowing
                # this hashed the property as if GET and SET were empty, and
                # that hash matched the one the previous run had computed the
                # same way -- so the cache said "identical" about a property
                # nobody could read, and the export skipped it.
                #
                # Not registered here. classify.collect_accessors reads the
                # same children of the same property earlier in the same pass
                # and registers it there; noting it again put one object in
                # the result twice ("2 object(s): P, P").
                log_warning("No quick hash for %s: its accessors could not be "
                            "read (%s)" % (name_of(obj), safe_str(exc)))
                return None

            content = format_property_content(decl, get_impl, set_impl)
        else:
            # Standard POU/GVL/DUT
            impl = obj.textual_implementation.text if ide_flag(obj, 'has_textual_implementation') else None
            if decl is not None or impl is not None:
                can_have_impl = obj_type_guid in IMPLEMENTATION_TYPES
                content = format_st_content(decl, impl, can_have_impl)
            else:
                return None

        # Include build attributes in the hash so attribute-only changes
        # (like toggling Exclude from build) invalidate the cache
        attrs = read_ide_attrs(obj, obj_type_guid)
        return build_state_hash(content, attrs)
    except Exception as e:
        log_warning("Quick hash failed: " + str(e))

    return None

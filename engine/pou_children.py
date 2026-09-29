# -*- coding: utf-8 -*-
"""Keeping a POU's members across a recreate.

The IDE deletes a POU's actions, methods and properties with it, so an update
that has to recreate the POU reads them out first and writes them back
afterwards, text and attributes both.

Both functions came over from codesys_compare_engine.py and have since been
rewritten here.
"""
from __future__ import print_function

from engine import unhandled
from engine.codesys_constants import TYPE_GUIDS, kind_of
from engine.ide_read import child_named, children_of
from engine.object_content import export_object_content, update_object_code
from engine.strings import safe_str
from engine.sync_log import log_error, log_info

# A property's text lives in these two children, not in the property.
ACCESSORS = ("get", "set")


def save_pou_children(pou_obj, project):
    """
    Save child objects (methods, actions, properties) of a POU before XML import.

    Returns list of child info dicts:
        [{'name': str, 'type_guid': str, 'declaration': str,
          'implementation': str, 'accessors': {'get': (decl, impl), ...}}, ...]

    A member that cannot be read here is lost when the import replaces the
    POU, so it is named now (SPEC D13) rather than logged and forgotten.
    """
    children_info = []
    child_types = [
        TYPE_GUIDS.get("action"),
        TYPE_GUIDS.get("method"),
        TYPE_GUIDS.get("property")
    ]
    try:
        children = pou_obj.get_children()
    except Exception as exc:
        unhandled.note(pou_obj, "its members could not be read: " + safe_str(exc))
        return children_info
    for child in children:
        try:
            child_type = safe_str(child.type)
            if child_type not in child_types:
                continue
            decl, impl = export_object_content(child, project)
            children_info.append({
                'name': child.get_name(),
                'type_guid': child_type,
                'declaration': decl,
                'implementation': impl,
                'accessors': _accessors_of(child, project),
            })
        except Exception as exc:
            unhandled.note(child, exc)
    return children_info


def _accessors_of(member, project):
    """A property's GET and SET text, by lower-case name; {} for the rest.

    One walk of the member's children for both, not one per accessor
    (PRINCIPLES 3). A child whose name will not read is named as child_named
    names it.
    """
    saved = {}
    for child in children_of(member):
        try:
            name = safe_str(child.get_name()).lower()
        except Exception as exc:
            unhandled.note(child, exc)
            continue
        if name in ACCESSORS:
            saved[name] = export_object_content(child, project)
    return saved


def restore_pou_children(pou_obj, saved_children, import_managers, project):
    """Put the saved members back on the POU the import made.

    Updates the ones the import kept and creates the rest with the creators
    POUManager uses. Every member that does not come back is named under
    "<POU>.<member>", so the run is not ok (SPEC D13): it used to be a log
    line, and the member was gone without a word in the result.
    """
    if not saved_children:
        return
    pou_name = safe_str(pou_obj.get_name())
    # One walk of the new POU's children, not one per member (PRINCIPLES 3).
    existing = dict((safe_str(child.get_name()).lower(), child)
                    for child in children_of(pou_obj))
    for child_info in saved_children:
        try:
            _restore_one(pou_obj, child_info, existing,
                         import_managers["default"])
        except Exception as exc:
            what = pou_name + "." + child_info['name']
            log_error("Could not restore %s: %s" % (what, safe_str(exc)))
            unhandled.note(what, exc)


def _restore_one(pou_obj, child_info, existing, pou_manager):
    child_name = child_info['name']
    child = existing.get(child_name.lower())
    if child is None:
        log_info("Creating child " + child_name + " of " + safe_str(pou_obj))
        child = pou_manager.create_member(pou_obj, child_name,
                                          kind_of(child_info['type_guid']))
        if child is None:
            raise RuntimeError("could not be created again")
    update_object_code(child, child_info['declaration'],
                       child_info['implementation'])
    for name, (decl, impl) in child_info.get('accessors', {}).items():
        accessor = child_named(child, name) or _create_accessor(child, name)
        if accessor is None:
            raise RuntimeError("its %s accessor could not be created again"
                               % name.upper())
        update_object_code(accessor, decl, impl)


def _create_accessor(prop, name):
    creator = getattr(prop, "create_%s_accessor" % name, None)
    return creator() if creator is not None else None

# -*- coding: utf-8 -*-
"""Keeping a POU's members across a recreate.

The IDE deletes a POU's actions, methods and properties with it, so an update
that has to recreate the POU reads them out first and writes them back
afterwards, text and attributes both.

Moved out of codesys_compare_engine.py unchanged.
"""
from __future__ import print_function

from engine.codesys_constants import TYPE_GUIDS
from engine.object_content import export_object_content, update_object_code
from engine.strings import safe_str
from engine.sync_log import log_info, log_warning


def save_pou_children(pou_obj, project):
    """
    Save child objects (methods, actions, properties) of a POU before XML import.
    
    Returns list of child info dicts:
        [{'name': str, 'type_guid': str, 'declaration': str, 'implementation': str}, ...]
    """
    children_info = []
    
    child_types = [
        TYPE_GUIDS.get("action"),
        TYPE_GUIDS.get("method"),
        TYPE_GUIDS.get("property")
    ]
    
    try:
        for child in pou_obj.get_children():
            try:
                child_type = safe_str(child.type)
                if child_type in child_types:
                    decl, impl = export_object_content(child, project)
                    children_info.append({
                        'name': child.get_name(),
                        'type_guid': child_type,
                        'declaration': decl,
                        'implementation': impl
                    })
            except Exception as e:
                log_warning("Could not save child " + safe_str(child) + ": " + safe_str(e))
    except Exception as e:
        log_warning("Could not get children of " + safe_str(pou_obj) + ": " + safe_str(e))
    
    return children_info


def restore_pou_children(pou_obj, saved_children, import_managers, project):
    """
    Restore child objects (methods, actions, properties) after XML import.
    
    Updates existing children or creates new ones.
    """
    if not saved_children:
        return
    
    try:
        existing_children = {}
        for child in pou_obj.get_children():
            existing_children[child.get_name().lower()] = child
    except Exception as e:
        log_warning("Could not get children of POU " + safe_str(pou_obj) + ": " + safe_str(e))
        return
    
    for child_info in saved_children:
        try:
            child_name = child_info['name']
            child_type = child_info['type_guid']
            decl = child_info['declaration']
            impl = child_info['implementation']
            
            existing_child = existing_children.get(child_name.lower())
            
            if existing_child:
                log_info("Restoring child " + child_name + " of " + safe_str(pou_obj))
                if update_object_code(existing_child, decl, impl):
                    log_info("  Successfully updated " + child_name)
            else:
                log_info("Creating child " + child_name + " of " + safe_str(pou_obj))
                try:
                    new_child = pou_obj.create_object(
                        name=child_name,
                        type_guid=child_type
                    )
                    if new_child:
                        if update_object_code(new_child, decl, impl):
                            log_info("  Successfully created " + child_name)
                        else:
                            log_warning("  Could not update code for new child " + child_name)
                    else:
                        log_warning("  Could not create child " + child_name)
                except Exception as e:
                    log_warning("  Failed to create child " + child_name + ": " + safe_str(e))
        except Exception as e:
            log_warning("Failed to restore child: " + safe_str(e))

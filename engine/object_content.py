# -*- coding: utf-8 -*-
"""The textual content of one IDE object: reading it out, writing it back.

Declaration and implementation come from the object's textual interface;
property accessors are the one kind whose text has to be parsed back into
parts before it can be written.

Moved out of codesys_managers.py unchanged.
"""
from __future__ import print_function

from engine.ide_attrs import ide_flag
from engine.strings import safe_str
from engine.sync_log import log_error, log_warning
from engine.codesys_constants import TYPE_GUIDS
from engine.ide_read import name_of
from engine.object_kind import native_xml_of


def export_interface_declaration(obj, project):
    """Extract interface declaration via native XML export fallback."""
    import re
    try:
        if project is None:
            return None

        xml_content = native_xml_of(project, obj)
        if xml_content is None:
            return None

        match = re.search(r'<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>', xml_content, re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception as e:
        log_warning("Could not extract interface declaration for " + name_of(obj) + ": " + safe_str(e))
    return None


def export_object_content(obj, project):
    """Extract declaration and implementation text from object."""
    declaration = None
    implementation = None
    # getattr-with-default rather than hasattr()-then-read: hasattr() is itself
    # a read, so the guarded form fetched each has_textual_* flag twice.
    try:
        if ide_flag(obj, "has_textual_declaration"):
            declaration = obj.textual_declaration.text
    except: pass

    if declaration is None and safe_str(obj.type) == TYPE_GUIDS["itf"]:
        declaration = export_interface_declaration(obj, project)

    try:
        if ide_flag(obj, "has_textual_implementation"):
            implementation = obj.textual_implementation.text
    except: pass
    return declaration, implementation


def update_object_code(obj, declaration, implementation):
    """Update object's textual declaration and/or implementation.
    
    Handles multiple CODESYS versions:
    - Some allow direct .text assignment
    - Some have read-only .text but support .replace(new_content) with a single string arg
    """
    updated = False
    try:
        if declaration is not None and ide_flag(obj, "has_textual_declaration"):
            doc = obj.textual_declaration
            if doc.text != declaration:
                try:
                    doc.text = declaration
                    updated = True
                except:
                    # Fallback: ScriptTextDocument.replace(new_content)
                    # takes a single string argument to replace the entire content
                    doc.replace(declaration)
                    updated = True

        if implementation is not None and ide_flag(obj, "has_textual_implementation"):
            doc = obj.textual_implementation
            if doc.text != implementation:
                try:
                    doc.text = implementation
                    updated = True
                except:
                    doc.replace(implementation)
                    updated = True
    except Exception as e:
        log_error("Error updating " + safe_str(obj.get_name()) + ": " + safe_str(e))
    return updated


def parse_accessor_content(combined_content):
    """Split combined accessor content into (declaration, implementation).
    
    Args:
        combined_content: String containing declaration and optionally
                          IMPL_MARKER followed by implementation code.
    
    Returns:
        tuple: (declaration, implementation) — implementation may be None.
    """
    from engine.codesys_constants import IMPL_MARKER
    if IMPL_MARKER in combined_content:
        parts = combined_content.split(IMPL_MARKER, 1)
        decl = parts[0].strip()
        code = parts[1].strip() if len(parts) > 1 else None
        return decl, code
    return combined_content.strip(), None

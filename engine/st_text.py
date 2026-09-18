# -*- coding: utf-8 -*-
"""The .st file format: what goes on disk for one object, and reading it back.

A file is the sync pragmas, the declaration, the implementation marker
and the implementation. Everything here is text in, text out -- no IDE
object is touched -- which is what lets the format be tested without one.
determine_object_type() sniffs a kind out of the text when no pragma says.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

import os
import codecs
from engine.codesys_constants import (
    IMPL_MARKER,
    PROPERTY_GET_MARKER,
    PROPERTY_SET_MARKER,
)
from engine.text_kind import determine_object_type
from engine.strings import calculate_hash, safe_str
from engine.sync_log import log_error, log_warning


def format_st_content(declaration, implementation, can_have_impl=False):
    """
    Format ST file content with clean structure.
    Uses markers for import script to parse sections.
    Ensures consistent whitespace for reliable hashing.
    
    Args:
        declaration: The declaration text
        implementation: The implementation text (may be None or empty)
        can_have_impl: True if object type can have implementation even if empty
    """
    content = []
    
    decl = (declaration or "").strip()
    if decl:
        content.append(decl)
    
    impl = (implementation or "").strip()
    if impl or can_have_impl:
        if content:
            content.append("")  # Empty line separator
        content.append(IMPL_MARKER)
        if impl:
            content.append(impl)
    
    return "\n".join(content)


def format_property_content(declaration, get_impl, set_impl):
    """
    Format property file content with GET and SET accessors combined.
    """
    content = []
    
    decl = (declaration or "").strip()
    if decl:
        content.append(decl)
    
    # Add GET section if present
    get = (get_impl or "").strip()
    if get:
        if content:
            content.append("")  # Empty line separator
        content.append(IMPL_MARKER)
        content.append(PROPERTY_GET_MARKER)
        content.append(get)
    
    # Add SET section if present
    set_content = (set_impl or "").strip()
    if set_content:
        if not get:
            # If no GET but we have SET, still need IMPL_MARKER
            if content:
                content.append("")
            content.append(IMPL_MARKER)
        content.append("")  # Empty line before SET
        content.append(PROPERTY_SET_MARKER)
        content.append(set_content)
    
    return "\n".join(content)


def merge_native_xmls(file_paths, output_path):
    """
    Merge multiple CODESYS .xml (Native Export) files into one.
    This allows importing them in a single batch, showing only one dialog.
    """
    if not file_paths: return False
    
    header = None
    footer = None
    payloads = []
    
    for path in file_paths:
        try:
            if not os.path.exists(path): continue
            with codecs.open(path, 'r', 'utf-8') as f:
                content = f.read()
            
            # Find the EntryList container
            start_marker = '<List2 Name="EntryList">'
            end_marker = '</List2>'
            
            s_idx = content.find(start_marker)
            e_idx = content.rfind(end_marker)
            
            if s_idx == -1 or e_idx == -1:
                log_warning("Could not find EntryList in " + path + ". Skipping merge.")
                continue
                
            if header is None:
                # Take the file structure from the first file
                header = content[:s_idx + len(start_marker)]
                footer = content[e_idx:]
            
            # Extract the actual object(s) inside the EntryList
            payload = content[s_idx + len(start_marker) : e_idx]
            payloads.append(payload)
        except Exception as e:
            log_error("Failed to read XML for merge: " + str(e))
            
    if not payloads: return False
    
    # Reassemble: Header + all payloads + Footer
    merged = header + "\n".join(payloads) + footer
    try:
        with codecs.open(output_path, 'w', 'utf-8') as f:
            f.write(merged)
        return True
    except Exception as e:
        log_error("Failed to write merged XML: " + str(e))
        return False


def parse_property_content(content):
    """
    Parse property file content to extract declaration, GET, and SET sections.
    
    Args:
        content: Full property file content string
    
    Returns:
        Tuple (declaration, get_impl, set_impl)
    """
    declaration = None
    get_impl = None
    set_impl = None
    
    if not content:
        return declaration, get_impl, set_impl
    
    # Split by IMPL_MARKER first
    if IMPL_MARKER in content:
        parts = content.split(IMPL_MARKER, 1)
        declaration = parts[0].strip()
        impl_section = parts[1].strip() if len(parts) > 1 else ""
        
        # Now split implementation by GET and SET markers
        if PROPERTY_GET_MARKER in impl_section:
            # Has GET section
            get_parts = impl_section.split(PROPERTY_GET_MARKER, 1)
            get_content = get_parts[1] if len(get_parts) > 1 else ""
            
            # Check if SET follows GET
            if PROPERTY_SET_MARKER in get_content:
                set_parts = get_content.split(PROPERTY_SET_MARKER, 1)
                get_impl = set_parts[0].strip()
                set_impl = set_parts[1].strip() if len(set_parts) > 1 else None
            else:
                get_impl = get_content.strip()
        elif PROPERTY_SET_MARKER in impl_section:
            # Has only SET section (no GET)
            set_parts = impl_section.split(PROPERTY_SET_MARKER, 1)
            set_impl = set_parts[1].strip() if len(set_parts) > 1 else None
        else:
            # No property markers, treat entire impl as GET (backward compatibility)
            get_impl = impl_section
    else:
        # No implementation marker - entire content is declaration
        declaration = content.strip()
    
    return declaration, get_impl, set_impl


def parse_sync_pragmas(content):
    """Parse leading cds-text-sync pragma lines from file content.

    Returns:
        (pragmas, clean_st)
        - pragmas: dict {key: value-string}, e.g. {"exclude_from_build":
          "true", "kind": "persistent_gvl"}
        - clean_st: content with the pragma block removed
    """
    from engine.codesys_constants import SYNC_PRAGMA_PREFIX
    lines = content.split("\n")
    pragmas = {}
    first_non_pragma = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(SYNC_PRAGMA_PREFIX):
            kv = stripped[len(SYNC_PRAGMA_PREFIX):]
            if "=" in kv:
                key, val = kv.split("=", 1)
                pragmas[key.strip()] = val.strip()
            first_non_pragma = i + 1
        elif stripped == "":
            if not pragmas:
                break
            first_non_pragma = i + 1
        else:
            break

    clean_st = "\n".join(lines[first_non_pragma:])
    clean_st = clean_st.lstrip("\n")
    return pragmas, clean_st


def needs_kind_pragma(kind, clean_content):
    """True when keyword sniffing (determine_object_type) would not recover
    this kind's primary GUID from the ST text alone.

    Such files (persistent GVLs, parameter lists, actions, interface
    methods, ...) carry a //% cds-text-sync.kind=<kind> pragma so import can
    reconstruct the right object kind. Unambiguous files (pou/gvl/dut/...)
    return False and stay byte-identical to pre-pragma exports.
    """
    from engine.codesys_constants import TYPE_GUIDS
    if not kind:
        return False
    return determine_object_type(clean_content) != TYPE_GUIDS.get(kind)


def attrs_from_pragmas(pragmas):
    """Filter a pragma dict down to boolean build attributes.

    Returns {attr_key: True} for ATTR_REGISTRY keys whose value is 'true' -
    the shape read_ide_attrs/write_ide_attrs/normalize_sync_attrs work with.
    """
    from engine.codesys_constants import ATTR_REGISTRY
    attrs = {}
    for key, val in pragmas.items():
        if key in ATTR_REGISTRY and str(val).strip().lower() == "true":
            attrs[key] = True
    return attrs


def render_sync_pragmas(pragmas, clean_st):
    """Render sync pragmas + clean ST content to final file content.

    Args:
        pragmas: dict that may contain "kind" (string) and boolean build
                 attributes ({"exclude_from_build": True, ...})
        clean_st: ST content without pragmas
    Returns:
        Final file content string
    """
    from engine.codesys_constants import ATTR_ORDER, SYNC_PRAGMA_PREFIX
    pragma_lines = []
    if pragmas.get("kind"):
        pragma_lines.append("%skind=%s" % (SYNC_PRAGMA_PREFIX, pragmas["kind"]))
    for key in ATTR_ORDER:
        if pragmas.get(key):
            pragma_lines.append("%s%s=true" % (SYNC_PRAGMA_PREFIX, key))

    if pragma_lines:
        return "\n".join(pragma_lines) + "\n\n" + clean_st
    return clean_st


def normalize_sync_attrs(attrs):
    """Normalize attrs dict to a stable, hashable tuple.

    Only includes keys from ATTR_ORDER that are True.
    Returns a tuple of sorted (key, True) pairs for deterministic hashing.
    """
    from engine.codesys_constants import ATTR_ORDER
    return tuple((k, True) for k in ATTR_ORDER if attrs.get(k))


def build_state_hash(code_content, attrs):
    """Build combined state hash from code content and attributes.

    Args:
        code_content: ST code string (already clean, no pragmas)
        attrs: dict {"exclude_from_build": True, ...}
    Returns:
        str: hex hash representing full object state
    """
    code_hash = calculate_hash(code_content)
    attrs_hash = calculate_hash(str(normalize_sync_attrs(attrs)))
    return calculate_hash(code_hash + "|" + attrs_hash)


def read_sync_text(file_path):
    """Read one file out of the sync folder as text. The only reader.

    utf-8-sig, not utf-8: a leading BOM is a byte-order mark, not the first
    character of the POU. Windows editors add one (PowerShell's Out-File,
    Notepad, Visual Studio), and read as plain utf-8 it becomes a U+FEFF at
    the head of the declaration that import then writes into the IDE. Measured
    on the bench 2026-09-06 (CODESYS 3.5.21.40): the untouched PLC_PRG.st with
    a BOM in front of it imported "successfully" and took the build from 0
    errors to 6. Nothing here ever writes a BOM, so this only ever drops one
    somebody else's editor put there.

    Raises whatever the read raises; each caller already has an answer for a
    file it cannot read, and they are not the same answer.
    """
    with codecs.open(file_path, "r", "utf-8-sig") as handle:
        return handle.read()


def parse_st_file(file_path):
    """Parse an ST file: strip sync pragmas, then extract declaration and
    implementation sections.

    Returns tuple (declaration, implementation, pragmas).
    pragmas is the dict from parse_sync_pragmas (may be empty); use
    attrs_from_pragmas() to get the boolean build attributes.
    """
    try:
        content = read_sync_text(file_path)
    except Exception as e:
        print("Error reading file " + file_path + ": " + safe_str(e))
        return None, None, {}

    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # Strip sync pragmas first
    pragmas, clean_content = parse_sync_pragmas(content)

    declaration = None
    implementation = None

    if IMPL_MARKER in clean_content:
        parts = clean_content.split(IMPL_MARKER)
        declaration = parts[0].strip()
        implementation = parts[1].strip() if len(parts) > 1 else None
    else:
        # No implementation marker - entire content is declaration
        declaration = clean_content.strip()

    return declaration, implementation, pragmas

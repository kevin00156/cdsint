# -*- coding: utf-8 -*-
"""Which kind an .st text reads as, when no pragma says.

The declaration's first keyword names the kind for most files; the kinds it
cannot name (a persistent GVL, an action) are the ones needs_kind_pragma()
writes a pragma for. Text in, GUID out, no IDE.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

from engine.codesys_constants import TYPE_GUIDS


def determine_object_type(content):
    """Determine CODESYS object type from ST content"""
    import re
    # Remove comments and pragmas to avoid false matches
    
    # 1. Remove (* ... *) multiline comments
    content = re.sub(r"\(\*[\s\S]*?\*\)", "", content)
    
    # 2. Remove { ... } pragmas/attributes
    content = re.sub(r"\{[\s\S]*?\}", "", content)
    
    # 3. Remove // ... single line comments
    content = re.sub(r"//.*", "", content)
    
    content = content.strip()
    lines = content.splitlines()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check keywords
        parts = line.split()
        if not parts:
            continue
        word = parts[0].upper()
        
        if word == "PROGRAM":
            return TYPE_GUIDS["pou"]
        if word == "FUNCTION_BLOCK":
            return TYPE_GUIDS["pou"]
        if word == "FUNCTION":
            return TYPE_GUIDS["pou"]
        if word == "VAR_GLOBAL":
            return TYPE_GUIDS["gvl"]
        if word == "TYPE":
            return TYPE_GUIDS["dut"]
        if word == "INTERFACE":
            return TYPE_GUIDS["itf"]
        if word == "METHOD":
            return TYPE_GUIDS["method"]
        if word == "PROPERTY":
            return TYPE_GUIDS["property"]
        if word == "ACTION":
            return TYPE_GUIDS["action"]
        
    return None

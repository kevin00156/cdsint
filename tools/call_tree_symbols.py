# -*- coding: utf-8 -*-
"""What the exported .st text defines: the symbol tables the resolver looks up.

Project functions and function blocks, their methods, the instances GVLs
declare and what type each one is, and the IEC system catalogue from
sys_funcs.json. call_tree_resolve.py reads these; nothing here reads it back.

CPython 3 only (see call_tree_parse.py for why the IronPython rule does not
apply). Moved out of call_tree_resolve.py unchanged.
"""

from __future__ import annotations, print_function

import io
import json
import os
import re

from call_tree_parse import (
    _blank_comments,
    detect_owner_kind,
    iter_st_files,
    parse_var_blocks,
    pou_name,
    read_text,
    split_decl_impl,
)


def load_system_catalog(path: str | None = None) -> dict:
    """Load the system-function catalog.

    Returns a dict with keys ``functions`` and ``function_blocks``, each a
    ``set`` of uppercase names.
    """
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "sys_funcs.json")
    with io.open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        "functions": {n.upper() for n in data.get("functions", [])},
        "function_blocks": {n.upper() for n in data.get("function_blocks", [])},
    }


def _collect_local_symbols(decl: str) -> dict[str, str]:
    """Build a dict ``{variable_name: type_name}`` from VAR blocks."""
    symbols: dict[str, str] = {}
    for block in parse_var_blocks(decl):
        for member in block.get("members", []):
            name = member.get("name", "")
            typ = member.get("type", "")
            if name and typ:
                # Strip array dimensions like ARRAY[0..7] OF BOOL -> BOOL
                bare = re.sub(
                    r"\bARRAY\b.*?\bOF\b", "", typ, flags=re.IGNORECASE
                ).strip()
                if not bare:
                    bare = typ
                symbols[name] = bare
    return symbols


def _collect_methods(decl: str) -> dict[str, dict]:
    """Extract METHOD definitions from a declaration block.

    Returns {qualified_name: {"kind": "method", "guid": ""}} plus a simple
    entry for the bare method name.
    """
    methods: dict[str, dict] = {}
    owner = pou_name(decl, None)
    blanked = _blank_comments(decl)
    for m in re.finditer(r"(?im)^\s*METHOD\s+([A-Za-z_]\w*)", blanked):
        method_name = m.group(1)
        qualified = f"{owner}.{method_name}" if owner else method_name
        methods[qualified] = {"kind": "method", "guid": ""}
        methods[method_name] = {"kind": "method", "guid": ""}
    return methods


def _collect_project_symbols_from_st_files(project_root: str) -> dict[str, dict]:
    """Scan .st files and extract POU/FB/function names from declarations.

    Returns {name: {"kind": str, "guid": ""}}.
    """
    symbols: dict[str, dict] = {}
    for st_path in iter_st_files(project_root):
        try:
            text = read_text(st_path)
        except OSError:
            continue
        decl, _ = split_decl_impl(text)
        if not decl:
            continue
        name = pou_name(decl, None)
        if name and name not in symbols:
            kind = detect_owner_kind(decl)
            symbols[name] = {"kind": kind or "unknown", "guid": ""}
        # Also check for methods (METHOD keyword in declaration)
        method_kind = _collect_methods(decl)
        if method_kind:
            symbols.update(method_kind)
    return symbols


def _build_global_instance_types(project_root: str) -> dict[str, str]:
    """Build a global ``{variable_name: type_name}`` map from ALL ``.st`` files.

    Keys are stored in *lowercase* for case-insensitive lookup because
    CODESYS is case-insensitive.
    """
    types: dict[str, str] = {}
    for st_path in iter_st_files(project_root):
        try:
            text = read_text(st_path)
        except OSError:
            continue
        decl, _ = split_decl_impl(text)
        if not decl:
            continue
        local_types = _collect_local_symbols(decl)
        for name, typ in local_types.items():
            key = name.lower()
            if key not in types or (typ and not types[key]):
                types[key] = typ
    return types


def _build_gvl_members(project_root: str) -> dict[str, dict[str, str]]:
    """Build a ``{gvl_name: {member_name: type_name}}`` map from GVL files.

    Keys are stored in *lowercase* for case-insensitive lookup.
    """
    members: dict[str, dict[str, str]] = {}
    for st_path in iter_st_files(project_root):
        try:
            text = read_text(st_path)
        except OSError:
            continue
        decl, _ = split_decl_impl(text)
        if not decl:
            continue
        kind = detect_owner_kind(decl)
        if kind != "gvl":
            continue
        # GVL declarations carry no name; fall back to the file stem
        # (e.g. LogComponent.st -> LogComponent).
        gvl_name = pou_name(decl, None)
        if not gvl_name:
            gvl_name = os.path.splitext(os.path.basename(st_path))[0]
        local_types = _collect_local_symbols(decl)
        if local_types:
            members[gvl_name.lower()] = {k.lower(): v for k, v in local_types.items()}
    return members

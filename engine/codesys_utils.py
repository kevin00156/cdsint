# -*- coding: utf-8 -*-
"""
codesys_utils.py - Shared utility functions for CODESYS scripts

Contains common utility functions used across export, import, and sync scripts.
"""
from __future__ import print_function

import os
import codecs
import json
import zlib
import sys
import traceback
import time
import tempfile
import shutil

from engine import unhandled
from engine.unhandled import name_of
from engine.codesys_constants import IMPL_MARKER, FORBIDDEN_CHARS, TYPE_GUIDS, PROPERTY_GET_MARKER, PROPERTY_SET_MARKER, IMPLEMENTATION_TYPES

# Cache version - bump when the cache format or hash semantics change to
# force a full rebuild
# 3.1: ide hashes include build_properties (exclude_from_build, etc.)
# 3.2: kind pragma - ambiguous-kind files get a one-time header rewrite
# 3.3: disk_mtime is now milliseconds-since-epoch as an int, produced by
# file_signature(). Older caches stored whole seconds (export) or a float
# (compare), so they are discarded rather than silently mis-compared.
CACHE_VERSION = "3.3"


# --- Logging System ---
# --- Logging System ---
class Logger:
    def __init__(self):
        self.log_file = None
        self.is_final = False
        self.debug = False  # Set by init_logging from the settings file.
        
    def _initialize(self, base_dir=None):
        # If explicitly providing base_dir, override everything
        if base_dir:
            self.log_file = os.path.join(base_dir, "sync_debug.log")
            self.is_final = True
            return

        # If we already have a final path, don't change it unless forced
        if self.is_final:
            return

        # Nothing is looked up here: init_logging() is handed the folder the
        # settings resolved to, and every entry body calls it before anything
        # worth logging happens. TEMP is where a log written before that call
        # goes, and it stays overwritable so the real path still wins.
        if not self.log_file:
            try:
                # Use temp directory to avoid cluttering ScriptDir
                self.log_file = os.path.join(tempfile.gettempdir(), "cds_sync_debug.log")
            except:
                pass
            # allow overwriting later since this is a fallback
            self.is_final = False

    def log(self, level, message, include_traceback=False):
        self._initialize()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = "[%s] [%s] %s\n" % (timestamp, level, message)
        
        if include_traceback:
            log_entry += traceback.format_exc() + "\n"
            
        print("[%s] %s" % (level, message))

        # Console always shows the message; the log FILE is debug-only so a
        # normal run leaves no sync_debug.log behind. ERROR always writes so a
        # real failure is never silent.
        if not self.debug and level != "ERROR":
            return

        try:
            with codecs.open(self.log_file, "a", "utf-8") as f:
                f.write(log_entry)
        except:
            pass

_logger = Logger()

def log_info(message):
    _logger.log("INFO", message)

def log_warning(message):
    _logger.log("WARNING", message)

def init_logging(base_dir, debug=False):
    """Point the log at the sync folder, and say whether to write one at all.

    Both come from the settings this run read (engine/settings.py). The debug
    flag used to be fetched from here, which meant the logger reached back
    into the project through two more modules to answer a question its caller
    already had the answer to.
    """
    if base_dir and os.path.exists(base_dir):
        _logger._initialize(base_dir)
    _logger.debug = bool(debug)

def log_error(message):
    _logger.log("ERROR", message, include_traceback=True)


# --- Utility Functions ---

def is_valid_projects(obj):
    """Check if the projects object is valid and functional."""
    if obj is None:
        return False
    try:
        # Accessing .primary is the ultimate test. 
        # If it's a stale/dead object from a previous run, this throws.
        _ = obj.primary
        return True
    except:
        return False


def resolve_projects(projects_obj=None, caller_globals=None):
    """
    Ensure we have a reference to the CODESYS projects engine.
    
    Tries multiple strategies:
    1. Use the explicitly passed object (if valid)
    2. Check caller's globals
    3. Check __main__ module
    4. Search sys.modules for an object with .primary attribute
    
    Returns the projects object or None.
    """
    if is_valid_projects(projects_obj):
        return projects_obj
    
    # Strategy 1: caller globals
    if caller_globals and "projects" in caller_globals:
        candidate = caller_globals["projects"]
        if is_valid_projects(candidate):
            return candidate
    
    # Strategy 2: __main__
    try:
        import __main__
        obj = getattr(__main__, "projects", None)
        if is_valid_projects(obj):
            return obj
    except:
        pass
    
    # Strategy 3: sys.modules scan
    try:
        # sys is already imported at top level
        # Sort modules to prioritize those that might be "more" main
        for module in sys.modules.values():
            if hasattr(module, "projects"):
                candidate = getattr(module, "projects")
                if is_valid_projects(candidate):
                    return candidate
    except:
        pass
    
    return None


def is_valid_system(obj):
    """Check if the system object is valid and functional."""
    if obj is None:
        return False
    try:
        # Accessing .ui is a good test for the CODESYS system object
        _ = obj.ui
        return True
    except:
        return False


def resolve_system(caller_globals=None):
    """Resolve the CODESYS 'system' global object."""
    # Strategy 1: caller globals
    if caller_globals and "system" in caller_globals:
        candidate = caller_globals["system"]
        if is_valid_system(candidate):
            return candidate
            
    # Strategy 2: __main__
    try:
        import __main__
        obj = getattr(__main__, "system", None)
        if is_valid_system(obj):
            return obj
    except:
        pass
        
    # Strategy 3: sys.modules scan
    try:
        if "system" in sys.modules:
            return sys.modules["system"]
        for module in sys.modules.values():
            if hasattr(module, "system"):
                candidate = getattr(module, "system")
                if is_valid_system(candidate):
                    return candidate
    except:
        pass
        
    return None


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
                unhandled.note(obj, exc)
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


def calculate_hash(content):
    """Calculate CRC32 checksum of string content (faster than SHA256)"""
    if content is None:
        return ""
    if isinstance(content, str):
        content = content.encode('utf-8')
    # CRC32 returns signed int, convert to unsigned and format as hex
    crc = zlib.crc32(content) & 0xFFFFFFFF
    return "%08X" % crc


def safe_str(value):
    """Safely convert value to string, handling Unicode in Python 2.7"""
    if value is None:
        return ""
    try:
        if sys.version_info[0] < 3:
            if isinstance(value, unicode):
                return value
            return unicode(value)
        return str(value)
    except:
        return "N/A"


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


def clean_filename(name):
    """Clean filename from invalid characters"""
    clean_name = name
    for char in FORBIDDEN_CHARS:
        clean_name = clean_name.replace(char, "_")
    return clean_name


def is_debug():
    """True when the settings file turned debug on (SPEC 4.4).

    The flag reaches here through init_logging(), which every entry body
    calls once with the settings this run read. It used to be a project
    property with a cache of its own in front of it, because reading it
    crossed into .NET and read_ide_attrs() consults it once per object; a
    value handed in needs no cache to be cheap.
    """
    return _logger.debug


def ensure_git_configs(export_dir):
    """Create .gitignore and .gitattributes if they don't exist in the export directory."""
    gitignore_path = os.path.join(export_dir, ".gitignore")
    gitattributes_path = os.path.join(export_dir, ".gitattributes")
    
    # 1. Gitignore handling
    if not os.path.exists(gitignore_path):
        content = [
            "# CODESYS Sync local files",
            "*.json",
            "*.log",
            "*.tmp",
            "*.bak",
            "",
            "# CODESYS temporary and build files",
            "*.~u",
            "*.precompilecache",
            "*.opt",
            "*.bootinfo",
            "*.bootinfo_guids",
            "*.compileinfo",
            "*.simulation.bootinfo",
            "*.simulation.bootinfo_guids",
            "*.simulation.compileinfo",
            ""
        ]
        try:
            with codecs.open(gitignore_path, "w", "utf-8") as f:
                f.write("\n".join(content))
            log_info("Created: .gitignore")
        except Exception as e:
            log_error("Failed to create .gitignore: " + safe_str(e))
    else:
        # File exists, check if essential patterns are present
        try:
            with codecs.open(gitignore_path, "r", "utf-8") as f:
                lines = f.readlines()
            
            # Ensure *.log is ignored
            if not any("*.log" in line for line in lines):
                with codecs.open(gitignore_path, "a", "utf-8") as f:
                    f.write("\n*.log\n")
                log_info("Updated .gitignore with *.log")
        except: pass

    # 2. Gitattributes handling
    if not os.path.exists(gitattributes_path):
        content = [
            "# Git LFS configuration for CODESYS project binary",
            "*.project filter=lfs diff=lfs merge=lfs -text",
            "",
            "# Prevent line ending conversion for CODESYS Structured Text files",
            "*.st -text",
            "",
            "# GitHub linguist language detection",
            "*.st linguist-language=Pascal",
            ""
        ]
        try:
            with codecs.open(gitattributes_path, "w", "utf-8") as f:
                f.write("\n".join(content))
            log_info("Created: .gitattributes")
        except Exception as e:
            log_error("Failed to create .gitattributes: " + safe_str(e))


# Removed MetadataLock and load_metadata (metadata files no longer used)


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


# Removed save_metadata (metadata files no longer used)


# --- Sync Pragma API ---
# ONE mechanism for every //% cds-text-sync.<key>=<value> pragma line at the
# top of a .st file: build attributes (ATTR_REGISTRY) and the kind pragma
# both go through parse_sync_pragmas / render_sync_pragmas.

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


def is_container_device(obj):
    """
    Check if a device is a 'container' (like a PLC root) that contains logic/applications.
    Such devices should NOT be monolithic XMLs because they are too large and
    their children (Applications, etc.) are already handled separately.
    """
    try:
        obj_type = safe_str(obj.type)
        if obj_type != TYPE_GUIDS["device"]:
            return False
            
        # Check if it has an Application or Plc Logic child
        # We only check direct children to avoid heavy recursion
        children = obj.get_children(recursive=False)
        for child in children:
            child_type = safe_str(child.type)
            if child_type in [TYPE_GUIDS["application"], TYPE_GUIDS["plc_logic"]]:
                return True
        return False
    except:
        return False


def find_child_transparent(parent_obj, name):
    """
    Find a child object by name, transparently looking through 'Plc Logic' nodes.
    
    The export skips 'Plc Logic' in paths (e.g. PLC/ST_Application instead of
    PLC/Plc Logic/ST_Application). This helper first checks direct children, then
    looks through any plc_logic children for the target name.
    
    Returns the found object or None.
    """
    if not parent_obj or not name:
        return None
    
    name_lower = name.lower()
    
    try:
        children = parent_obj.get_children()
    except:
        return None
    
    # First pass: direct child match
    for child in children:
        try:
            if child.get_name().lower() == name_lower:
                return child
        except:
            continue
    
    # Second pass: look through 'plc_logic' children transparently
    # (the export skips this level in the path)
    for child in children:
        try:
            c_type = safe_str(child.type)
            if c_type == TYPE_GUIDS.get("plc_logic"):
                for grandchild in child.get_children():
                    try:
                        if grandchild.get_name().lower() == name_lower:
                            return grandchild
                    except:
                        continue
        except:
            continue
    
    return None


def strip_src_prefix(path_str):
    """Drop the retired "src/" the earliest exports wrote in front of paths.

    One reader for it, because two spellings of the same migration drift: a
    path that keeps its prefix on one side and loses it on the other resolves
    to two different places in the tree.
    """
    normalized = path_str.replace("\\", "/")
    if normalized.startswith("src/"):
        return normalized[4:]
    return normalized


def _create_folder(container, name):
    """Make one folder under container and hand it back.

    Two calls do this depending on the CODESYS version, and either of them
    may create the folder and still return something falsy -- so the folder
    is looked up again rather than trusted to come back. That re-scan is a
    documented quirk, not a retry: it runs once, and if the folder is still
    not there this raises rather than returning a None the caller would carry
    on with (SPEC D13, PRINCIPLES 6).
    """
    made = None
    try:
        if hasattr(container, "create_folder"):
            made = container.create_folder(name)
        elif hasattr(container, "create_child"):
            made = container.create_child(name, TYPE_GUIDS["folder"])
        else:
            raise RuntimeError(
                "cannot create '%s' under %s: it exposes neither "
                "create_folder() nor create_child()"
                % (name, name_of(container)))
    except Exception as exc:
        # The folder may exist anyway; the exception can come from the part
        # of the call that happens after it was made.
        made = None
        log_warning("create folder '%s' raised: %s" % (name, safe_str(exc)))

    if made:
        return made
    found = find_child_transparent(container, name)
    if found:
        return found
    raise RuntimeError("could not create the folder '%s' under %s"
                       % (name, name_of(container)))


def ensure_folder_path(path_str, project):
    """Walk (and create) the folder path, and hand back the object it ends at.

    path_str is a relative path like "PLC/Application/MainFolder". The export
    skips 'Plc Logic' nodes, so the lookup looks through those transparently.

    Raises when a component cannot be found or made. The caller is inside the
    per-object step of an import, which records the object by name and carries
    on with the rest (SPEC D13); a None returned from here used to travel one
    frame further and become an object created in the wrong place.
    """
    if not path_str or path_str == "." or path_str == "src":
        return project

    current = project
    for part in strip_src_prefix(path_str).split("/"):
        if not part:
            continue
        current = find_child_transparent(current, part) or _create_folder(current, part)
    return current


def find_object_by_name(name, name_map, parent_name=None):
    """
    Find a CODESYS object by name using cache.
    Returns first match or None.
    """
    found = name_map.get(name)
    if not found:
        return None
    
    if len(found) == 1:
        return found[0]
    
    # Multiple matches - filter by parent if provided
    if parent_name:
        for obj in found:
            try:
                if hasattr(obj, "parent") and obj.parent:
                    if obj.parent.get_name() == parent_name:
                        return obj
            except:
                continue
        # Strict matching: if parent_name was provided but not found, return None
        return None
    
    # Return first match ONLY if no parent filter was requested
    return found[0]


def find_object_by_path(rel_path, project):
    """
    Find a CODESYS object using its hierarchical path.
    Example rel_path: "PLC/ST_Application/02_Object_GVL/_02_TaskLocalGVL.xml"
    
    Note: The export skips 'Plc Logic' nodes in paths, so this function
    transparently looks through plc_logic children when a direct match
    isn't found.
    """
    if not rel_path: return None
    
    path_str = strip_src_prefix(rel_path)
    
    # Strip extension for lookup
    root, ext = os.path.splitext(path_str)
    parts = root.split("/")
    
    # Handle New Format: Name.Type.xml
    if ext.lower() == ".xml" and parts:
        last_part = parts[-1]
        if "." in last_part:
            name_part, doc_type = last_part.rsplit(".", 1)
            # Verify if doc_type is a known CODESYS type name. Retired kind
            # names count too - old exports on disk still carry them.
            from engine.codesys_constants import KNOWN_TYPE_SUFFIXES
            if doc_type in KNOWN_TYPE_SUFFIXES:
                parts[-1] = name_part

    current_obj = project
    for part in parts:
        if not part: continue
        found = find_child_transparent(current_obj, part)
        
        if found:
            current_obj = found
        else:
            return None
            
    return current_obj


def cleanup_old_backups(project_folder, retention_count):
    """
    Clean up old timestamped backups in .project/ folder.
    Only deletes files matching pattern: YYYYMMDD_HHMMSS_*.bak
    Preserves non-timestamped backup files (Git LFS backups).
    
    Args:
        project_folder: Path to the .project folder
        retention_count: Number of timestamped backups to keep
    """
    if retention_count <= 0:
        return
    
    if not os.path.exists(project_folder):
        return
    
    import re
    
    timestamped_backups = []
    try:
        for filename in os.listdir(project_folder):
            if not filename.endswith(".bak"):
                continue
            
            # Pattern: YYYYMMDD_HHMMSS_*.bak
            # Example: 20260325_143022_MyProject.project.bak
            if re.match(r'^\d{8}_\d{6}_.*\.bak$', filename):
                full_path = os.path.join(project_folder, filename)
                if os.path.isfile(full_path):
                    timestamped_backups.append(full_path)
        
        if len(timestamped_backups) <= retention_count:
            return
        
        # Sort by filename (timestamp is encoded in name)
        timestamped_backups.sort(reverse=True)
        
        # Delete files beyond retention count
        files_to_delete = timestamped_backups[retention_count:]
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                filename = os.path.basename(file_path)
                log_info("Deleted old backup: .project/" + filename)
                print("Deleted old backup: .project/" + filename)
            except Exception as e:
                log_warning("Failed to delete old backup " + file_path + ": " + safe_str(e))
                print("Warning: Failed to delete old backup: " + file_path)
    except Exception as e:
        log_warning("Error during backup cleanup: " + safe_str(e))
        print("Warning: Error during backup cleanup: " + safe_str(e))


def backup_project_binary(export_dir, projects_obj=None, backup_name="",
                          timestamped=False, retention_count=None):
    """
    Copy the current project binary to /project folder.
    Forces a project save before copying to ensure the backup is current.
    If timestamped=True, creates a backup with date and time.
    
    Args:
        export_dir: Directory where .project folder will be created
        projects_obj: CODESYS projects object
        backup_name: What to call the non-timestamped copy; "" means the
                     project's own filename
        timestamped: If True, create timestamped backup with date and time
        retention_count: Optional. If provided, clean up old timestamped backups
                         keeping only this many (only applies to timestamped backups)
    
    Returns:
        Backup filename if created successfully, None otherwise
    """
    try:
        if not projects_obj:
            try:
                import projects
                projects_obj = projects
            except:
                pass
        
        if not projects_obj or not hasattr(projects_obj, "primary") or not projects_obj.primary:
            log_warning("Cannot identify project for backup.")
            print("Debug: Cannot identify project for backup (projects_obj missing or invalid).")
            return None

        # Force save to ensure we backup the latest state
        try:
            projects_obj.primary.save()
            log_info("Project saved for backup.")
        except Exception as e:
            msg = "Could not save project before backup: " + safe_str(e)
            log_warning(msg)
            print("Debug: " + msg)

        if not hasattr(projects_obj.primary, "path") or not projects_obj.primary.path:
            log_warning("Project not saved to disk yet. Skipping binary backup.")
            print("Debug: Project has no path on disk.")
            return None

        project_path = projects_obj.primary.path
        project_folder = os.path.join(export_dir, ".project")
        
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
            
        # Determine target filename
        if timestamped:
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            base_name = os.path.basename(project_path)
            # Format: YYYYMMDD_HHMMSS_ProjectName.project.bak
            file_name = "{}_{}.bak".format(timestamp, base_name)
        else:
            custom_name = backup_name
            if custom_name:
                # Ensure it ends with .project
                if not custom_name.lower().endswith(".project"):
                    file_name = custom_name + ".project"
                else:
                    file_name = custom_name
            else:
                file_name = os.path.basename(project_path)
            
        target_path = os.path.join(project_folder, file_name)
        
        shutil.copy2(project_path, target_path)
        log_info("Binary backup created: .project/" + file_name)
        print("Binary backup created: .project/" + file_name)
        
        # Clean up old timestamped backups if retention is specified
        if timestamped and retention_count is not None:
            cleanup_old_backups(project_folder, retention_count)
        
        return file_name
        
    except Exception as e:
        log_error("Warning: Could not create binary backup: " + str(e))
        print("Warning: Could not create binary backup: " + str(e))
        return None


# --- Interaction timing -------------------------------------------------
# Sync operations time themselves to report "Time elapsed", but the timed
# region spans blocking dialogs (the orphan-cleanup prompt, the import
# confirmation). Those measure how long a human took to click, which is not
# information about the sync, and it swamped the numbers being compared when
# tuning performance. Prompts routed through timed_prompt() are subtracted.
_interaction_seconds = [0.0]


def reset_interaction_timer():
    """Zero the accumulated prompt time. Call when starting a timed operation."""
    _interaction_seconds[0] = 0.0


def get_interaction_seconds():
    """Seconds spent waiting on user prompts since the last reset."""
    return _interaction_seconds[0]


def timed_prompt(prompt_func, *args, **kwargs):
    """Call a blocking UI prompt, keeping its duration out of sync timings.

    Wrapping at the call site rather than inside codesys_ui keeps this module
    free of the WinForms/clr import that codesys_ui needs.
    """
    started = time.time()
    try:
        return prompt_func(*args, **kwargs)
    finally:
        _interaction_seconds[0] += time.time() - started


def format_elapsed(total_seconds, interaction_seconds=None):
    """Render an elapsed time, noting prompt time when it was material."""
    if interaction_seconds is None:
        interaction_seconds = get_interaction_seconds()
    text = "{:.2f} seconds".format(total_seconds)
    if interaction_seconds >= 0.5:
        text += " (plus {:.2f}s waiting for input)".format(interaction_seconds)
    return text


def file_signature(file_path, stat_info=None):
    """Canonical (disk_mtime, disk_size) pair used to decide whether a file on
    disk still matches its sync-cache entry.

    Every writer and every reader of the cache MUST go through this helper.
    The export side used to compute int(st.st_mtime) while the compare side
    used os.path.getmtime() (a float), and both stored the result under the
    same 'disk_mtime' key. NTFS timestamps almost always carry a fractional
    part, so each side rejected every entry the other had written: an export
    followed by an import followed by an export saw a 0% cache hit rate on
    every single run, in both directions.

    Milliseconds keep sub-second resolution (plain int(st_mtime) would miss an
    edit made within the same second as the cached stamp) while staying an
    integer, which survives the JSON round-trip exactly -- unlike a float,
    where equality would depend on repr() reproducing the same value.
    """
    s = stat_info if stat_info is not None else os.stat(file_path)
    return int(s.st_mtime * 1000), s.st_size


def normalize_path(path):
    """Normalize path separators to forward slashes for cross-platform consistency in cache keys."""
    if path is None: return ""
    return path.replace("\\", "/").strip("/")


def build_folder_hashes(object_hashes):
    """
    Build hierarchical folder hashes from a dictionary of object hashes.
    
    Args:
        object_hashes: dict of {norm_path: content_hash}
    
    Returns:
        dict: {folder_path: folder_hash}
    """
    from collections import defaultdict
    folder_children = defaultdict(list)
    
    for path, o_hash in object_hashes.items():
        if not o_hash: continue
        
        parts = path.split("/")
        # Add hash to all parent folders
        for i in range(1, len(parts)):
            folder_path = "/".join(parts[:i])
            folder_children[folder_path].append(o_hash)
            
    result = {}
    for folder_path, child_hashes in folder_children.items():
        # Folder hash is the hash of sorted child hashes
        sorted_hashes = "|".join(sorted(child_hashes))
        result[folder_path] = calculate_hash(sorted_hashes)
        
    return result


def cached_classification(entry):
    """One cached classification, always (eff_type, is_xml, rel_path).

    JSON hands the tuple back as a list, and older caches stored a shorter
    one. Padding it here is what lets every reader write `entry[2]` instead
    of asking how long it is -- that question used to be asked in three
    places, in the same defensive one-liner, which is three chances for one
    of them to answer it differently.

    None for anything that is not a list at all: a cache file of the wrong
    shape is no cache.
    """
    if not isinstance(entry, (list, tuple)):
        return None
    padded = list(entry) + [None, None, None]
    return tuple(padded[:3])


def load_sync_cache(base_dir):
    """Load the synchronization cache from sync_cache.json in the base directory.

    The cache stores object classifications, so it is only trusted when it was
    built with the same type profile: a profile edit (new GUID alias, changed
    sync direction) changes PROFILE_HASH and forces a full re-classification.
    """
    from engine.codesys_constants import PROFILE_HASH
    cache_path = os.path.join(base_dir, "sync_cache.json")
    empty = {"objects": {}, "folders": {}, "types": {}, "version": CACHE_VERSION}
    if os.path.exists(cache_path):
        try:
            with codecs.open(cache_path, "r", "utf-8") as f:
                data = json.load(f)
                cache_version = data.get("version", "1.0")
                if cache_version != CACHE_VERSION:
                    log_info("Cache version mismatch (%s vs %s), triggering full rebuild."
                             % (cache_version, CACHE_VERSION))
                    return empty
                if data.get("profile_hash") != PROFILE_HASH:
                    log_info("Sync cache discarded: type profile changed "
                             "(cache=%s, current=%s) - full re-classification."
                             % (data.get("profile_hash"), PROFILE_HASH))
                    return empty
                types = {}
                for guid, entry in (data.get("types") or {}).items():
                    shaped = cached_classification(entry)
                    if shaped is not None:
                        types[guid] = shaped
                return {
                    "objects": data.get("objects", {}),
                    "folders": data.get("folders", {}),
                    "types": types,
                    "version": cache_version
                }
        except Exception as e:
            log_warning("Could not load sync cache: " + safe_str(e))
    return empty


def save_sync_cache(base_dir, objects_cache, folder_hashes=None, type_cache=None):
    """Save the synchronization cache to sync_cache.json in the base directory."""
    from engine.codesys_constants import PROFILE_HASH
    cache_path = os.path.join(base_dir, "sync_cache.json")
    cache_data = {
        "version": CACHE_VERSION,
        "profile_hash": PROFILE_HASH,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "folders": folder_hashes or {},
        "types": type_cache or {},
        "objects": objects_cache
    }
    try:
        with codecs.open(cache_path, "w", "utf-8") as f:
            # Compact, not indented. sync_cache.json is machine-read and
            # gitignored, and every entry carries an mtime that changes each
            # run, so it never produces a readable diff anyway. Indenting cost
            # roughly half a second across the write and the following read,
            # and doubled a 125 KB file.
            json.dump(cache_data, f, separators=(",", ":"))
    except Exception as e:
        log_warning("Could not save sync cache: " + safe_str(e))


def save_sync_metadata(base_dir, action, stats, elapsed):
    """Write sync_metadata.json, in debug mode only.

    Used by both entry_export.py and entry_import.py. Part of the debug
    audit trail (e179ef9 policy: a normal run produces only project
    content). The version property is not written here -- it has to be in
    the project before the save, and this runs after it; see
    finalize_sync_operation.

    Args:
        base_dir: Export/import directory path
        action: "export" or "import"
        stats: Statistics dict
        elapsed: Elapsed time in seconds (float)
    """
    from engine.codesys_constants import SCRIPT_VERSION
    if not is_debug():
        return

    metadata = {
        "script_version": SCRIPT_VERSION,
        "last_action": action,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_sec": round(elapsed, 2),
        "statistics": stats
    }
    metadata_path = os.path.join(base_dir, "sync_metadata.json")
    try:
        with codecs.open(metadata_path, "w", "utf-8") as f:
            json.dump(metadata, f, indent=2)
        log_info("%s metadata saved to sync_metadata.json (v%s)" % (action.capitalize(), SCRIPT_VERSION))
    except Exception as e:
        log_warning("Failed to save %s metadata: %s" % (action, safe_str(e)))


def finalize_sync_operation(base_dir, projects_obj, values, is_import=False):
    """Save the project, or back it up, as the settings say.

    One or the other, not both: the binary backup saves the project itself
    before copying it, so doing the save as well would be two full writes of
    the same file.
    """
    save_after_op = values["save_after_import" if is_import
                           else "save_after_export"]

    if values["backup_binary"] and getattr(projects_obj, 'primary', None):
        try:
            print("Action: Updating binary backup...")
            backup_project_binary(base_dir, projects_obj,
                                  values["backup_name"])
        except Exception as e:
            print("Warning: Could not update binary backup: " + safe_str(e))
    elif save_after_op and getattr(projects_obj, 'primary', None):
        try:
            print("Action: Saving project...")
            projects_obj.primary.save()
            print("Project saved successfully.")
        except Exception as e:
            op_str = "import" if is_import else "export"
            print("Warning: Could not save project after " + op_str + ": " + safe_str(e))


def create_safety_backup(base_dir, projects_obj, items_to_import, values):
    """Create a timestamped safety backup of the project before importing changes."""
    if not values["safety_backup"] or not items_to_import:
        return None
    return backup_project_binary(
        base_dir, projects_obj, values["backup_name"], timestamped=True,
        retention_count=values["backup_retention_count"])


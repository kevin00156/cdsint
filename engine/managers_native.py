# -*- coding: utf-8 -*-
"""The managers for objects that only exist as native CODESYS XML.

The IDE stamps a fresh timestamp and GUIDs into every native export, so
comparing two exports means keeping only the lines that mean something;
which lines those are depends on the flavour of document, and the
flavours are the table here.

Moved out of codesys_managers.py unchanged.
"""
from __future__ import print_function

import collections
import os
import zlib
from engine.ide_tree import is_container_device
from engine.st_text import read_sync_text
from engine.strings import safe_str
from engine.sync_log import log_info, log_error
from engine.codesys_constants import TYPE_GUIDS
from engine.managers_base import ObjectManager
from engine.native_import import import_native


def _crc(text):
    return str(zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF)


def _rewritten_every_export(line):
    """The two things CODESYS stamps afresh into any native XML it writes."""
    if 'Name="Timestamp"' in line:
        return True
    return 'Name="Guid"' in line and 'Type="System.Guid"' in line


def _keep_plain(line):
    """Any native XML that is not one of the flavours below."""
    if _rewritten_every_export(line):
        return False
    # Visualization object GUIDs churn the same way the attribute ones do.
    stripped = line.strip()
    return not (stripped.startswith('<Object Guid="')
                and ('visu' in line.lower() or 'frame' in line.lower()))


def _keep_all_but_volatile(line):
    if _rewritten_every_export(line):
        return False
    return '<Timestamp>' not in line


def _keep_device(line):
    """A device: keep the structure, drop the ids that change per session."""
    if not _keep_all_but_volatile(line):
        return False
    lowered = line.lower()
    return 'vqid' not in lowered and 'instanceid' not in lowered


def _keep_alarm_group(line):
    """An alarm group: only the lines that say which group this is."""
    if not _keep_all_but_volatile(line):
        return False
    if '<Single Name="Name" Type="string">' in line and 'AlarmGroup' in line:
        return True
    if ('CODESYS_HMI' in line and 'HMI_Application' in line
            and 'Alarm Configuration' in line):
        return True
    # A substring test, not startswith: the object element is nested and the
    # line arrives with its indentation. The plain filter below does use
    # startswith, deliberately -- it is throwing lines away rather than
    # keeping them, and there a looser match drops more than it should.
    return ('<Object Guid="' in line
            and ('Type="type_21f"' in line or 'Type="textlist"' in line))


def _keep_alarm_config(line):
    """An alarm configuration: only the lines that identify it."""
    if not _keep_all_but_volatile(line):
        return False
    return ('<Single Name="Name" Type="string">' in line
            or 'CODESYS_HMI' in line)


_Flavour = collections.namedtuple("_Flavour",
                                  "detect keep name_is_the_fallback")

# Ordered, and the order is the one the if/elif chain had: the first detector
# that matches decides. A document that reads as both a device and an alarm
# group is a device, as it always was.
#
# Four booleans sniffed out of the text used to be computed up front and then
# consulted by a chain that mixed "which flavour is this" with "keep this
# line", nine levels deep. What each flavour keeps is the knowledge here; the
# chain was only ever the way it was written down.
_XML_FLAVOURS = (
    _Flavour(lambda t: '<Single Name="Name" Type="string">GlobalTextList' in t,
             _keep_all_but_volatile, True),
    _Flavour(lambda t: '225bfe47-7336-4dbc-9419-4105a7c831fa' in t or '<Device' in t,
             _keep_device, True),
    _Flavour(lambda t: 'AlarmGroup' in t and 'GlobalTextList' not in t,
             _keep_alarm_group, True),
    _Flavour(lambda t: 'Alarm Configuration' in t,
             _keep_alarm_config, True),
)

# The plain filter is the one that does not fall back on the name. It throws
# away only what CODESYS rewrites, so a document it empties really is empty,
# and two empty documents are the same document.
_PLAIN = _Flavour(lambda t: True, _keep_plain, False)


def _xml_flavour(text):
    for flavour in _XML_FLAVOURS:
        if flavour.detect(text):
            return flavour
    return _PLAIN


class NativeManager(ObjectManager):
    """Handle objects exported as native CODESYS XML"""
    def _hash_file(self, file_path):
        """This file's hash, or "" when there is no readable file there.

        "" means "nothing on disk to compare against", which is what the
        export path does with it: is_new is already true in that case, so the
        hash is never consulted. It does NOT mean "hashing failed" -- that
        raises, because a failure that returns a falsy value the caller
        ignores is the same bug as a silent skip (PRINCIPLES 6).
        """
        try:
            content_full = read_sync_text(file_path)
        except (IOError, OSError, UnicodeDecodeError):
            return ""
        return self._hash_content(content_full, os.path.basename(file_path))

    def _hash_content(self, content_full, fallback_name=""):
        """Hash native XML text, ignoring the parts CODESYS rewrites on every
        export (timestamps, internal GUIDs, volatile instance ids).

        Split out of _hash_file so callers that already hold the XML as a
        string can reach this logic directly. The compare engine holds both
        sides in memory and used to write each one back out to a temp file
        purely because this function only accepted a path -- three writes and
        three reads per differing object, on files up to a third of a
        megabyte.

        fallback_name is only consulted for a flavour whose filter left
        nothing at all; see NOTHING_SURVIVES_FILTERING below.

        Raises rather than returning "" for an unhashable input. "" used to be
        the answer, and NativeManager.export tests `old_hash and old_hash ==
        new_hash`, which "" makes false forever -- so the object was reported
        "updated" on every single export and nobody could see why.
        """
        flavour = _xml_flavour(content_full)
        kept = [line for line in content_full.splitlines(True)
                if flavour.keep(line)]
        if not kept and flavour.name_is_the_fallback:
            # NOTHING_SURVIVES_FILTERING: an alarm group or alarm config whose
            # every line was volatile. Hashing the name means the hash says
            # where the content came from rather than what it is, and
            # contents_are_equal passes two deliberately different names so
            # that such an object always compares as different. Preserved
            # here, not endorsed.
            return _crc(fallback_name)
        return _crc("".join(kept))

    def export(self, obj, effective_type, rel_path, context, recursive=False):
        # Determine target directory and file path
        file_path = os.path.join(context['export_dir'], rel_path.replace("/", os.sep))
        target_dir = os.path.dirname(file_path)
        is_new = not os.path.exists(file_path)
        # --- CACHE SKIP OPTIMIZATION ---
        skip = self._try_cache_skip(obj, rel_path, file_path, context, is_xml=True)
        if skip:
            return skip
        # -------------------------------

        # Get existing file hash before overwriting
        old_hash = "" if is_new else self._hash_file(file_path)
        
        # Export to a temp file first, then compare
        tmp_path = file_path + ".tmp"
        if self.project is None:
            raise RuntimeError("Native export failed: this manager was built "
                               "without a project.")
        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            self.project.export_native([obj], tmp_path, recursive=recursive)
        except Exception:
            # The half-written temp file goes, the reason does not: the
            # caller records the object by name (SPEC D13).
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

        if not os.path.exists(tmp_path):
            raise RuntimeError("export_native wrote no file for " + rel_path)

        # From here the temp file is this function's to clean up, whichever
        # way it leaves. _hash_content raises on content it cannot hash, and
        # without this the .xml.tmp stayed in the sync folder -- where the
        # next orphan sweep does not recognise it and the next export writes
        # a second one beside it.
        try:
            new_hash = self._hash_file(tmp_path)

            # Content identical - keep the original, drop the temp.
            if not is_new and old_hash and old_hash == new_hash:
                return self._tracked(obj, rel_path, file_path, context,
                                     new_hash, "identical")

            # Content changed or new - replace with the temp file, unless the
            # change is somebody's, not the IDE's (SPEC 6.1).
            if not is_new and self._disk_moved_since_sync(rel_path, file_path,
                                                          context):
                return self._pending(rel_path, context)

            if os.path.exists(file_path):
                os.remove(file_path)
            os.rename(tmp_path, file_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return self._tracked(obj, rel_path, file_path, context, new_hash,
                             "new" if is_new else "updated")

    def update(self, obj, file_path):
        obj_name = obj.get_name() if obj else "Unknown"
        try:
            # Try parent-level import first (more precise)
            try:
                parent = obj.parent
            except:
                parent = None
            
            if parent and hasattr(parent, "import_native"):
                log_info("Updating native object " + obj_name + " via parent import.")
                import_native(parent, file_path)
                return True
            else:
                # Fallback to project-level import (object ref may be stale)
                log_info("Updating native object " + obj_name + " via project import.")
                if self.project is None:
                    return False
                import_native(self.project, file_path)
                return True
        except Exception as e:
            log_error("Native update failed for " + obj_name + ": " + safe_str(e))
            return False

    def create(self, container, name, file_path, type_guid):
        try:
            # CODESYS import_native imports into the project/container
            # If container is provided, use its import_native method
            if container and hasattr(container, "import_native"):
                import_native(container, file_path)
            else:
                # Fallback to project-level import
                if self.project is not None:
                    import_native(self.project, file_path)
            
            # Find newly created object
            if container:
                for child in container.get_children():
                    if child.get_name().lower() == name.lower():
                        return child
            return None
        except Exception as e:
            log_error("Native import failed for " + name + ": " + safe_str(e))
            return None


class ConfigManager(NativeManager):
    """Specialized handling for configurations (forced XML)"""
    def export(self, obj, effective_type, rel_path, context):
        # Devices are monolithic only if they are not containers (Project Roots)
        recursive = True
        if safe_str(obj.type) == TYPE_GUIDS["device"]:
            if is_container_device(obj):
                recursive = False
        
        return super(ConfigManager, self).export(obj, effective_type, rel_path,
                                                 context, recursive=recursive)

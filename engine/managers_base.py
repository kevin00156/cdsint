# -*- coding: utf-8 -*-
"""The manager every object kind starts from, and the folder one.

ObjectManager is the export/compare/import contract: one instance per
kind, handed an object and a path. FolderManager is the kind with no
content of its own.

Moved out of codesys_managers.py unchanged.
"""
from __future__ import print_function

import os
import codecs
from engine.sync_cache import file_signature, normalize_path
from engine.ide_hash import get_quick_ide_hash
from engine.st_text import read_sync_text
from engine.strings import calculate_hash


class ObjectManager(object):
    """Base class for managing CODESYS objects"""
    def __init__(self, project=None, pou_type=None):
        """The primary project and the PouType enum, handed over once.

        Six methods used to go looking for it themselves, through a resolver
        that tried the caller's globals, then __main__, then every module in
        every loaded module. What they needed was the project the command had
        open, and a command has exactly one.

        None is allowed because one caller wants nothing but the hashing:
        content_compare keeps a bare NativeManager to hash two strings
        it already holds.

        pou_type is the IDE's PouType enum, needed only where a new POU is
        created. Measured on ScriptEngine 4.2.0.0 (CODESYS 3.5.21.40) and
        4.0.0.0 (DIADesigner-AX 1.10): it is in the script's own namespace,
        which is where the entry body reads it from.
        """
        self.project = project
        self.pou_type = pou_type

    def _update_cache_entry(self, obj, rel_path, file_path, context, q_hash=None, stat_info=None):
        """Update the shared context cache with latest object metadata."""
        if 'new_cache' not in context or not os.path.exists(file_path):
            return
        
        norm_path = normalize_path(rel_path)
        try:
            # If q_hash not provided, calculate it based on type
            if q_hash is None:
                q_hash = get_quick_ide_hash(obj, False)

            disk_mtime, disk_size = file_signature(file_path, stat_info)
            context['new_cache'][norm_path] = {
                "ide_hash": q_hash,
                "disk_mtime": disk_mtime,
                "disk_size": disk_size
            }
        except Exception:
            # A cache entry that cannot be written costs the next run its
            # fast path and nothing else, so it is not worth failing over.
            pass

    def _try_cache_skip(self, obj, rel_path, file_path, context, is_xml=False):
        """Attempt to skip export via IDE-cache-disk fast path.

        If the IDE state matches the cache AND the disk file matches the
        cache, then IDE == disk and the slow extraction can be skipped.
        Returns "identical" if skip succeeds, None otherwise.

        The disk-side checks run first on purpose. They cost a dict lookup and
        one os.stat(), whereas get_quick_ide_hash() reads the object's
        declaration and implementation back out of the IDE. Testing the cheap
        half first means a new or genuinely-edited object never pays for a
        hash that was always going to be thrown away.
        """
        norm_path = normalize_path(rel_path)
        cache = context.get('cache_data')
        if not cache:
            return None

        cached_obj = cache.get('objects', {}).get(norm_path)
        if not cached_obj:
            return None

        try:
            s = os.stat(file_path)
        except OSError:
            return None

        disk_mtime, disk_size = file_signature(file_path, s)
        if disk_mtime != cached_obj.get('disk_mtime') or disk_size != cached_obj.get('disk_size'):
            return None

        q_hash = get_quick_ide_hash(obj, is_xml)
        if not q_hash or cached_obj.get('ide_hash') != q_hash:
            return None

        return self._tracked(obj, rel_path, file_path, context, q_hash,
                             "identical", stat_info=s)

    def _write_text(self, obj, rel_path, file_path, content, content_hash, context):
        """Put `content` on disk and say what that did: identical, pending,
        new or updated.

        POUManager.export and PropertyManager.export ended in twenty-five
        identical lines; the two differ only in how they build the text. The
        identical check, the dirty-file guard (SPEC 6.1), the write, the
        exported_paths entry and the cache update all belong to "write this
        text", not to "work out what the text is".

        exported_paths is what the orphan sweep reads as "the project still
        has an object for this file", so adding to it and writing the file
        are the same act -- doing them in two places is how a file ends up
        written and then offered for deletion.
        """
        target_dir = os.path.dirname(file_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        is_new = not os.path.exists(file_path)
        if not is_new:
            try:
                if calculate_hash(read_sync_text(file_path)) == calculate_hash(content):
                    return self._tracked(obj, rel_path, file_path, context,
                                         content_hash, "identical")
            except (IOError, OSError, UnicodeDecodeError):
                pass  # Unreadable or not utf-8: treat it as needing a rewrite

            if self._disk_moved_since_sync(rel_path, file_path, context):
                return self._pending(rel_path, context)

        with codecs.open(file_path, "w", "utf-8") as f:
            f.write(content)
        return self._tracked(obj, rel_path, file_path, context, content_hash,
                             "new" if is_new else "updated")

    def _tracked(self, obj, rel_path, file_path, context, content_hash, verdict,
                 stat_info=None):
        """Claim the file for this object, remember its state, and hand back
        the verdict the caller returns.

        Claiming and remembering always happen together: exported_paths is
        what the orphan sweep reads as "the project still has an object for
        this file", and a file the cache knows about but the sweep does not
        is a file the next export offers to delete.

        stat_info is passed on when the caller already has one -- the cache
        skip path stats the file to decide, and stat is not free.
        """
        if 'exported_paths' in context:
            context['exported_paths'].add(rel_path)
        self._update_cache_entry(obj, rel_path, file_path, context,
                                 content_hash, stat_info)
        return verdict

    def _disk_moved_since_sync(self, rel_path, file_path, context):
        """Has somebody edited this file since the last sync? (SPEC 6.1)

        Only ever asked at the point where this run would otherwise write:
        the file is not identical to what the IDE holds, or could not be read
        to find out. A yes means the disk is the side that moved. Disk is the
        source of truth, an edit nobody imported yet is work, and overwriting
        work is the one failure this tool cannot apologise for afterwards.

        "No cache entry" is not "unchanged", it is "no idea": the cache is
        local state and gitignored, so a fresh clone has none and a first
        export there must still write. That is the known hole -- exporting
        into a folder full of files this machine has never synced overwrites
        them -- and closing it would mean refusing the ordinary first export
        on a new machine.
        """
        cached = (context.get('cache_data') or {}).get('objects', {}).get(
            normalize_path(rel_path))
        if not cached:
            return False
        try:
            signature = file_signature(file_path)
        except OSError:
            return False
        return signature != (cached.get('disk_mtime'), cached.get('disk_size'))

    def _pending(self, rel_path, context):
        """Say this object was left alone, and keep its file off the orphan list.

        exported_paths is what orphan cleanup reads as "the project still has
        an object for this file". A file protected from being overwritten
        that then gets offered for deletion is worse than no protection at
        all, because the offer looks routine.
        """
        if 'exported_paths' in context:
            context['exported_paths'].add(rel_path)
        return "pending"

    def export(self, obj, effective_type, rel_path, context):
        """Write this object to disk; return "new", "updated" or "identical".

        effective_type is the classification the caller already made -- the
        normalized type GUID, which is not always obj.type (an NVL reports
        itself as a GVL). It is a parameter because it is one: it used to be
        stashed in the shared context dict on the way in and fished back out
        here, so nothing in any signature said a manager needed it, and a
        manager reached without it quietly re-read obj.type and paid a .NET
        round trip for an answer the caller was already holding.

        "pending" means the file on disk holds an edit nobody imported yet,
        so this object was deliberately left alone (SPEC 6.1).

        False means there was nothing to write, and it is the only thing
        False may mean. Anything that goes wrong RAISES, because the caller
        already has one place per command that turns a raised object into a
        named entry in engine/unhandled.py (SPEC D13) and a run that is not
        ok (D11). A write that failed used to return False as well, so a
        sync folder deep enough to push paths past Windows' 260 characters
        reported a clean export of 87 files while 130 objects never reached
        the disk at all.
        """
        pass
    
    def update(self, obj, file_path):
        """Update existing object from file system"""
        pass
    
    def create(self, container, name, file_path, type_guid):
        """Create new object from file system"""
        pass


class FolderManager(ObjectManager):
    """Handle folder creation and management"""
    def export(self, obj, effective_type, rel_path, context):
        # Folders have no content of their own; the cache entry is there to
        # remember the path, and "folder" is a hash that never changes.
        file_path = os.path.join(context['export_dir'], rel_path.replace("/", os.sep))
        return self._tracked(obj, rel_path, file_path, context, "folder",
                             "identical")

    def update(self, obj, file_path):
        # Folders don't have textual content to update
        return False

    def create(self, container, name, file_path, type_guid):
        # For folders, container should be the parent folder/application
        # But we also have absolute path in file_path (which is relative in metadata)
        from engine.ide_tree import ensure_folder_path
        try:
            # file_path here is the rel_path from the sync folder, e.g.
            # "Device/Application/Folder/Sub".
            if self.project is None:
                return None
            return ensure_folder_path(file_path, self.project)
        except:
            return None

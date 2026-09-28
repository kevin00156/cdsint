# -*- coding: utf-8 -*-
"""Which files in the sync folder are orphans, and deleting them.

An orphan is a file no object claims that is exactly as the last sync here
left it: the sync cache has an entry for it and the file's signature still
matches that entry. Every other unclaimed file is somebody's work -- a file
written by hand for import to create, or an edit made after its object went
away -- and deleting it is the one thing this tool cannot apologise for
afterwards (PRINCIPLES 5). Those are kept and handed back to be reported as
waiting for import.

The price: a folder this machine has no cache for (a fresh clone) has no
orphans. The sweep cannot tell a stale file from a new one there, so it
deletes none of them, whatever auto_delete_orphans or --delete-orphans says.

The prompt, the deletion and the empty-folder pass were moved here out of
entry_export.py; the orphan rule above is new.
"""
from __future__ import print_function

import os

from cds.core import dialogs
from engine import unhandled
from engine.strings import safe_str
from engine.sync_cache import normalize_path, signature_matches
from engine.sync_dir import sync_files
from engine.sync_log import log_warning

PREVIEW = 15


def cleanup_orphaned_files(export_dir, claimed, auto_delete, cached, new_cache):
    """Delete the orphans in export_dir. Returns (removed count, kept paths).

    claimed holds the paths this export wrote or deliberately left alone;
    cached is the last sync's cache entries. An unclaimed file that is still
    there afterwards gets its old entry carried into new_cache: without it a
    declined orphan would read as never synced next time, and an edited one
    as unknown rather than edited.

    auto_delete is the settings file's answer to the dialog, passed in so the
    settings are read once per command.
    """
    orphans, kept = _unclaimed(export_dir, claimed, cached)
    if (orphans or kept) and unhandled.any_so_far():
        # An object this run could not classify has no path, so its file is
        # one of these, and the run cannot say which (SPEC D13). Only the
        # deletion is skipped: a kept file still carries its entry, or the
        # edit in it reads as never synced once the object is readable again,
        # and the export after that writes over it.
        print("Orphan cleanup skipped: " + unhandled.summary())
        log_warning("Not deleting %d orphan(s): this run could not classify "
                    "every object, so some of them may belong to one of those."
                    % len(orphans))
        removed = []
    else:
        removed = _delete_confirmed(export_dir, orphans, auto_delete)
    for rel_path in kept:
        log_warning("Not deleting %s: no object claims it, but the last sync "
                    "here did not leave it this way. Import it to create its "
                    "object, or delete it by hand." % rel_path)
    for rel_path in orphans + kept:
        key = normalize_path(rel_path)
        if rel_path not in removed and key in cached:
            new_cache[key] = cached[key]
    if removed:
        _remove_empty_dirs(export_dir, claimed)
    return len(removed), kept


def _unclaimed(export_dir, claimed, cached):
    """(orphans, kept): the unclaimed sync files, split by the rule above.

    The walk and its skip rules are sync_dir's, the same ones the new-file
    scan uses: this sweep deletes, so it must not see a file the scan
    refuses to look at (and therefore never claims)."""
    claimed_keys = set(normalize_path(path) for path in claimed)
    orphans, kept = [], []
    for rel_path, abs_path in sync_files(export_dir):
        key = normalize_path(rel_path)
        if key in claimed_keys:
            continue
        if signature_matches(cached.get(key), abs_path):
            orphans.append(rel_path)
        else:
            kept.append(rel_path)
    return orphans, kept


def _delete_confirmed(export_dir, orphans, auto_delete):
    """Ask, unless the settings already answered, then delete. The deleted."""
    if not orphans:
        return []
    if not auto_delete and not _ask(orphans):
        print("Orphaned files ignored.")
        return []
    print("Cleaning up orphaned files...")
    removed = []
    for rel_path in orphans:
        full_path = os.path.join(export_dir, rel_path.replace("/", os.sep))
        try:
            os.remove(full_path)
            removed.append(rel_path)
            print("Deleted: " + rel_path)
        except OSError as exc:
            print("Error deleting " + rel_path + ": " + safe_str(exc))
    return removed


def _ask(orphans):
    """The dialog has two buttons, Delete and Ignore, so two answers."""
    message = ("The following files exist in the export directory but are "
               "NOT in the CODESYS project (orphans):\n\n")
    for rel_path in orphans[:PREVIEW]:
        message += "- " + rel_path + "\n"
    if len(orphans) > PREVIEW:
        message += "... and " + str(len(orphans) - PREVIEW) + " more.\n"
    message += "\nWould you like to delete these orphaned files?"

    from engine.codesys_ui import ask_yes_no
    from engine.sync_log import timed_prompt
    return timed_prompt(ask_yes_no, dialogs.DELETE_ORPHANS, message)


def _remove_empty_dirs(export_dir, claimed):
    """Drop the folders the deletions emptied that no claimed path needs.

    Bottom up, so a folder whose only content was an emptied subfolder goes
    too."""
    for root, dirs, files in os.walk(export_dir, topdown=False):
        rel_path = os.path.relpath(root, export_dir).replace("\\", "/")
        if rel_path == "." or any(part.startswith(".")
                                  for part in rel_path.split("/")):
            continue
        if rel_path in claimed or any(path.startswith(rel_path + "/")
                                      for path in claimed):
            continue
        try:
            if not os.listdir(root):
                os.rmdir(root)
                print("Deleted empty folder: " + rel_path)
        except OSError:
            pass  # Not empty, or gone already. Either way, leave it.

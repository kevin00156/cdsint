# -*- coding: utf-8 -*-
"""What an import must not apply, and what it must not delete.

Pass 1 of perform_import_items asks these of every item before it sorts
it: a kind the profile does not import, a file refused by path, an object
import never deletes. Moved out of import_items.py to keep that file under
the size limit.
"""
from __future__ import print_function

from engine import unhandled
from engine.codesys_constants import kind_allows_import, kind_of, sync_direction_of
from engine.sync_log import log_error, log_info, log_warning


def is_import_allowed(item):
    """Kinds the profile marks export_only or disabled are never imported,
    overwritten or DELETED: their disk file is a projection for Git to see,
    not a source of truth."""
    kind = kind_of(item.get("type_guid") or "")
    if item.get("device_pass") or not kind or kind_allows_import(kind):
        return True
    msg = ("Skipping import of '%s' (%s): sync_direction=%s"
           % (item.get("name"), kind, sync_direction_of(kind)))
    print("  [!] " + msg)
    log_warning(msg)
    return False


LEGACY_LIBRARY_XML = (
    "an old Library Manager XML; it is not imported, because it would put "
    "back libraries removed since. Run export first: it writes Library "
    "Manager.libraries, and then delete this file")


def refused_by_path(item, tally):
    """An item this import must not apply, recorded by path.

    Two kinds: a Library Manager's XML from before SPEC 6.9, which imported as
    native XML merges back libraries removed since (research 4.2); and a
    device item the device pass refused, because the settings file does not
    allow device settings (SPEC 6.10).
    """
    path = item.get("path", "")
    why = item.get("refused")
    if (not why and path.endswith(".library_manager.xml")
            and not item.get("is_orphan")):
        why = LEGACY_LIBRARY_XML
    if not why:
        return False
    log_error("%s: %s" % (path, why))
    unhandled.note(path, why)
    tally.failed += 1
    return True


def never_deleted(item):
    """A Library Manager or an EtherCAT device with no file is kept: import
    never deletes either, and a missing file means "not synchronised yet"
    (SPEC 6.9, 6.10)."""
    if (not item.get("device_pass")
            and kind_of(item.get("type_guid") or "") != "library_manager"):
        return False
    log_info("Kept %s: import never deletes it" % item.get("name"))
    return True

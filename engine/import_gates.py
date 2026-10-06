# -*- coding: utf-8 -*-
"""What an import must not apply, and what it must not delete.

Pass 1 of perform_import_items asks these of every item before it sorts
it: a kind the profile does not import, a file refused by path, an object
import never deletes. Moved out of import_items.py to keep that file under
the size limit.
"""
from __future__ import print_function

import os

from engine import unhandled
from engine.strings import safe_str
from engine.codesys_constants import (IMPLEMENTATION_KINDS, kind_allows_import,
                                      kind_of, sync_direction_of)
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


CODE_AS_XML = (
    "code as native XML, which an older export wrote; it is not imported, "
    "because the IDE asks a person which language to give it and, answered, "
    "drops ABSTRACT. Run export first: it writes this object as a .st, and "
    "then delete this file")


def refused_by_path(item, tally):
    """An item this import must not apply, recorded by path.

    Three kinds: a Library Manager's XML from before SPEC 6.9, which imported
    as native XML merges back libraries removed since (research 4.2); code
    as native XML, which cdsint no longer writes (SPEC 4.5); and a device
    item the device pass refused, because the settings file does not allow
    device settings (SPEC 6.10).
    """
    path = item.get("path", "")
    why = item.get("refused")
    if (not why and path.endswith(".library_manager.xml")
            and not item.get("is_orphan")):
        why = LEGACY_LIBRARY_XML
    if not why and _is_code_xml(path):
        why = CODE_AS_XML
    if not why:
        return False
    log_error("%s: %s" % (path, why))
    unhandled.note(path, why)
    tally.failed += 1
    return True


def _is_code_xml(path):
    """Is this '<Name>.<kind>.xml' with a kind that holds an implementation?"""
    stem, ext = os.path.splitext(os.path.basename(path))
    if ext.lower() != ".xml" or "." not in stem:
        return False
    return kind_of(stem.rsplit(".", 1)[1]) in IMPLEMENTATION_KINDS


def stale_code_names(to_sync):
    """Lower-cased names of the objects whose file is old code XML."""
    return set(safe_str(item.get("name")).lower() for item in to_sync
               if _is_code_xml(item.get("path", "")))


def never_deleted(item, stale_code=()):
    """An object with no file that this import keeps anyway.

    A Library Manager or an EtherCAT device: import never deletes either, and
    a missing file means "not synchronised yet" (SPEC 6.9, 6.10). And code
    whose file is still the native XML an older export wrote: the new path
    has no file yet, the XML is refused, and deleting the object here would
    lose it in the very import that says to run export first. Matched by
    name only, so a same-named orphan elsewhere waits one run longer.
    """
    name = safe_str(item.get("name"))
    if name.lower() in stale_code:
        log_info("Kept %s: its file is still old code XML" % name)
        return True
    if (not item.get("device_pass")
            and kind_of(item.get("type_guid") or "") != "library_manager"):
        return False
    log_info("Kept %s: import never deletes it" % name)
    return True

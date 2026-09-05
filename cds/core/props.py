# -*- coding: utf-8 -*-
"""The names of the project properties the settings live in (SPEC 4.4).

One prefix, defined once. It is `cds-sync-` and not the product name on
purpose (SPEC D10): it describes the sync feature, not the product, and
renaming it would mean a migration pass over every existing .project for no
gain at all. Keeping it in one place is what makes that a decision rather
than a fact of life -- before this module the prefix was written out 49
times across ten files.

Here rather than in engine/ or cds/ide/ because both sides need it and D12
forbids either from importing the other. Pure Python (PRINCIPLES.md 4): no
CODESYS imports, so it also runs in CI.

What each property means is SPEC 4.4's table; which of them a caller may
write is cds/ide/config.py. This module only says what they are called.
"""
from __future__ import print_function

PREFIX = "cds-sync-"


def _name(suffix):
    return PREFIX + suffix


FOLDER = _name("folder")
PC = _name("pc")
VERSION = _name("version")
DEBUG = _name("debug")
EXPORT_XML = _name("export-xml")
BACKUP_BINARY = _name("backup-binary")
SAFETY_BACKUP = _name("safety-backup")
BACKUP_NAME = _name("backup-name")
BACKUP_RETENTION_COUNT = _name("backup-retention-count")
SAVE_AFTER_IMPORT = _name("save-after-import")
SAVE_AFTER_EXPORT = _name("save-after-export")
AUTO_DELETE_ORPHANS = _name("auto-delete-orphans")
PLC = _name("plc")

# The one property that does not carry the prefix, and it stays that way.
# It was named before the rest and it is written into every .project that
# has ever been synced; folding it in would buy one consistent spelling in
# exchange for a migration pass over all of them (the same trade D10 turned
# down for the prefix itself). Named here anyway, so the odd spelling has
# one home and this paragraph is next to it.
MULTIPLE_APPS = "cds-text-sync-multipleApps"

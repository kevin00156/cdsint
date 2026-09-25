# -*- coding: utf-8 -*-
"""The sync engine: everything that walks the IDE object tree or touches a PLC.

Runs under the IronPython 2.7 the IDE ships, so Python 2/3 compatible source,
standard library only (SPEC D4). It never imports cds.ide — the dependency
runs the other way, cds/ide drives an entry body by name (SPEC D12).

    codesys_constants   GUID tables and per-kind sync policy, from profiles/
    strings             safe_str, the CRC, filename cleaning
    sync_log            the run's log, the debug flag, the interaction timer
    st_text             the .st file format, written and parsed
    ide_attrs           an object's build attributes, read and written
    ide_hash            a cheap hash of what an object would export
    ide_tree            finding and making places in the object tree
    git_configs         the .gitignore and .gitattributes an export leaves
    object_kind         what kind an object is when its GUID cannot say
    object_paths        where an object sits, as the path its file takes
    object_content      an object's text, read out and written back
    managers_base       ObjectManager, the per-kind contract; FolderManager
    managers_pou        POUManager and PropertyManager
    managers_native     NativeManager and ConfigManager: native XML kinds
    managers_library    LibraryManager: the .libraries file of SPEC 6.9
    library_refs        a Library Manager's references, read and changed
    build_clean         clean before a build whose libraries changed
    managers_device     DeviceManager: an EtherCAT device's .device file
    device_params       a device's parameters and mappings, read and written
    device_pass         the EtherCAT devices, synced beside the objects
    device_changes      which devices an import changed, for the result
    content_compare     is the IDE's text the same as the file's
    change_detect       what differs, object by object
    move_detect         which of those are moves, paired by file name
    object_create       one file's content into the IDE: update or create
    pou_children        a POU's members kept across a recreate
    import_order        parents before members; orphans with their parent
    device_remap        a renamed device, mapped for the import
    text_kind           which kind an .st text reads as
    codesys_ui          the WinForms dialogs a person clicks
    codesys_online      is anyone logged into a PLC right now

    entry_*             the bodies behind the Scripts menu entries. stub/ has
                        the ten-line files the IDE scans; entry.py lends a body
                        the IDE globals it was written to find in its own
                        namespace.
"""

from __future__ import print_function

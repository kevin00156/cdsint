# -*- coding: utf-8 -*-
"""The manager for EtherCAT devices: a `.device` file out, its edits back in.

SPEC 6.10. The ObjectManager contract around engine/device_params.py, used
by the device pass (engine/device_pass.py) on the way out and by the import's
text pass on the way back. It never creates, removes or updates a device.
"""
from __future__ import print_function

import io
import os

from cds.core import device_text
from engine import device_changes, device_params
from engine.managers_base import ObjectManager
from engine.st_text import read_sync_text
from engine.strings import calculate_hash, safe_str

NOT_CREATED = ("%s has no device at that place in the IDE, and import does "
               "not create one (SPEC 6.10)")


class DeviceManager(ObjectManager):
    """Export renders the settings; update applies a file and reads back."""

    def export(self, obj, effective_type, rel_path, context):
        text = device_params.render(obj)
        file_path = os.path.join(context["export_dir"],
                                 rel_path.replace("/", os.sep))
        if (os.path.exists(file_path)
                and device_text.same(text, read_sync_text(file_path))):
            return self._put_in_order(obj, rel_path, file_path, text, context)
        return self._write_text(obj, rel_path, file_path, text,
                                calculate_hash(text), context)

    def _put_in_order(self, obj, rel_path, file_path, text, context):
        """Same settings in another form: rewrite past the dirty-file guard,
        as managers_library does, since nothing unimported can be lost."""
        if read_sync_text(file_path) != text:
            with io.open(file_path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            verdict = "updated"
        else:
            verdict = "identical"
        return self._tracked(obj, rel_path, file_path, context,
                             calculate_hash(text), verdict)

    def update(self, obj, file_path):
        """Apply the file. True when the device changed; raises naming every
        key that did not land, and changes nothing for a file that does not
        parse or names another device."""
        wanted, problems = device_text.parse(read_sync_text(file_path))
        if problems:
            raise RuntimeError("nothing changed: " + "; ".join(problems))
        ident = device_params.ident_of(obj)
        if wanted["ident"] != ident:
            raise RuntimeError(
                "nothing changed: the file is for identification %s and the "
                "device is %s; changing a device's identification is the "
                "IDE's job (SPEC 6.10)" % (wanted["ident"], ident))
        before = device_params.render(obj)
        problems = device_params.apply(obj, wanted)
        if device_params.render(obj) != before:
            device_changes.changed(safe_str(obj.get_name()))
        if problems:
            raise RuntimeError("; ".join(problems))
        return device_params.render(obj) != before

    def create(self, container, name, file_path, type_guid):
        raise RuntimeError(NOT_CREATED % file_path)

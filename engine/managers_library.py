# -*- coding: utf-8 -*-
"""The Library Manager's manager: its text file out, its edits back in.

SPEC 6.9. One Library Manager per application and one `.libraries` file
each. What the file means, and how a difference is judged, is
cds/core/library_list.py; reading and changing the references is
engine/library_refs.py. This file is only the ObjectManager contract around
them.
"""
from __future__ import print_function

import io
import os

from cds.core import library_list
from engine import build_clean, library_refs
from engine.managers_base import ObjectManager
from engine.st_text import read_sync_text
from engine.strings import calculate_hash, safe_str

NOT_CREATED = ("%s has no Library Manager beside it in the IDE, and import "
               "does not create one (SPEC 6.9)")


class LibraryManager(ObjectManager):
    """Export renders the references; update applies a file and reads back."""

    def export(self, obj, effective_type, rel_path, context):
        text = library_refs.render_ide(obj)
        file_path = os.path.join(context["export_dir"],
                                 rel_path.replace("/", os.sep))
        if self._same_entries(file_path, text):
            return self._put_in_order(obj, rel_path, file_path, text, context)
        return self._write_text(obj, rel_path, file_path, text,
                                calculate_hash(text), context)

    def _same_entries(self, file_path, text):
        if not os.path.exists(file_path):
            return False
        return library_list.same(text, read_sync_text(file_path))

    def _put_in_order(self, obj, rel_path, file_path, text, context):
        """The file says what the IDE holds, perhaps in another order.

        The dirty-file guard (SPEC 6.1) must not stop this rewrite: right
        after an import of a hand-edited file, the file is newer than the
        last sync and in the editor's order, and refusing to put it in
        export's form left verify stopped with "waiting to be imported" on a
        file that had just been imported (measured on 3.5.21.40). Nothing is
        lost: the entries are the same, only order, spacing and comments go.
        """
        if read_sync_text(file_path) == text:
            return self._tracked(obj, rel_path, file_path, context,
                                 calculate_hash(text), "identical")
        with io.open(file_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return self._tracked(obj, rel_path, file_path, context,
                             calculate_hash(text), "updated")

    def update(self, obj, file_path):
        """Apply the file. True when the IDE changed; raises naming every
        line that did not land, and on a file that does not parse changes
        nothing at all."""
        wanted, problems = library_list.parse(read_sync_text(file_path))
        if problems:
            raise RuntimeError("nothing changed: " + "; ".join(problems))
        before = library_refs.render_ide(obj)
        problems = library_refs.apply(obj, wanted)
        changed = library_refs.render_ide(obj) != before
        if changed:
            self._next_build_cleans(obj)
        if problems:
            raise RuntimeError("; ".join(problems))
        return changed

    def _next_build_cleans(self, obj):
        path = getattr(self.project, "path", None)
        if path:
            build_clean.forget(safe_str(path), safe_str(obj.parent.get_name()))

    def create(self, container, name, file_path, type_guid):
        raise RuntimeError(NOT_CREATED % file_path)

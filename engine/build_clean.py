# -*- coding: utf-8 -*-
"""Clean before building when an application's libraries changed (SPEC 6.9).

After a library change build() can report "application is up to date, 0
errors" without compiling anything (docs/library-manager-research.md 5.2).
The list is compared with the one recorded at the application's last build
(cds/core/build_record.py), so whoever changed it -- cdsint's import or a
person in the IDE -- the next build cleans first.
"""
from __future__ import print_function

from cds.core import build_record
from engine import library_refs
from engine.codesys_constants import kind_of
from engine.ide_read import children_of
from engine.strings import safe_str


def _library_manager(app):
    for child in children_of(app):
        if kind_of(safe_str(child.type)) == "library_manager":
            return child
    return None


def forget(project_path, app_name):
    """Make the application's next build clean, whatever the list says then.

    Called when an import changed a Library Manager. The record knows only
    cdsint's own builds: after a person builds a changed list in the IDE and
    import puts the recorded one back, the digests agree and the IDE's last
    compile is of the other list -- the "up to date, 0 errors" trap of
    research 5.2.
    """
    path = build_record.path_for(project_path)
    record = build_record.read(path)
    if record.pop(app_name, None) is not None:
        build_record.write(path, record)


def clean_if_libraries_changed(app, app_name, project_path):
    """Clean `app` when its library list is not the one last built with.

    Returns what it did, for the build to print, or None when nothing
    changed. The new list is recorded at once: after the clean, whatever the
    build then says is about this list.
    """
    libman = _library_manager(app)
    text = library_refs.render_ide(libman) if libman is not None else u""
    path = build_record.path_for(project_path)
    record = build_record.read(path)
    now = build_record.digest(text)
    if record.get(app_name) == now:
        return None
    app.clean()
    record[app_name] = now
    build_record.write(path, record)
    return ("%s: its libraries differ from its last build, so it was "
            "cleaned first (SPEC 6.9)" % app_name)

# -*- coding: utf-8 -*-
"""Clean before a build whose library list changed (SPEC 6.9, Build)."""
from cds.core import build_record
from engine import build_clean
from engine.codesys_constants import TYPE_GUIDS
from tests.fakes import Node
from tests.library_fakes import a_project_libman


class App(Node):
    """An application with one Library Manager, counting its cleans."""

    def __init__(self, libman):
        Node.__init__(self, "Application", TYPE_GUIDS["application"],
                      children=[libman])
        self.cleaned = 0

    def clean(self):
        self.cleaned += 1


def recorded(project):
    return build_record.read(build_record.path_for(project))


def test_the_first_build_cleans_and_records(tmp_path):
    project = str(tmp_path / "Line.project")
    app = App(a_project_libman())
    assert build_clean.clean_if_libraries_changed(app, "Application", project)
    assert app.cleaned == 1
    assert "Application" in recorded(project)


def test_an_unchanged_list_does_not_clean(tmp_path):
    project = str(tmp_path / "Line.project")
    app = App(a_project_libman())
    build_clean.clean_if_libraries_changed(app, "Application", project)
    assert build_clean.clean_if_libraries_changed(app, "Application",
                                                  project) is None
    assert app.cleaned == 1


def test_a_library_removed_by_anyone_cleans(tmp_path):
    project = str(tmp_path / "Line.project")
    libman = a_project_libman()
    app = App(libman)
    build_clean.clean_if_libraries_changed(app, "Application", project)
    libman.remove_library("#SysMem")    # a system one, as a person might
    assert build_clean.clean_if_libraries_changed(app, "Application", project)
    assert app.cleaned == 2


def test_each_application_has_its_own_record(tmp_path):
    project = str(tmp_path / "Line.project")
    build_clean.clean_if_libraries_changed(App(a_project_libman()), "A", project)
    other = App(a_project_libman())
    assert build_clean.clean_if_libraries_changed(other, "B", project)
    assert sorted(recorded(project)) == ["A", "B"]


def test_an_application_without_a_library_manager_still_builds(tmp_path):
    project = str(tmp_path / "Line.project")
    app = App(a_project_libman())
    app._children = []
    assert build_clean.clean_if_libraries_changed(app, "Application", project)
    assert build_clean.clean_if_libraries_changed(app, "Application",
                                                  project) is None

# -*- coding: utf-8 -*-
"""What counts as a file in the sync folder, asked once.

Three walks used to answer this, and they disagreed: the orphan sweep did not
skip `__pycache__` and never consulted RESERVED_FILES, so a `.st` inside a
bytecode folder was a file it would offer to delete and a file the new-file
scan would never claim. Nothing had gone wrong yet only because RESERVED_FILES
holds no `.st`, which is a fact about today's constant, not a rule.
"""
import os

import pytest

from engine.codesys_constants import RESERVED_FILES
from engine.sync_dir import has_st_files, sync_files


@pytest.fixture
def folder(tmp_path):
    def write(rel, text="FUNCTION_BLOCK FB\nEND_FUNCTION_BLOCK\n"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    return tmp_path, write


def paths(base):
    return sorted(rel for rel, _abs in sync_files(str(base)))


class TestWhatItYields:
    def test_source_files_at_any_depth(self, folder):
        base, write = folder
        write("Top.st")
        write("Device/App/Deep.st")
        write("Device/Task configuration.task_config.xml")
        assert paths(base) == ["Device/App/Deep.st",
                               "Device/Task configuration.task_config.xml",
                               "Top.st"]

    def test_rel_paths_use_forward_slashes(self, folder):
        """The IDE-side paths and the cache keys are already in this form."""
        base, write = folder
        write("Device/App/Deep.st")
        assert "\\" not in paths(base)[0]

    def test_the_absolute_path_points_at_the_file(self, folder):
        base, write = folder
        write("Device/Deep.st")
        _rel, abs_path = list(sync_files(str(base)))[0]
        assert os.path.isfile(abs_path)


class TestWhatItSkips:
    def test_dot_folders(self, folder):
        """Where git and the backups keep their own copies of the project."""
        base, write = folder
        write(".git/Objects.st")
        write("Real.st")
        assert paths(base) == ["Real.st"]

    def test_pycache_folders(self, folder):
        """The sweep used to walk into these and the scan did not."""
        base, write = folder
        write("__pycache__/Cached.st")
        write("Real.st")
        assert paths(base) == ["Real.st"]

    def test_dot_files(self, folder):
        base, write = folder
        write(".gitignore", "sync_cache.json\n")
        write("Real.st")
        assert paths(base) == ["Real.st"]

    def test_reserved_files(self, folder):
        """RESERVED_FILES holds no .st today. This does not depend on that."""
        base, write = folder
        reserved = sorted(n for n in RESERVED_FILES if not n.startswith("."))
        for name in reserved:
            write(name, "{}")
        write("Real.st")
        assert paths(base) == ["Real.st"]

    def test_anything_that_is_not_st_or_xml(self, folder):
        base, write = folder
        write("notes.md", "# notes\n")
        write("Real.st")
        assert paths(base) == ["Real.st"]


class TestHasStFiles:
    def test_true_when_a_source_file_is_there(self, folder):
        base, write = folder
        write("Device/Main.st")
        assert has_st_files(str(base)) is True

    def test_false_for_an_empty_folder(self, folder):
        base, _write = folder
        assert has_st_files(str(base)) is False

    def test_an_xml_alone_is_not_something_to_import(self, folder):
        base, write = folder
        write("Device/Task configuration.task_config.xml", "<x/>")
        assert has_st_files(str(base)) is False

    def test_it_asks_the_same_walk_the_scan_does(self, folder):
        """A .st the scan will not look at cannot be a source of truth."""
        base, write = folder
        write("__pycache__/Cached.st")
        write(".git/Stashed.st")
        assert has_st_files(str(base)) is False

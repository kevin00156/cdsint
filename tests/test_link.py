# -*- coding: utf-8 -*-
"""Tests for cdsint.link, against ScriptDirs built in a tmp_path.

The body is a tmp directory too, so body.path is never written into the
checkout under test. Junctions are real on Windows; elsewhere a directory
symlink stands in, which os.readlink and os.unlink treat the same way.
"""
import io
import json
import os
import subprocess

import pytest

from cds.core.exits import EXIT_FAILED, EXIT_OK
from cdsint import cli, link


def junction(menu, target):
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", menu, target],
                       check=True, capture_output=True)
    else:
        os.symlink(target, menu, target_is_directory=True)


def install(name, script_dir, admin=False):
    return {"name": name, "script_dir": script_dir,
            "script_dir_needs_admin": admin}


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A body with a stub folder, and whatever installs a test declares."""
    body = str(tmp_path / "body")
    os.makedirs(os.path.join(body, "stub"))
    monkeypatch.setattr(link, "REPO_ROOT", body)
    monkeypatch.setattr(link, "make_junction", junction)
    monkeypatch.setattr(link, "is_elevated", lambda: False)
    found = []
    monkeypatch.setattr(link.installs, "find", lambda: found)
    return tmp_path, found


def menu_of(script_dir):
    return os.path.join(script_dir, link.MENU_FOLDER)


def test_every_script_dir_is_linked_once(machine):
    root, found = machine
    shared, other = str(root / "codesys"), str(root / "lenze")
    found += [install("SP20", shared), install("SP21", shared),
              install("Lenze 4.0", other)]
    rows = link.link_all()
    assert [(r["ide"], r["state"]) for r in rows] == [
        ("SP20 + SP21", link.LINKED), ("Lenze 4.0", link.LINKED)]
    assert link.points_here(menu_of(shared))
    assert link.points_here(menu_of(other))


def test_the_stubs_are_told_where_the_body_is(machine):
    link.link_all()
    with io.open(os.path.join(link.stub_dir(), "body.path"), "rb") as f:
        assert f.read() == link.REPO_ROOT.encode("utf-8")


def test_a_second_run_changes_nothing(machine):
    root, found = machine
    found.append(install("SP21", str(root / "codesys")))
    link.link_all()
    assert [r["state"] for r in link.link_all()] == [link.ALREADY]


def test_a_junction_onto_another_body_is_repointed(machine):
    root, found = machine
    script_dir = str(root / "codesys")
    elsewhere = str(root / "old-clone" / "stub")
    os.makedirs(elsewhere)
    os.makedirs(script_dir)
    junction(menu_of(script_dir), elsewhere)
    found.append(install("SP21", script_dir))
    assert [r["state"] for r in link.link_all()] == [link.LINKED]
    assert link.points_here(menu_of(script_dir))
    assert os.path.isdir(elsewhere)


def test_a_real_directory_in_the_way_is_left_alone(machine):
    root, found = machine
    script_dir = str(root / "codesys")
    os.makedirs(menu_of(script_dir))
    keep = os.path.join(menu_of(script_dir), "somebody's.py")
    open(keep, "w").close()
    found.append(install("SP21", script_dir))
    assert [r["state"] for r in link.link_all()] == [link.OCCUPIED]
    assert os.path.isfile(keep)


def test_program_files_needs_an_elevated_shell(machine, monkeypatch):
    root, found = machine
    script_dir = str(root / "delta")
    found.append(install("Delta 1.10", script_dir, admin=True))
    assert [r["state"] for r in link.link_all()] == [link.NEEDS_ADMIN]
    assert not os.path.lexists(menu_of(script_dir))
    monkeypatch.setattr(link, "is_elevated", lambda: True)
    assert [r["state"] for r in link.link_all()] == [link.LINKED]


def test_a_failed_junction_is_reported(machine, monkeypatch):
    root, found = machine
    found.append(install("SP21", str(root / "codesys")))

    def refuse(menu, target):
        raise OSError("Access is denied.")
    monkeypatch.setattr(link, "make_junction", refuse)
    row, = link.link_all()
    assert row["state"] == link.FAILED
    assert "Access is denied." in row["detail"]


def test_script_dir_links_that_one_only(machine):
    root, found = machine
    found.append(install("SP21", str(root / "codesys")))
    given = str(root / "given")
    rows = link.link_all(given)
    assert [r["state"] for r in rows] == [link.LINKED]
    assert link.points_here(menu_of(given))
    assert not os.path.lexists(menu_of(str(root / "codesys")))


def test_unlinked_names_the_ides_without_this_body(machine):
    root, found = machine
    found += [install("SP21", str(root / "codesys")),
              install("Delta 1.10", str(root / "delta"), admin=True)]
    link.link_all()
    assert link.unlinked() == [("Delta 1.10", True)]


def test_link_through_the_cli(machine, capsys):
    root, found = machine
    found.append(install("SP21", str(root / "codesys")))
    assert cli.main(["link", "--json"]) == EXIT_OK
    rows = json.loads(capsys.readouterr().out)
    assert [r["state"] for r in rows] == [link.LINKED]


def test_a_skipped_ide_is_exit_1(machine, capsys):
    root, found = machine
    found.append(install("Delta 1.10", str(root / "delta"), admin=True))
    assert cli.main(["link"]) == EXIT_FAILED
    assert "elevated" in capsys.readouterr().out


def test_no_ide_at_all_is_exit_1(machine, capsys):
    assert cli.main(["link"]) == EXIT_FAILED
    assert "--script-dir" in capsys.readouterr().out

# -*- coding: utf-8 -*-
"""Tests for cdsint.toolbar, against .opt.tbar files built in a tmp_path.

The shape is the one a first start of a real IDE writes. What the IDE then does
with an edited file is not something these can show; that was measured against
real IDEs, and the module's docstring says what was seen.
"""
import codecs
import json
import os
import xml.etree.ElementTree as ElementTree

import pytest

from cds.core.exits import EXIT_FAILED, EXIT_OK
from cdsint import cli, installs, toolbar
from cdsint.exits import Failure

NEW = "142063ff-039a-46ff-afd8-16c0c4afaacd"
LANE = "aaaaaaaa-0000-0000-0000-000000000000"


def tbar(first_items=(NEW,), second_items=(LANE,), newline="\r\n"):
    """A toolbar file, as text."""
    def items(guids):
        return "".join(
            '        <Single Type="{item}" Method="IArchivable">\n'
            '          <Single Name="CommandGuid" Type="System.Guid">%s</Single>\n'
            '          <Single Name="InfoCache" Type="string">AAAA</Single>\n'
            '        </Single>\n' % guid for guid in guids)
    text = (
        '<?xml version="1.0" encoding="utf-16"?>\n'
        '<Single xml:space="preserve" Type="{root}" Method="IArchivable">\n'
        '  <List Name="Toolbars" Type="{bars}">\n'
        '    <Single Type="{bar}" Method="IArchivable">\n'
        '      <Single Name="Name" Type="string">Standard</Single>\n'
        '      <Single Name="Visible" Type="bool">True</Single>\n'
        '      <List Name="Items" Type="{list}">\n' + items(first_items) +
        '      </List>\n'
        '    </Single>\n'
        '    <Single Type="{bar}" Method="IArchivable">\n'
        '      <Single Name="Name" Type="string">Other</Single>\n'
        '      <List Name="Items" Type="{list}">\n' + items(second_items) +
        '      </List>\n'
        '    </Single>\n'
        '  </List>\n'
        '</Single>\n')
    return text.replace("\n", newline)


def encoded(text):
    return codecs.BOM_UTF16_LE + text.encode("utf-16-le")


def commands(raw):
    """Each toolbar's command GUIDs in order."""
    bars = ElementTree.fromstring(raw).find("List[@Name='Toolbars']")
    return [[e.text for e in bar.iter() if e.get("Name") == "CommandGuid"]
            for bar in bars]


def write(path, raw):
    with open(str(path), "wb") as handle:
        handle.write(raw)
    return str(path)


def read(path):
    with open(str(path), "rb") as handle:
        return handle.read()


def test_button_goes_first_on_the_first_toolbar_only():
    result = toolbar.with_button(encoded(tbar()))
    assert commands(result) == [[toolbar.COMMAND_GUID, NEW], [LANE]]


@pytest.mark.parametrize("newline", ["\r\n", "\n"])
def test_nothing_else_in_the_file_changes(newline):
    raw = encoded(tbar(newline=newline))
    result = toolbar.with_button(raw)
    inserted = result[len(codecs.BOM_UTF16_LE):].decode("utf-16-le")
    lines = inserted.split(newline)
    at = next(i for i, line in enumerate(lines) if toolbar.COMMAND_GUID in line)
    without = lines[:at - 1] + lines[at + 2:]
    assert encoded(newline.join(without)) == raw


def test_the_first_toolbar_empty_is_refused_not_spilled_into_the_second():
    text = tbar(first_items=()).replace(
        '<List Name="Items" Type="{list}">\r\n      </List>',
        '<List Name="Items" Type="{list}" />', 1)
    assert toolbar.with_button(encoded(text)) is None


@pytest.mark.parametrize("raw", [
    tbar().encode("utf-8"),
    codecs.BOM_UTF16_BE + tbar().encode("utf-16-be"),
    encoded(tbar()) + b"x",
    encoded("<Single />"),
    encoded(tbar().replace('Name="Toolbars"', 'Name="Bars"')),
    encoded(tbar().replace("</Single>\r\n", "", 1)),
], ids=["utf8", "big-endian", "odd-bytes", "no-toolbars", "renamed", "broken"])
def test_an_unknown_shape_is_refused(raw):
    assert toolbar.with_button(raw) is None


def test_add_keeps_the_original_and_adds_once(tmp_path):
    original = encoded(tbar())
    path = write(tmp_path / "a.opt.tbar", original)
    assert toolbar.add_to_file(path) == (toolbar.ADDED, path)
    assert commands(read(path))[0][0] == toolbar.COMMAND_GUID
    assert read(path + toolbar.BACKUP_SUFFIX) == original
    changed = read(path)
    assert toolbar.add_to_file(path) == (toolbar.ALREADY, path)
    assert read(path) == changed
    assert sorted(os.listdir(str(tmp_path))) == [
        "a.opt.tbar", "a.opt.tbar" + toolbar.BACKUP_SUFFIX]


def test_a_button_on_any_toolbar_counts_and_nothing_is_written(tmp_path):
    raw = encoded(tbar(second_items=(toolbar.COMMAND_GUID,)))
    path = write(tmp_path / "a.opt.tbar", raw)
    assert toolbar.add_to_file(path)[0] == toolbar.ALREADY
    assert os.listdir(str(tmp_path)) == ["a.opt.tbar"]


def test_a_second_add_keeps_the_first_backup(tmp_path):
    """A backup that is overwritten stops being the original."""
    first = encoded(tbar())
    path = write(tmp_path / "a.opt.tbar", first)
    toolbar.add_to_file(path)
    write(path, encoded(tbar(first_items=(LANE,))))
    toolbar.add_to_file(path)
    assert read(path + toolbar.BACKUP_SUFFIX) == first


def test_an_unknown_shape_is_left_exactly_as_it_was(tmp_path):
    raw = encoded("<Single />")
    path = write(tmp_path / "a.opt.tbar", raw)
    assert toolbar.add_to_file(path) == (toolbar.UNRECOGNISED, path)
    assert read(path) == raw
    assert os.listdir(str(tmp_path)) == ["a.opt.tbar"]


def test_a_file_that_cannot_be_read_is_reported(tmp_path):
    state, detail = toolbar.add_to_file(str(tmp_path / "gone.opt.tbar"))
    assert state == toolbar.FAILED
    assert "gone.opt.tbar" in detail


def test_a_failed_swap_leaves_the_file_whole(tmp_path, monkeypatch):
    raw = encoded(tbar())
    path = write(tmp_path / "a.opt.tbar", raw)

    def refuse(_new, _path):
        raise OSError("in use")
    monkeypatch.setattr(toolbar.os, "replace", refuse)
    assert toolbar.add_to_file(path)[0] == toolbar.FAILED
    assert read(path) == raw


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Installs a test declares, and nothing running."""
    found = []
    monkeypatch.setattr(toolbar.installs, "find", lambda: found)
    monkeypatch.setattr(toolbar.update, "running_ides", lambda: [])
    return tmp_path, found


def install(name, profile, *roots):
    """An install with the scripting plug-in, in a directory of its own."""
    plugins = roots[0].parent / ("plugins-" + name)
    os.makedirs(str(plugins / toolbar._SCRIPT_ENGINE_PLUGIN / "4.1.0.0"),
                exist_ok=True)
    return {"name": name, "profiles": [profile], "plugins": str(plugins),
            "user_options": [str(r) for r in roots]}


def options_file(root, profile, hashed="UserOptions-1", prefix="CODESYS"):
    folder = root / hashed
    os.makedirs(str(folder), exist_ok=True)
    return write(folder / ("%s (%s).opt.tbar" % (prefix, profile)),
                 encoded(tbar()))


def test_each_install_gets_its_own_profiles_file_only(machine):
    root, found = machine
    sp20 = options_file(root, "SP20", "UserOptions-A")
    sp21 = options_file(root, "SP21", "UserOptions-B")
    found.append(install("CODESYS 3.5.20", "SP20", root))
    assert toolbar.add_everywhere() == [
        {"ide": "CODESYS 3.5.20", "state": toolbar.ADDED, "detail": sp20}]
    assert commands(read(sp21))[0] == [NEW]


def test_a_profile_is_matched_whole(machine):
    """"V1" must not take the file of the install called "SP V1"."""
    root, found = machine
    options_file(root, "SP V1")
    found.append(install("X", "V1", root))
    assert [r["state"] for r in toolbar.add_everywhere()] == [toolbar.NO_FILE]


def test_every_leftover_file_of_an_install_is_changed(machine):
    root, found = machine
    newer, older = root / "new", root / "old"
    options_file(newer, "DIA", "A/B/UserOptions-1", "Delta")
    options_file(older, "DIA", "UserOptions-2", "DIADesigner-AX")
    found.append(install("Delta", "DIA", newer, older))
    assert [r["state"] for r in toolbar.add_everywhere()] == [
        toolbar.ADDED, toolbar.ADDED]


def test_an_ide_never_opened_is_said_and_others_still_get_theirs(machine):
    root, found = machine
    options_file(root, "SP21")
    found += [install("new one", "SP22", root), install("SP21", "SP21", root)]
    assert [(r["ide"], r["state"]) for r in toolbar.add_everywhere()] == [
        ("new one", toolbar.NO_FILE), ("SP21", toolbar.ADDED)]


def test_an_ide_without_the_plugin_is_not_written_or_called_a_failure(
        machine, capsys):
    """It would ignore the item and show nothing: an SP19 did, on 2026-11-06."""
    root, found = machine
    path = options_file(root, "SP19")
    before = read(path)
    bare = install("SP19", "SP19", root)
    bare["plugins"] = str(root / "nothing-here")
    found.append(bare)
    assert cli.main(["toolbar"]) == EXIT_OK
    assert "no scripting plug-in" in capsys.readouterr().out
    assert read(path) == before
    assert not os.path.exists(path + toolbar.BACKUP_SUFFIX)


def test_an_ide_without_the_plugin_does_not_excuse_one_with_it(machine):
    root, found = machine
    bare = install("SP19", "SP19", root)
    bare["plugins"] = str(root / "nothing-here")
    found += [bare, install("new", "SP22", root)]
    assert cli.main(["toolbar"]) == EXIT_FAILED


def test_any_open_ide_stops_every_write(machine, monkeypatch):
    root, found = machine
    path = options_file(root, "SP20")
    before = read(path)
    found.append(install("CODESYS 3.5.20", "SP20", root))
    monkeypatch.setattr(toolbar.update, "running_ides",
                        lambda: ["CODESYS.exe"])
    assert toolbar.add_everywhere() == [
        {"ide": "every IDE", "state": toolbar.IDE_OPEN,
         "detail": "CODESYS.exe"}]
    assert read(path) == before


def test_not_knowing_what_runs_stops_every_write_too(machine, monkeypatch):
    root, found = machine
    path = options_file(root, "SP20")
    before = read(path)
    found.append(install("CODESYS 3.5.20", "SP20", root))

    def unknown():
        raise Failure("could not list")
    monkeypatch.setattr(toolbar.update, "running_ides", unknown)
    assert [r["state"] for r in toolbar.add_everywhere()] == [toolbar.FAILED]
    assert read(path) == before


def test_command_exits_zero_when_every_ide_has_it(machine, capsys):
    root, found = machine
    path = options_file(root, "SP20")
    found.append(install("SP20", "SP20", root))
    assert cli.main(["toolbar", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)[0]["detail"] == path


def test_command_exits_one_when_an_ide_is_left_without(machine, capsys):
    root, found = machine
    options_file(root, "SP20")
    found += [install("SP20", "SP20", root), install("new", "SP22", root)]
    assert cli.main(["toolbar"]) == EXIT_FAILED
    assert "start it once" in capsys.readouterr().out


def test_command_exits_one_when_no_ide_is_found(machine, capsys):
    assert cli.main(["toolbar"]) == EXIT_FAILED
    assert "no CODESYS-family IDE" in capsys.readouterr().out


def test_every_vendor_says_where_its_options_live(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    for vendor in installs.VENDORS:
        assert vendor["options"]
    exe_dir = tmp_path / "CODESYS 3.5" / "CODESYS" / "Common"
    os.makedirs(str(exe_dir))
    write(exe_dir / "CODESYS.exe", b"")
    described = installs._describe(str(tmp_path / "CODESYS 3.5"),
                                   installs.VENDORS[0], {})
    assert described["user_options"] == [str(tmp_path / "CODESYS")]
    assert described["plugins"] == str(
        tmp_path / "CODESYS 3.5" / "CODESYS" / "PlugIns")

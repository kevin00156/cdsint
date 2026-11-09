# -*- coding: utf-8 -*-
"""An object's name and its file name, both ways (CDSI-15).

An FB called AUX was exported as AUX.st, which is not a file on Windows:
Windows 10 writes it to the AUX device, and git on Windows 11 will not
index it, so a colleague's clone had no such POU. And a folder `IO: Inputs`
is written `IO_ Inputs`; every lookup compared that segment with the raw
name, so importing a new file in it made a second folder beside it.
"""
import pytest

from engine import unhandled
from engine.file_names import clean_filename, name_from_file
from engine.ide_tree import (AmbiguousSegment, ensure_folder_path,
                             find_child_transparent)
from tests.sync_bench import Bench, Item, folder, pou


@pytest.mark.parametrize("name", ["AUX", "CON", "PRN", "NUL", "COM1", "COM9",
                                  "LPT1", "LPT9", u"COM¹", u"LPT³"])
def test_a_reserved_name_gets_a_mark_and_loses_it_coming_back(name):
    assert clean_filename(name) == name + "_"
    assert name_from_file(clean_filename(name)) == name


@pytest.mark.parametrize("name", ["aux", "Aux", "com1", "lPt5"])
def test_reserved_names_are_reserved_in_any_case(name):
    assert clean_filename(name) == name + "_"
    assert name_from_file(name + "_") == name


def test_the_name_before_the_first_dot_is_what_windows_checks():
    # AUX.Main.st is the AUX device on Windows as surely as AUX.st is.
    assert clean_filename("AUX.Main") == "AUX_.Main"
    assert name_from_file("AUX_.Main") == "AUX.Main"
    assert clean_filename("FB.AUX") == "FB.AUX"
    # A member's file name is cleaned a part at a time, so a method AUX of
    # FB is FB.AUX_.st, and its part comes back on its own.
    assert name_from_file("FB.AUX_") == "FB.AUX_"
    assert name_from_file("AUX_") == "AUX"


@pytest.mark.parametrize("name", ["MAIN_", "COM_", "COM10", "COM0", "AUXX",
                                  "AUX__", "MyAUX", "LPT", "_AUX"])
def test_a_name_that_is_not_reserved_stays_as_it_is(name):
    assert clean_filename(name) == name
    assert name_from_file(name) == name


def test_forbidden_characters_still_become_underscores():
    assert clean_filename("IO: Inputs") == "IO_ Inputs"
    assert clean_filename('a<b>c"d/e\\f|g?h*') == "a_b_c_d_e_f_g_h_"
    # A forbidden character that leaves a reserved name is a reserved name.
    assert clean_filename("AUX:") == "AUX_"


def _make_pous(item):
    """Let item create POUs, the way the IDE's create_pou does."""
    def create_pou(name, kind):
        made = pou(name, u"")
        made.owner, made.parent = item._children, item
        item._children.append(made)
        return made
    item.create_pou = create_pou
    item.create_child = create_pou


def _named(item, name):
    return [child for child in item._children if child.get_name() == name]


def test_an_fb_named_aux_exports_as_aux_underscore(monkeypatch, tmp_path):
    bench = Bench(monkeypatch, tmp_path,
                  Item("App", "application", [pou("AUX")]))

    result = bench.export()

    assert result["ok"] is True
    assert bench.files() == ["App/AUX_.st"]


FB = u"FUNCTION_BLOCK %s\nVAR\nEND_VAR\n\n// === IMPLEMENTATION ===\ny := 2;"


def test_a_new_aux_underscore_file_creates_an_fb_named_aux(monkeypatch,
                                                           tmp_path):
    app = Item("App", "application", [pou("Main")])
    bench = Bench(monkeypatch, tmp_path, app)
    bench.export()
    bench.write("App/AUX_.st", FB % "AUX")
    bench.write("App/MAIN_.st", FB % "MAIN_")
    _make_pous(app)

    result = bench.import_()

    assert result["data"]["created"] == 2
    assert len(_named(app, "AUX")) == 1 and len(_named(app, "MAIN_")) == 1
    assert bench.compare()["new_on_disk"] == []


METHOD = u"METHOD %s : BOOL\nVAR_INPUT\nEND_VAR\n\n// === IMPLEMENTATION ===\n"


def _method(name):
    return Item(name, "method", decl=METHOD % name, impl=u"")


def test_a_method_named_aux_round_trips(monkeypatch, tmp_path):
    fb = pou("AUX", u"")
    fb._children.append(_method("Old"))
    fb._children[0].parent, fb._children[0].owner = fb, fb._children
    app = Item("App", "application", [fb])
    bench = Bench(monkeypatch, tmp_path, app)
    bench.export()
    written = [f for f in bench.files() if f.endswith("Old.st")][0]
    assert written.endswith("AUX_.Old.st")
    bench.write(written.replace("AUX_.Old", "AUX_.LPT1_"), METHOD % "LPT1")

    def create_method(name):
        made = _method(name)
        made.parent, made.owner = fb, fb._children
        fb._children.append(made)
        return made
    fb.create_method = create_method

    result = bench.import_()

    assert result["data"]["created"] == 1
    assert [c.get_name() for c in fb._children] == ["Old", "LPT1"]


def test_aux_beside_aux_underscore_is_refused_naming_both(monkeypatch,
                                                          tmp_path):
    bench = Bench(monkeypatch, tmp_path, Item("App", "application", [
        pou("AUX", u"first := 1;"), pou("AUX_", u"second := 1;")]))

    result = bench.export()

    assert result["ok"] is False
    assert sorted(result["data"]["failed_objects"]) == ["AUX", "AUX_"]
    assert u"first := 1;" in bench.read("App/AUX_.st")


def test_a_new_file_in_a_cleaned_folder_lands_in_that_folder(monkeypatch,
                                                             tmp_path):
    inputs = folder("IO: Inputs", pou("Old"))
    app = Item("App", "application", [inputs])
    bench = Bench(monkeypatch, tmp_path, app)
    bench.export()
    assert bench.files() == ["App/IO_ Inputs/Old.st"]
    bench.write("App/IO_ Inputs/New.st", FB % "New")
    _make_pous(inputs)
    app.create_folder = lambda name: pytest.fail("made a folder " + name)

    result = bench.import_()

    assert result["data"]["created"] == 1
    assert [c.get_name() for c in app._children] == ["IO: Inputs"]
    assert [c.get_name() for c in inputs._children] == ["Old", "New"]


def test_a_reserved_folder_segment_is_found_and_made_by_its_name(
        monkeypatch, tmp_path):
    app = Item("App", "application", [folder("COM1")])
    made = []

    def create_folder(name):
        made.append(folder(name))
        made[-1].owner, made[-1].parent = app._children, app
        app._children.append(made[-1])
        return made[-1]
    app.create_folder = create_folder

    assert ensure_folder_path("COM1_", app).get_name() == "COM1"
    assert ensure_folder_path("LPT2_", app).get_name() == "LPT2"
    assert ensure_folder_path("lpt2_", app) is made[0]
    assert [f.get_name() for f in made] == ["LPT2"]


def test_two_children_one_segment_is_refused_naming_both():
    app = Item("App", "application", [folder("IO: A"), folder("IO_ A")])

    with pytest.raises(AmbiguousSegment) as raised:
        find_child_transparent(app, "IO_ A")

    assert "IO: A" in str(raised.value) and "IO_ A" in str(raised.value)


def test_a_refused_segment_fails_its_import_by_name(monkeypatch, tmp_path):
    app = Item("App", "application", [folder("IO: A"), folder("IO_ A")])
    bench = Bench(monkeypatch, tmp_path, app)
    bench.write("App/IO_ A/New.st", FB % "New")
    unhandled.start()

    result = bench.import_()

    assert result["data"]["created"] == 0
    assert "App/IO_ A/New.st" in result["data"]["failed_objects"]

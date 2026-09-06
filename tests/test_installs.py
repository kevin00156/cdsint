# -*- coding: utf-8 -*-
"""Tests for cdsint.installs, against a Program Files tree built here.

The real machine has seven installs and no test can depend on that, so the
shapes that matter are built in a tmp_path: a real one, a directory that only
looks like one, and two Lenze generations whose ScriptDirs differ.
"""
import os

import pytest

from cds.core.exits import EXIT_HEADLESS
from cdsint import installs
from cdsint.exits import Failure


def make(root, relative, exe, profiles=()):
    """Put an executable and its profiles where a vendor's tree would."""
    directory = os.path.join(root, *relative.split("/"))
    common = os.path.join(directory, exe["inner"], "Common")
    os.makedirs(common)
    open(os.path.join(common, exe["name"]), "w").close()
    profile_dir = os.path.join(directory, exe["inner"], "Profiles")
    os.makedirs(profile_dir)
    for name in profiles:
        open(os.path.join(profile_dir, name + ".profile.xml"), "w").close()
    return directory


CODESYS = {"inner": "CODESYS", "name": "CODESYS.exe"}
DELTA = {"inner": "CODESYS", "name": "DIADesigner-AX.exe"}
LENZE = {"inner": "PlcDesigner", "name": "PlcDesigner.exe"}


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A Program Files tree with one of each vendor, plus two decoys."""
    program_files = str(tmp_path / "Program Files")
    x86 = str(tmp_path / "Program Files (x86)")
    for variable, value in (("ProgramFiles", program_files),
                            ("ProgramFiles(x86)", x86),
                            ("LOCALAPPDATA", str(tmp_path / "Local")),
                            ("ProgramData", str(tmp_path / "ProgramData"))):
        monkeypatch.setenv(variable, value)
    monkeypatch.setattr(installs, "run_as_admin_layers", dict)
    make(program_files, "CODESYS 3.5.21.40", CODESYS,
         ["CODESYS V3.5 SP21 Patch 4"])
    make(program_files,
         "Delta Industrial Automation/DIAStudio/DIADesigner-AX 1.10", DELTA,
         ["DIADesigner-AX 1.10"])
    make(program_files, "Lenze/PlcDesigner/4.0.1.33999", LENZE,
         ["PLC Designer V4.0.1"])
    make(x86, "Lenze/PlcDesigner/3.24.0.24457", LENZE,
         ["PLC Designer V3.24.0"])
    # Decoys: the vendors put these beside the real installs, and a scan by
    # directory name reports each of them as an IDE with a ScriptDir of its own.
    os.makedirs(os.path.join(program_files, "Lenze", "PlcDesigner",
                             "GatewayPLC"))
    os.makedirs(os.path.join(program_files, "Delta Industrial Automation",
                             "DIAStudio", "DIADesigner-AX", "Launcher"))
    return tmp_path


def by_name(found):
    return [i["name"] for i in found]


# --- what counts as an install ---------------------------------------------

def test_only_directories_with_the_executable_count(machine):
    assert by_name(installs.find()) == [
        "CODESYS 3.5.21.40",
        "Delta DIADesigner-AX 1.10",
        "Lenze PLC Designer 3.24.0.24457",
        "Lenze PLC Designer 4.0.1.33999",
    ]


def test_the_profile_name_comes_from_the_file_not_the_directory(machine):
    # --noUI without --profile exits without a word, and the name it wants is
    # "CODESYS V3.5 SP21 Patch 4", not 3.5.21.40 (SPEC 6.4).
    found = installs.find()[0]
    assert found["profiles"] == ["CODESYS V3.5 SP21 Patch 4"]


def test_nothing_installed_is_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "nowhere"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "nowhere either"))
    monkeypatch.setattr(installs, "run_as_admin_layers", dict)
    assert installs.find() == []


# --- ScriptDir (SPEC 5.3) --------------------------------------------------

def test_each_vendor_gets_its_own_scriptdir(machine):
    found = dict((i["name"], i["script_dir"]) for i in installs.find())
    local = os.environ["LOCALAPPDATA"]
    assert found["CODESYS 3.5.21.40"] == os.path.join(local, "CODESYS",
                                                      "ScriptDir")
    assert found["Lenze PLC Designer 4.0.1.33999"] == os.path.join(
        local, "PLCDesigner", "ScriptDir")
    assert found["Lenze PLC Designer 3.24.0.24457"] == os.path.join(
        os.environ["ProgramData"], "PLCDesigner", "ScriptDir")
    assert found["Delta DIADesigner-AX 1.10"].endswith(
        os.path.join("DIADesigner-AX 1.10", "CODESYS", "ScriptDir"))


def test_only_the_scriptdir_inside_program_files_needs_an_elevated_shell(machine):
    needs = [i["name"] for i in installs.find()
             if i["script_dir_needs_admin"]]
    assert needs == ["Delta DIADesigner-AX 1.10"]


# --- the elevation flag ----------------------------------------------------

def test_a_run_as_admin_flag_is_reported_against_the_executable(machine,
                                                                monkeypatch):
    # The manifest can say asInvoker and the launch still be refused; the
    # error says only "requires elevation", never who asked for it (SPEC 6.4).
    exe = installs.find()[0]["exe"]
    monkeypatch.setattr(installs, "run_as_admin_layers",
                        lambda: {exe.lower(): "HKCU\\...\\Layers"})
    assert installs.find()[0]["run_as_admin"] == "HKCU\\...\\Layers"


# --- picking one -----------------------------------------------------------

def test_a_fragment_of_the_name_picks_one(machine):
    assert installs.resolve(installs.find(), "3.5.21.40")["name"] == \
        "CODESYS 3.5.21.40"


def test_the_delta_name_works_as_written_in_the_acceptance(machine):
    assert installs.resolve(installs.find(), "DIADesigner-AX 1.10")["name"] == \
        "Delta DIADesigner-AX 1.10"


def test_several_matches_are_refused_rather_than_guessed(machine):
    # This machine has seven; guessing drives a whole run against an IDE that
    # cannot open the project.
    with pytest.raises(Failure) as raised:
        installs.resolve(installs.find(), "Lenze")
    assert len(raised.value.lines) == 2


def test_no_match_lists_what_there_was(machine):
    with pytest.raises(Failure) as raised:
        installs.resolve(installs.find(), "InoProShop")
    assert len(raised.value.lines) == 4


def test_no_install_asked_for_is_refused_too(machine):
    with pytest.raises(Failure):
        installs.resolve(installs.find(), None)


def test_a_wrong_install_is_exit_4_and_not_a_traceback(machine, capsys):
    # It used to be an exception of its own that cdsint/cli.py did not catch,
    # so `--install definitely-not-an-ide` printed a traceback and exited 1.
    # 4 is "no usable IDE for this project" (SPEC 4.3), the same answer as a
    # project somebody else has open.
    with pytest.raises(Failure) as raised:
        installs.resolve(installs.find(), "definitely-not-an-ide")
    assert raised.value.report() == EXIT_HEADLESS
    printed = capsys.readouterr().err
    assert "definitely-not-an-ide" in printed
    assert "Traceback" not in printed


# --- picking a profile -----------------------------------------------------

def test_a_lone_profile_is_the_answer(machine):
    found = installs.resolve(installs.find(), "3.5.21.40")
    assert installs.profile_of(found) == "CODESYS V3.5 SP21 Patch 4"


def test_an_explicit_profile_wins(machine):
    found = installs.resolve(installs.find(), "3.5.21.40")
    assert installs.profile_of(found, "CODESYS V3.5 SP19") == \
        "CODESYS V3.5 SP19"


def test_two_profiles_need_the_caller_to_choose(machine, tmp_path):
    found = installs.resolve(installs.find(), "3.5.21.40")
    found["profiles"].append("CODESYS V3.5 SP21")
    with pytest.raises(Failure):
        installs.profile_of(found)


def test_no_profile_at_all_says_which_install(machine):
    found = installs.resolve(installs.find(), "3.5.21.40")
    found["profiles"] = []
    with pytest.raises(Failure) as raised:
        installs.profile_of(found)
    assert "CODESYS 3.5.21.40" in str(raised.value)

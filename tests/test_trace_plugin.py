# -*- coding: utf-8 -*-
"""An IDE without the CODESYS Trace package is told so, with the commands
that fetch the package and install it into that very IDE.

Before this, the first trace command there died on "'NoneType' object has no
attribute 'create'" (docs/trace-research.md 16), which names neither the
package nor the fix. The version strings are the ones these IDEs give
IronPython, copied from run reports on the machines they were measured on.
"""
import json
import sys

import pytest

from engine import trace_plugin

KNOWN = [
    (r"C:\Program Files\CODESYS 3.5.21.40\CODESYS\Common\CODESYS.exe",
     "CODESYS.exe CODESYS V3.5 SP21 Patch 4, ScriptEngine.plugin 4.2.0.0",
     "CODESYS V3.5 SP21 Patch 4"),
    (r"C:\Program Files\Delta Industrial Automation\DIAStudio"
     r"\DIADesigner-AX 1.10\CODESYS\Common\DIADesigner-AX.exe",
     "2.7.7 (DIADesigner-AX.exe DIADesigner-AX 1.10, "
     "ScriptEngine.plugin 4.0.0.0)",
     "DIADesigner-AX 1.10"),
    (r"C:\Program Files (x86)\Lenze\PlcDesigner\3.24.0.24457\PlcDesigner"
     r"\Common\PlcDesigner.exe",
     "2.7.7 (PlcDesigner.exe PLC Designer V3.24.0, "
     "ScriptEngine.plugin 4.0.0.0)",
     "PLC Designer V3.24.0"),
]


@pytest.mark.parametrize("executable, version, profile", KNOWN)
def test_the_command_names_this_ides_installer_and_profile(executable,
                                                           version, profile):
    hint = trace_plugin.install_hint(executable, version)
    common = executable.rsplit("\\", 1)[0]
    assert '"%s\\PackageManagerCLI.exe"' % common in hint
    assert '--profile="%s"' % profile in hint
    assert "CODESYS Trace" in hint and "APInstaller.CLI.exe" in hint


def test_the_download_names_the_package_as_guid_and_version():
    """APInstaller.CLI reads any other shape as the all-zero guid."""
    hint = trace_plugin.install_hint("", "2.7.7")
    line = [l for l in hint.splitlines() if "--packageIds" in l][0]
    ids = line.split('--packageIds "', 1)[1].rstrip('"')
    assert json.loads(ids.replace('\\"', '"')) == [
        {"Guid": "4e530ec4-2e4e-4639-b965-5b6267572c9b",
         "Version": "4.2.0.0"}]


def test_a_version_string_of_another_shape_still_says_what_to_install():
    hint = trace_plugin.install_hint(r"C:\X\Common\Other.exe", "2.7.12")
    assert trace_plugin.UNKNOWN_PROFILE in hint
    assert "PackageManagerCLI.exe" in hint and "CODESYS Trace" in hint


def test_no_executable_names_no_folder():
    hint = trace_plugin.install_hint("", "2.7.7")
    assert trace_plugin.UNKNOWN_FOLDER in hint
    assert trace_plugin.UNKNOWN_PROFILE in hint


def test_outside_an_ide_the_interpreter_is_the_executable():
    assert trace_plugin.this_executable() == sys.executable


def test_an_ide_with_both_globals_can_script_traces():
    assert trace_plugin.missing({"trace": object(),
                                 "Resolution": object()}) is None


@pytest.mark.parametrize("present", [{}, {"trace": object()},
                                     {"Resolution": object()}])
def test_an_ide_short_of_either_global_is_told_how_to_install(present):
    executable, version, profile = KNOWN[1]
    hint = trace_plugin.missing(present, executable, version)
    assert hint == trace_plugin.install_hint(executable, version)

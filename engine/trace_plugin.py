# -*- coding: utf-8 -*-
"""Whether this IDE can script traces, and the command that makes it able to.

Every trace command and plc trace work through the `trace` and `Resolution`
globals, and only the CODESYS Trace package's script driver puts them there.
An IDE built on CODESYS can ship without that package, and there the first
use died on "'NoneType' object has no attribute 'create'", which names
neither the package nor the fix (docs/trace-research.md 16). So the check
comes first, and its answer is the command that installs the package into
this very IDE: an agent that reads it can offer to run it.

Apart from asking .NET where the IDE's executable is, plain Python on two
strings, so CI holds the command to the IDEs it was measured on.
"""
from __future__ import print_function

import ntpath
import re
import sys

from engine import entry

GLOBALS = ("trace", "Resolution")
INSTALLER = "PackageManagerCLI.exe"
UNKNOWN_FOLDER = "<the folder this IDE's executable is in>"
UNKNOWN_PROFILE = "<this IDE's profile name>"

HINT = (
    "this IDE has no trace scripting: the CODESYS Trace package, whose "
    "script driver every trace command works through, is not installed in "
    "it. Close the IDE, install the package from an administrator prompt "
    "with\n"
    "  \"%s\" --profile=\"%s\" --install=\"<the CODESYS Trace .package "
    "file>\"\n"
    "and start the IDE again. In Windows PowerShell put & before the quoted "
    "path and --%% after it, or it mangles the quotes. The package, CODESYS "
    "Trace 4.2 or later, is on the CODESYS Store (store.codesys.com) and "
    "in the CODESYS Installer; download it from there yourself")


def missing(ide_globals, executable=None, version=None):
    """None when this IDE can script traces, else how to make it able to.

    executable and version default to this IDE's own; a test hands in
    another IDE's.
    """
    if all(entry.borrowed(ide_globals, name) is not None for name in GLOBALS):
        return None
    return install_hint(this_executable() if executable is None
                        else executable,
                        sys.version if version is None else version)


def this_executable():
    """The IDE's executable, folder and all.

    Inside the IDE sys.executable is the bare file name (measured in Lenze
    PLC Designer 3.24), and the installer is found by the folder. Outside
    one there is no .NET, and the interpreter is the only executable.
    """
    try:
        from System.Diagnostics import Process
    except ImportError:
        return sys.executable
    return Process.GetCurrentProcess().MainModule.FileName


def install_hint(executable, version):
    """The refusal, with this IDE's installer and profile filled in."""
    folder = ntpath.dirname(executable or "") or UNKNOWN_FOLDER
    return HINT % (ntpath.join(folder, INSTALLER),
                   profile_of(executable, version))


def profile_of(executable, version):
    """The profile name in the version string CODESYS gives IronPython.

    That string holds the executable's file name, then the profile, then a
    comma and the ScriptEngine plug-in. The installer wants the profile by
    name, and this string is where a script finds it.
    """
    name = ntpath.basename(executable or "")
    found = name and re.search(r"%s (.+?), ScriptEngine" % re.escape(name),
                               version or "")
    return found.group(1) if found else UNKNOWN_PROFILE

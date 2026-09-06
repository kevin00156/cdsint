# -*- coding: utf-8 -*-
"""Which CODESYS-family IDEs are on this machine, and how to start one.

The headless form needs three things about an install before it can launch
it: where the executable is, what its profile is called, and whether starting
it needs an elevated shell. None of the three is guessable from the install
path, and getting the profile name wrong means the IDE exits without a word
(SPEC 6.4).

The fourth thing nobody can guess is which directory that IDE scans for menu
scripts (SPEC 5.3). It is answered here too, and here only: irm/setup.ps1
used to carry its own copy of the same table, and the two disagreed for
months about whether writing into ProgramData needs an elevated shell. The
installer asks `cdsint installs --json` now.

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import fnmatch
import os
import sys

from cds.core.exits import EXIT_HEADLESS
from cdsint.exits import Failure

# The environment variables whose directories hold installed programs. Both,
# for every vendor: a 32-bit installer on a 64-bit machine lands in the second
# one, and this machine has Lenze 3.24 there and Lenze 4.0 in the first.
ROOTS = ("ProgramFiles", "ProgramFiles(x86)")

PROFILE_SUFFIX = ".profile.xml"

# Where the registry records "this exe always runs elevated". A manifest that
# says asInvoker is not the last word: this flag overrides it, and the launch
# failure it causes says only "requires elevation", never who asked for it.
LAYER_KEYS = (
    ("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"),
    ("HKCU", r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"),
)


def _profile_dir():
    """%LOCALAPPDATA%, read now rather than at import: tests move it."""
    return os.environ.get("LOCALAPPDATA", "")


def _codesys_script_dir(_directory):
    """SP17 to SP21 all scan the same one, however many are installed."""
    return os.path.join(_profile_dir(), "CODESYS", "ScriptDir")


def _lenze_script_dir(directory):
    """4.x moved it into the user profile; 3.x is still machine-wide.

    Machine-wide is not the same as elevated. ProgramData's default rules let
    any user create things, and the Lenze installer leaves this directory
    Full Control for Everyone -- measured on this machine on 2026-09-06 by
    making a junction in it from an ordinary shell, which worked.
    """
    if os.path.basename(directory).startswith("4."):
        return os.path.join(_profile_dir(), "PLCDesigner", "ScriptDir")
    return os.path.join(os.environ.get("ProgramData", ""), "PLCDesigner",
                        "ScriptDir")


def _delta_script_dir(directory):
    """Delta keeps it inside the install, so under Program Files."""
    return os.path.join(directory, "CODESYS", "ScriptDir")


# What each vendor's tree looks like. Only the executable proves an install:
# these vendors put shared targets, gateways and an unversioned stub
# directory beside the real ones, and a scan by directory name reports every
# one of those as an IDE of its own.
#
#   prefix      what to call it, in front of the directory name
#   under       path segments under each root, empty when the installs sit
#               right there; segments, not a joined string, because a joined
#               "a\b" is one filename on Linux and the scan finds nothing
#   pattern     the directory name shape, matched with fnmatch
#   inner       the subdirectory holding Common\ and Profiles\
#   exe         the executable inside Common\
#   script_dir  the menu directory this IDE scans, given the install
#               directory. A function rather than a template because Lenze's
#               answer depends on the version, and that fork belongs in this
#               row rather than in an if/elif that re-derives every vendor.
VENDORS = (
    {"prefix": "", "under": (), "pattern": "CODESYS *",
     "inner": "CODESYS", "exe": "CODESYS.exe",
     "script_dir": _codesys_script_dir},
    {"prefix": "Lenze PLC Designer ",
     "under": ("Lenze", "PlcDesigner"), "pattern": "*",
     "inner": "PlcDesigner", "exe": "PlcDesigner.exe",
     "script_dir": _lenze_script_dir},
    {"prefix": "Delta ",
     "under": ("Delta Industrial Automation", "DIAStudio"),
     "pattern": "DIADesigner-AX*",
     "inner": "CODESYS", "exe": "DIADesigner-AX.exe",
     "script_dir": _delta_script_dir},
)


def _no_install(message, matches=()):
    """The one exception the CLI catches, with the candidates under it.

    Exit 4, because "no usable IDE for this project" is what 4 means and the
    reader's next move is the same as for a project somebody else has open:
    look at what is actually installed (SPEC 4.3). This used to be an
    exception of its own with no code on it, and cdsint/cli.py caught only
    Failure -- so a wrong --install printed a traceback and exited 1.
    """
    return Failure(message, EXIT_HEADLESS,
                   ["%-34s %s" % (i["name"], i["exe"]) for i in matches])


def find():
    """Every IDE installed on this machine, sorted by name.

    Reads the environment on every call so a test can point the roots at a
    tree it built.
    """
    layers = run_as_admin_layers()
    found = [_describe(directory, vendor, layers)
             for vendor, directory in _candidates()]
    return sorted([install for install in found if install is not None],
                  key=lambda install: install["name"])


def _candidates():
    """(vendor, directory) for every directory that might hold an install.

    Might, not does: the directory name is not proof, and _describe is where
    the executable settles it.
    """
    for vendor in VENDORS:
        for variable in ROOTS:
            base = os.environ.get(variable)
            if base:
                root = os.path.join(base, *vendor["under"])
                for name in _names_in(root):
                    if fnmatch.fnmatch(name, vendor["pattern"]):
                        yield vendor, os.path.join(root, name)


def _names_in(root):
    """The directory names directly under root, sorted. Nothing if it is not there."""
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [name for name in names if os.path.isdir(os.path.join(root, name))]


def resolve(installs, wanted):
    """The one install the caller meant, by case-insensitive name fragment.

    Never picks for the caller when several match: this machine has seven,
    and a wrong guess drives a whole run against an IDE that cannot open the
    project (SPEC 6.4).
    """
    if not wanted:
        raise _no_install("say which IDE with --install; `cdsint installs` "
                          "lists them", installs)
    matches = [i for i in installs if wanted.lower() in i["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise _no_install("no IDE matches --install %r" % (wanted,), installs)
    raise _no_install("several IDEs match --install %r; be more specific"
                      % (wanted,), matches)


def profile_of(install, wanted=None):
    """The --profile name to launch this install with.

    Without --profile the IDE exits immediately under --noUI, and the name it
    wants is "CODESYS V3.5 SP21 Patch 4", not the install directory. The file
    name in Profiles\\ is that name, which is why it is read rather than
    composed.
    """
    if wanted:
        return wanted
    profiles = install["profiles"]
    if len(profiles) == 1:
        return profiles[0]
    if not profiles:
        raise _no_install("%s has no profile in %s; pass --profile"
                          % (install["name"], install["exe"]))
    raise _no_install("%s has %d profiles (%s); pass --profile"
                      % (install["name"], len(profiles), ", ".join(profiles)))


def warn_if_elevated(install):
    """Say who asked for elevation before the launch fails without saying.

    Windows refuses to start a RUNASADMIN executable from an ordinary shell
    with a message that names neither the flag nor who set it, so the fact
    this module already read out of the registry is worth spending a line on
    up front.
    """
    if not install["run_as_admin"]:
        return
    print("warning: %s is marked RUNASADMIN in %s, so this launch will fail "
          "unless this shell is elevated"
          % (install["exe"], install["run_as_admin"]), file=sys.stderr)


def run_as_admin_layers():
    """exe path (lower case) -> the registry key that forces elevation."""
    try:
        import winreg
    except ImportError:
        return {}          # not Windows: nothing to read, nothing to warn about
    found = {}
    for hive_name, path in LAYER_KEYS:
        for name, value in _values_under(winreg, hive_name, path):
            if "RUNASADMIN" in str(value).upper():
                found[name.lower()] = hive_name + "\\" + path
    return found


def _values_under(winreg, hive_name, path):
    """(name, value) for one registry key, or nothing when it is not there."""
    hive = (winreg.HKEY_LOCAL_MACHINE if hive_name == "HKLM"
            else winreg.HKEY_CURRENT_USER)
    try:
        key = winreg.OpenKey(hive, path)
    except OSError:
        return []
    try:
        return [winreg.EnumValue(key, index)[:2]
                for index in range(winreg.QueryInfoKey(key)[1])]
    finally:
        key.Close()


def _describe(directory, vendor, layers):
    """One install, or None when the executable is not there."""
    common = os.path.join(directory, vendor["inner"], "Common")
    exe = os.path.join(common, vendor["exe"])
    if not os.path.isfile(exe):
        return None
    script_dir = vendor["script_dir"](directory)
    return {
        "name": vendor["prefix"] + os.path.basename(directory),
        "exe": exe,
        "profiles": _profiles(os.path.join(directory, vendor["inner"],
                                           "Profiles")),
        "script_dir": script_dir,
        "script_dir_needs_admin": _under_program_files(script_dir),
        "run_as_admin": layers.get(exe.lower()),
    }


def _profiles(directory):
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    return [n[:-len(PROFILE_SUFFIX)] for n in names
            if n.endswith(PROFILE_SUFFIX)]


def _under_program_files(path):
    """Writing here needs an elevated shell.

    Program Files is the one location no ordinary account may write to, so
    only Delta's ScriptDir earns this. ProgramData looks similar and is not:
    its default rules let any user create things, and the Lenze installer
    leaves its ScriptDir Full Control for Everyone (measured on this machine,
    2026-09-06). Marking it would send people to an elevated shell they do
    not need, which is what irm/setup.ps1's own copy of this table did.
    """
    lowered = os.path.normcase(path)
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base and lowered.startswith(os.path.normcase(base) + os.sep):
            return True
    return False

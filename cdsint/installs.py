# -*- coding: utf-8 -*-
"""Which CODESYS-family IDEs are on this machine, and how to start one.

The headless form needs three things about an install before it can launch
it: where the executable is, what its profile is called, and whether starting
it needs an elevated shell. None of the three is guessable from the install
path, and getting the profile name wrong means the IDE exits without a word
(SPEC 6.4).

CPython only: the CLI side never runs inside the IDE.
"""
from __future__ import print_function

import os

# What each vendor's tree looks like. Only the executable proves an install:
# these vendors put shared targets, gateways and an unversioned stub
# directory beside the real ones, and a scan by directory name reports every
# one of those as an IDE of its own (irm/setup.ps1 hit the same thing).
#
#   prefix    what to call it, in front of the directory name
#   roots     the environment variables whose directories hold the installs
#   under     a path under each root, or "" when the installs sit right there
#   pattern   the directory name shape, matched with fnmatch
#   inner     the subdirectory holding Common\ and Profiles\
#   exe       the executable inside Common\
VENDORS = (
    {"prefix": "", "roots": ("ProgramFiles", "ProgramFiles(x86)"),
     "under": "", "pattern": "CODESYS *",
     "inner": "CODESYS", "exe": "CODESYS.exe"},
    {"prefix": "Lenze PLC Designer ",
     "roots": ("ProgramFiles", "ProgramFiles(x86)"),
     "under": r"Lenze\PlcDesigner", "pattern": "*",
     "inner": "PlcDesigner", "exe": "PlcDesigner.exe"},
    {"prefix": "Delta ", "roots": ("ProgramFiles", "ProgramFiles(x86)"),
     "under": r"Delta Industrial Automation\DIAStudio",
     "pattern": "DIADesigner-AX*",
     "inner": "CODESYS", "exe": "DIADesigner-AX.exe"},
)

PROFILE_SUFFIX = ".profile.xml"

# Where the registry records "this exe always runs elevated". A manifest that
# says asInvoker is not the last word: this flag overrides it, and the launch
# failure it causes says only "requires elevation", never who asked for it.
LAYER_KEYS = (
    ("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"),
    ("HKCU", r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"),
)


class InstallError(Exception):
    """No install matched, or more than one did. Carries the candidates."""

    def __init__(self, message, matches=None):
        Exception.__init__(self, message)
        self.matches = matches or []


def find():
    """Every IDE installed on this machine, sorted by name.

    Reads the environment on every call so a test can point the roots at a
    tree it built.
    """
    layers = run_as_admin_layers()
    found = []
    for vendor in VENDORS:
        for root in _roots(vendor):
            for directory in _directories(root, vendor["pattern"]):
                install = _describe(directory, vendor, layers)
                if install is not None:
                    found.append(install)
    found.sort(key=lambda i: i["name"])
    return found


def resolve(installs, wanted):
    """The one install the caller meant, by case-insensitive name fragment.

    Never picks for the caller when several match: this machine has seven,
    and a wrong guess drives a whole run against an IDE that cannot open the
    project (SPEC 6.4).
    """
    if not wanted:
        raise InstallError("say which IDE with --install; `cdsint installs` "
                           "lists them", installs)
    matches = [i for i in installs if wanted.lower() in i["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise InstallError("no IDE matches --install %r" % (wanted,), installs)
    raise InstallError("several IDEs match --install %r; be more specific"
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
        raise InstallError("%s has no profile in %s; pass --profile"
                           % (install["name"], install["exe"]))
    raise InstallError("%s has %d profiles (%s); pass --profile"
                       % (install["name"], len(profiles), ", ".join(profiles)))


def run_as_admin_layers():
    """exe path (lower case) -> the registry key that forces elevation."""
    try:
        import winreg
    except ImportError:
        return {}          # not Windows: nothing to read, nothing to warn about
    found = {}
    for hive_name, path in LAYER_KEYS:
        hive = getattr(winreg, "HKEY_LOCAL_MACHINE" if hive_name == "HKLM"
                       else "HKEY_CURRENT_USER")
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            for index in range(winreg.QueryInfoKey(key)[1]):
                name, value, _kind = winreg.EnumValue(key, index)
                if "RUNASADMIN" in str(value).upper():
                    found[name.lower()] = hive_name + "\\" + path
        finally:
            key.Close()
    return found


def _roots(vendor):
    for variable in vendor["roots"]:
        base = os.environ.get(variable)
        if not base:
            continue
        root = os.path.join(base, vendor["under"]) if vendor["under"] else base
        if os.path.isdir(root):
            yield root


def _directories(root, pattern):
    import fnmatch
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return
    for name in names:
        path = os.path.join(root, name)
        if os.path.isdir(path) and fnmatch.fnmatch(name, pattern):
            yield path


def _describe(directory, vendor, layers):
    """One install, or None when the executable is not there."""
    common = os.path.join(directory, vendor["inner"], "Common")
    exe = os.path.join(common, vendor["exe"])
    if not os.path.isfile(exe):
        return None
    script_dir = _script_dir(directory, vendor)
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


def _script_dir(directory, vendor):
    """The directory this IDE scans for menu scripts (SPEC 5.3).

    Not derivable from the install path, which is the whole reason the table
    is written out: three vendors, four answers, and the usual reason nothing
    appears in the Scripts menu is having picked the wrong one.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    if vendor["exe"] == "CODESYS.exe":
        return os.path.join(local, "CODESYS", "ScriptDir")
    if vendor["exe"] == "DIADesigner-AX.exe":
        # Delta keeps it inside the install, so under Program Files.
        return os.path.join(directory, "CODESYS", "ScriptDir")
    if os.path.basename(directory).startswith("4."):
        return os.path.join(local, "PLCDesigner", "ScriptDir")
    return os.path.join(os.environ.get("ProgramData", ""), "PLCDesigner",
                        "ScriptDir")


def _under_program_files(path):
    """Writing here needs an elevated shell.

    Program Files is the one location no ordinary account may write to.
    ProgramData looks similar and is not: its default rules let any user
    create things, and the Lenze installer leaves its ScriptDir writable by
    everyone. Marking it would send people to an elevated shell they do not
    need.
    """
    lowered = os.path.normcase(path)
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base and lowered.startswith(os.path.normcase(base) + os.sep):
            return True
    return False

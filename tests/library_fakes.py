# -*- coding: utf-8 -*-
"""A Library Manager and its references, as the script API shows them.

Behaviour copied from the measurements (docs/library-manager-research.md):
ScriptEngine 4.2.0.0 accepts an uninstalled library and only reading
`managed_library` fails; 4.0.0.0 refuses it in add_library (`strict`).
"""
from engine.codesys_constants import TYPE_GUIDS

# Display name -> (title, default namespace), for what "installed" means
# here. A library that names no default namespace reports None and uses its
# title (measured on 3.5.21.40: Util and ISysTypes2 do, CAA Memory has MEM).
INSTALLED = {
    "Util, 3.5.19.0 (System)": ("Util", None),
    "CAA Memory, * (CAA Technical Workgroup)": ("CAA Memory", "MEM"),
    "ISysTypes2, 3.5.0.0 (System)": ("ISysTypes2", None),
}


class Managed(object):
    def __init__(self, title, namespace):
        self.title = title
        self.displayname = title
        self.default_namespace = namespace


class Ref(object):
    """A plain reference. Like the real IScriptLibraryReference it has none
    of the placeholder members: reading default_resolution off one raises
    (measured on 3.5.21.40)."""

    is_placeholder = False

    def __init__(self, name, system=False, namespace=None):
        self.name = name
        self.system_library = system
        self.qualified_only = True
        self.optional = False
        self.hide_when_referenced_as_depencency = False
        self.publish_symbols_in_container = False
        known = INSTALLED.get(name)
        self.namespace = namespace or (known and (known[1] or known[0])) or name
        self._managed = Managed(*known) if known else None

    @property
    def managed_library(self):
        # Measured on 3.5.21.40: for a library that is not installed the
        # property itself answers, and reading anything off it raises.
        return self._managed if self._managed is not None else Unresolved()


class Unresolved(object):
    """What managed_library hands back for a library that is not there."""

    def __getattr__(self, name):
        raise Exception("Object reference not set to an instance of an "
                        "object.")


class Placeholder(object):
    """A placeholder reference (IScriptPlaceholderReference)."""

    is_placeholder = True

    def __init__(self, name, default, info="", system=False, redirect=None):
        self.name = "#" + name
        self.placeholder_name = name
        self.system_library = system
        self.default_resolution = default
        self.resolution_info = info
        self._redirect = redirect
        self._effective = None       # set by a test to resolve elsewhere
        self.qualified_only = False
        self.optional = False
        self.hide_when_referenced_as_depencency = False
        self.publish_symbols_in_container = False
        self.namespace = name

    @property
    def is_redirected(self):
        return self._redirect is not None

    @property
    def effective_resolution(self):
        return self._effective or self._redirect or self.default_resolution

    def get_redirection(self):
        return self._redirect

    def set_redirection(self, fixed):
        self._redirect = fixed or None


class Libman(object):
    """The Library Manager object: references plus the three changers."""

    def __init__(self, refs, strict=False):
        self.references = list(refs)
        self.strict = strict
        self.type = TYPE_GUIDS["library_manager"]
        self.parent = None
        self.guid = "guid-Library Manager"

    def get_name(self):
        return "Library Manager"

    def get_children(self, recursive=False):
        return []

    def add_library(self, name):
        if self.strict and name not in INSTALLED:
            raise Exception("The library '%s' has not been installed to the "
                            "system." % name)
        self.references.append(Ref(name))

    def add_placeholder(self, name, default):
        self.references.append(Placeholder(
            name, default, info="Resolved by placeholder redirection"))

    def remove_library(self, name):
        for ref in self.references:
            if ref.name == name:
                self.references.remove(ref)
                return
        raise KeyError("library '%s' was not found." % name)


def a_project_libman(strict=False):
    """The shape of the CODESYS sample project's list (research 2)."""
    return Libman([
        Placeholder("SM3_Basic", "SM3_Basic, 4.20.0.0 (CODESYS)", system=True,
                    info="Resolved by SoftMotion profile 4.20.1.0"),
        Placeholder("SysMem", "SysMem, * (System)", info="Resolved by device"),
        Placeholder("Standard", "Standard, * (System)",
                    info="Resolved by placeholder redirection",
                    redirect="Standard, 3.5.18.0 (System)"),
        Ref("Util, 3.5.19.0 (System)"),
    ], strict=strict)

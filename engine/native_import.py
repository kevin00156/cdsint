# -*- coding: utf-8 -*-
"""Native XML into the IDE, with the "overwrite?" question already answered.

`import_native(path)` with no handler asks PromptImportConflict ("these
objects already exist, pick the ones to overwrite") for every object the
project already has. That prompt is a multiple choice, so neither
system.prompt_answers nor --answer can answer it, and headless it failed
every edited native object — a trace, a visualisation, a text list — by name
(docs/trace-research.md 6.3). The overload that takes a handler has been in
every ScriptEngine on the compatibility matrix (SPEC 7), 4.0.0.0 included,
so there is one call and no fallback.

The answer is always replace: an import is "disk wins" (SPEC 4.2) and had to
get past -y to be here, so overwriting the IDE's copy is the whole request.
"""
from __future__ import print_function

from engine.strings import safe_str

SCRIPT_ENGINE_ASSEMBLY = "ScriptEngine3"
HANDLER_TYPE = "_3S.CoDeSys.ScriptEngine.BasicFunctionality.INativeImportHandler"
RESOLVE_TYPE = "_3S.CoDeSys.ScriptEngine.BasicFunctionality.NativeImportResolve"


def import_native(target, path):
    """Import `path` into `target` (a project or a container), replacing.

    Raises when the IDE says anything went wrong, naming what it said: the
    callers record the objects of a failed import by name (SPEC D13), and a
    result of "errors" that nobody reads is a silent skip.
    """
    handler = replace_handler()
    result = target.import_native(path, None, handler)
    if handler.failures or safe_str(result) == "errors":
        raise RuntimeError("native import of %s: %s" % (
            path, "; ".join(handler.failures) or "the IDE reported errors"))
    return result


def replace_handler():
    """An INativeImportHandler that replaces on conflict and keeps the failures.

    Built on each call rather than at import time: the interface only exists
    inside the IDE, and this module is imported by CPython tests too.
    """
    import clr
    from System import AppDomain

    assembly = _loaded_assembly(AppDomain.CurrentDomain.GetAssemblies())
    interface = clr.GetPythonType(assembly.GetType(HANDLER_TYPE))
    resolve = clr.GetPythonType(assembly.GetType(RESOLVE_TYPE))

    class ReplaceOnConflict(interface):
        def __init__(self):
            self.failures = []

        def conflict(self, name, existing, guid):
            return resolve.replace

        def progress(self, name, obj, exc):
            if exc is not None:
                self.failures.append("%s: %s" % (safe_str(name), safe_str(exc)))

        def skipped(self, items):
            for item in items:
                self.failures.append("%s: skipped" % safe_str(item))

    return ReplaceOnConflict()


def _loaded_assembly(assemblies):
    """The ScriptEngine assembly the IDE already loaded; it is never loaded here."""
    for assembly in assemblies:
        if assembly.GetName().Name == SCRIPT_ENGINE_ASSEMBLY:
            return assembly
    raise RuntimeError("%s is not loaded in this IDE, so there is no native "
                       "import handler to give it" % SCRIPT_ENGINE_ASSEMBLY)

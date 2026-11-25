# -*- coding: utf-8 -*-
"""Every non-public CODESYS member cdsint reaches for, and nothing else.

The script API leaves out a few things cdsint cannot do without, and the only
way to them is reflection over members an IDE release may rename or drop. They
all live here, so such a release breaks one file, and each is looked up before
use so a missing one refuses by name instead of failing somewhere downstream.
SPEC section 7 records which IDEs each was checked on.

`clr` is imported inside each function, so this module loads under CPython
too. Inside an IDE `clr` is always there; outside one (the tests) there is
no .NET object to look into, which in_script_run treats like a missing
field and setter_for leaves to the tests, which replace it.
"""
from __future__ import print_function

import sys

MEMBER = "PerformWithWriteableCopy"

# ScriptOnline's private fields (ScriptDriverOnline.plugin, 4.2.0.0):
# the executor that runs scripts, and the stack of script runs it is in.
EXECUTOR = "_executor"
EXECUTION_STACK = "_executionStack"

# The trace plug-in's (ScriptDriverTraceObject.plugin, 4.2.0.0): the static
# that wraps an existing trace object, the editor's real editor behind its
# script object, and that editor's loader (docs/trace-research.md 15.6-7).
SCRIPT_TRACE_TYPE = "ScriptTraceObject"
CREATE_SCRIPT_TRACE = "CreateScriptTraceObject"
EDITOR_VIEW = "_view"
LOAD_TRACE = "LoadTrace"

# The EtherCAT plug-in's reader and writer of a slave's PDOs, which rebuilds the
# channel list as its Process Data page does, and the two fields of the PDO
# items it hands out (docs/ethercat-research.md 13).
PDO_PLUGIN = "deviceeditorethercat.plugin"
PDO_TYPE = "_3S.CoDeSys.Ethercat.LoadSavePDOData"
LOAD_PDOS = "LoadDataFromConfig"
SAVE_PDO = "SaveMappingToConfig"
PDO_ID = "lParameterId"
PDO_SM = "iSm"

# Where in_script_run parks the call for the nested run to pick up. One name
# is enough: inside the nested run the stack is not empty, so a call() that
# itself goes through in_script_run calls straight through.
_PARKED = "_cdsint_in_script_run"


def setter_for(api):
    """set_buffers(ring, per_variable) for this trace, or None.

    The script API exposes neither the controller's ring (`uiBufferEntries`)
    nor the IDE's per-variable buffer, and with the default ring of 100 a task
    faster than about 4 ms loses most of its samples (docs/trace-research.md
    2.1). The trace plug-in's script object has a private
    `PerformWithWriteableCopy` that hands a callback the object holding both
    (SPEC 6.8 "The buffers").

    None when this IDE's trace plug-in has no such member, which the caller
    refuses on: recording with the default ring would silently lose samples,
    and that is the failure the command exists to prevent.
    """
    import clr
    from System import Array
    from System.Reflection import BindingFlags
    method = clr.GetClrType(type(api)).GetMethod(
        MEMBER, BindingFlags.NonPublic | BindingFlags.Instance)
    if method is None:
        return None
    # The parameter is an Action<ITraceObject7>; wrapping the Python function
    # in that delegate type is what lets Invoke accept it.
    action = clr.GetPythonType(method.GetParameters()[0].ParameterType)

    def set_buffers(ring, per_variable):
        def change(writable):
            # Without the override flag the runtime computes its own ring
            # size and ignores uiBufferEntries (research 2.2).
            writable.TraceSettings.bOverrideRTSBufferSize = True
            writable.Record.uiBufferEntries = ring
            writable.TraceSettings.uiBufferPerVariable = per_variable
        method.Invoke(api, Array[object]([action(change)]))
    return set_buffers


def in_script_run(online_api, call):
    """call(), made to happen inside a script run as far as `online` can tell.

    ScriptOnline.create_online_application peeks at a stack its executor
    pushes when a script starts and pops when it ends, to know which run the
    new object belongs to. The watcher calls from a timer tick, after the
    script that armed it has returned, so the stack is empty and every call
    raises "Stack empty" (docs/trace-research.md 15). Asking the executor to
    run a one-line script around the call pushes it the ordinary way.

    Nothing to do when a script is already running (the `--project` form,
    the menu), and nothing that can be done when either private field is
    missing: then call() runs as it is and the caller sees whatever it
    raises. call()'s own exception is re-raised here, never left to the
    executor, which would report it as a failed script.
    """
    executor = _field(online_api, EXECUTOR)
    stack = _field(online_api, EXECUTION_STACK)
    if executor is None or stack is None or stack.Count:
        return call()
    box = {}

    def parked():
        try:
            box["value"] = call()
        except Exception as exc:
            box["error"] = exc

    setattr(sys, _PARKED, parked)
    try:
        executor.ExecuteSource("import sys\nsys.%s()\n" % _PARKED)
    finally:
        delattr(sys, _PARKED)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def script_trace(trace_global, project_handle, guid_text):
    """The ScriptTraceObject for an existing trace object, or None.

    `trace` only creates; an object found by name is a plain script object
    without the trace members. CreateScriptTraceObject wraps one. The GUID
    goes in as a System.Guid built from its text: that is the form the
    bench call worked with (docs/trace-research.md 15.7).
    """
    try:
        import clr
        from System import Array, Guid, Int32
        from System.Reflection import BindingFlags
    except ImportError:
        return None
    create = _creator(clr.GetClrType(type(trace_global)).Assembly,
                      BindingFlags.NonPublic | BindingFlags.Static)
    if create is None:
        return None
    args = Array.CreateInstance(object, 2)
    args[0] = Int32(project_handle)
    args[1] = Guid(guid_text)
    return create.Invoke(None, args)


# The member found in each assembly, for this run: the IDE side loads the
# engine afresh for every command (cds/ide/entries.py), so this lives as long
# as one trace list, which reaches one trace after another.
_CREATORS = {}


def _creator(assembly, flags):
    """CreateScriptTraceObject in `assembly`, or None; scanned for once."""
    if assembly not in _CREATORS:
        found = [kind for kind in assembly.GetTypes()
                 if kind.Name == SCRIPT_TRACE_TYPE]
        _CREATORS[assembly] = (found[0].GetMethod(CREATE_SCRIPT_TRACE, flags)
                               if found else None)
    return _CREATORS[assembly]


def loader_for(editor):
    """load(path) -> the editor's error text or None, or None if there is none.

    The script API has no load; the editor's script object keeps the real
    editor in `_view`, whose public LoadTrace is what the Trace menu's
    "Load Trace..." calls. Loading replaces the trace object's definition
    with the file's (docs/trace-research.md 15.6), which is why trace show
    loads only into a trace the caller names and confirms.
    """
    view = _field(editor, EDITOR_VIEW)
    if view is None:
        return None
    from System import Array
    method = view.GetType().GetMethod(LOAD_TRACE)
    if method is None:
        return None

    def load(path):
        args = Array[object]([path, None])
        if method.Invoke(view, args):
            return None
        return args[1] or "LoadTrace returned false and said nothing"
    return load


def pdo_saver_for(connector):
    """save({PDO parameter id: SM number}) for this connector, or None.

    Writing a PDO's `Sm` through the script API leaves the slave's channel
    list as it was (GitHub #16). The plug-in's own save rebuilds it, and
    computes the sync managers' lengths and the channel counts. One save
    covers one direction, so each PDO given is saved. Everything happens on
    one writable copy, which the IDE drops when the callback raises: a save
    that fails changes nothing.

    None when this IDE's EtherCAT plug-in lacks any of it, which the caller
    refuses on.
    """
    try:
        import clr
    except ImportError:
        return None
    from System import Array, Type
    kind = _pdo_type()
    load = _only_method(kind, LOAD_PDOS, 2)
    save = _only_method(kind, SAVE_PDO, 3)
    copying = _only_method(clr.GetClrType(type(connector)), MEMBER, 1)
    if None in (load, save, copying) or not copying.IsGenericMethodDefinition:
        return None
    item, copy_type = [p.ParameterType for p in save.GetParameters()][1:]
    fields = [item.GetField(name, _everything()) for name in (PDO_ID, PDO_SM)]
    if None in fields:
        return None
    from System import Action
    action = Action[clr.GetPythonType(copy_type)]
    invoke = copying.MakeGenericMethod(Array[Type]([copy_type])).Invoke

    def run(callback):
        invoke(connector, Array[object]([action(callback)]))
    return lambda sms: _aborting(
        run, lambda copy: _save_pdos(load, save, fields, sms, copy))


def _save_pdos(load, save, fields, sms, copy):
    """Put each PDO in `sms` on its sync manager, on one writable connector."""
    from System import Activator, Array, Int32
    from System.Collections import ArrayList
    id_of, sm_of = fields
    pdos, plugin = ArrayList(), Activator.CreateInstance(load.DeclaringType)
    load.Invoke(plugin, Array[object]([pdos, copy]))
    chosen = [p for p in pdos if int(id_of.GetValue(p)) in sms]
    if len(chosen) != len(sms):
        raise RuntimeError("the EtherCAT plug-in lists %d of the %d PDOs to "
                           "assign" % (len(chosen), len(sms)))
    for pdo in chosen:
        sm_of.SetValue(pdo, Int32(sms[int(id_of.GetValue(pdo))]))
    for pdo in chosen:
        save.Invoke(plugin, Array[object]([pdos, pdo, copy]))


def _aborting(run, body):
    """run(callback), raising what `body` raised instead of the wrapper
    reflection puts around it, which says only that the target threw."""
    raised = []

    def callback(copy):
        try:
            body(copy)
        except Exception as exc:
            raised.append(exc)
            raise

    try:
        run(callback)
    except Exception as exc:
        raise RuntimeError(_innermost(raised[0] if raised else exc))


def _innermost(exc):
    """The text of the .NET exception at the bottom, or of `exc` itself."""
    inner = getattr(exc, "clsException", None)
    while inner is not None and inner.InnerException is not None:
        inner = inner.InnerException
    return str(exc) if inner is None else inner.Message


def _pdo_type():
    """The plug-in's PDO class, or None. Two loaded versions are no answer:
    nothing says which of them this project's slaves belong to."""
    from System import AppDomain
    found = [a.GetType(PDO_TYPE) for a in AppDomain.CurrentDomain.GetAssemblies()
             if a.GetName().Name.lower() == PDO_PLUGIN]
    return found[0] if len(found) == 1 else None


def _everything():
    from System.Reflection import BindingFlags
    return (BindingFlags.Instance | BindingFlags.Public
            | BindingFlags.NonPublic)


def _only_method(kind, name, count):
    """The one method of that name and parameter count, or None."""
    if kind is None:
        return None
    found = [m for m in kind.GetMethods(_everything())
             if m.Name == name and len(m.GetParameters()) == count]
    return found[0] if len(found) == 1 else None


def _field(obj, name):
    """The value of `obj`'s private instance field `name`, or None."""
    try:
        import clr
    except ImportError:
        return None
    from System.Reflection import BindingFlags
    field = clr.GetClrType(type(obj)).GetField(
        name, BindingFlags.NonPublic | BindingFlags.Instance)
    return None if field is None else field.GetValue(obj)

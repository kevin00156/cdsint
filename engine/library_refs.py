# -*- coding: utf-8 -*-
"""A Library Manager's references, read and changed through the script API.

SPEC 6.9. The native XML is not the way in: importing it merges and never
removes (docs/library-manager-research.md 4.2). Every change here is read
back, because the API reports success for things that did not happen: on
ScriptEngine 4.2.0.0 add_library accepts a library that is not installed and
the build never mentions it (research 3.2), and a placeholder can resolve to
another version than the one it was given (research 3.1).

Every problem is a string that starts "<kind> <name>:", so a reader can find
the line of the file it is about.
"""
from __future__ import print_function

from cds.core import library_list
from engine.strings import safe_str

# What resolution_info says when a device, a profile or a licence put the
# placeholder there (research 2). Those references are the devices'.
SYSTEM_MARKS = ("by device", "by subdevice", "SoftMotion profile",
                "licensing", "Essentials")
# The file's option word -> the reference's attribute (the API's own
# spelling of "dependency" included).
FLAG_ATTRS = (("qualified_only", "qualified_only"),
              ("optional", "optional"),
              ("hide_when_referenced", "hide_when_referenced_as_depencency"),
              ("publish_symbols", "publish_symbols_in_container"))


def _text(value):
    return None if value is None else safe_str(value)


def is_system(ref):
    """Put there by a device, a profile or a licence, not by the user."""
    if ref.system_library:
        return True
    if not ref.is_placeholder:
        return False
    info = _text(ref.resolution_info) or ""
    return any(mark in info for mark in SYSTEM_MARKS)


def _default_namespace(ref):
    """The namespace the library gets when nobody sets one: its declared
    default, or its title when it declares none (default_namespace is None
    for Util and ISysTypes2 on 3.5.21.40)."""
    try:
        managed = ref.managed_library
        return _text(managed.default_namespace) or _text(managed.title)
    except Exception:
        # Not installed, or an IDE that will not say: the namespace is then
        # written out rather than assumed to be the default.
        return None


def _options(ref):
    options = dict((word, True) for word, attr in FLAG_ATTRS
                   if getattr(ref, attr))
    namespace = _text(ref.namespace)
    if namespace and namespace != _default_namespace(ref):
        options["namespace"] = namespace
    return options


def _placeholder_entries(ref, entries, system):
    name = _text(ref.placeholder_name)
    if ref.is_redirected:
        entries.append(library_list.entry(
            "redirect", name, _text(ref.get_redirection())))
    if is_system(ref):
        system.append((name, _text(ref.default_resolution),
                       _text(ref.resolution_info) or ""))
    else:
        entries.append(library_list.entry(
            "placeholder", name, _text(ref.default_resolution)))


def read(libman):
    """(entries, system): the user's references, and the devices' as
    (name, value, info) for the file's comments."""
    entries, system = [], []
    for ref in libman.references:
        if ref.is_placeholder:
            _placeholder_entries(ref, entries, system)
        elif is_system(ref):
            system.append((_text(ref.name), "", "system library"))
        else:
            entries.append(library_list.entry("library", _text(ref.name),
                                              options=_options(ref)))
    return entries, system


def render_ide(libman):
    """The file export writes for this Library Manager."""
    entries, system = read(libman)
    return library_list.render(entries, system)


def _same_name(a, b):
    return library_list.squeeze(a).lower() == library_list.squeeze(b).lower()


def _find(libman, e):
    wanted = e["name"] if e["kind"] == "library" else "#" + e["name"]
    for ref in libman.references:
        if _same_name(_text(ref.name), wanted):
            return ref
    return None


def _set_options(ref, options):
    for word, attr in FLAG_ATTRS:
        setattr(ref, attr, bool(options.get(word)))
    namespace = options.get("namespace") or _default_namespace(ref)
    if namespace:
        ref.namespace = namespace


def _remove(libman, e, problems):
    ref = _find(libman, e)
    if e["kind"] == "redirect":
        if ref is not None:
            ref.set_redirection(None)
        return
    try:
        libman.remove_library(_text(ref.name) if ref is not None
                              else e["name"])
    except Exception as exc:
        problems.append("%s %s: could not be removed: %s"
                        % (e["kind"], e["name"], safe_str(exc)))


def _add_library(libman, e, problems):
    """Add, then make sure it resolves; take back what does not."""
    before = set(_text(r.name) for r in libman.references)
    ref = None
    try:
        libman.add_library(e["name"])
        # The new reference is the one whose name was not there before: the
        # IDE may spell it differently from the line that asked for it. By
        # name, because each read of `references` can hand out new wrappers.
        ref = [r for r in libman.references
               if _text(r.name) not in before][0]
        # The property answers even for a library that is not installed;
        # only reading from it fails (measured on 3.5.21.40).
        ref.managed_library.displayname
    except Exception:
        if ref is not None:
            libman.remove_library(_text(ref.name))
        problems.append("library %s: not installed on this machine"
                        % e["name"])
        return
    _set_options(ref, e["options"])


def _add(libman, e, problems):
    if e["kind"] == "library":
        _add_library(libman, e, problems)
    elif e["kind"] == "placeholder":
        libman.add_placeholder(e["name"], e["value"])
    else:
        _change(libman, e, problems)


def _change(libman, e, problems):
    ref = _find(libman, e)
    if ref is None:
        problems.append("%s %s: there is no placeholder of that name"
                        % (e["kind"], e["name"]))
    elif e["kind"] == "library":
        _set_options(ref, e["options"])
    elif e["kind"] == "placeholder":
        ref.default_resolution = e["value"]
    else:
        ref.set_redirection(e["value"])


def _resolution_problems(libman):
    """The user's placeholders with a concrete default that resolved to
    something else. A device's placeholders do that by design (research 5.1)."""
    found = []
    for ref in libman.references:
        # A plain reference has no placeholder members at all, so the kind
        # is asked before any of them is read.
        if not ref.is_placeholder or ref.is_redirected or is_system(ref):
            continue
        default = _text(ref.default_resolution)
        if not default or "*" in default:
            continue
        effective = _text(ref.effective_resolution)
        if effective != default:
            found.append("placeholder %s: resolved to %s, not %s"
                         % (_text(ref.placeholder_name), effective, default))
    return found


def _guarded(step, libman, e, problems):
    """One entry's change. An IDE call that raises is that entry's problem,
    by name, and the other entries still get their turn."""
    try:
        step(libman, e, problems)
    except Exception as exc:
        problems.append("%s %s: %s" % (e["kind"], e["name"], safe_str(exc)))


def apply(libman, wanted):
    """Make the user's references what `wanted` says. Problems, by name.

    Redirections come off before placeholders, so removing a placeholder and
    its redirection does not look for the one after the other is gone. What
    was already reported is not reported again by the read-back.
    """
    have, _ = read(libman)
    d = library_list.diff(have, wanted)
    problems = []
    for e in sorted(d["remove"], key=lambda e: e["kind"] != "redirect"):
        _guarded(_remove, libman, e, problems)
    for e in sorted(d["add"], key=library_list.key):
        _guarded(_add, libman, e, problems)
    for _, new in d["change"]:
        _guarded(_change, libman, new, problems)
    reported = set(p.split(":")[0] for p in problems)
    after, _ = read(libman)
    problems.extend(p for p in library_list.mismatches(after, wanted)
                    if p.split(":")[0] not in reported)
    problems.extend(_resolution_problems(libman))
    return problems

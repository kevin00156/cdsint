# -*- coding: utf-8 -*-
"""The three layering rules of SPEC D12, read off the parsed imports.

    cds/core   imports no CODESYS at all -- not clr, not the IDE globals,
               not engine, not cds.ide. That is what lets it be tested in
               full under CPython in CI.
    cds/ide    imports no engine module and nothing online. It is plumbing:
               protocol endpoints, timers, the stand-in UI, prompt answers,
               the status window, opening a project headlessly.
    engine     imports no cds.ide. The dependency runs one way -- cds/ide
               drives an entry body by name, never the reverse.

SPEC D12 called these "three rules you can check with grep", and grep is how
they were checked until now. Grep reads text, so `cds/ide/silent.py`'s
docstring about `from engine.codesys_ui import ...` is a hit, and a reader
who has been shown one false hit stops trusting the next real one. This
reads the imports instead.

The one real exception is silent.py loading engine.codesys_ui by string name
to swap two dialog functions for stand-ins and put them back. Registering
it here is the point: an exception a test knows about is one nobody has to
remember, and a second one cannot appear quietly.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The IDE globals are handed to a function, never imported; naming them here
# is what stops somebody deciding to import them one day.
CODESYS_GLOBALS = ("system", "projects", "online")

LAYERS = {
    os.path.join("cds", "core"):
        CODESYS_GLOBALS + ("clr", "System", "engine", "cds.ide"),
    os.path.join("cds", "ide"): ("online", "engine"),
    "engine": ("cds.ide",),
}

# file -> how many `__import__` calls it is allowed. SPEC D12's only
# recorded exception.
STRING_IMPORTS_ALLOWED = {"cds/ide/silent.py": 1}

# The dialog module, which no engine file may import as it loads. Every use
# of it in the engine is a `from engine.codesys_ui import ...` inside the
# function that asks, and that is what lets cds/ide/silent.py put stand-ins
# in the module and take them out again around one command. A module-level
# `from engine.codesys_ui import ask_yes_no` binds a second reference to
# whichever function was there at import time, and the undo cannot reach it:
# whether a body gets the stand-in then depends on two mechanisms staying in
# step -- the swap going in first, and forget_engine() re-importing every
# time -- instead of on one. It is zero today, and this is what keeps it
# there. `from engine import codesys_ui` is not the same thing and is fine:
# it binds the module, so the attribute is read when the dialog is asked.
UI_MODULE = "engine.codesys_ui"


def sources(folder):
    for where, _dirs, files in os.walk(os.path.join(REPO_ROOT, folder)):
        if "__pycache__" in where:
            continue
        for name in sorted(files):
            if name.endswith(".py"):
                full = os.path.join(where, name)
                yield os.path.relpath(full, REPO_ROOT).replace("\\", "/")


def parse(rel_path):
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=rel_path)


def module_level_imports(tree):
    """(line, dotted name) for the imports that run when the file loads.

    tree.body only. An import inside a function runs when that function is
    called, which is the whole of the difference this file cares about.
    """
    found = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def loads_the_dialogs(tree):
    """The lines where this file imports the dialog module as it loads."""
    return [line for line, module in module_level_imports(tree)
            if reaches(module, UI_MODULE)]


def imported_modules(tree):
    """(line, dotted name) for every module this file imports, at any depth."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def reaches(module, banned):
    """Is `module` the banned package, or something inside it?"""
    return module == banned or module.startswith(banned + ".")


def layered_sources():
    for folder, banned in sorted(LAYERS.items()):
        for rel_path in sources(folder):
            yield pytest.param(rel_path, banned, id=rel_path)


@pytest.mark.parametrize("rel_path,banned", list(layered_sources()))
def test_a_layer_imports_nothing_from_the_layer_above_it(rel_path, banned):
    offences = ["%s:%d imports %s" % (rel_path, line, module)
                for line, module in imported_modules(parse(rel_path))
                for name in banned if reaches(module, name)]
    assert not offences, "SPEC D12: " + "; ".join(offences)


@pytest.mark.parametrize("rel_path", sorted(
    rel for folder in LAYERS for rel in sources(folder)))
def test_only_the_registered_file_loads_a_module_by_name(rel_path):
    calls = sum(1 for node in ast.walk(parse(rel_path))
                if isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "__import__")
    assert calls == STRING_IMPORTS_ALLOWED.get(rel_path, 0), (
        rel_path + " loads a module by string name. SPEC D12 records one "
        "such exception (cds/ide/silent.py swapping the dialog functions "
        "for stand-ins); a second one needs a decision, not a habit.")


@pytest.mark.parametrize("rel_path", sorted(sources("engine")))
def test_no_engine_file_imports_the_dialogs_as_it_loads(rel_path):
    lines = loads_the_dialogs(parse(rel_path))
    assert not lines, (
        "%s imports %s at module level (line %s). Import it inside the "
        "function that asks, so cds/ide/silent.py's stand-in is the one that "
        "answers." % (rel_path, UI_MODULE, lines))


def test_that_rule_would_catch_one():
    # Zero for zero today, and a rule nothing has ever tripped is a rule
    # nobody knows still works. No engine file is touched: the checker is
    # handed the line it exists to object to.
    assert loads_the_dialogs(
        ast.parse("from engine.codesys_ui import ask_yes_no")) == [1]
    assert loads_the_dialogs(ast.parse("import engine.codesys_ui")) == [1]
    inside_the_function_that_asks = """
def ask():
    from engine.codesys_ui import ask_yes_no
"""
    assert loads_the_dialogs(ast.parse(inside_the_function_that_asks)) == []

# -*- coding: utf-8 -*-
"""The IDE side uses nothing IronPython 2.7 does not have (PRINCIPLES 8).

Every test in this suite runs under CPython 3, which is the one runtime the
IDE side is never short of anything on. `os.makedirs(p, exist_ok=True)` is a
TypeError in the IDE and a pass here; so are `FileNotFoundError`, zero-arg
`super()`, `shutil.which` and `import pathlib`. Each is found the first time
somebody runs that line inside CODESYS, which is the worst place to find it.

So this reads the code for them. It is a denylist, and a denylist is never
complete: it names what has been written into IDE-side code before or is the
first thing a CPython 3 author reaches for. The syntax half -- f-strings,
annotations and the rest -- is the cheap copy of the py27-grammar CI job,
which compiles every file with a real 2.7 parser; this copy runs on every
`pytest`, including on a machine with no container to hand.

A guarded use -- asked for by `getattr(os, "replace", None)`, say -- is a
string lookup and not seen, so it needs no entry. ALLOWED is for a use this
check does see and that is guarded some other way, keyed by file and by what
was flagged, with the reason.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IDE_SIDE = ("engine", os.path.join("cds", "ide"), os.path.join("cds", "core"),
            "stub")

ALLOWED = {}

KEYWORDS = ("exist_ok", "flush")
OPEN_KEYWORDS = ("encoding", "errors", "newline")

EXCEPTIONS = frozenset((
    "FileNotFoundError", "PermissionError", "FileExistsError", "TimeoutError",
    "ConnectionError", "ProcessLookupError", "BrokenPipeError",
    "IsADirectoryError", "NotADirectoryError", "InterruptedError",
    "ChildProcessError", "BlockingIOError", "RecursionError",
    "ModuleNotFoundError",
))

MODULE_ATTRIBUTES = frozenset((
    ("os", "replace"), ("time", "monotonic"), ("time", "perf_counter"),
    ("shutil", "which"), ("subprocess", "run"), ("math", "isclose"),
    ("functools", "lru_cache"),
))

# Methods on str, bytes and int that 2.7 does not have, whatever they are
# called on.
METHODS = frozenset(("isascii", "from_bytes", "to_bytes"))

MODULES = (
    "typing", "dataclasses", "pathlib", "enum", "concurrent", "asyncio",
    "secrets", "statistics", "urllib.request", "urllib.parse", "queue",
    "configparser", "builtins", "ctypes", "multiprocessing", "sqlite3", "ssl",
)

SYNTAX = {
    ast.JoinedStr: "f-string",
    ast.AnnAssign: "annotation",
    ast.Nonlocal: "nonlocal",
    ast.YieldFrom: "yield from",
    ast.Await: "await",
    ast.AsyncFunctionDef: "async def",
    ast.AsyncFor: "async for",
    ast.AsyncWith: "async with",
    ast.NamedExpr: "walrus",
}


def _call(node):
    found = ["%s=" % k.arg for k in node.keywords if k.arg in KEYWORDS]
    func = node.func
    if isinstance(func, ast.Name) and func.id == "open":
        found += ["open(%s=)" % k.arg for k in node.keywords
                  if k.arg in OPEN_KEYWORDS]
    if isinstance(func, ast.Name) and func.id == "super" and not node.args:
        found.append("super()")
    if (isinstance(func, ast.Attribute) and func.attr == "hex"
            and not node.args):
        found.append(".hex()")
    return found


def _name(node):
    return [node.id] if node.id in EXCEPTIONS else []


def _attribute(node):
    found = [".%s" % node.attr] if node.attr in METHODS else []
    owner = getattr(node.value, "id", None)
    if (owner, node.attr) in MODULE_ATTRIBUTES:
        found.append("%s.%s" % (owner, node.attr))
    return found


def _banned_module(name):
    return any(name == m or name.startswith(m + ".") for m in MODULES)


def _import(node):
    return ["import " + a.name for a in node.names if _banned_module(a.name)]


def _import_from(node):
    module = node.module or ""
    if _banned_module(module):
        return ["import " + module]
    return ["import %s.%s" % (module, a.name) for a in node.names
            if _banned_module("%s.%s" % (module, a.name))
            or (module, a.name) in MODULE_ATTRIBUTES]


def _arg(node):
    return ["annotation"] if node.annotation is not None else []


def _function(node):
    # A def or a lambda: only the def has a return annotation, both can have
    # keyword-only arguments.
    found = ["keyword-only argument"] if node.args.kwonlyargs else []
    if getattr(node, "returns", None) is not None:
        found.append("annotation")
    return found


def _raise(node):
    return ["raise from"] if node.cause is not None else []


CHECKS = {
    ast.Call: _call,
    ast.Name: _name,
    ast.Attribute: _attribute,
    ast.Import: _import,
    ast.ImportFrom: _import_from,
    ast.arg: _arg,
    ast.FunctionDef: _function,
    ast.Lambda: _function,
    ast.Raise: _raise,
}


def _call_argument_stars(tree):
    """`f(*args)` is 2.7; a star anywhere else is not."""
    return set(id(arg) for node in ast.walk(tree) if isinstance(node, ast.Call)
               for arg in node.args if isinstance(arg, ast.Starred))


def offences(path):
    """(line, what) for every py3-only construct this check knows of."""
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    allowed_stars = _call_argument_stars(tree)
    found = []
    for node in ast.walk(tree):
        whats = list(CHECKS.get(type(node), lambda n: [])(node))
        if type(node) in SYNTAX:
            whats.append(SYNTAX[type(node)])
        if isinstance(node, ast.Starred) and id(node) not in allowed_stars:
            whats.append("starred target")
        found += [(node.lineno, what) for what in whats]
    return sorted(set(found))


def repo_relative(path):
    return os.path.relpath(path, REPO_ROOT).replace("\\", "/")


def ide_side_sources():
    for folder in IDE_SIDE:
        for where, _dirs, files in os.walk(os.path.join(REPO_ROOT, folder)):
            if "__pycache__" in where:
                continue
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(where, name)


@pytest.mark.parametrize("path", sorted(ide_side_sources()),
                         ids=repo_relative)
def test_an_ide_side_file_uses_nothing_2_7_lacks(path):
    rel = repo_relative(path)
    found = ["%s:%d: %s" % (rel, line, what) for line, what in offences(path)
             if (rel, what) not in ALLOWED]
    assert not found, "IronPython 2.7 has none of these:\n" + "\n".join(found)


def test_every_allowance_names_a_file_that_is_there_and_says_why():
    for (rel, _what), reason in ALLOWED.items():
        assert os.path.isfile(os.path.join(REPO_ROOT, rel)), rel
        assert reason.strip(), rel


# One line of each kind the check claims to see. A category with no line here
# is a category nobody has shown can fail.
GUILTY = [
    (u"os.makedirs(p, exist_ok=True)", "exist_ok="),
    (u"print(x, flush=True)", "flush="),
    (u"open(p, encoding='utf-8')", "open(encoding=)"),
    (u"open(p, 'w', errors='replace')", "open(errors=)"),
    (u"open(p, 'w', newline='')", "open(newline=)"),
    (u"try:\n    f()\nexcept FileNotFoundError:\n    pass", "FileNotFoundError"),
    (u"raise ModuleNotFoundError()", "ModuleNotFoundError"),
    (u"os.replace(a, b)", "os.replace"),
    (u"t = time.monotonic()", "time.monotonic"),
    (u"t = time.perf_counter()", "time.perf_counter"),
    (u"shutil.which('x')", "shutil.which"),
    (u"subprocess.run(['x'])", "subprocess.run"),
    (u"math.isclose(a, b)", "math.isclose"),
    (u"@functools.lru_cache()\ndef f():\n    pass", "functools.lru_cache"),
    (u"from os import replace", "import os.replace"),
    (u"s.isascii()", ".isascii"),
    (u"int.from_bytes(b, 'big')", ".from_bytes"),
    (u"n.to_bytes(4, 'big')", ".to_bytes"),
    (u"b.hex()", ".hex()"),
    (u"class A(B):\n    def f(self):\n        super().f()", "super()"),
    (u"s = f'{x}'", "f-string"),
    (u"def f(x: int):\n    pass", "annotation"),
    (u"def f(x) -> int:\n    pass", "annotation"),
    (u"x: int = 1", "annotation"),
    (u"def f(*, x):\n    pass", "keyword-only argument"),
    (u"def f():\n    x = 1\n    def g():\n        nonlocal x", "nonlocal"),
    (u"def f():\n    yield from g()", "yield from"),
    (u"async def f():\n    await g()", "async def"),
    (u"async def f():\n    await g()", "await"),
    (u"if (n := 1):\n    pass", "walrus"),
    (u"a, *rest = xs", "starred target"),
    (u"raise X from Y", "raise from"),
    (u"import typing", "import typing"),
    (u"from pathlib import Path", "import pathlib"),
    (u"import urllib.request", "import urllib.request"),
    (u"from urllib import parse", "import urllib.parse"),
    (u"import concurrent.futures", "import concurrent.futures"),
]


@pytest.mark.parametrize("source, what", GUILTY, ids=[g[1] for g in GUILTY])
def test_the_check_can_actually_see_one(tmp_path, source, what):
    guilty = tmp_path / "guilty.py"
    guilty.write_text(source + u"\n", encoding="utf-8")
    assert what in [found for _line, found in offences(str(guilty))]


def test_what_2_7_has_is_not_flagged(tmp_path):
    # The near misses: each of these reads like one of the above and is fine.
    fine = tmp_path / "fine.py"
    fine.write_text(u"import io, os, urllib\n"
                    u"io.open(p, encoding='utf-8', newline='')\n"
                    u"f(*args, **kwargs)\n"
                    u"super(A, self).f()\n"
                    u"replace = getattr(os, 'replace', None)\n"
                    u"'%x' % n\n", encoding="utf-8")
    assert offences(str(fine)) == []

# -*- coding: utf-8 -*-
"""The IDE side has one concurrency model, and it is the message loop (SPEC D5).

No sleeping, no threads, no system.delay(). The reasons are in D5 and they
are not negotiable per call site: system.delay() does not pump mouse and
keyboard, execute_on_primary_thread was removed in SP21, and the CODESYS API
is not thread-safe. A rule with one carefully worded exception is a rule
every future author has to hold in their head; a rule a test enforces is
one they can forget.

The check reads the parsed code, not the text, so a comment or a docstring
may say "no threads" — cds/ide/watcher.py does — without tripping it. What
is banned is the call, not the word.

tools/ used to be out of scope by directory, which meant an IDE-side script
was one `git mv` away from escaping the rule. It is in scope now, but only the
files that actually load into an IDE — asked, not listed: a file that imports
`engine` or `cds` is loaded by the IDE at some point, and one that imports
neither cannot be. That keeps `probe_click_menu.py` out, and it has to be out:
it drives an IDE from a *separate* CPython process over Win32, and sleeping
between real mouse clicks is its whole method, not a violation.

D5's one stated exception — headless_watch.park(), which parks a --noUI
process with system.delay() because with no window there is no screen to
freeze and nothing else holds the process up — is registered below by name,
so a second delay() in that file is still red.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where the rule applies unconditionally: everything under these runs inside
# the IDE.
IDE_SIDE = ("engine", os.path.join("cds", "ide"), "stub")

# And tools/, for the files there that reach into the IDE-side packages.
# `_root` counts because that module exists for exactly one purpose: putting
# the install root on sys.path so engine/ and cds/ can be imported. It catches
# perf_probe.py, which reaches the engine through __import__ by string name
# and is invisible to the import walk below.
MIXED = ("tools",)
IDE_SIDE_IMPORTS = ("engine", "cds", "_root")

# D5's one exception, by file and by what it calls. Registered rather than
# excused by directory: the file stays under the rule, and anything else it
# grows is caught. See the module docstring and SPEC D5.
ALLOWED = {"tools/headless_watch.py": ["delay"]}

BANNED_CALLS = {
    "sleep": "blocks the IDE's message loop",
    "delay": "system.delay() does not pump mouse or keyboard",
    "Thread": "the CODESYS API is not thread-safe",
    "ThreadStart": "the CODESYS API is not thread-safe",
    "execute_on_primary_thread": "removed in SP21",
}

BANNED_IMPORTS = ("threading", "System.Threading", "thread")


def sources_under(folders):
    for folder in folders:
        root = os.path.join(REPO_ROOT, folder)
        for where, _dirs, files in os.walk(root):
            if "__pycache__" in where:
                continue
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(where, name)


def loads_into_an_ide(path):
    """Does this file import its way into the IDE-side packages?"""
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            if name.split(".")[0] in IDE_SIDE_IMPORTS:
                return True
    return False


def ide_side_sources():
    for path in sources_under(IDE_SIDE):
        yield path
    for path in sources_under(MIXED):
        if loads_into_an_ide(path):
            yield path


def offences(path):
    """(line, what) for every banned call or import in one file."""
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", None) or getattr(
                node.func, "id", None)
            if called in BANNED_CALLS:
                found.append((node.lineno, called))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BANNED_IMPORTS:
                    found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module in BANNED_IMPORTS:
                found.append((node.lineno, node.module))
    allowed = list(ALLOWED.get(
        os.path.relpath(path, REPO_ROOT).replace("\\", "/"), []))
    kept = []
    for line, what in found:
        if what in allowed:
            allowed.remove(what)       # one pass each, not a blanket pardon
            continue
        kept.append((line, what))
    return kept


@pytest.mark.parametrize("path", sorted(ide_side_sources()),
                         ids=lambda p: os.path.relpath(p, REPO_ROOT))
def test_no_sleeping_and_no_threads(path):
    found = offences(path)
    assert not found, "%s: %s" % (
        os.path.relpath(path, REPO_ROOT),
        "; ".join("line %d uses %s (%s)" % (line, what, BANNED_CALLS.get(
            what, "SPEC D5 bans it")) for line, what in found))


def test_the_check_can_actually_see_one(tmp_path):
    # A rule test that cannot fail is decoration. This is the shape it is
    # looking for, written out so the parametrized run above means something.
    guilty = tmp_path / "guilty.py"
    guilty.write_text(u"import time\ndef park():\n    time.sleep(3)\n",
                      encoding="utf-8")
    assert offences(str(guilty)) == [(3, "sleep")]

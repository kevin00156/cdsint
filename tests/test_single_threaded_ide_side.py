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

tools/ is out of scope on purpose. tools/headless_watch.py parks a --noUI
process with system.delay(), which is D5's one stated exception: with no
window there is no screen to freeze, and with nothing holding the process up
the IDE exits the moment the script returns.
"""
import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where the rule applies: everything that runs inside the IDE.
IDE_SIDE = ("engine", os.path.join("cds", "ide"), "stub")

BANNED_CALLS = {
    "sleep": "blocks the IDE's message loop",
    "delay": "system.delay() does not pump mouse or keyboard",
    "Thread": "the CODESYS API is not thread-safe",
    "ThreadStart": "the CODESYS API is not thread-safe",
    "execute_on_primary_thread": "removed in SP21",
}

BANNED_IMPORTS = ("threading", "System.Threading", "thread")


def ide_side_sources():
    for folder in IDE_SIDE:
        root = os.path.join(REPO_ROOT, folder)
        for where, _dirs, files in os.walk(root):
            if "__pycache__" in where:
                continue
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(where, name)


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
    return found


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

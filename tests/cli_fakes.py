# -*- coding: utf-8 -*-
"""A runner that answers from a table, and results built the way real ones are.

Shared by test_verify.py and test_cli_surface.py, which both drive the CLI
with no IDE behind it. `record` goes through cds/core/commands.py rather
than writing a dict literal with the four fields a test happens to read: the
printer indexes all twelve, and a record short of one is a producer that
forgot it.
"""
from cds.core import commands


class FakeRunner(object):
    """Answers run(steps) from a table, and remembers what it was asked."""

    def __init__(self, answers=None, sync=None):
        self.answers = answers or {}
        self.asked = []
        self.sync = sync

    def describe(self):
        return "a fake IDE"

    def sync_dir(self):
        return self.sync

    def run(self, steps):
        self.asked = steps
        results = []
        for command, _args in steps:
            results.append(self.answers.get(command) or done(command))
            if not results[-1]["ok"]:
                break
        return results


def record(command, ok, **rest):
    """One result, built the way every real producer builds one.

    Not a dict literal with the four fields a test happens to read: the
    printer indexes all twelve now, because a record that is short of one is
    a producer that forgot it (cds/core/commands.py new_result).
    """
    return commands.new_result(commands.new_command(command), ok, **rest)


def done(command, **rest):
    rest.setdefault("data", {})
    return record(command, True, **rest)


def failed(command, error="it broke"):
    return record(command, False, error=error, data={})


def compared(**counts):
    data = {"different": 0, "new_in_ide": 0, "new_on_disk": 0, "moved": 0}
    data.update(counts)
    return done("compare", data=data)

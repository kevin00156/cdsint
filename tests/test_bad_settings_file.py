# -*- coding: utf-8 -*-
"""A settings file nobody can parse stops every command, not just some.

SPEC 4.4 says the whole command refuses. The two commands that do not need a
sync folder — `build` and `discover` — used to get that for free by ignoring
the error `prepare` handed back, and ignoring it swallowed the other kind of
error with it: a project with `"debgu": true` beside it built to a clean
finish and said nothing at all. Which is the exact outcome the validation
exists to prevent, arriving through the door marked "tolerant".

So the two answers are separate now, and this is the test that keeps them
separate: a missing folder is not an error, an unreadable file is, and every
command that reads the file says so.
"""
import io
import os

import pytest

from cds.core import settings as schema
from tests.fakes import DeafSystem, Project, Projects
from engine import entry_build, entry_discover


class Primary(Project):
    """A project whose properties are empty, whatever it is asked for."""

    def __init__(self, path):
        Project.__init__(self, values={}, path=path)


@pytest.fixture
def project(tmp_path):
    return os.path.join(str(tmp_path), "Line.project")


@pytest.fixture
def body(monkeypatch, project):
    """One entry body, with the IDE globals it reads already in place."""

    def load(module):
        monkeypatch.setattr(module, "projects", Projects(Primary(project)),
                            raising=False)
        monkeypatch.setattr(module, "system", DeafSystem(), raising=False)
        return module
    return load


def unreadable(project):
    with io.open(schema.path_for(project), "w", encoding="utf-8") as handle:
        handle.write(u'{"sync_folder": "./sync", "debgu": true}')


@pytest.mark.parametrize("name", [entry_build, entry_discover],
                         ids=lambda m: m.__name__.split(".")[-1])
def test_a_misspelt_key_stops_the_command_that_does_not_need_a_folder(
        body, project, name):
    module = body(name)
    unreadable(project)

    result = module.main()

    assert result["ok"] is False
    assert "debgu" in result["summary"]
    # The whole table comes with it, so the reader can see the name they meant
    # (SPEC 4.4).
    assert "debug" in result["summary"]


@pytest.mark.parametrize("name", [entry_build, entry_discover],
                         ids=lambda m: m.__name__.split(".")[-1])
def test_it_is_said_out_loud_and_not_only_returned(body, project, name):
    # These two ran to a clean finish and printed nothing at all. A caller
    # watching the IDE has to see it too, not just a caller reading a record.
    module = body(name)
    unreadable(project)

    module.main()

    assert [level for level, _text in module.system.ui.said] == ["error"]


def test_discover_still_works_with_no_sync_folder_at_all(body, project):
    # The whole reason discover tolerates a missing folder: it is what
    # somebody runs *because* the export did not work, and refusing it for
    # want of a folder would take away the one diagnostic they have left.
    module = body(entry_discover)

    result = module.main()

    assert result["ok"] is True
    assert not os.path.exists(schema.path_for(project))

# -*- coding: utf-8 -*-
"""Every instrument in tools/ is named in the readMe, and nothing else is.

The readMe listed three of the nine for months. Nobody noticed, because the
only way to notice is to run `ls tools/` and compare by eye — and a maintainer
reaching for an instrument reads the readMe precisely because they do not yet
know what is in there.

Both directions matter. A tool the readMe does not mention is a tool nobody
will find; a tool the readMe mentions that is not there sends the reader
looking for a file that was deleted.
"""
import io
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# tools/_root.py earns its underscore: it is not an instrument, it is the
# sys.path bootstrap the instruments stand on, and the readMe says so in one
# line rather than giving it an entry.
PRIVATE = "_"

MENTION = re.compile(r"`tools/([A-Za-z0-9_]+\.py)`")


def on_disk(include_private=False):
    folder = os.path.join(REPO_ROOT, "tools")
    return set(name for name in os.listdir(folder)
               if name.endswith(".py")
               and (include_private or not name.startswith(PRIVATE)))


def mentioned():
    with io.open(os.path.join(REPO_ROOT, "tools", "README.md"),
                 encoding="utf-8") as handle:
        return set(MENTION.findall(handle.read()))


def test_every_tool_has_a_line_in_the_readme():
    assert sorted(on_disk() - mentioned()) == []


def test_the_readme_names_no_tool_that_is_gone():
    # Against everything on disk, private ones included: the readMe is allowed
    # to name _root.py while saying it is not an instrument, but not to name a
    # file that no longer exists.
    assert sorted(mentioned() - on_disk(include_private=True)) == []

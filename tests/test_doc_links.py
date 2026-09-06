# -*- coding: utf-8 -*-
"""Every in-repo link in the docs points at something that exists.

A dead link is the failure nobody notices: `docs/AI_WORKFLOW.md` spent the
whole move pointing at two readMe sections that had not come across, and the
only way anyone would find out is by clicking. Headings move, so this checks
the anchors too, using GitHub's own slug rule.
"""
import io
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every markdown file a reader is meant to follow links out of. docs/history
# is deliberately absent: those are records of what was decided on a day, and
# their links describe the repo as it was then.
DOCS = ("readMe.md", "CONTRIBUTING.md", "PRINCIPLES.md",
        "docs/SPEC.md", "docs/WATCHER.md", "docs/AI_WORKFLOW.md",
        "skills/cdsint/SKILL.md")

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
# GitHub's slug: lower-case, strip everything but word characters, spaces and
# hyphens, then spaces to hyphens.
NOT_IN_SLUG = re.compile(r"[^\w\s-]", re.UNICODE)


def read(rel_path):
    with io.open(os.path.join(REPO_ROOT, *rel_path.split("/")),
                 encoding="utf-8") as handle:
        return handle.read()


def slug(heading):
    return NOT_IN_SLUG.sub("", heading.strip().lower()).replace(" ", "-")


def anchors(rel_path):
    return set(slug(text) for text in HEADING.findall(read(rel_path)))


def links(rel_path):
    """(target, anchor) for every link that stays inside the repo."""
    folder = os.path.dirname(rel_path)
    for href in LINK.findall(read(rel_path)):
        if href.startswith(("http://", "https://", "mailto:")):
            continue
        target, _, anchor = href.partition("#")
        if not target:
            yield rel_path, anchor
            continue
        joined = os.path.normpath(os.path.join(folder, target))
        yield joined.replace("\\", "/"), anchor


@pytest.mark.parametrize("rel_path", DOCS)
def test_every_link_reaches_a_file_that_exists(rel_path):
    missing = [target for target, _anchor in links(rel_path)
               if not os.path.exists(os.path.join(REPO_ROOT,
                                                  *target.split("/")))]
    assert missing == []


@pytest.mark.parametrize("rel_path", DOCS)
def test_every_anchor_reaches_a_heading_that_exists(rel_path):
    known = {}
    broken = []
    for target, anchor in links(rel_path):
        if not anchor or not target.endswith(".md"):
            continue
        if not os.path.exists(os.path.join(REPO_ROOT, *target.split("/"))):
            continue                      # the other test names this one
        if target not in known:
            known[target] = anchors(target)
        if anchor not in known[target]:
            broken.append("%s#%s" % (target, anchor))
    assert broken == []

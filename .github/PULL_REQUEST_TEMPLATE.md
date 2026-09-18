## What this changes

One sentence. If it takes two because the pull request does two things, split
the pull request.

## Why

The problem, not the patch. Link the issue if there is one. If this replaces an
existing mechanism or moves code between files, link the issue where that was
agreed — see `CONTRIBUTING.md`.

## How it was tested

- [ ] `python -m pytest tests -q` passes locally
- [ ] New behaviour has a test, or this pull request says why it cannot
- [ ] Tried against a real IDE — which one, which version, what I saw:

## Checks

- [ ] **One change.** Nothing renamed, reformatted or tidied that this change
      did not need.
- [ ] No new file over 400 lines, no new function over 60, and no function I
      touched came out longer than it went in (PRINCIPLES 2)
- [ ] Nothing I added under `engine/`, `cds/` or `stub/` uses type annotations,
      f-strings or `pathlib` — those run on IronPython 2.7 inside the IDE
      (PRINCIPLES 8)
- [ ] No bare `except:` (PRINCIPLES 6)
- [ ] If this replaces something, the old one is deleted here — no parallel
      paths left behind (PRINCIPLES 7)
- [ ] The on-disk `.st` format and the `//% cds-text-sync.*` pragma names are
      unchanged

## What the reviewer should look at first

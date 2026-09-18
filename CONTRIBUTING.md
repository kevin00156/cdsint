# Contributing

Pull requests are welcome. Two things decide whether one gets merged: CI has to
be green, and the change has to be one change.

## One change per pull request

A pull request does one thing. Fix one bug, or add one feature, or clean up one
thing — not two, and not "while I was in there". A branch that does three things
cannot be reviewed as three decisions, cannot be reverted when one of them turns
out wrong, and cannot be bisected when a regression shows up months later.

Large rewrites are not accepted as a surprise. If your change moves code between
files, replaces an existing mechanism with a different one, or touches more than
a handful of files, open an issue first and say what you want to do. The answer
is often yes — but it has to be yes *before* you write it, because afterwards
the only choices are merge it or waste your week.

A pull request gets sent back regardless of how good the code is if it:

- renames or restructures something the change did not need
- adds a second way to do something that already has one (PRINCIPLES 7)
- reformats a file it also edits, so the diff hides the real change
- changes the format of what lands on disk

## The line you cannot cross

The `.st` files and the `//% cds-text-sync.<key>=<value>` pragma lines in them
are user data. Somebody's project has those files committed to git. Changing the
format, or the spelling of a pragma, breaks every checkout of every project that
has ever been synced, and no amount of migration code makes that free. That is a
major version, not a pull request.

The pragma prefix says `cds-text-sync` because this code came from there and the
files already on disk still say it. It stays.

## Before you open the pull request

```
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

CI runs exactly that, on Windows and on Linux, on Python 3.12. Both have to
pass. Windows is the real target, because the IDE only exists there. Linux is
the portability guard: it is the only thing that catches a Windows path handled
with `os.path`, because on Windows that mistake cannot fail.

New behaviour needs a test. Everything in `cds/core/` has a unit test — that is
the whole reason `core/` is kept pure Python. Engine logic is tested against
fake IDE objects. If your change genuinely cannot be tested in CI, say so in the
pull request and say what you did instead: which IDE, which version, what you
saw. "A person at a real machine has to confirm this" is a valid answer;
silence is not.

## Read PRINCIPLES.md first

[`PRINCIPLES.md`](PRINCIPLES.md) is the rulebook, and a pull request that breaks
one of its rules comes back with the rule number. These are the ones that catch
people out:

- **Size limits (2).** Files 300 lines soft, 400 hard, no exceptions: the test
  fails on any file over 400 and on a module named `utils`, `helpers`,
  `common` or `misc`. Functions 40 soft, 60 hard; the ones still over 60 are
  a debt table in `tests/test_size_limits.py` that may only shrink, and a
  function you touch may not come out longer than it went in.
- **Two tiers (the preamble).** `engine/`, and the diagnostics that came with it
  into `tools/`, were moved here rather than written here, and splitting them
  did not change that: their functions keep the knowledge real projects beat
  into them, so a rewrite for style's sake is not welcome. Everything written
  since — including a new file added under `engine/` — is held to the rules
  exactly as written.
- **IronPython 2.7 (8).** `engine/`, `cds/ide/`, `cds/core/` and `stub/` all run
  inside the IDE at some point, and the IDE ships IronPython 2.7. That means no
  type annotations, no f-strings, no `pathlib`, standard library only, and
  `from __future__ import print_function` at the top of every module. `cdsint/`
  runs outside the IDE on CPython 3.11+ and has none of these restrictions.
- **No bare `except:` (6).** Catch the exception you expect and let the rest
  crash; a traceback is a gift. Code written here is held at zero.
- **Layer boundaries (4).** `engine/` may not import `cds/ide`. `cds/core/` may
  not import `system`, `projects`, `online` or `clr`.
- **No parallel paths (7).** When you replace something, delete the old one in
  the same pull request.

Several of these are enforced twice: once as a rule you can read, and once as a
test that parses the source, so you will find out either way. When such a test
fails, read the rule rather than the test — the test is only the ratchet.

## Reporting a bug

Open an issue. The template asks for the things that actually narrow it down:
which IDE and version, the exact command, the exit code, and what it printed.
`cdsint installs` prints every IDE on this machine with its profile and
ScriptDir, and is usually the fastest way to answer the first one.

If an object failed to export or import, run `cdsint discover` and include the
lines for the objects involved. It names every object and the kind it counted
as, which is what says whether the kind is unknown or the GUID is.

## Suggesting a feature

Open an issue and describe the situation you are in, not the API you want. This
tool has a scope, and [`docs/SPEC.md`](docs/SPEC.md) lists the non-goals
explicitly; the useful thing to argue about is whether your case sits inside
that line.

## Where the code came from

This repository was moved out of
[`kevin-cds-text-sync`](https://github.com/kevin00156/cds-text-sync), itself a
fork of
[`ArthurkaX/cds-text-sync`](https://github.com/ArthurkaX/cds-text-sync). Much of
`engine/` and most of `tools/` is still that code. Where a file says which
upstream commit it was adapted from, leave the note in place when you edit
around it.

The licence is MIT and the copyright is Arthur's — see [`LICENSE`](LICENSE). By
opening a pull request you agree your contribution goes in under the same
licence.

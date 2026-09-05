# Coding Principles

These are the rules for this codebase. They are not suggestions. If a change
violates one of these, the change is wrong — fix the change, not the rule.

The spirit: **KISS and the UNIX philosophy.** Small things that each do one
job well, that you can read in one sitting, and that compose. If you cannot
explain a module in one sentence, it is doing too much.

**Two tiers, and the line between them is where the code came from.**
All of `engine/`, and the diagnostics that came with it into `tools/`, were
moved here rather than written here: they carry knowledge that real projects
beat into them, and rewriting them to satisfy a rule would throw that away
(SPEC D1). `git log --follow` on a file settles which tier it is in — the
moved ones all arrive in this repo's first commit. Everything written since,
including a new file added under `engine/`, is in the strict tier.

A rule the code does not follow is worse than no rule, so where a tier is
looser, it says so out loud rather than being quietly ignored.

---

## 1. One job per module. One job per function.

- A module has a single responsibility, stated in its first docstring line.
- A function does one thing. If you need "and" to describe it, split it.
- If you cannot name a function without `_and_`, `_handle_`, `_do_`, or
  `_process_`, you do not yet understand the job. Think harder, then name it.

Everywhere. This one has no looser tier, because it is not about size — it
is about whether you can say what something is for.

## 2. Size limits.

- **Files: 300 lines soft, 400 lines hard.**
- **Functions: 40 lines soft, 60 hard.**
- A dispatcher with more than ~5 branches is a `dict`, not an `if/elif`.

**Hard means: no new file starts over it, and no file already over it gets
longer.** A file past the limit is not a bug to be fixed today; it is a file
that has to be split before the next thing goes in. That is a rule you can
actually keep, and "a file over 400 lines is a bug" was not — this repo
shipped with three engine files over 1100 lines and the sentence just sat
there being false.

- Written here: the limits apply as written, to every file.
- Moved here: exempt as it stands, and there are files well past 400. What is
  not exempt: a function you touch may not come out longer than it went in,
  and a function or file you add obeys the limits like anything else.

## 3. The expensive boundary gets crossed once.

Every attribute read on a CODESYS script object crosses into .NET, and on a
project with a few hundred objects that cost dominates everything else.

- Do not read the same property twice. Read it once and pass it down. The
  helpers in `engine/codesys_managers.py` carry `obj_guid` and `parent`
  through their call chains for exactly this reason, and
  `tests/test_ide_round_trips.py` counts the reads so a refactor cannot
  quietly put a second one back.
- Do not do work per object that could be done once for the project.
- Everything that is not an API call is plain Python on local data and is
  effectively free. Spend there instead.

The engine still walks the tree object by object rather than pulling it out
in one `export_native` call. Whether to change that is open (SPEC 11.1) and
waits on the phase 4 measurements; until then this rule is about not paying
twice for what you already fetched.

## 4. Three layers, and the boundaries are the ones in SPEC D12.

- `engine/` — walks the object tree, talks to the CODESYS API, talks to the
  PLC. May not import `cds/ide`.
- `cds/ide/` — plumbing only: the file protocol's IDE end, the timer, the
  stand-in UI, prompt answers, the status window, opening a project
  headless. May not import `online`, may not import an engine module.
- `cds/core/` — pure Python. May not import `system`, `projects`, `online`
  or `clr`. Runs in CI, so it is where anything both sides need goes.
- `cdsint/` — outside the IDE entirely, CPython only.

The direction is: `cds/ide` drives the engine by entry name; the engine does
not know `cds/ide` exists. If you are tempted to import `system` inside
`core/`, you have put logic in the wrong layer. Move the logic out; pass the
data in.

## 5. Disk is the source of truth. Text is the format.

- The `.st` (and minimal `.xml` sidecar) files on disk are canonical. The
  native snapshot is a *transport*, never the truth. This is what lets a
  human or an AI create a new object by writing a file — and have it import
  cleanly.
- A file on disk with no matching object in the IDE means **create it**, not
  "ignore it."
- The other half of the same rule: a file on disk that somebody edited and
  has not imported yet does not get overwritten by an export (SPEC 6.1). If
  the disk is the truth, then quietly writing over it is the worst thing
  this tool can do.

## 6. Fail loud. Never skip silently.

- If you cannot handle an object, say so — by name, on screen and in the
  result (SPEC D13, `engine/unhandled.py`). "It just didn't import and I
  don't know why" is the single worst outcome and the reason we are
  rewriting this.
- A failure that returns a falsy value the caller ignores is the same bug as
  a silent skip, wearing a different hat. Raise, or record it by name.
- No bare `except:`. Catch the exception you expect. Let the rest crash — a
  crash with a traceback is a gift.

`tests/test_bare_excepts.py` is where this one is enforced. Code written
here is held at zero. The code that was moved here arrived with about a
hundred of them; they come out a function at a time, whenever somebody is in
there for another reason, and the table in that test is the ratchet — it
records what is left, file by file, and only ever goes down.

## 7. No dead code. No parallel paths.

- One way to do a thing. Not a "new" way and a "legacy fallback" living side
  by side forever. When you replace something, delete the old one in the
  same PR (SPEC D16).
- Two names for one constant is a parallel path too: one of them goes stale.
- No commented-out code. Git remembers; you do not need to.

## 8. IDE-side code runs on IronPython 2.7 *and* CPython 3.

`engine/`, `cds/ide/`, `cds/core/` and `stub/` are all inside the IDE at some
point, so all four are Python 2/3 compatible: `from __future__ import
print_function`, **no type annotations** (a syntax error in 2.7), no
f-strings, no `pathlib`-only idioms. Standard library only — if a feature
needs a pip package, it does not run inside CODESYS (SPEC D4).

`tests/test_print_function.py` enforces the `__future__` line over all
four directories, with no carve-out for the docstring-only `__init__.py`
files: a rule with an exception is one every future author has to
remember.

`cdsint/` is CPython 3.11+ and has none of these restrictions.

## 9. One concurrency model inside the IDE, and it is the message loop.

No `time.sleep()`, no `system.delay()`, no threads, no
`execute_on_primary_thread` in `engine/`, `cds/ide/` or `stub/` (SPEC D5).
Waiting is a WinForms timer hung on the IDE's own message loop, so the script
returns and the IDE stays usable. `tests/test_single_threaded_ide_side.py`
enforces this by parsing the code, so it cannot rot.

## 10. No premature abstraction.

- Write the concrete thing first. Extract an abstraction only on the third
  copy, never on the first guess. A base class with one subclass is not an
  abstraction, it is two files where one would do.
- YAGNI. Delete the option nobody asked for.

## 11. Tests follow the boundary.

- Everything in `cds/core/` has a unit test. No exceptions — that is why
  `core/` is pure.
- Engine logic is tested against fake IDE objects, in CI.
- The IDE end is verified against a real IDE: `cdsint verify --project` is
  that script, and some things (a tray balloon, a PLC download) only a person
  at the machine can confirm. Say which of the two a claim rests on.
- A rule worth writing down twice — once here and once as a test that parses
  the code — is worth writing down twice. The tests named above exist because
  a rule nobody can forget beats a rule everybody agrees with.

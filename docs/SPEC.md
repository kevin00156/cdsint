# Product spec: cdsint

> This document describes what the finished thing looks like, not the order of
> construction and not a progress report.
> "How far along it is" is not written here: that is what `git log` and
> `CHANGELOG.md` answer, and progress written into a spec is always stale.
> Every rule lives only in the decision table of section 3; the other sections
> and the code comments cite the D numbers and do not repeat the content.
> The code comes from `kevin-cds-text-sync` (branch
> `fix/member-creation-parent-resolution`, commit 9aa9886). This repo only reads
> from it, never writes back.

---

## 0. In one sentence

**The `.st` text files on disk are the source of truth for a PLC project.
cdsint turns moving them in and out of the CODESYS-family IDEs, driving those
IDEs and verifying the result into something that can be called from outside.**

How the name splits: `cdsint` is the product, and it is also the name of the
settings file beside the project, `<project>.cdsint.json` (D9, D10).

The difference from upstream cds-text-sync 3.x and from the official CODESYS
MCP Server is the reason cdsint exists:

| | cdsint | upstream 3.x | official MCP Server |
|---|---|---|---|
| Source of truth | `.st` on disk | XML snapshot; text mode is optional | the project open in the IDE |
| Is the IDE usable outside a command's execution | yes | no, the daemon holds the main thread with `time.sleep` | yes |
| IDE-side dependencies | the IDE itself only | a separate Python 3.11 plus pywebview | paid subscription |
| Supported IDEs | stock SP17 to SP21, Lenze PLC Designer, Delta DIADesigner-AX | claims SP10 and above | stock SP22 and above |
| Runs with the IDE closed | yes, headless mode | no | no |

---

## 1. Who uses it, and how

Three scenarios. cdsint has to support all three, and on the same engine.

**Scenario A, an engineer's day.** The IDE has the project open, with VS Code
open beside it editing `.st`. After an edit, press "import" in the IDE's
Scripts menu, or type one line in a terminal. Between two commands the IDE is
fully usable.

**Scenario B, an AI agent's loop.** The agent has no way to see the IDE's
window; it can only read files and command output. It edits `.st`, runs compare
to see the differences, runs import to send them into the IDE, runs build to
get the error list, fixes, and goes again. Every dialog is answered by a
command-line flag; with no flag it reports "which flag is needed" instead of
hanging (D7).

**Scenario C, a pipeline.** The IDE is not open. `make` or CI starts a headless
IDE process, opens a copy of the project, imports, exports to verify, builds,
downloads to the test rig, and then confirms the rig is still holding what was
just put on it. Nobody is at the keyboard for the whole run.

---

## 2. Goals and non-goals

### Goals

1. The text on disk is the source of truth. A `.st` that exists on disk and not
   in the IDE gets created; if it cannot be created, report an error saying
   which file and why.
2. With the IDE open it can be driven from outside, and between commands the
   IDE is fully usable.
3. The IDE side needs only the IronPython 2.7 and standard library the IDE
   ships; nothing else gets installed.
4. Stock CODESYS 3.5 SP17 to SP21, Lenze PLC Designer 3.24 and 4.0, and Delta
   DIADesigner-AX 1.8 and 1.10 can all install it and run it.
5. With the IDE closed the same engine runs headless.
6. Every silent failure is a bug. An object not imported, a file not exported,
   a dialog nobody answered: each has to be reported by object name or file
   name (D13).
7. An action that changes the PLC needs explicit authorisation; the default is
   refusal (D8).

### Non-goals

- No rewrite of the sync engine. The GUID table, member creation, device
  renaming and pragmas inside it are knowledge beaten out of real projects;
  whoever rewrites it will not discover in the first week what they are
  missing.
- No static analysis, FSM diagrams, formatting, SVG conversion of
  visualisations, or live read/write of PLC variables. Upstream has them;
  cdsint does not chase them.
- No HTTP or MCP server in the first version. The CLI's `--json` is already
  machine-readable; wrapping it as MCP is a job outside the IDE, can be added
  any time, and does not touch the command hand-off protocol (D6).
- No online change. A download is always a full download.
- No multi-user, no cross-network. The command directory sits under the local
  user's `%LOCALAPPDATA%`; whoever is logged in to this machine can issue
  commands.

---

## 3. Decisions taken

Each has a number, a decision and a reason. Other sections cite the number
only. How far along it is does not go here; that is what git log and
`CHANGELOG.md` answer.

**D1 Open a new repo `cdsint`; the code moves over from `kevin-cds-text-sync`,
no rewrite.**
Reason: the product changes name and the whole directory layout changes;
editing the old repo in place means moving every file anyway while still
minding the old paths. The new repo's git history starts at the moment of the
move; the old history stays in the source repo. The engine, the watcher and the
CLI move over as they are and get tidied afterwards, for the same reason as the
first non-goal: the knowledge in the engine came out of real projects. The last
"clean restart", the `cds/` skeleton, was written from scratch and was deleted
without a single acceptance box ticked.

**D2 One engine, one CLI namespace, the mode decided by flags.** `--target X`
goes through the watcher inside an open IDE; `--project P --install I` starts a
headless IDE. The two sets of flags are mutually exclusive, and argparse blocks
giving both with a mutually exclusive group.
Reason: the two scenarios exclude each other; CODESYS blocks a second process
from opening the same project file, so one command can never take both routes.
But the two do the same job, and giving them two vocabularies only lets the
subcommands each grow things that exist on one side only. No auto-detection,
because it would make the required flags depend on runtime state, and an
unexpected twenty-second IDE start is the hardest kind of surprise to track
down. Both halves (`cdsint/target.py`, and `cdsint/headless.py` with
`cds/ide/headless.py`) expose `run(steps)`, so `verify` is written once.

**D3 The IDE's Scripts menu has exactly three entries: export, import,
watcher. The body lives outside ScriptDir.**
Reason: the menu scans every `.py` under ScriptDir recursively; upstream
v2.9.0 found by experiment that even the hidden attribute does not escape it.

**D4 The IDE-side code is Python 2/3-compatible code that IronPython 2.7 can
run, standard library only. CPython 3 exists only outside the IDE.**
Reason: goal 3.

**D5 Waiting for commands inside the IDE uses a WinForms timer hung on the
IDE's message loop, and the script returns immediately. On the IDE side there
is no `time.sleep()`, no `system.delay()`, no threads, no
`execute_on_primary_thread`.** This is absolute; there is no "a background
thread that does not touch the API is fine" exception.
Reason: `system.delay()` does not service mouse and keyboard,
`execute_on_primary_thread` was removed in SP21, and the CODESYS API is not
thread-safe. One concurrency model for the whole IDE side is worth more than
one precisely worded exception. The timer design has been checked by a person
on ScriptEngine 4.0.0.0 and 4.2.0.0. The rule is guarded by
`tests/test_single_threaded_ide_side.py`: it parses every `.py` under
`engine/`, `cds/ide/` and `stub/`, plus the ones in `tools/` that get loaded
into the IDE (the criterion is whether the file imports `engine`, `cds` or
`tools/_root.py`). It looks at the two kinds of syntax node, calls and imports,
not at text, so a comment that mentions "thread" is not a false hit.

The only permitted exception to this rule is `park()` in
`tools/headless_watch.py`, which uses `system.delay()`, and only under
`--noUI`: with no window there is no screen to freeze, and with nothing holding
the process up the IDE exits the instant the script returns, before the watcher
gets a single tick. It checks `system.ui_present` before running and refuses to
park when there is a UI, so the exception cannot leave the situation that
justifies it. It is an acceptance tool and does not live under `cds/ide/`.

**D6 Command hand-off is a file protocol; not a named pipe, not HTTP.** The
protocol spec is in `docs/WATCHER.md`.
Reason: the existing protocol has already run against real projects, and
IronPython and CPython both need only the standard library.

**D7 cdsint's own dialogs are answered by flags, never guessed. With no flag it
returns `needs_input`.** The IDE's own prompts are outside this rule: in
headless mode they go through `system.prompt_answers`, filled by
`--answer KEY=VALUE`; a prompt with no answer takes the IDE's default and its
key is written into the report.
Reason: scenario B rests on the agent not being able to see the window. For
the IDE's built-in prompts it is the IDE guessing, not cdsint, and the spec has
to state that boundary honestly rather than claim nothing is ever guessed. The
stand-in UI is in `cds/ide/silent.py`, shared by both forms. `--answer` exists
only in the `--project` form, and none of them has a default, because answering
Yes to `UpgradeProjectConfirmation` rewrites the project's storage format and an
older IDE can never open it again. Unanswered prompts print their key to stdout
through `LogMessageKeys`, and the message says which `--answer` to add.

**D8 Only actions that touch the PLC are under permission control, in two
layers.** The `plc` list in the settings file decides whether this project
allows it; `-y` confirms this one call. The watcher mode refuses PLC commands
outright.
Reason: an agent issuing a wrong command can now download straight to a PLC.
`export`, `import`, `compare` and `build` touch no hardware; putting them under
the permission list would only add a pre-check to every command in exchange
for a feature none of the three scenarios uses. The watcher runs inside the
user's IDE, and a login would take the user's online session away. The first
layer used to be a project property, which meant "someone decided this inside
the IDE"; after the settings moved to a text file (D10) that meaning no longer
holds, the first layer is just "the file says so", and the real gate is `-y`.

**D9 The product name is `cdsint`.** The same string is used for the pip
package, the Python package, the command, the `%LOCALAPPDATA%` directory, the
ScriptDir subfolder and the window title.
Reason: upstream has the same name and 93 stars, and the old README and
install scripts pointed at upstream. No hyphen, so the pip name, the import
name and the command name do not need two spellings. `cds-ide` would collide
with the IDE it drives, and every sentence of documentation would need one more
explanation.

**D10 Settings live in `<project>.cdsint.json` beside the project file, not in
the `.project`'s project properties.**
Reason: `.project` is a binary file that only an IDE process can open, so a
setting stored in it needs a live IDE before it can be changed, an agent needs
to start an IDE to read a setting, and every new project starts from zero. That
one fact grew four entry points (the Properties grid, the Settings window, the
`config` command, the first-export dialog) and three mechanisms that existed
only for it (a mandatory `--sync-dir`, the machine-name stamp, and the engine's
wrap-up after `config set`). A text file can be edited by any editor, no IDE
needed. It goes beside the project rather than inside the sync folder because
most of these settings are about this machine, not team policy, and because
only then can the sync folder itself be moved out, which lets the
project-property route be closed completely. The old `cds-sync-*` properties
are neither read nor migrated: no version has been released yet, the only key
without a default is the sync folder, and that one already has a dialog asking
for it. The schema is in `cds/core/settings.py`, one copy, shared by both
sides, testable in CI.

**D11 The four entry points return a result, and the stand-in UI reads the
return value to decide success or failure.**
Reason: the four `main()`s used to return `None` whether they succeeded or
failed, and the stand-in UI could only infer from whether `system.ui.warning`
and `error` had been called. That turned "warning may only be called at an
abort point" into a rule every future author has to remember, with
consequences far from the scene: someone writes one harmless warning halfway
through an export, and a successful export becomes exit 1. The return shape is
`result(ok, summary, **data)` from `engine/entry.py`; the stand-in UI reads
`ok`, and returning `None` counts as failure. `ok` means "this command finished
every object it was supposed to": if any one object cannot be classified,
created or exported, `ok` is False and the name is listed in `data` (D13); the
command still finishes the other objects instead of giving up part way.

**D12 Three layering rules, checked on resolved imports.** `cds/core` may not
import `system`, `projects`, `online` or `clr`. `cds/ide` may not import
`online` and may not import engine modules. The engine may not import
`cds/ide`.
Reason: `cds/core` has to be fully tested in CI. `cds/ide` does plumbing only:
the protocol endpoint, the timer, the stand-in UI, prompt answers, the status
window, and `projects.open` for headless mode. Walking the object tree and
touching the PLC are all in the engine. The dependency direction is `cds/ide`
driving the engine by entry-point name, never the reverse. The guard is
`tests/test_layering.py`, which reads the AST, not the text: grep would count
the comment in `cds/ide/silent.py` that says "no engine import here" as a hit,
and someone fooled once by a false hit will not believe the next real one. The
single exception is `silent.py` loading `engine.codesys_ui` by string name,
only to swap two dialog functions for stand-ins and back, calling nothing on
it; that `__import__` is registered in the test as one entry, and a second one
goes red.

**D13 No silently skipped objects.** Anything that cannot be classified,
created or imported has to be reported by name. When a run has objects it
could not handle, the export does not delete orphan files, because it cannot
tell which files belong to them.
Reason: goal 6. `engine/unhandled.py` is the register for one command; objects
that could not be handled are recorded there by name, and the three commands
`export`, `compare` and `import` write it into the return value's
`data.failed_objects` and set `ok` to False (D11). The catch point is the
"handle this one object" step of every loop, so one broken object does not
drag the whole run down. The moved-over code still has a batch of bare
`except:`; the count and the ratchet are in `tests/test_bare_excepts.py`, see
6.1.

**D14 Credentials never appear on the command line, in files or in the
report.** They are read from environment variables only.
Reason: reports end up in git or pasted into tickets. `USER_ENV` and
`PASS_ENV` in `engine/plc_link.py` are the only place that reads them; once the
password is handed to `set_default_credentials` it never appears in any string
again, while the user name does appear in the notes (who logged in is the
basis for reading the record afterwards). One test runs a full download and
then confirms the password is in none of the result record, stdout or
messages.

**D15 The `.st` format and the pragma names do not change.** Changing them
means a major version. The format is defined in 4.5.
Reason: the git history of every existing project is in this format; this is
the compatibility floor.

**D16 No old and new route side by side.** Replace means delete.
Reason: PRINCIPLES.md keeps no dead code. That is how the last `cds/` skeleton
got cleared out.

---

## 4. What the user sees

### 4.1 IDE menu

Under `Tools > Scripting > Scripts` there are exactly three items (D3):

| Entry | What it does |
|---|---|
| `Project_export.py` | Writes the IDE project out as `.st`. On first run, if no sync folder is set, it goes through the setup flow first (6.7) |
| `Project_import.py` | Reads the `.st` back into the IDE, disk wins. Same setup flow first |
| `Project_watch.py` | Starts the watcher, and the script returns immediately; run it again to stop |

Compare, build, diagnostics, resource statistics and performance measurement
do not appear in the menu. Compare and build are called from the CLI. The rest
moved to `tools/`.

### 4.2 CLI

The command is `cdsint`, CPython 3.11 or later, standard library only,
installed as a console script through `pyproject.toml`. The package may not be
called `cli`; upstream v2.9.0 renamed it precisely because the top-level
package name `cli` collided with users' own directories.

Every command has two forms (D2). `--target X` finds the watcher in an open
IDE; `--project P --install I` starts a headless IDE. The two sets of flags are
mutually exclusive, and argparse blocks them directly.

| Command | `--target X` | `--project P --install I` | What it does |
|---|---|---|---|
| `installs` | n/a | n/a | list the IDEs on this machine, their profile names, and whether they need admin |
| `list` | n/a | n/a | list the IDEs that are listening. It asks "who is listening", not about one IDE, so it takes neither form |
| `ping`, `status`, `stop` | yes | n/a | the watcher's lifecycle, not under permission control |
| `export [--delete-orphans]` | yes | yes | write the IDE project out as `.st` |
| `import -y` | yes | yes | read the `.st` back into the IDE, disk wins |
| `compare` | yes | yes | list the differences between the IDE and the disk |
| `discover` | yes | yes | name every object and the kind it counted as, and list the type GUIDs no kind recognises (`data.unknown`). Read-only, no permission needed |
| `build [--app NAME]` | yes | yes | compile, return the error list |
| `verify -y` | yes | yes | import, export, compare the disk for a diff, build, all in one run. It contains an import, so it needs `-y` like `import` does |
| `plc connect [--gateway IP --port N]` | refused | yes | read-only: list files, pull `Application.crc`, compare with the value recorded at the last download |
| `plc download -y` | refused | yes | full download, write the boot application, start, read the CRC back and record it |

There is no `config` command. The settings are one text file beside the
project (4.4); the file is the interface, and validation is in the one
function that reads it, which every route passes through.

Shared flags: `--timeout SECONDS` (default 120, the ceiling for **one command
step**; the `--project` form derives the process deadline from it: launch
allowance + number of steps × timeout + shutdown allowance, so `verify`'s real
waiting ceiling is larger than the literal value), `--json`.
Only in the `--project` form: `--profile NAME`, `--report FILE`,
`--force-lock`, `--sync-dir D` (optional, semantics below),
`--answer KEY=VALUE` (repeatable, D7). `--answer` answers the IDE's own
prompts, and in the `--target` half there is a person sitting in front of the
IDE whose prompts those are, so it does not go in the shared row.

One safety line tied to "disk wins". `import` (on all three routes: the menu,
`--target`, `--project`) refuses when there is not a single `.st` in the sync
folder, because that is not the fact "there is nothing on disk"; it is a folder
nobody has exported to or a wrong path, and following the disk-wins rule from
there would empty the project.

`--sync-dir` means "use this folder for this run": it is an argument of the
command, travels into the IDE side by the same route as `-y`, and when the
engine sees it, it overrides `sync_folder` from the settings file and is never
written back to any file. Without it the settings file's value is used; with
neither, export and import return `needs_input`, the same as in the `--target`
form. It used to be mandatory, on the grounds that a copied `.project` carries
the original project's folder property; after the settings moved to the text
file beside the project (D10), a copy of the `.project` alone carries nothing,
and that reason is gone. The resolved sync folder is printed on the first line
of the output and written into the report as `sync_dir`; that field holds the
value that actually took effect on the IDE side, not what the flag said.

`-y` uniformly means "confirm that this step changes state"; `import`,
`verify` and `plc download` share it. Without it the command prints what this
run would do, returns `needs_input`, exits 1, and changes nothing. There is no
`-N`, because leaving out `-y` already means "don't"; the other dialogs with a
safe default each have a named flag, and `--delete-orphans` answers "delete
the orphans".

Why `plc` commands refuse the `--target` form is in D8.

### 4.3 Exit codes and output

| Exit code | Meaning |
|---|---|
| 0 | done |
| 1 | the command failed, including `needs_input` for a missing flag |
| 2 | the command line itself is wrong: flags that do not go together, or no single live IDE found |
| 3 | timed out |
| 4 | headless mode: no usable IDE for this project — the project is open in another process, `--install` matched no install (the message lists which are installed), or the IDE failed to start |
| 5 | permission refused: the `plc` list in the settings file does not hold this command |

2 has two causes, flags that do not go together and no single live IDE found,
in one row because the caller's response is the same: do not retry the same
line, read the message first. 2 and 4 are two causes of "is there a live IDE
for this project", split because the difference is useful to an agent. `list`
is outside 2's scope: it asks "who is listening", and when nobody is it prints
one line, `--json` gives an empty array, exit 0, because an empty list is an
answer, not a failure. `needs_input` does not get its own row, because the
agent has to read `needs_input.arg` in the JSON anyway to know which flag to
add, and a separate code would not save that parse.

The `--json` output keeps the structure of the existing result file: `ok`,
`command`, `elapsed_s`, `messages`, `stdout_tail`, `error`, `needs_input`,
`denied`, `data`. The `--project` form adds `ide` (which install was used),
`sync_dir` (this run's source of truth, the same value as at the top of the
report), `report_path`, `notes`.

`notes` is what the launcher has to say about "this run" rather than about
"the work": it cleared a lock file, it had to kill an IDE, the exit code did
not match what the script recorded. Only the `--project` form has it, because
only that half starts an IDE. It goes into the record and not only onto stderr
because the agent reads exactly this JSON, and "I cleared a lock file for you"
is something it has to hear. Every record of one run carries the same list, so
reading only one of them misses nothing.

`denied` is normally `null`; when the settings file blocks the command it is
`{"file", "key", "action"}`, and exit code 5 is decided from it. It is a
separate field from `needs_input` because the two ask the caller to do
different things: `needs_input` is "add a flag and run again", `denied` is
"add a word to the `plc` list in the settings file".

### 4.4 Settings file

Settings live in a JSON file beside the project file, named after the project
(D10): next to `Line.project` is `Line.cdsint.json`. UTF-8, real JSON types:
booleans, integers, strings, lists. It is a separate file from the download
record `Line.cdsint-plc.json`, because a preference a person decided and a
record a machine left after a run have different lifetimes.

Only keys a person has decided appear in the file; a key that is not written
takes the default in the code, and that default exists in one place only. So
"what I chose" and "what it filled in" stay distinguishable, and changing a
default in the code means going back to no file. The file written after the
first export or import's folder dialog has exactly one key, `sync_folder`.

| Key | Type | Meaning | Default |
|---|---|---|---|
| `sync_folder` | string | the sync folder. Starting with `./` it is relative to the directory holding the project file; otherwise used as written | none, asked on first run |
| `plc` | list of strings | PLC authorisation; only `connect` and `download` are recognised as elements, see 6.5 | empty list |
| `debug` | boolean | write `sync_metadata.json` and `*.log` only when on | false |
| `export_xml` | boolean | also save visualisations, alarms and text lists as XML | false |
| `backup_binary` | boolean | copy the `.project` into the sync folder on export | false |
| `safety_backup` | boolean | back the `.project` up before an import | true |
| `backup_name` | string | the backup file name | empty |
| `backup_retention_count` | integer | how many backups to keep | 10 |
| `save_after_import`, `save_after_export` | boolean | save after a sync | true |
| `auto_delete_orphans` | boolean | delete orphans on disk automatically on export | false |

The one function that reads the file is the only validation: an unknown key, a
wrong type, an unrecognised word in `plc`, broken JSON, and the whole command
refuses, with every key and default from the table in 4.4 printed as they are
in the message. The file is edited by hand, so typos will happen, and a setting
that quietly does nothing is worse than an error.

There is no machine-name stamp and no tool-version stamp. The former is a
proxy for "is the folder on this machine", and only the dialog route ever
wrote it; the situation the latter wanted to guard against is ruled out by D15,
so it would only demand one more flag after every upgrade. The paths of the
`.st` files and the sync folder are, as before, unaffected by this file (4.5).

### 4.5 Disk format

The existing format is kept, not one byte changed (D15):

- One `.st` per object, the declaration and the implementation separated by
  `// === IMPLEMENTATION ===`.
- Paths follow the IDE tree; a POU's members go in a folder named after the
  POU, for example `Function Blocks/MC_BasicControl/MC_BasicControl.Main.st`.
- The `//% cds-text-sync.kind=<kind>` pragma is stamped only on kinds the
  keywords cannot express: persistent GVLs, parameter lists, actions,
  interface methods.
- Build attributes use `//% cds-text-sync.<attr>=true`: `exclude_from_build`,
  `link_always`, `external_implementation`, `enable_system_call`.
- The mapping of kinds to GUIDs is in `profiles/default.json`: `guid_aliases`
  (a list of GUIDs per kind, the first being the primary one used when
  creating an object), `legacy_kind_names`, `sync_direction`
  (`bidirectional`, `export_only`, `import_only`, `disabled`). How many kinds
  there are is decided by that file and not repeated here.
- `sync_cache.json` is local state, gitignored. `sync_metadata.json` and
  `*.log` are written only with debug on.

---

## 5. Architecture

### 5.1 Four layers

```
IDE side (IronPython 2.7, standard library only)
  engine/   the sync engine and the bodies of the four entry points: classify,
            export, compare, import, backup, cache, build, online pre-check,
            PLC connection and download
  cds/ide/  the watcher, the stand-in UI, the message store, project info, the
            status window, the IDE side of the headless launcher
  stub      Project_export.py, Project_import.py, Project_watch.py

Runs on both sides (Python 2/3 compatible, standard library)
  cds/core/ the file protocol: directories, instance registration, commands
            and results

Outside the IDE (CPython 3.11 or later)
  cdsint/   the CLI, the CLI side of the headless launcher, IDE install
            detection, report interpretation
  tools/    the maintainer's instruments: call tree, cache doctor, perf probe,
            a few probes. How many there are and what each does is decided by
            tools/README.md and not repeated here
```

The boundaries between layers are the three rules of D12.

### 5.2 Data flow in the three scenarios

**Scenario A, the menu button**: the stub loads the engine, the engine calls
the IDE API directly, and a person answers the dialogs.

**Scenario B, the watcher**:

```
The CLI writes a command file
  The watcher's timer picks it up on its next tick, deletes the command file, then runs it
    The stand-in UI takes over system.ui and codesys_ui.ask_yes_no; a flag with an answer answers, no flag raises NeedsInput
    The engine runs, the same code as scenario A, and returns a result
  Writes the result file, heartbeat back to idle
The CLI reads the result file, deletes it, prints it
```

**Scenario C, headless**:

```
The CLI finds the IDE, infers the profile, checks the lock file, assembles the command line
  Starts <exe> --profile=… --noUI --runscript=<IDE-side launcher>
    The launcher opens the project with projects.open(), puts --sync-dir into every command's arguments as this run's override, and pre-fills prompt_answers
    Loads the engine and runs export/import/build; dialogs are answered by the stand-in UI from the flags
    Writes the report file, the script returns, the process exits
The CLI waits for the process or the timeout, reads the report, and judges whether stdout came back and whether the exit code can be trusted
```

The engine is the same in all three scenarios; the only difference is who
answers the dialogs.

### 5.3 Install layout

Split into body and stubs, as in upstream v2.9.0:

```
Body  %LOCALAPPDATA%\cdsint\             or any git clone
      engine\  cds\  cdsint\  profiles\  tools\  docs\ …

ScriptDir\cdsint\                       what the IDE scans; only the three stubs
      Project_export.py   hard-codes the body path, adds it to sys.path, calls the body
      Project_import.py
      Project_watch.py
```

The ScriptDir location differs across the three vendors; it is the easiest
trap at install time, and the installer has to work it out itself:

| IDE | ScriptEngine.plugin | Where it scans |
|---|---|---|
| stock 3.5.21 | 4.2.0.0 | `%LOCALAPPDATA%\CODESYS\ScriptDir` |
| Lenze 4.0 | 4.1.0.0 | `%LOCALAPPDATA%\PLCDesigner\ScriptDir` |
| Lenze 3.24 | 4.0.0.0 | `C:\ProgramData\PLCDesigner\ScriptDir` |
| Delta 1.8, 1.10 | 4.0.0.0 | `<install dir>\CODESYS\ScriptDir`, needs admin |

Development mode keeps the current NTFS junction, but the junction points at
the "stub folder", not the whole repo.

---

## 6. Component specs

### 6.1 Engine

The sync engine under `engine/`, plus the bodies of the four entry points.
What is required of it:

- **Dirty-file protection**. On export, if a `.st` on disk has been changed
  since the last sync and not yet imported, do not overwrite it; list it and
  report it as "pending import". The decision is in
  `ObjectManager._disk_moved_since_sync`; it is asked only after the two
  contents are known to differ, and what it asks is "are this file's mtime and
  size the same as what the last sync recorded". The same means the IDE side
  moved, so overwrite as before; different means the disk side moved, so leave
  it unwritten, the path goes into `data.pending_import`, and that run's `ok`
  is False. When the cache has no record of the file it does not block,
  because that is not "unchanged" but "unknown": the cache is local state and
  gitignored, and a fresh clone has not one entry. A command that only looks
  may not take that evidence away: `find_all_changes` keeps the old cache
  entry for objects that are "different" or "unreadable this run", because
  that entry describes "what the disk looked like at the last sync", which is
  exactly what this decision asks about. It used to write back only the ones
  it saw as identical, so any `compare`, `verify`, or unconfirmed `import`
  (the comparison runs before the confirmation dialog) would let the next
  export overwrite that edit outright.
- **One save backup per operation.**
- **Time spent waiting for a person to press a button is not counted in the
  elapsed time.**
- **No bare `except:` in newly written code.** The moved-over ones need not be
  cleared in one go, but fix them in any function you touch.
  `tests/test_bare_excepts.py` is the ratchet: new places are pinned at zero,
  each moved-over file gets one number, and it may only go down.
- **Dialogs only through `codesys_ui.ask_yes_no` and `system.ui.choose`**,
  because the stand-in UI intercepts only those two. A new dialog has to be
  registered in the stand-in UI's answer table first;
  `test_every_shared_title_has_an_answer_and_no_answer_is_stale` in
  `tests/test_silent.py` blocks unregistered ones, in both directions: a title
  missing from the answer table is red, and a title in it that nobody asks is
  red too. Both sides take the titles themselves from `cds/core/dialogs.py`,
  so the test compares against that table, not a hand-copied list.
- **The success/failure signal** goes through the return value (D11). Every
  `return` has to return a `result()`; message level no longer affects the
  verdict.

### 6.2 Watcher

The spec is in `docs/WATCHER.md`, not repeated here. The essentials:

- Instance directory `%LOCALAPPDATA%\cdsint\instances\<project stem>-<pid>\`;
  the registration file heartbeats every 2 seconds; a `busy` registration file
  is never cleaned up automatically.
- A command is deleted first, then run. An import that died halfway had better
  let the caller time out than run again.
- No two watchers in one IDE.
- There is a status window (`cds/ide/statusform.py`) showing what it is doing,
  how many it has done, and the last result. The window title is `cdsint`.

### 6.3 CLI

The package is called `cdsint`; its behaviour is the table in 4.2.
Structurally it is split into target resolution and result printing, the
headless launcher, IDE install detection, and the PLC subcommands, one module
each, none over 300 lines.

### 6.4 Headless launcher

The CLI side is `cdsint/headless.py`, the IDE side `cds/ide/headless.py`. The
behaviour was moved over from an earlier customer project's
`codesys-probe.ps1` and its Python version; both are retired, and this is the
only copy. The behaviours to keep, every one of them written after falling
into the hole:

| Behaviour | Why |
|---|---|
| List the installs: scan `Program Files` for `CODESYS *` and `Delta Industrial Automation\DIAStudio\DIADesigner-AX*`, and read the file names of `Profiles\*.profile.xml` as the profile names | `--noUI` without `--profile` exits straight away, and the right name has the shape "CODESYS V3.5 SP21 Patch 4", not the install directory's name |
| Check the registry `AppCompatFlags\Layers` for `RUNASADMIN` | An exe whose manifest says asInvoker can still be blocked by that flag, and the error message does not say who asked for it |
| More than one matching install: refuse, do not guess | This machine has five installed; a wrong guess silently probes an unrelated one |
| Check for the `.~u` lock file before starting, in both file-name shapes | Saves a twenty-second IDE start, and the message has a path a person can read |
| The project path travels in an environment variable, not in `--project` and not in `--scriptargs` | `--project` under `--noUI` does not actually open the project; `--scriptargs`'s quoting rules cannot take a Chinese path |
| The command line is assembled as a single string, not an array | PowerShell 5.1's array arguments re-quote and break `--profile="name with spaces"` |
| stdout and stderr are redirected to a file named after the report | A GUI-subsystem exe gives the shell no output; the file name follows the report so two parallel processes do not fight over the file |
| On timeout, kill. Only an incomplete report (no `intended_exit`) counts as "a dialog hung"; a complete report is authoritative, and only "the script finished but the IDE did not exit in time" is noted. After the kill, wait until the process is really gone | A hang is ten times harder to diagnose than an error; and a complete report is evidence that a slow shutdown should not override |
| After a kill, clear only lock files that "did not exist before this run started", and write into `notes` that it did; a lock file that was there before the start (that is, `--force-lock` was used) is left alone, with the reason stated | `--force-lock` means "run anyway", not "that lock is mine". Clearing it could release a project another IDE really has open, and the next run has two IDEs on one project. The same holds when the process was not killed: the lock stays |
| The script writes the exit code it intends to use into the report, and the CLI compares it with the one actually received | Whether the exit code makes it back has to be verified; if it does not, read the report instead |
| `system.prompt_handling` turns on `LogMessageKeys`, so an unanswered prompt prints its key; `--answer KEY=VALUE` fills `prompt_answers` | Delta 1.10 opening a 1.8 project asks whether to upgrade, and the default answer is "don't open it". This is the exception D7 spells out |
| No close after opening | close asks whether to save, and nobody can answer under `--noUI` |

Known and unsolved: Delta 1.10 headless, the first `save()` after a project
has just had its storage format upgraded throws NullReferenceException. The
launcher prints one line and continues, without aborting.

The table's "the project path travels in an environment variable" lands as one
environment variable, `CDSINT_HEADLESS_JOB`, pointing at a JSON job file that
holds the project path, the command list and the `--answer` answers; the
reason is the same as that row's, and it also spares both sides from growing
one environment variable per new flag. The IDE side writes a JSON report when
done, and the CLI side adds what only the outside knows: `stdout_reached`
(only counts when both markers were seen), `exit_code_actual` and
`exit_code_trusted`, `timed_out`.

### 6.5 Permissions

Where D8 lands.

**The `plc` list in the settings file** (4.4), its elements recognised as
exactly `connect` and `download`, case-insensitive, empty by default. A `plc`
command checks it before running; if the command is not in the list it returns
exit 5, and the refusal says three things: where the file is, what the value
is now, and what to add. A misspelt word is not guessed into the right one;
the function that reads the file prints it as written and refuses the whole
command (4.4).

**`plc download` also needs `-y`.** Without it the command prints what this
run would do (full download, stop, write the boot application, start), returns
`needs_input`, exit 1. That is exactly the same as `import` without `-y`. Exit
5 has one meaning only: "the list does not allow it".

The first layer used to carry the meaning "only a person inside the IDE can
write it"; that was the project-property era (D8). Now it is one key in a text
file, and whoever can write the file can write it. The real gate is `-y`, and
it is already there.

Every other command is outside permission control.

### 6.6 PLC connection and download

Moved from the probe, placed in the engine next to `codesys_online.py` (D12),
offered only in the `--project` form (D8). Split into four files:
`entry_plc.py` is the front for the two commands, `plc_trip.py` the steps of
one run, `plc_link.py` the part that connects to the controller, and
`plc_crc.py` the verdict itself (pure bytes, paths and JSON; no IDE).

- `connect`: set `online.auth_fallback_modes` to `CredentialSourceKind.None`
  to switch off the credential dialog (on ScriptEngine 4.2.0.0 it is, by
  experiment, a writable property, not a method; only when the property does
  not exist does it fall back to calling `set_auth_fallback_modes`, and with
  neither it refuses to connect, because under `--noUI` a dialog that cannot
  be switched off is a hang, not a failure). Credentials come only from the
  environment variables `CDS_DEV_USER` and `CDS_DEV_PASS` (D14). List the
  gateways, `find_address_by_ip`, `set_gateway_and_ip_address` on the device
  node, `create_online_device` to connect, list `PlcLogic/Application`, pull
  `Application.crc` and take bytes 5 to 8. If there is a source archive, pull
  it back. Compile nothing.
- `download`: first pull the controller's current `Application.crc`, then
  `login(OnlineChangeOption.Never, False)` for a full download,
  `create_boot_application`, `start`, `logout`, then pull again. The two values
  must differ: every compile stamps a new four-byte identifier on every block
  of the boot application, so if the download really landed the value changes;
  unchanged means "no error reported but nothing was written", and the run
  counts as failed. If it landed, record the new value.
- **What is compared.** The controller's current `Application.crc`, against
  the value this project left on this controller after its last completed
  download. The record is written to `<project>.cdsint-plc.json` beside the
  project file, one entry per controller (the key is `IP:port`; a run without
  `--gateway` uses the key `project`), so one working copy can serve two rigs
  at once without them overwriting each other. Copy the project elsewhere and
  the record does not follow, which is right: it describes what this working
  copy has done.
- **The locally built boot application is not compared.** That was the
  original approach, and on the rig two independent reasons for it were
  measured and both fail (2026-09-06, 3.5.21.40 / ScriptEngine 4.2.0.0). One:
  the `.app` on the controller is 2118764 bytes and the offline build is
  2098340, with 1.68 million bytes differing; the two files are simply not the
  same thing, and their CRCs cannot be equal. Two: the offline value is not a
  property of the source; it changes whenever the project is written to.
  Pointing the device at a gateway changes it, logging in changes it, setting
  one project property changes it, and every `--project` run sets
  `cds-sync-folder`, so two `plc connect` runs a minute apart built 128DBA21
  and 59B20109. It is stable only for "a working copy nobody has touched", and
  even a byte-identical copy at a different path differs, because it comes
  from the `.compileinfo` and `.bootinfo` the IDE keeps beside the project
  file.
- **`MATCH` therefore means something narrower than it originally did: "this
  controller is still holding what cdsint put on it from this project", not
  "the controller is running this source tree".** If the project changed and
  was not downloaded again, `connect` still returns `MATCH`, because the
  controller really has not changed. Whether the project agrees with the disk
  is answered by `compare` and `verify`, which read every object; that is the
  only way of asking that does not miss "changed but not saved". There is one
  road to a stronger claim: do a source download along with the download, and
  have `connect` pull the source archive back and compare it. That is a
  separate job, not done yet.
- The report of both commands has to contain the comparison result, `MATCH`
  or `DIFFERENT`; the pipeline uses it as the gate.

A few more things. `connect` touches the device node's gateway setting only
when `--gateway` was given; without it the project's own is used, because that
is an answer somebody else set, and a read-only command should not change it
in passing. `--port` defaults to 11740. When the project has more than one
device node, both commands refuse and list the names; there is no flag to pick
one, since guessing a download target is not something that can have a default
(D7). The comparison has three answers, `MATCH`, `DIFFERENT` and `UNKNOWN`;
when either side cannot be obtained it is `UNKNOWN`; only `MATCH` exits 0,
because outside these two commands there is nothing like `verify` that turns
findings into a verdict, so the exit code itself has to be the verdict. The
local boot application and the file pulled back from the PLC are written to
`%TEMP%\cdsint\plc\<project>\`, overwritten on every run of the same project
and deleted before writing, so that a call that wrote no file cannot have the
previous run's answer read as this run's.

### 6.7 Setup flow

Three routes to the settings, one per kind of user:

1. **First run.** When `Project_export.py` or `Project_import.py` starts and
   the settings file has no `sync_folder`, it opens a folder dialog. A chosen
   folder at or below the project file's directory is written as `./...`;
   anything else (another drive, outside the project) keeps the absolute path,
   because a relative path like `..\..\` holds only as long as the project
   does not move. It writes a settings file with the single key `sync_folder`,
   creates the directory, and writes `.gitattributes` and `.gitignore`. The
   confirmation message says the other settings and their defaults are in the
   settings table of README.md. No flag can answer this dialog, so unattended
   (the `--target` form, or the `--project` form without `--sync-dir`) it
   returns `needs_input`, and the message says which file and which key to
   write beside the project, or to run an export from the menu once.
2. **Changing it later.** Open the file and edit it. No `config` command and
   no Settings window, because those are a second editor for the same file,
   and every new key would need one more row.
3. **A different folder for this run.** `--sync-dir`, semantics in 4.2.

Gone: the machine-name mismatch dialog, the version mismatch dialog, and
`--force` (4.4 says why).

---

## 7. Compatibility matrix

This section differs from the rest of the document: it is a measurement
record, not a spec. Each cell says "what somebody had verified as of that
day", so every table carries a date, and the date matters more than the
numbers; a measurement without a date means nothing.

**Compatibility matrix, as of 2026-09-06.** "verified" means there is a report
or a person's record; anything else is "should work".

| Feature | stock 3.5.21.40 | Lenze 3.24 | Lenze 4.0 | Delta 1.8 | Delta 1.10 |
|---|---|---|---|---|---|
| Menu export and import | verified | verified, in daily use | installed, not verified | verified; the k1.1.1 bug was caught on it | verified |
| Watcher does not block the IDE | verified, real clicks | should work, same 4.0.0.0 | should work | should work | verified, by a person |
| CLI export, import, build | verified, 229 objects | not verified | not verified | not verified | verified |
| Headless starts | verified | verified | not verified | not verified | verified |
| Headless opens the project and runs the engine | verified | not verified | not verified | not verified | verified |
| Headless build | verified | not verified | not verified | not verified | verified; only really compiles after a fix, see below |
| `verify --project` in one command | verified | not verified | not verified | not verified | verified |
| PLC connect, download | verified, 2026-09-06, full round on two WSL soft PLCs | not verified | not verified | not verified | not verified |

Every cell in this table is "one vendor's IDE opening its own project". One
round each was verified on 2026-09-05: stock 3.5.21.40 opening the softplc
copy, Delta 1.10 opening the Shm copy; `export`, `import`, `compare` and
`build` all exit 0, 229 objects, build 0 errors. Later the same day
`verify --project` was run once more against the same two copies, and all four
steps passed.

Details of the PLC row (2026-09-06, two WSL soft PLCs): on A and on B,
`download -y` followed by `connect` was `MATCH` exit 0; downloading twice in a
row to the same one moved the controller's value from DC848126 to CF9DD644, so
the check in 6.6 that "an unchanged value means nothing landed" holds on a real
machine; after downloading a different copy to A, the original copy's
`connect` returned `DIFFERENT` exit 1, while B was unaffected and still
`MATCH`. `connect` does not compile; one run takes 63 to 71 seconds.

**ScriptEngine 4.0.0.0's build has two traps, both measured and fixed on Delta
1.10**; Lenze 3.24, same version, should be the same (not verified). One:
`get_message_objects` has no single-argument form on 4.0.0.0; both overloads
need a severity as well. Giving only the category throws
`Value cannot be null. Parameter name: category`, and the whole build result
becomes one traceback. Two: that category also has to be holding messages at
the time; a build that recompiled nothing leaves it empty, and the same call
throws the same line. 4.2.0.0 tolerates both, which is why stock never exposed
them.

More important is the one below: **on Delta 1.10 the first `app.build()` in a
process does not really compile**. Three runs in a row in the same IDE
measured 7.4 seconds with no messages at all, 31.7 seconds with 101 warnings,
5.8 seconds with the same 101. And the `--project` form only ever gets the
first one in a process, so it used to report a clean result it had never
compiled. What it does now: if a build did not even write its own summary
line, build again; if neither did, report "this IDE produced no build output
at all" rather than 0 errors.

Opening a project across vendors is a different matter, and it now has defined
behaviour: when stock opens Delta's Shm project, the plug-in for 7 objects is
missing, all three commands exit 1, put those 7 names into
`data.failed_objects`, and finish the other 229 as normal (D13, D11). This is
not "cross-vendor supported"; it is "cross-vendor does not lie".

**Performance baseline, 229 objects, measured 2026-09-05, commit `1645a62`.**
Each cell is the median of three. What is measured is the command step's
`elapsed_s`, the number the caller sees in the report; IDE start plus project
open is not included and is listed separately below. Stock opens the softplc
copy, Delta the Shm copy, each its own vendor's project.

Conditions: before every export the sync folder is emptied, so each run writes
all 229 files from scratch; before compare one POU is changed on disk, so there
is exactly one difference; nothing is touched between the two builds.

**Whether the same machine has just run one makes a two-to-three-fold
difference; that is the most important finding of this measurement.**

| Operation | stock (machine cold) | stock (machine warm) | Delta (machine cold) | Delta (machine warm) |
|---|---|---|---|---|
| export | 33.4 s | 12.2 s | 26.6 s | 9.9 s |
| compare, one POU changed | 30.6 s | 10.9 s | 23.7 s | 8.6 s |
| build | 44.1 s | 14.8 s | 42.9 s | 16.3 s |

"Cold" is the first few runs after this machine has not started a headless IDE
for a while; the three runs differ by up to ±20% (Delta's build from 23.9 to
45.4 seconds). "Warm" is the same set run again; the three differ by under 2%.
The wall time of a whole run follows: cold, 78 to 184 seconds per run; warm,
33 to 48 seconds; the difference is the IDE start and the project open.

The difference is not the project copy or the sync folder's path: after
warming up, a fresh copy of the project was made at a path never used before
and export was run once more, still 12.1 seconds. So it is the state of the
whole machine (the OS file cache, .NET assemblies, antivirus scanning a new
path, that sort of thing), not any one file. Anyone comparing numbers needs
both sides in the same state.

An earlier set of baselines was export 59.7 / 56.6 seconds, compare 50.6 /
47.1 seconds, build 23.3 / 32.5 seconds, also 2026-09-05, also 229 objects,
but that set recorded neither whether the machine was cold or warm nor whether
the sync folder was empty, so it serves only as a reference and cannot be used
to compute an improvement.

**Before and after folding the engine's parallel paths, 229 objects, measured
2026-09-07.** Not directly subtractable from the two sets above: the machine
state differed, and this set's compare is "change one `.st` on disk" rather
than "change one POU". Its purpose is to answer one question: how much speed
was paid for folding the same rule from two copies into one. Each cell is the
median of four runs with the first dropped.

| Operation | stock 3.5.21.40 (softplc copy) | Delta 1.10 (Shm copy) |
|---|---|---|
| export | 22.9 → 24.1 s | 23.3 → 21.7 s |
| compare | 15.8 → 17.3 s | 15.3 → 15.2 s |
| build | 25.8 → 25.2 s | 30.5 → 30.5 s |

**This set of numbers has a trap, written down here so the next person does
not step in it.** The cells above were measured at different times, and the
state of the copy and the sync folder differed before each measurement, so the
error is large enough to swamp what is being measured: the same script,
measuring code that had "only had dead code deleted", also showed compare
"7.8% slower". The more usable method controls the starting point and runs old
and new code back to back: every set starts from a clean `.project` copy, an
empty sync folder, one export, and one `.st` changed. Two such paired
measurements were made, and they pointed in opposite directions: the first,
old code 16.59 seconds, new code 17.63 seconds (new 6.3% slower); the second,
new code 17.74 seconds, old code 17.96 seconds (new 1.2% faster). An hour and
a half passed between the two, and the same old code drifted from 16.59 to
17.96 seconds; the machine's own variation is 8%, the same order of magnitude
as the thing being measured. So the only thing that can be said is this: **the
difference in compare lies inside this machine's measurement error; no
identifiable slowdown was measured.** Being more certain would take several
interleaved pairs within the same hour, which this ticket did not do.

The exported `.st` and `.xml` did not change by one byte: two copies, 229
objects, measured once after each layer was done, and the 231-line list of
paths and SHA-256 hashes had the same hash from start to finish.

**A full `verify --project` run, the same 229 objects, measured 2026-09-05.**
Every step in this set is the "no differences" case (disk and IDE already
agree), so it is faster than the set above; that set stays as the baseline,
and the two cannot replace each other. IDE start plus project open is counted
separately, thirty-odd seconds for both vendors.

| Step | stock 3.5.21.40 (softplc copy) | Delta 1.10 (Shm copy) |
|---|---|---|
| import | 24.2 s | 18.4 s |
| export | 14.8 s | 14.8 s |
| compare | 13.2 s | 14.0 s |
| build | 23.5 s | 31.3 s |
| whole run (including start) | 124.6 s | 142.3 s |

---

## 8. Quality requirements

**The rules are in `PRINCIPLES.md`**; the size limits have two tiers: code
written in this repo is under the hard limit, and the moved-over `engine/` is
only required to "not let a touched function grow, and have new functions and
files respect the limit". Documentation that says something different from the
code is worse than no documentation.

**Tests come in three layers**:

| Layer | Runs where | How |
|---|---|---|
| pure functions in `cds/core` and the CLI | CI | ordinary unit tests |
| engine logic | CI | run against fake IDE objects; the stand-ins are in `tests/fakes.py` |
| real-IDE acceptance: start a project copy headless, run export, import, build, compare the output | locally, by hand or on a schedule, once per vendor | `cdsint verify --project` is that script. The `--target` half needs an open IDE; `tools/headless_watch.py` can bring one up |

**CI** runs on a push to any branch, not only `main` and `claude/**`.

**The version has one source**: `SCRIPT_VERSION` in
`engine/codesys_constants.py`. `pyproject.toml` reads that line directly with
`version = {attr = "engine.codesys_constants.SCRIPT_VERSION"}` under
`[tool.setuptools.dynamic]`, the watcher's registration file gets it passed in
by `stub/Project_watch.py`, and README.md does not state a version number.
There is no release script and none is needed: a release is changing that line
and tagging.

---

## 9. Documentation

- `README.md`: positioning, one example under ten lines for each of the three
  scenarios, install (the ScriptDir table for the three vendors), the CLI
  command table, exit codes, permissions, FAQ. The install source points at
  this repo. Whatever in `WORKFLOW.md` still holds is folded into the
  three-scenarios section.
- `skills/cdsint/SKILL.md`: the operating manual for scenario B; paths and
  command names updated with the move. Add the section on the `--project`
  form.
- `docs/SPEC.md`: this document, what it looks like when done.
- `docs/WATCHER.md`: new file. The watcher's protocol spec, the watcher spec
  and the timer design, extracted from sections 5, 6 and 14 of
  `WATCHER_CLI_PLAN.md`. The six pointers in the code that cite section
  numbers now point at it.
- `CHANGELOG.md`: one section per release, written as "symptom, root cause,
  fix", not as a file list.

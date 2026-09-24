# The watcher and the command hand-off protocol

> This document describes what is, not what is planned.
> Code comments cite it by section number, as in "WATCHER.md 6".

The watcher is a timer hung on the IDE's own message loop. On every tick it
picks up a command file; if there is one it runs it, writes the result file and
refreshes the heartbeat, and if there is none it returns at once. The script
that arms it exits immediately, so the IDE is fully usable between two commands.

---

## 1. Why files

Commands and results are JSON files on disk (SPEC D6). The IDE side runs on
IronPython 2.7 with nothing but the standard library, the CLI side on CPython 3;
files are the one thing both sides can use without installing anything extra.

## 2. Directories and the registration file

The root is `%LOCALAPPDATA%\cdsint\instances\`, overridable with the
environment variable `CDS_INSTANCES_DIR`. Each open IDE gets one subdirectory:

```
instances\
  <instance-id>.json          the instance's registration file, heartbeat included
  <instance-id>\
    cmd\                      command files the CLI writes in
    result\                   result files the watcher writes back
```

`instance-id` is "project file stem-process id", for example
`Shm_2026.07.29-14012`. The project path comes from `projects.primary.path`,
the process id from `os.getpid()`.

The registration file's fields: `instance_id`, `pid`, `ide`, `project_path`,
`project_name`, `sync_dir`, `state`, `busy_since`, `heartbeat`, `started_at`,
`watcher_version`. Times come in two copies: the string one is for a person
opening the file, and `heartbeat_epoch` and `busy_since_epoch` are for a
program to subtract. Storing numbers saves parsing a local-time string and
sidesteps the ambiguous hour around a daylight-saving change.

### 2.1 A few time constants

The code is in `cds/core/instances.py`. These four numbers are starting points,
not settled values:

| Constant | Value | Meaning |
|---|---|---|
| `HEARTBEAT_INTERVAL_S` | 2 s | how often the watcher rewrites the registration file |
| `ALIVE_TIMEOUT_S` | 10 s | how long an idle instance's heartbeat may go without an update before it counts as dead |
| `BUSY_TIMEOUT_S` | 120 s | how long a busy instance may stay busy and still count as alive; the CLI's `--timeout` overrides it |
| `STALE_TIMEOUT_S` | 60 s | at start-up, idle registration files quiet for longer than this are cleared |

**A `busy` registration file is never cleared.** "Clean up the files a dead
process left behind" and "decide that a command has run too long" are two
different things. Tied to one number, the protection only holds while a command
runs shorter than the timeout, and an import of a real project takes more than
two minutes as a matter of course. An instance stuck in `busy` is cleared by
running `Project_watch.py` again.

**Do not use `os.kill(pid, 0)` to check whether a process is alive.** On
Windows, CPython's `os.kill` terminates the target process outright. To check,
use `ctypes` and `OpenProcess`, or simply trust the heartbeat.

**How the registration file is overwritten depends on the runtime.** With
`os.replace` available, use it; the overwrite is atomic. Without it, fall back
to "delete the target, then rename", which is the path IronPython 2.7 takes. On
Windows, `os.rename` fails outright when the target exists, and the registration
file overwrites the same name every two seconds. This is also why the CLI waits
one extra tick before declaring an instance dead: between the delete and the
rename there is an instant with no file at all.

## 3. Command files and result files

A command file is named `<13-digit millisecond timestamp>-<6 random hex
digits>.json`; the watcher sorts by name and handles one at a time. The result
file has the same name and lives in `result\`.

```json
{"id": "1725453665123-a3f9c1", "command": "import",
 "args": {"yes": true}, "created_at": "..."}
```

```json
{"id": "1725453665123-a3f9c1", "ok": true, "command": "import",
 "started_at": "...", "finished_at": "...", "elapsed_s": 4.2,
 "messages": [{"level": "info", "text": "Import complete! ..."}],
 "stdout_tail": "…last 200 lines…", "error": null, "needs_input": null,
 "denied": null, "data": null}
```

- When `ok` is false, `error` always carries text.
- When the engine asked a question and the command's arguments held no answer,
  `ok` is false and `needs_input` carries the question verbatim and the flag
  to answer it with.
- `denied` only has a value when the `plc` list in the project's settings file
  blocked the command, and the watcher never runs `plc` at all (see the command
  table below), so in a result file that came through this protocol it is
  always null. It is here because both forms share one result record.
- Every write goes to `<name>.tmp` first and is then renamed to the final name;
  the reading side never sees half a file, and always ignores `.tmp`.
- The CLI deletes a result file as soon as it has read it. At start-up the
  watcher clears anything in `result\` older than an hour.

## 4. The commands

| Command | Arguments | How its dialog is answered |
|---|---|---|
| `ping` | none | none |
| `status` | none | none |
| `stop` | none | none |
| `export` | `delete_orphans`, default false | "Delete Orphaned Files?" is answered by it |
| `import` | `yes`, required | "Confirm Import" is answered by `yes`; without it, `needs_input` comes back |
| `compare` | none | none. The per-object differences are in `data.changes`, one row per object with `name`, `path` and `state`; the interactive picker window has been removed |
| `discover` | none | none. The object tree is printed to stdout; unknown type GUIDs are in `data.unknown` |
| `build` | `app`, when there is more than one application | `system.ui.choose` matches the option by the name in `app`; without it, `needs_input` comes back |
| `plc connect`, `plc download`, `plc trace` | — | The watcher always refuses, with an error that states the reason: it runs inside an IDE somebody is using, and logging in to a controller would take that person's online session away (SPEC D8). These three commands exist only in the `--project` form |

## 5. What one tick does

The code is in `cds/ide/watcher.py`, and it can be tested completely under
CPython, because it takes the IDE's globals as parameters.

1. Still running? Busy right now? `silent.running()`? If any one of the three
   holds, return at once.
2. Pick up one command file and **delete it before running it**.
3. Before running, set `state` to `busy` and write `busy_since`.
4. Run, write the result file.
5. In `finally`, write `state` back to `idle`.

**The command file is deleted before it runs.** If the watcher dies halfway
through an import, the next start-up would pick that import up and run it a
second time. Losing one result only makes the caller wait until the timeout;
running an import twice touches the project.

**No two watchers in one IDE.** The instance id is the project name plus the
process id, so two watchers in the same IDE would get the same id and fight
over the same directory. When start-up finds a live watcher already on `sys`,
it treats the run as "running it again means stop".

**Catch everything inside a tick.** An uncaught exception escaping a WinForms
tick handler becomes the IDE's thread-exception dialog, and can take the IDE
down with it.

## 6. Why a timer, not a main loop

The original design was a `while` loop with `system.delay(50)`. It makes the
IDE unclickable, and it does not look broken: the window keeps repainting,
Windows does not judge it frozen, and posted messages are still answered.
Measured with a real mouse on 2026-09-05: **`system.delay()` pumps repaints,
timers and non-input messages; mouse and keyboard are filtered out**.

| Scenario | Before the script starts | During the `system.delay(50)` loop |
|---|---|---|
| Started from the Scripts menu | the File drop-down opens | never opens |
| Started with `--runscript` | no baseline measured | never opens |

So changing how the script is started does not help. The fix is to let the
script exit and hang the work on the IDE's own message loop: `Project_watch.py`
creates a WinForms `Timer` (250 ms interval), attaches the handler and
**returns at once**. The moment the script ends the progress display goes away
and the IDE is entirely back in the user's hands.

The premise is "CODESYS's API objects still work after the script returns".
Officially warned against in 2012, so it was measured in two rounds, and both
stock SP21 (ScriptEngine 4.2.0.0) and Delta 1.10 (4.0.0.0) passed: a held
`projects.primary.path`, `get_children()`, `system.write_message` and
`system.delay` all still worked after the script returned, and even after the
user had run another script from the menu, and `__main__.projects` was still
the same object.

Real-click testing was done only on stock 3.5.21.40. Delta 1.10 had no input
measured, but the mechanism is the same and there is no separate assumption
that it would differ.

## 7. Rules of the timer design

- **State lives on an attribute of `sys`** (`sys._cds_watcher`), not in the
  script module's globals. After the script ends the module namespace is not
  guaranteed to survive; `sys` always is. The timer object lives there too, so
  it does not get collected.
- **Re-entrancy guard.** Commands like import and build pump messages, and
  while they pump, the timer ticks again. A tick checks the busy flag first.
- **No threads, no `time.sleep()`, no `execute_on_primary_thread`** (SPEC D5).
  The tick is already on the UI thread; nothing cross-thread is needed.
- **Two ways to stop**: the CLI's `stop`, and running `Project_watch.py` again.
  Both take the same tear-down: stop the timer, close the status window, delete
  the registration file and directory, clear the state on `sys`.
- **The heartbeat stays in the tick.** No heartbeat can go out while a command
  runs; the registration file's `busy` state already covers that.
- **The status window uses `Show()`, not `ShowDialog()`.** A modal window holds
  the main thread and puts the IDE right back into the state this whole design
  exists to avoid. The window is owned by the IDE's main window and is not
  TopMost, so it minimises with the IDE and does not sit on top of anyone
  else's windows.

## 8. How real-input acceptance is done

The instrument is `tools/probe_click_menu.py`: `SetForegroundWindow` plus
`mouse_event` to really click File, the leftmost entry on the menu bar, and
`EnumWindows` to count whether a drop-down window appeared. The launcher is
`tools/probe_watcher_ui.py`: it creates a temporary project, writes a settings
file beside it holding only `sync_folder`, goes through `Project_watch.py`'s
start-up path, and returns.

The procedure: start the IDE and run the launcher; the instrument clicks the
File menu every 5 seconds and requires the drop-down to open every time, while
`cdsint ping`, `export` and `stop` run from outside. The few seconds during
`export` when it will not open are expected, and it must recover afterwards;
after `stop` the registration file is gone and the menu is still clickable.

Results from 2026-09-05: stock 3.5.21.40 passed everything. On Delta 1.10 the
click instrument failed, because another window on the desktop kept grabbing
the top and `SetForegroundWindow` kept returning False, which has nothing to do
with the watcher — the menu would not open even with no script running at all.
The Delta 1.10 cell was later filled in by the user by hand: he started the
watcher from the Tools menu on his own real project and reported that the IDE
was indeed usable, while a `status` round trip measured 57 ms from outside. So
the timer design has data from a real person on both major ScriptEngine
versions, 4.0.0.0 and 4.2.0.0.

## 9. What this design cannot stop

`cds/ide/silent.py` has a module-level flag, `silent.running()`, and a tick
that sees it returns at once.

**It cannot stop a script the user starts by hand from the Scripts menu.** That
path goes through the IDE's own executor and never passes through `silent.run`,
so this module cannot see it. There is currently no known way to detect such a
script from inside the timer. What the flag actually stops is "another caller":
a second `Watcher` built somewhere else, or an MCP wrapper around the outside
later on.

## 10. The stand-in UI for unattended mode

The engine was written for a person: it asks "Confirm Import?" and waits. The
watcher answers from the command's arguments instead, and when it has no answer
it refuses loudly rather than guessing (SPEC D7). For that to hold, three things
have to be swapped:

| What gets swapped | Why |
|---|---|
| The `system` in the body's own namespace | That is the one the body reads |
| `ask_yes_no` on `sys.modules["engine.codesys_ui"]` | It opens a WinForms message box of its own, never touching `system.ui` at all |
| `show_sync_folder_dialog` on `sys.modules["engine.codesys_ui"]` | It opens the first-run folder picker of its own, which no flag can answer, so it must refuse instead |

Four pitfalls hit in the implementation:

- **If the stand-in cannot take over, nothing runs.** Nowhere in the engine
  imports `codesys_ui` at module level, and the watcher empties the whole
  engine out of `sys.modules` before every command, so at this moment
  `codesys_ui` is usually absent. `cds/ide/silent.py` therefore loads it by
  name itself; if it cannot, it returns a failed `Outcome` and not one line of
  the body runs. The reason is that the two failures look nothing alike: not
  running only fails this one command, while running leaves a WinForms dialog
  nobody can click stuck on the IDE's message loop, and the IDE does not move
  until someone walks over to that machine.

- **`NeedsInput` inherits from `BaseException`, not `Exception`.**
  `entry_build.py` wraps the whole `system.ui.choose` call in
  `except Exception`; if `NeedsInput` were an ordinary exception it would be
  swallowed, and the engine would fall back to "build the active application",
  which means the user never said which one to build and a different one got
  built silently. It is the same reason `KeyboardInterrupt` must not be eaten
  by application-level error handling.
- **`exec` must be fed bytes, not unicode.** Every body has
  `# -*- coding: utf-8 -*-`, and Python 2's `compile()` throws SyntaxError
  outright on unicode source carrying a coding declaration, and does not accept
  a BOM either.
- **The body is exec'd, not imported.** The stand-in `system` has to be in the
  body's namespace before its module-level code starts running. The menu path
  has no such need; it goes through `engine/entry.py`.

Success or failure is read from the body's return value (SPEC D11). Every path
through a body has to return a `result()` from `engine/entry.py`: `ok` is the
verdict, `summary` is the one line for a person (when `ok` is false it is also
the error message the caller gets), and `data` is this command's own counts.
Returning `None` (that is, one path forgot to return) counts as failure, with
the message "returned no result", because that is exactly the shape of
"quietly did nothing and reported success".

Message levels no longer affect the verdict, so `warning` can be used for
something worth noticing that does not abort.

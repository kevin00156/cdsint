---
name: cdsint
description: Drive a CODESYS or DIADesigner-AX IDE from the shell with the cdsint command — edit .st files, compare, import them into the IDE, build, and read the compile errors, whether or not anyone has the IDE open. Use when the user mentions CODESYS, DIADesigner, PLC Designer, a .st file, PLC/IEC 61131 code, structured text, importing into the IDE, building a PLC application, or downloading to a controller and checking what it runs (CODESYS、DIADesigner、PLC 程式、.st 檔、匯入 IDE、編譯 PLC、下載到 PLC).
---

# Driving a CODESYS IDE from the shell

CODESYS project files are binary and cannot be edited. What can be edited are the
`.st` text files in the project's sync folder; the IDE is then told to read them
back in.

There are two ways to say which IDE, and they are mutually exclusive because
CODESYS will not open one project twice:

- **`--target X`** drives the watcher inside an IDE somebody has open. Start here
  when the user is at the machine with their project up.
- **`--project P --install I`** starts an IDE of its own, runs the command and
  lets it go. This is the one for a project nobody has open.

`cdsint` is a console command, installed with `pip install -e .` from a clone of
the cdsint repo. If the command is not on PATH, ask the user where that repo is
checked out and run `python -m cdsint.cli` from it instead.

## Before anything: is an IDE listening?

```
cdsint list
```

One line per listening IDE. Nothing listed means nothing to `--target`: either ask
the user to run `Project_watch.py` once from **Tools > Scripting** (it finishes
immediately and leaves a listener behind, with the IDE still usable), or switch to
`--project` below. Never start an IDE by hand to get around it — a second instance
cannot open a project another IDE already has open, and that is what `--project`'s
lock check is for.

Find the sync folder — the only directory to edit — from:

```
cdsint status --json      # data.sync_dir
```

`null` there means the project has no `cds-sync-folder` property set. Ask the user
to set it; do not guess a path.

## The loop

```
edit .st files under sync_dir
cdsint compare            # read-only, shows what differs
cdsint import --yes       # disk wins, writes into the IDE
cdsint build              # or build --app NAME
# errors > 0 → read them, fix, go again
```

`export` runs the other way, writing the IDE's objects out as `.st`. Run it before
starting so the disk is current, or after an import to confirm it landed.

`import` refuses a sync folder with no `.st` anywhere under it, on every route
into it. Disk wins, so an empty folder would mean "this project should contain
nothing" and delete every object; the refusal names the folder. Export first, or
fix the folder you pointed at.

## Nobody has it open: `--project`

```
cdsint installs                                  # names, profiles, ScriptDirs
cdsint verify -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported --report r.json
```

`--install` takes a fragment of a name from `installs`; more than one match is
refused rather than guessed. `--sync-dir D` is required in this form: the project
you name may be a copy, and a copy carries the original's `cds-sync-folder`, which
often points into the original's own export folder. The resolved folder is the
first line of the output and the report's `sync_dir`. Also here: `--report FILE`
for the full record, `--force-lock`, `--profile NAME`, and `--answer KEY=VALUE`
for the IDE's own prompts.

`verify` is the one worth knowing: import, export, compare, build, and exit 0 only
if all four agree. It contains an import, so it takes `-y` like `import` does —
without it you get the comparison and a count of what the import would have
changed, created and deleted, `needs_input`, exit 1, and an untouched IDE. compare is what makes it mean something — import and export can
each report success having done nothing, and only asking afterwards whether the IDE
and the disk still differ turns the pair into a round trip that was checked.

Two things stop a `--project` run before it starts, both on purpose. A `.~u` lock
beside the project means something has it open: exit 4, with the lock path. And the
IDE's own prompts get no default answer — a project saved by an older IDE asks
`UpgradeProjectConfirmation`, and yes rewrites its storage format so that older IDE
can never open it again. The message names the key; the user decides.

## Talking to a controller: `plc`

```
cdsint plc connect --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
cdsint plc download -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
```

`plc download` is the only command that changes a machine, and it has two gates in
front of it. **The project has to allow it**: the property `cds-sync-plc` lists
`connect`, `download`, or both, and a command that is not listed is exit 5 with the
current value quoted back. No flag answers that one — `cdsint config set` refuses
to write this property, because its whole meaning is that a person decided in the
IDE. Ask the user to set it in **Project Information > Properties**. **And the call
has to be confirmed**: `plc download` takes `-y`, exactly as `import` does.

There is no `--target` form. The watcher runs inside an IDE somebody is using, and
a PLC login would take their online session away from them.

Both commands answer one question — is the machine running this tree — by comparing
the boot application this project compiles to against the one on the controller.
`data.crc` is `MATCH` (exit 0), `DIFFERENT` (exit 1: it is running something else)
or `UNKNOWN` (exit 1: one side could not be read, which is not agreement).
Credentials come only from `CDS_DEV_USER` and `CDS_DEV_PASS` in the environment.
`--gateway IP [--port N]` overrides the project's own gateway settings; without it
the project's are left alone.

## Reading the answer

Exit codes: `0` done, `1` failed or a flag is missing, `2` no single live IDE
matched, `3` timed out with no report to show for it (raise `--timeout`: it
bounds one step, default 120s, and big imports and builds need more), `4` the
project is open elsewhere or the IDE would not start, `5` the project's
`cds-sync-plc` does not allow this `plc` command.

A `--project` run that was killed after its report was written is not exit 3:
the report is the answer, and the exit code is the thing that went missing. The
lock file such a kill leaves behind is cleared by cdsint itself.

With `--json`: `messages` carries what the IDE would have shown a person,
`stdout_tail` carries the detail (compare's per-object list, build's error list
with line numbers), `error` explains a failure, `needs_input` names the flag that
was missing, `denied` says the project's own policy refused the command (only
`plc`, and no flag fixes it), and `data` holds this command's own numbers — the counts, and
`failed_objects` naming anything the command could not handle.

## Flags answer the questions a person would have

A question with no flag behind it comes back as `needs_input`, exit code 1, and
**nothing in the IDE is changed**. That is the design. Supply the flag named in
`needs_input.arg` and run it again — never retry unchanged, never guess.

| `arg` | flag | the question |
|---|---|---|
| `yes` | `--yes` | "change the IDE / the controller?" — required for `import`, `verify` and `plc download` |
| `force` | `--force` | version or computer mismatch; stop and ask the user instead of forcing |
| `app` | `--app NAME` | which application to build |
| `delete_orphans` | `--delete-orphans` | export found sync files with no object behind them |

## Several IDEs

With more than one listening, every command needs `--target`, taking either the
full instance id (`Shm_2026.07.29-14012`) or the project name (case-insensitive).
Without it the command exits 2 and lists the candidates.

## While a command runs, the IDE is frozen

Waiting costs the IDE nothing, but export, import and build each hold the UI thread
for seconds — that is the CODESYS object model, not a bug. Send one command at a
time and wait for it.

## Never

- Edit the `.project` file, or anything outside the sync folder.
- Import while the PLC is logged in — the tool refuses, and the IDE would reject
  every create, move and delete anyway.
- Start or close the IDE the user has open. That project is their workbench.
  `--project` starting one of its own is a different thing and is fine.
- Use `--force` when unsure. It exists to override a safety check.

## The `.st` format

Declaration and implementation are split by one marker line:

```
FUNCTION_BLOCK Counter
VAR
    count : INT;
END_VAR

// === IMPLEMENTATION ===
count := count + 1;
```

Leading `//% cds-text-sync.<key>=<value>` lines are kind and build-attribute
pragmas; leave them alone unless deliberately changing that attribute. Creating a
new `.st` file creates a new object in the IDE, at the tree position matching its
folder.

Fuller detail, including every flag and the whole result schema, is in
`docs/AI_WORKFLOW.md` in the cdsint repo.

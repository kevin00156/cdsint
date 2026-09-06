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

`null` there means the project's settings file has no `sync_folder` in it yet
(see **Settings**). Ask the user to set it; do not guess a path.

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
refused rather than guessed. `--sync-dir D` is optional: it is this run's sync
folder, overriding the settings file and never written back, which is what makes
it safe against a copy. Without it the settings file decides; with neither,
export and import come back as `needs_input`. The resolved folder is the first
line of the output and the report's `sync_dir`. Also here: `--report FILE` for
the full record, `--force-lock`, `--profile NAME`, and `--answer KEY=VALUE` for
the IDE's own prompts.

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

## Settings

Every setting for a project is one JSON file beside the project file, named
after it: `Line.project` sits next to `Line.cdsint.json`. There is no `config`
command — read and write the file. Only the keys somebody decided appear in
it; the rest take their default:

```json
{
  "plc": ["connect"],
  "sync_folder": "./sync"
}
```

| Key | Type | Default |
|---|---|---|
| `sync_folder` | string, `./` is relative to the `.project`'s directory | none — the first export asks |
| `plc` | list of `connect` and `download` | `[]` |
| `debug` | boolean — write `sync_metadata.json` and the `*.log` files | `false` |
| `export_xml` | boolean — also export visualisations and alarms as XML | `false` |
| `backup_binary` | boolean — copy the `.project` into the sync folder on export | `false` |
| `safety_backup` | boolean — back the `.project` up before an import | `true` |
| `backup_name` | string — what to call those backups | `""` |
| `backup_retention_count` | integer — how many backups to keep | `10` |
| `save_after_import`, `save_after_export` | boolean | `true` |
| `auto_delete_orphans` | boolean — delete orphaned `.st` files without asking | `false` |

A key cdsint does not know, a wrong type, a word `plc` does not recognise, or
broken JSON stops the whole command with the table in the message. Nothing is
guessed and nothing is silently ignored.

## Talking to a controller: `plc`

```
cdsint plc connect --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
cdsint plc download -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
```

`plc download` is the only command that changes a machine, and it has two gates in
front of it. **The project has to allow it**: the `plc` key in the settings file
lists `connect`, `download`, or both, and a command that is not listed is exit 5
with the file, the current list and what to add named in the message. No flag
answers that one — ask the user to add the word. **And the call has to be
confirmed**: `plc download` takes `-y`, exactly as `import` does.

There is no `--target` form. The watcher runs inside an IDE somebody is using, and
a PLC login would take their online session away from them.

Both commands answer one question — is this controller still holding what cdsint
downloaded to it from this project. `download` writes the controller's CRC into
`<project>.cdsint-plc.json` beside the project, one entry per controller, and
`connect` holds the controller against that. `data.crc` is `MATCH` (exit 0),
`DIFFERENT` (exit 1: something else has been downloaded to it since) or `UNKNOWN`
(exit 1: nothing was ever downloaded there from here, or the controller holds
nothing — neither is agreement). It does not answer "has the project changed
since": an edited POU nobody downloaded leaves the verdict at `MATCH`, and
`compare` and `verify` are the commands that read every object to answer that.
Credentials come only from `CDS_DEV_USER` and `CDS_DEV_PASS` in the environment.
`--gateway IP [--port N]` overrides the project's own gateway settings; without it
the project's are left alone.

## Reading the answer

Exit codes: `0` done, `1` failed or a flag is missing, `2` the command line
itself is wrong — flags that do not go together, or no single live IDE matched
— so change what you typed rather than running it again, `3` timed out with no
report to show for it (raise `--timeout`: it bounds one step, default 120s, and
big imports and builds need more), `4` the project is open elsewhere, the IDE
would not start, or `--install` matched no IDE (it lists what there was), `5`
the `plc` list in the project's settings file does not allow this command.

A `--project` run that was killed after its report was written is not exit 3:
the report is the answer, and the exit code is the thing that went missing. The
lock file such a kill leaves behind is cleared by cdsint only when there was no
lock file before the run started — `--force-lock` says "go ahead anyway", not
"that lock is mine", so a lock that was already there may belong to an IDE that
really does have the project open. In that case the lock stays, `notes` says
why, and the next run needs `--force-lock` again.

With `--json`: `messages` carries what the IDE would have shown a person,
`data` carries the counts and the lists behind them (compare's `changes`, one
row per object with `name`, `path` and `state`; discover's `unknown`),
`stdout_tail` carries what the script printed on the way (build's error list
with line numbers is there; compare's is not, and a run that worked has no
tail at all), `error` explains a failure, `needs_input` names the flag that
was missing, `denied` says the project's own policy refused the command (only
`plc`, and no flag fixes it), and `failed_objects` in `data` names anything
the command could not handle.

A `--project` record carries `notes` as well: what the launcher had to say
about the run rather than about the work — a lock file it cleared, an IDE it
had to kill, an exit code it cannot vouch for. Every step of a `verify`
carries the same list, so reading any one of them is enough.

When `failed_objects` is not empty, run `cdsint discover` next. It walks the
same tree and reports `data.unknown` — every type GUID no kind in
`profiles/default.json` claimed, with an example object's name. Append each
GUID to the matching kind's list under `guid_aliases` in that file (first
entry is the primary GUID, the rest are aliases other CODESYS versions emit),
then run `discover` again and the command that failed after it. No code
change is involved.

export adds `data.pending_import`: files you edited on disk and have not
imported yet. It does not overwrite those, and the run is not ok. That is not
an error — run `import` first, or delete the file if you do not want the edit.

## Flags answer the questions a person would have

A question with no flag behind it comes back as `needs_input`, exit code 1, and
**nothing in the IDE is changed**. That is the design. Supply the flag named in
`needs_input.arg` and run it again — never retry unchanged, never guess.

| `arg` | flag | the question |
|---|---|---|
| `yes` | `--yes` | "change the IDE / the controller?" — required for `import`, `verify` and `plc download` |
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

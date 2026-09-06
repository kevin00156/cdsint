# cdsint

**The `.st` text files on disk are the truth about a PLC project. cdsint moves
them in and out of the CODESYS-family IDEs, drives those IDEs, and checks the
result — from outside, where a script or an agent can reach it.**

A CODESYS `.project` file is binary. What you can edit, diff, review and commit
is the text beside it. cdsint keeps the two in step and lets you say so from a
terminal: export the project to text, edit the text, import it back, build, read
the errors. It works whether the IDE is open in front of you or not open at all.

The code came out of
[`kevin-cds-text-sync`](https://github.com/kevin00156/cds-text-sync), which is
itself a fork of [ArthurkaX/cds-text-sync](https://github.com/ArthurkaX/cds-text-sync);
that repo holds the history up to the move.

> **Early days.** No published release yet, so the one-line installer has
> nothing to download — clone the repo and point the installer at it, below.
> The version number lives in one place, `engine/codesys_constants.py`;
> `pip show cdsint` reads it from there.

---

## What it needs

- Windows, and one of: CODESYS 3.5 SP17 to SP21, Lenze PLC Designer 3.24 or 4.0,
  Delta DIADesigner-AX 1.8 or 1.10.
- Python 3.11 or later, for the `cdsint` command. Nothing else — no pip
  dependencies on either side.
- Inside the IDE it uses only the IronPython 2.7 the IDE already ships.

## Three ways it gets used

### An engineer, with the IDE open

Open the project, run **Project_export** once from **Tools > Scripting >
Scripts**, and pick a sync folder when it asks. From then on the `.st` files
beside your project are yours to edit in whatever editor you like, and
**Project_import** reads them back. Run **Project_watch** once and the same
things work from a terminal, with the IDE still usable between commands:

```
cdsint compare              # what differs, changes nothing
cdsint import --yes         # disk wins
cdsint build                # 0 errors, 101 warnings
```

### A team, through git

The sync folder is the thing under version control; the `.project` binary is the
hardware and HMI, owned by whoever maintains those. A developer pulls `main`,
edits `.st`, imports, builds, and opens a pull request on the text. The reviewer
reads a diff instead of a binary. Whoever owns the project file merges, exports
once, and everyone pulls.

### A pipeline, with nothing open

No IDE, no person. cdsint starts one, drives it and lets it go:

```
cdsint installs                                     # what is on this machine
cdsint verify -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported --report r.json
```

`verify` imports the text, exports it back, checks the IDE and the disk still
agree about every object, and builds. Exit 0 means all four held.

Two flags are worth a sentence. `-y` confirms the import, the same way `import`
needs it: without it `verify` compares, prints what the import would have
changed, created and deleted, and stops without touching the IDE. `--sync-dir`
says "use this folder for this run": it overrides the `sync_folder` in the
project's settings file and is never written back, which is what makes it safe
to point at a copy. Leave it out and the settings file decides; with neither,
export and import say so and change nothing. The folder that run treated as
the truth is the first line of the output and the `sync_dir` field of the
report.

## Install

Two things get installed and they are independent: the `cdsint` command, and
the stubs the IDE's Scripts menu scans. A third, optional, is the skill file
that teaches Claude Code how to drive the command.

### The command

```
git clone https://github.com/kevin00156/cdsint
cd cdsint
python -m pip install -e .
cdsint --help
```

### The skill, if you use Claude Code

```
npx skills add kevin00156/cdsint
```

That reads `skills/cdsint/SKILL.md` straight out of this repo — there is no
separate package. It is what an agent reads before it starts editing `.st`
files: the loop, how to read a result, and what never to do.

### The IDE half

The IDE finds scripts by scanning one directory tree for `.py` files and putting
every one of them in **Tools > Scripting > Scripts**. So only the stubs go there;
the code they call lives in your clone.

The installer does both halves of that — it finds every IDE on the machine,
junctions each one's ScriptDir onto `stub\`, and writes the clone's path into
`stub\body.path`:

```powershell
.\irm\setup.ps1 -Clone .
```

Run it from an elevated shell to include Delta, whose ScriptDir is inside
Program Files; it says which ones it skipped otherwise. `.\irm\setup.ps1 -List`
shows what it found without touching anything, and `irm/setup.md` has the rest
of the options.

<details>
<summary>By hand, if you would rather</summary>

Write the clone's path — one line, no trailing slash, no BOM — into a file
called `body.path` next to the stubs:

```powershell
[System.IO.File]::WriteAllText("stub\body.path", (Get-Location).Path, `
    (New-Object System.Text.UTF8Encoding($false)))
```

Then point the IDE's ScriptDir at `stub\` with an NTFS junction. **Which
directory that is depends on the IDE**, and getting it wrong is the usual reason
nothing shows up in the menu — `cdsint installs` prints the right one per IDE:

| IDE | ScriptDir |
|---|---|
| CODESYS 3.5 SP17–SP21 (all versions share one) | `%LOCALAPPDATA%\CODESYS\ScriptDir` |
| Lenze PLC Designer 4.0 | `%LOCALAPPDATA%\PLCDesigner\ScriptDir` |
| Lenze PLC Designer 3.24 | `C:\ProgramData\PLCDesigner\ScriptDir` |
| Delta DIADesigner-AX 1.8, 1.10 | `<install dir>\CODESYS\ScriptDir` — needs an admin shell |

```
mklink /J "%LOCALAPPDATA%\CODESYS\ScriptDir\cdsint" "C:\path\to\cdsint\stub"
```

</details>

Restart the IDE. **Tools > Scripting > Scripts** should now list three entries:
`Project_export`, `Project_import`, `Project_watch`.

### Coming from kevin-cds-text-sync

Four things moved, and none of them migrate themselves:

- **The junction.** The old one points the ScriptDir at the whole
  `kevin-cds-text-sync` clone, which is why that IDE shows eleven menu
  entries. Remove it before adding the new one, or the menu carries both sets
  and you cannot tell which is running. `cdsint installs` prints each IDE's
  ScriptDir; the junction to delete is the `cds-text-sync` folder inside it.
- **The running watcher.** Stop it — run `Project_watch` a second time in the
  IDE that has it — before starting the new one. The instance directory moved
  from `%LOCALAPPDATA%\cds-text-sync\instances` to
  `%LOCALAPPDATA%\cdsint\instances`, so `cdsint list` cannot see the old one
  and cannot stop it for you.
- **The command name.** `python cli/cds_ide.py` is now `cdsint`.
- **A toolbar button, if you made one.** It is bound to a script by the name
  the ScriptEngine registered, and the ScriptDir subfolder changed from
  `cds-text-sync` to `cdsint`. Whether that breaks the binding has not been
  measured either way; if the button stops doing anything, remove it and add
  it again from the new entry.

**Where the settings live.** They used to be project properties inside the
`.project` file. They are a text file beside it now (see **Settings**). The
old properties are no longer read; they stay in the `.project` untouched and
nothing removes them, and nothing is migrated out of them.

That last part has a consequence worth reading twice: **a setting somebody
turned off in the old properties comes back on.** Every key falls back to the
default in the Settings table until the new file says otherwise. On a project
whose old save-after-export property was set to `False`, for instance, an export
now saves the project when it used to leave the file alone — measured on
softplc_refactor.project, 2026-09-06, where that save also changed what
`discover` counts in the project tree (407 nodes before, 402 after: five alarm
groups). Nothing cdsint writes causes that; it is what the IDE's own save does
to that project. Look at the old properties once, in the IDE, and write the
ones you had chosen into the new file.

A project already set up is also asked for its sync folder once more, on its
next export, and that answer goes into the new file.

## The commands

Every command that touches a project takes one of two forms, and never both:

- `--target X` drives the watcher inside an IDE somebody has open. `X` is an
  instance id or a project name, and it can be left out when only one IDE is
  listening.
- `--project P --install I` starts an IDE of its own, does the work and lets it
  go. `I` is a name from `cdsint installs`.

| Command | `--target` | `--project` | What it does |
|---|---|---|---|
| `installs` | — | — | the IDEs on this machine, with profile names and ScriptDirs |
| `list` | — | — | which IDEs are listening; it asks about this machine, not about one IDE |
| `ping`, `status`, `stop` | yes | — | one listener's lifecycle |
| `export [--delete-orphans]` | yes | yes | write the project out as `.st` |
| `import -y` | yes | yes | read the `.st` back in, disk wins |
| `compare` | yes | yes | list what differs, change nothing |
| `discover` | yes | yes | name every object and the kind it counted as; run it when something reports `failed_objects` |
| `build [--app NAME]` | yes | yes | compile, report the errors |
| `verify -y` | yes | yes | import, export, compare and build, all four or nothing |
| `plc connect [--gateway IP --port N]` | — | yes | is the controller still holding the last download from here |
| `plc download -y` | — | yes | download to the controller, read the CRC back, write it down |

Shared flags: `--timeout SECONDS` (default 120) is how long **one step** may
take, in both forms; with `--project` the deadline for the whole process is
derived from it — a launch allowance, plus that many seconds per step, plus a
shutdown allowance — so a four-step `verify` waits well past 120 seconds.
`--json` prints the raw record. A `--project` run's record carries four
fields the other form has no use for: `ide`, `sync_dir`, `report_path`, and
`notes` — what the launcher had to say about the run rather than about the
work, such as a lock file it cleared or an exit code it cannot vouch for.
They are in the record and not only on stderr because the caller reading
the JSON is exactly the one who needs to hear about a cleared lock.
Only with `--project`: `--sync-dir D` (optional — this run's sync folder,
overriding the settings file and never written back), `--profile NAME` when an
install has several, `--report FILE`, `--force-lock`, and `--answer KEY=VALUE`
(repeatable) for the IDE's own prompts.

There is no `config` command. The settings are a text file next to the
project; **Settings** below is the whole of it.

**Every dialog of cdsint's own is answered by a flag, never guessed.** A question
with no flag behind it comes back as `needs_input` naming the flag you need, exit
code 1, and nothing in the IDE changed.

### When something reports `failed_objects`

That list names objects the command could not handle, and the run is not ok.
The usual cause is a type GUID this build of CODESYS emits that
`profiles/default.json` does not know: `classify_object` recognises nothing,
so the object is exported nowhere and counted nowhere.

`cdsint discover` is the diagnostic. It walks the same tree, prints it, and
names every type GUID no kind claimed:

```
cdsint discover
cdsint discover --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported --json
```

The fix is a JSON edit, not a code change: append the GUID to the matching
kind's list under `guid_aliases` in `profiles/default.json` (the first GUID in
each list is the primary one; the rest are aliases other CODESYS versions
emit), then run `discover` again and the export after it.

`data.total` counts every object in the tree, so it is larger than the number
of files an export writes — property accessors, tasks and device modules are
skipped on purpose, and an object that vanished is only visible if they are
counted too. On one 229-file project `discover` reports 407.

### Three lines you cannot cross by accident

Disk wins. That cuts both ways: an import reads the sync folder as the answer to
"what should this project contain", and an export must not scribble over that
answer. Three situations are therefore refused rather than measured:

- **An empty sync folder.** No `.st` anywhere under it is not the answer
  "nothing" — it is a folder nobody has exported to, or the wrong folder — so
  `import` refuses it on all three routes (Scripts menu, `--target`,
  `--project`) instead of deleting every object in the project.
- **A copy that remembers where the original synced.** `--project` therefore
  requires `--sync-dir`, and the resolved folder is printed first and written
  into the report as `sync_dir`.
- **A file you edited and have not imported.** `export` leaves it alone, names
  it in `data.pending_import`, and the run is not ok. Run `import` first, or
  delete the file if you did not want the edit. This one only applies when the
  sync folder has been synced from this machine before: the answer comes from
  `sync_cache.json`, which is local and gitignored, so a fresh clone has no
  record to compare against and the first export there writes.

`verify` contains an import, so it needs `-y` exactly as `import` does. Without
it you get the comparison, the count of what the import would have changed,
created and deleted, `needs_input`, exit 1, and an untouched IDE.

### Talking to a controller

`plc download` is the only command that changes a machine, so it is the only
one with a permission layer in front of it, and the layer has two parts that
cannot stand in for each other.

- **The project has to allow it.** The `plc` key in the project's settings
  file is a list, and it recognises exactly `connect` and `download`:

  ```json
  { "plc": ["connect", "download"] }
  ```

  A command that is not in the list comes back as exit 5, and the message
  names the file, what the list holds now, and what to add. This is a policy,
  not a wall — whoever can write the file can write this key — so the gate
  that actually stops a download is the `-y` below.
- **This call has to be confirmed.** `plc download` needs `-y`, the same `-y`
  as `import` and `verify`. Without it: what the download would do,
  `needs_input`, exit 1, controller untouched.

`plc` has no `--target` form at all. The watcher lives inside an IDE somebody
is using, and a PLC login would take their online session away from them, so a
PLC command always starts an IDE of its own.

Both commands end in the same comparison: the CRC the controller reports now,
against the one it reported right after the last `plc download` from this
project, kept in `<project>.cdsint-plc.json` beside the project, one entry
per controller. `MATCH` is the only answer that exits 0 — it means the
controller still holds what cdsint last put on it from here. `DIFFERENT`
means something else has been loaded since. `UNKNOWN` means there is no
record for this controller (never downloaded from this machine, or the
project was copied without its record) or its CRC could not be read, which
is not the same as agreement. Whether the *source* on disk still matches the
project is `compare`'s question, not this one's; a boot application built
offline changes its CRC on every compile, so it cannot serve as that answer.

Credentials come from `CDS_DEV_USER` and `CDS_DEV_PASS` in the environment,
never from a flag, a file or the report.

Both commands are built and were run end to end on 2026-09-06, against two
CODESYS Control soft PLCs under WSL, driven by CODESYS 3.5.21.40. No Lenze or
Delta controller has been tried, and the two ways of switching the credential
dialog off have only been checked on ScriptEngine 4.2.0.0 — on a version with
neither, `connect` refuses rather than hanging.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | the command failed, or it needs a flag you did not give |
| 2 | the command line itself is wrong: flags that do not go together, or no single live IDE matched |
| 3 | timed out with nothing to show for it |
| 4 | the project is open elsewhere, `--install` matched no IDE, or the IDE would not start |
| 5 | the `plc` list in the project's settings file does not allow this command |

## Settings

Every setting for a project lives in one JSON file beside the project file,
named after it: `Line.project` sits next to `Line.cdsint.json`. Any editor
opens it, no IDE needed. It is a separate file from the download record
`Line.cdsint-plc.json`, because one is what a person decided and the other is
what a machine wrote down.

Only the keys somebody has decided appear in it. Everything else takes the
default below, and that default lives in one place in the code — so a file
like this is complete:

```json
{
  "plc": ["connect"],
  "sync_folder": "./sync"
}
```

| Key | Type | Meaning | Default |
|---|---|---|---|
| `sync_folder` | string | where the `.st` files live. Starting with `./` it is relative to the directory holding the `.project`; anything else is used as written | none — the first export asks |
| `plc` | list of strings | which PLC commands this project allows; only `connect` and `download` are recognised | `[]` |
| `debug` | boolean | write `sync_metadata.json` and the `*.log` files | `false` |
| `export_xml` | boolean | also export visualisations, alarms and text lists as XML | `false` |
| `backup_binary` | boolean | copy the `.project` into the sync folder on export | `false` |
| `safety_backup` | boolean | back the `.project` up before an import | `true` |
| `backup_name` | string | what to call those backups; empty means the project's own filename | `""` |
| `backup_retention_count` | integer | how many timestamped backups to keep | `10` |
| `save_after_import` | boolean | save the project after an import | `true` |
| `save_after_export` | boolean | save the project after an export | `true` |
| `auto_delete_orphans` | boolean | delete `.st` files with no object behind them, without asking | `false` |

**A file that is wrong stops the command.** A key cdsint does not know, a
value of the wrong type, a word `plc` does not recognise, broken JSON — any of
them and the whole command refuses, with the table above in the message. The
file is edited by hand, so a typo will happen; a setting that quietly does
nothing is worse than one that says so.

The first export or import of a project that has no file yet asks where the
sync folder goes and writes it — that one key, nothing else. With nobody at
the keyboard there is no dialog to answer, so the command comes back saying
which file to write and what to put in it.

## FAQ

**Nothing appears in the Scripts menu.** The ScriptDir differs per vendor; run
`cdsint installs` and compare with where the junction went.

**`cdsint list` says nobody is listening.** Run **Project_watch** once from the
Scripts menu. It arms a timer and returns immediately — the IDE is yours again
straight away. Running it a second time stops the listener.

**A `--project` run says the project is open in another process.** Something has
it open and CODESYS will not open it twice. Close that, or pass `--force-lock` if
you know the lock file is stale.

**A `--project` run stops on a prompt.** The IDE asks its own questions, and
cdsint does not answer them for you — a project saved by an older IDE asks
`UpgradeProjectConfirmation`, and saying yes rewrites its storage format so the
older IDE can never open it again. The keys are printed; answer the one you mean
with `--answer UpgradeProjectConfirmation=Yes`.

**Where do the settings live?** In a text file beside the project — see
**Settings**.

## Sync pragmas in `.st` files

An exported file may start with one or more `//% cds-text-sync.<key>=<value>`
lines. They carry what the ST text alone cannot say, and import reads them back:

- **`kind=<kind>`** is written only for kinds the text cannot express on its
  own — persistent GVLs, parameter lists, actions, interface methods. Without
  it, importing the file into a project that does not already have the object
  would recreate it as a guessed POU instead of the right kind.
- **`exclude_from_build`**, **`link_always`**, **`external_implementation`**
  and **`enable_system_call`** are the IDE's build attributes, the ones under
  an object's **Properties > Build**. They sync both ways: delete the line on
  disk and the next import clears the flag in the IDE.

Pragmas are stripped before content is compared, so a file that has none stays
in sync with no noise. Leave them alone unless you mean to change that
attribute.

## Type profiles (`profiles/default.json`)

Object-type GUIDs and per-kind policy live in this JSON file, next to the code
rather than in it, so teaching the engine about a new IDE build is an edit
rather than a change:

- **`guid_aliases`** maps each kind (`pou`, `gvl`, `persistent_gvl`, ...) to
  one or more GUIDs. The **first** is the primary one, used when creating an
  object; the rest are aliases — the different GUIDs other CODESYS versions
  emit for the same kind. When `cdsint discover` reports an unknown GUID,
  append it to the matching kind's list and run again. The sync cache rebuilds
  itself.
- **`sync_direction`** is the per-kind policy: `bidirectional` (the default),
  `export_only` (written to disk so git can see it, never read back or deleted
  from the IDE — the Library Manager is one), `import_only`, or `disabled`
  (invisible to sync, which is where `device` and `device_module` sit).

## `tools/`

Offline instruments for whoever maintains this. None of them is a cdsint
command and none appears in the Scripts menu (PRINCIPLES 12). Every `.py` in
that directory is listed here; `tests/test_tools_are_documented.py` fails if
one is added and this list is not.

Three of them run **inside** an IDE, through **Tools > Scripting > Execute
Script File** or `--runscript`. The rest are ordinary CPython you run from a
shell.

**`tools/call_tree.py`** builds a cross-file call graph from an exported sync
folder. Plain CPython, no IDE:

```
python tools/call_tree.py <sync-dir> MAIN -o call_tree.json
```

It follows calls between project functions and function-block methods across
files, including instances declared in GVLs, tags IEC system calls from
`tools/sys_funcs.json`, and marks whatever it could not resolve.
**`tools/call_tree_parse.py`** and **`tools/call_tree_resolve.py`** are its two
halves — reading `.st` text, and resolving names to definitions. Import them
if you want the pieces; run `call_tree.py`.

**`tools/cache_doctor.py`** answers "would the cache actually skip anything on
the next run?" without opening the IDE, and names the reasons it would not:

```
python tools/cache_doctor.py <sync-dir>
```

**`tools/perf_probe.py`** wraps the real engine functions and ranks where a
sync spends its time. Runs inside an IDE that has the project open: **Execute
Script File**, then pick the file. With no argument it profiles an export;
`compare` and `import` are the other two modes, given in the script-arguments
box. The report goes to `perf_probe_<mode>.txt` in the sync folder. Run the
same mode twice — the second run is the one that says whether the cache is
earning its keep.

**`tools/headless_watch.py`** opens a project in a headless IDE and arms the
watcher in it, so that `--target` has something to talk to without a person
opening the IDE. Runs inside the IDE it starts:

```
<exe> --profile="<name>" --noUI --runscript="<abs path>\tools\headless_watch.py"
```

with `CDSINT_WATCH_PROJECT` naming the `.project`, and optionally
`CDSINT_WATCH_SYNC` and `CDSINT_WATCH_ANSWERS` (`KEY=VALUE,KEY=VALUE`). Under
`--noUI` it parks the process with `system.delay()` — SPEC D5's one stated
exception, and it refuses to park when the IDE has a window.

**`tools/probe_watcher_ui.py`** is the acceptance launcher behind
`docs/WATCHER.md` 8: it builds a throwaway project, arms the watcher the way
**Project_watch** does, and returns, so that somebody can check the IDE is
still clickable. Runs inside the IDE, same `--runscript` shape.

**`tools/probe_click_menu.py`** is the other half of that acceptance, and the
only tool that drives an IDE from outside it: real mouse clicks on the File
menu, counting whether a drop-down appeared.

```
python tools/probe_click_menu.py --pid 1234 --seconds 60 --every 5
```

**`tools/_root.py`** is not an instrument. It puts the install root on
`sys.path` so the others can import `engine/` and `cds/`; the underscore is
what keeps it out of this list.

## Layout

```
engine/     the sync engine and the bodies behind the menu entries.
            IronPython 2.7, standard library only.
cds/core/   the file protocol the IDE and the CLI talk over. Pure Python,
            runs on both sides, fully unit-tested.
cds/ide/    the listener, the stand-in UI, the status window, the IDE side of
            the headless launcher.
stub/       the three small files the IDE's menu scans.
cdsint/     the `cdsint` command. CPython 3.11+.
tools/      the maintainer's instruments; every one of them is listed
            under `tools/` above.
profiles/   object-type GUIDs and per-kind sync policy, as JSON.
skills/     the manual an agent reads: skills/cdsint/SKILL.md.
docs/       SPEC.md is what it should be; WATCHER.md is how the listener works.
```

## Documentation

- [`docs/SPEC.md`](docs/SPEC.md) — the product spec: what this is for, every
  decision and why.
- [`docs/WATCHER.md`](docs/WATCHER.md) — the listener and the command protocol.
- [`docs/AI_WORKFLOW.md`](docs/AI_WORKFLOW.md) — the loop for an agent driving
  this without a screen.
- [`skills/cdsint/SKILL.md`](skills/cdsint/SKILL.md) — the same thing packaged
  for Claude Code; `npx skills add kevin00156/cdsint` installs it.
- [`CHANGELOG.md`](CHANGELOG.md) — what changed and why, per release.
- [`PRINCIPLES.md`](PRINCIPLES.md) — the rules the code is held to.

## Licence

MIT. Copyright belongs to Arthur, the upstream author; see [`LICENSE`](LICENSE).

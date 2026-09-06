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

> **Early days.** Version 0.0.1, no published release yet, so the one-line
> installer has nothing to download — clone the repo and point the installer at
> it, below. The PLC commands (`plc connect`, `plc download`) are not built yet.

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

Two flags are not decoration. `-y` confirms the import, the same way `import`
needs it: without it `verify` compares, prints what the import would have
changed, created and deleted, and stops without touching the IDE. `--sync-dir`
is required in this form, because the project you point at may be a copy whose
`cds-sync-folder` still names the original's folder — and an export would then
write there. The folder that run treated as the truth is the first line of the
output and the `sync_dir` field of the report.

## Install

### The command

```
git clone https://github.com/kevin00156/cdsint
cd cdsint
python -m pip install -e .
cdsint --help
```

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
| `list`, `ping`, `status`, `stop` | yes | — | the listeners' lifecycle |
| `export [--delete-orphans]` | yes | yes | write the project out as `.st` |
| `import -y [--force]` | yes | yes | read the `.st` back in, disk wins |
| `compare` | yes | yes | list what differs, change nothing |
| `discover` | yes | yes | name every object and the kind it counted as; run it when something reports `failed_objects` |
| `build [--app NAME]` | yes | yes | compile, report the errors |
| `verify -y [--force]` | yes | yes | import, export, compare and build, all four or nothing |
| `config get [KEY]`, `config set KEY=VALUE` | yes | yes | the project's `cds-sync-*` settings |
| `plc connect [--gateway IP --port N]` | — | yes | is the controller still holding the last download from here |
| `plc download -y` | — | yes | download to the controller, read the CRC back, write it down |

Shared flags: `--timeout SECONDS` (default 120) is how long **one step** may
take, in both forms; with `--project` the deadline for the whole process is
derived from it — a launch allowance, plus that many seconds per step, plus a
shutdown allowance — so a four-step `verify` waits well past 120 seconds.
`--json` prints the raw record.
Only with `--project`: `--sync-dir D` (required — see below), `--profile NAME`
when an install has several, `--report FILE`, `--force-lock`, and
`--answer KEY=VALUE` (repeatable) for the IDE's own prompts.

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

- **The project has to allow it.** The project property `cds-sync-plc` is a
  comma-separated list, and it recognises exactly `connect` and `download`. A
  command that is not in it comes back as exit 5 with the property's current
  value quoted at you. Only a person can change that — set it in **Project
  Information > Properties**. `cdsint config set` refuses to write this one
  property, because the whole meaning of it is that somebody decided in the
  IDE.
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

### Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | the command failed, or it needs a flag you did not give |
| 2 | no single listening IDE matched |
| 3 | timed out with nothing to show for it |
| 4 | the project is open elsewhere, or the IDE would not start |
| 5 | the project's `cds-sync-plc` does not allow this `plc` command |

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

**A sync says the version does not match.** The tool that wrote the sync folder
was a different version from this one. `--force` goes ahead anyway; without it
nothing is changed.

**Where do the settings live?** In the project's own properties, prefixed
`cds-sync-`. Read and write them with `cdsint config`, from the **Settings**
button on the watcher's status window, or by hand in **Project Information >
Properties**.

## Layout

```
engine/     the sync engine and the bodies behind the menu entries.
            IronPython 2.7, standard library only.
cds/core/   the file protocol the IDE and the CLI talk over. Pure Python,
            runs on both sides, fully unit-tested.
cds/ide/    the listener, the stand-in UI, the status window, the IDE side of
            the headless launcher.
stub/       the fifteen-line files the IDE's menu scans.
cdsint/     the `cdsint` command. CPython 3.11+.
tools/      offline diagnostics: call tree, cache doctor, perf probe.
profiles/   object-type GUIDs and per-kind sync policy, as JSON.
docs/       SPEC.md is what it should be; WATCHER.md is how the listener works.
```

## Documentation

- [`docs/SPEC.md`](docs/SPEC.md) — the product spec: what this is for, every
  decision and why.
- [`docs/WATCHER.md`](docs/WATCHER.md) — the listener and the command protocol.
- [`docs/AI_WORKFLOW.md`](docs/AI_WORKFLOW.md) — the loop for an agent driving
  this without a screen.
- [`CHANGELOG.md`](CHANGELOG.md) — what changed and why, per release.
- [`PRINCIPLES.md`](PRINCIPLES.md) — the rules the code is held to.

## Licence

MIT. Copyright belongs to Arthur, the upstream author; see [`LICENSE`](LICENSE).

# cdsint

**The `.st` text files on disk are the truth about a PLC project. cdsint moves
them in and out of the CODESYS-family IDEs, drives those IDEs, and checks the
result — from outside, where a script or an agent can reach it.**

A CODESYS `.project` file is binary. What you can edit, diff, review and commit
is the text beside it. cdsint keeps the two in step and lets you say so from a
terminal: export the project to text, edit the text, import it back, build, read
the errors. The IDE stays usable the whole time.

The code came out of
[`kevin-cds-text-sync`](https://github.com/kevin00156/cds-text-sync), which is
itself a fork of [ArthurkaX/cds-text-sync](https://github.com/ArthurkaX/cds-text-sync);
that repo holds the history up to the move.

> **Early days.** Version 0.0.1. There is no published release yet, so the
> one-line installer has nothing to download — clone the repo and point the
> installer at it, below. The headless mode (driving an IDE that is not open)
> is not in this repo yet either.

---

## What it needs

- Windows, and one of: CODESYS 3.5 SP17 to SP21, Lenze PLC Designer 3.24 or 4.0,
  Delta DIADesigner-AX 1.8 or 1.10.
- Python 3.11 or later, for the `cdsint` command. Nothing else — no pip
  dependencies on either side.
- Inside the IDE it uses only the IronPython 2.7 the IDE already ships.

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

Run it from an elevated shell to include Lenze 3.x and Delta, whose ScriptDirs
are outside your profile; it says which ones it skipped otherwise.
`.\irm\setup.ps1 -List` shows what it found without touching anything, and
`irm/setup.md` has the rest of the options.

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
nothing shows up in the menu:

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

## Using it

### From the IDE

Open a project and run **Project_export**. The first time it will ask where the
sync folder should go; everything after that is one click. **Project_import**
reads the text back in, disk wins.

The other settings live in the project's own properties. Change them from the
**Settings** button on the watcher's status window, or by hand in **Project
Information > Properties**.

### From a terminal

Run **Project_watch** once from the Scripts menu. It arms a timer and ends
immediately — the IDE is yours again straight away — and leaves a listener
behind. Run it a second time to stop it.

Then, from any shell:

| Command | What it does |
|---|---|
| `cdsint list` | which IDEs are listening |
| `cdsint ping` | is this one answering |
| `cdsint status` | what it has open, and where its sync folder is |
| `cdsint export [--delete-orphans]` | write the project out as `.st` |
| `cdsint import --yes [--force]` | read the `.st` back in, disk wins |
| `cdsint compare` | list what differs, change nothing |
| `cdsint build [--app NAME]` | compile, report the errors |
| `cdsint stop` | shut the listener down |

Shared flags: `--target X` picks one IDE by instance id or project name (needed
once more than one is listening), `--timeout SECONDS` (default 120), `--json`
for the raw record.

**Every dialog is answered by a flag, never guessed.** A question with no flag
behind it comes back as `needs_input` naming the flag you need, exit code 1, and
nothing in the IDE changed.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | the command failed, or it needs a flag you did not give |
| 2 | no single listening IDE matched |
| 3 | timed out waiting for the answer |

## Layout

```
engine/     the sync engine and the bodies behind the menu entries.
            IronPython 2.7, standard library only.
cds/core/   the file protocol the IDE and the CLI talk over. Pure Python,
            runs on both sides, fully unit-tested.
cds/ide/    the listener, the stand-in UI, the status window.
stub/       the ten-line files the IDE's menu scans.
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

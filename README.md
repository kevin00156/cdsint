# cdsint

**Let an agent work on a CODESYS project.** A `.project` file is binary; cdsint
keeps the `.st` text beside it in step with the IDE, and drives the IDE from a
terminal, so an agent can edit the text, import it, build, and read the errors,
whether the IDE is open in front of you or not open at all.

## What it needs

- Windows, and one of: CODESYS 3.5 SP17 to SP21, Lenze PLC Designer 3.24 or 4.0,
  Delta DIADesigner-AX 1.8 or 1.10.
- Python 3.11 or later on PATH.

## Install

The command, and an entry in every IDE's **Tools > Scripting > Scripts** menu,
in one line of PowerShell:

```powershell
irm https://raw.githubusercontent.com/kevin00156/cdsint/main/irm/setup.ps1 | iex
```

Run it from an elevated shell to include Delta, whose script folder is inside
Program Files. Restart any IDE that was open.

The skill that teaches Claude Code how to drive it:

```
npx skills add kevin00156/cdsint
```

`cdsint update` fetches the newest release later; `cdsint link` adds an IDE
installed after cdsint was.

## What it does

- **Edit PLC code as text.** Export the project to `.st` files, edit them, import
  them back, build, and get the compile errors. The text goes into git and
  pull requests like any other source.
- **Libraries and EtherCAT settings as text.** The Library Manager and every
  EtherCAT device's parameters and IO mapping are plain files an agent edits
  and imports.
- **Work with the controller.** Download to it and check that it still runs
  what was downloaded; record variables from a running controller to CSV.
- **Run with nobody at the IDE.** Every command can start an IDE of its own,
  do the work and close it, so the same loop runs in a pipeline.

It refuses what it cannot do safely instead of guessing: an import needs `-y`,
a download needs the project's settings to allow it, and a question with no
flag behind it comes back naming the flag.

## Using it with an agent

Open the project, run **Project_watch** once from the Scripts menu, then ask:

> Make the conveyor in `PRG_Conveyor` stop when `GVL.bEStop` is TRUE, import it
> and build.

> Add the CAA Memory library and fix what breaks.

> Record `GVL.rSpeed` and `GVL.rTorque` for 5 seconds from 192.168.1.5.

## More

- [`docs/REFERENCE.md`](docs/REFERENCE.md): every command and flag, exit codes,
  the settings file, the text formats.
- [`skills/cdsint/SKILL.md`](skills/cdsint/SKILL.md): what the agent reads.
- [`CHANGELOG.md`](CHANGELOG.md): what changed, per release.
- [`docs/SPEC.md`](docs/SPEC.md): what it is meant to be, and why.

The code came out of [ArthurkaX/cds-text-sync](https://github.com/ArthurkaX/cds-text-sync).
MIT; see [`LICENSE`](LICENSE).

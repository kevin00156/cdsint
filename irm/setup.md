# The setup script

`setup.ps1` installs cdsint into every CODESYS-family IDE on the machine.

## How to run it

```powershell
irm https://raw.githubusercontent.com/kevin00156/cdsint/main/irm/setup.ps1 | iex
```

No Git needed — it downloads a zip. To install against a clone you are
editing instead, run it from a file:

```powershell
.\irm\setup.ps1 -Clone C:\path\to\cdsint
```

## What it does

**Asks cdsint which IDEs are here.** Each vendor scans a different directory
for scripts, picking the wrong one is the usual reason nothing appears in the
menu (SPEC 5.3), and none of it is guessable from the install path. That
table lives in `cdsint/installs.py`, which has tests and a `--json` output,
and the script runs `python <body>\cdsint\cli.py installs --json` to read
it. It used to carry a second copy of the same table; see **What needs an
elevated shell** below for what that cost.

To see the answer without installing anything:

```powershell
.\irm\setup.ps1 -List
```

An install counts only when its executable is there. These vendors put
shared targets, a gateway and an unversioned directory beside the real
installs, and going by directory name alone reports each of those as an IDE
with a ScriptDir of its own.

**What needs an elevated shell.** One thing: a ScriptDir under
`Program Files`, which is Delta's, because Delta keeps it inside the install.
Nothing else does. The machine-wide one is under `ProgramData`, whose default
rules let any user create things — measured on a real machine on 2026-09-06
by making the junction from an ordinary shell, which worked. The two copies
of this table disagreed about exactly that for months, and the one without
tests was the one saying you needed administrator.

Without an elevated shell the script says which ScriptDir it skipped and
carries on with the rest; run it again as administrator to add it.

**Installs the body.** Downloads the requested version (`-Version`, default
the newest release) into `%LOCALAPPDATA%\cdsint\body`, replacing whatever is
there rather than merging — a stub deleted upstream must not survive an
upgrade and keep showing in the menu. With `-Clone` it skips this and uses the
clone.

The body has a directory of its own because `%LOCALAPPDATA%\cdsint` also
holds the registrations of the IDEs that are listening and the status
window's position, and replacing the body must not take those with it. 0.0.1
unpacked the body straight into `%LOCALAPPDATA%\cdsint`; the script removes
what that left there, and only that.

This happens before the listing, because the body is what answers it. The one
exception is `-List` run from a checkout: listing changes nothing, so it must
not download a release either, and the checkout the script file sits in can
answer just as well.

**Points ScriptDir at the stubs.** `ScriptDir\cdsint` becomes an NTFS
junction onto the body's `stub\` directory, and `stub\body.path` is written
with the body's location, one line, no BOM. The IDE scans ScriptDir
recursively and menus every `.py` it finds, which is why only the three stubs
are reachable from there and everything else stays outside.

Downloaded or cloned, it is the same junction. One mechanism means an upgrade
cannot leave a stale stub in one IDE's ScriptDir and a fresh one in another's.

## Options

| | |
|---|---|
| `-List` | print the IDEs and ScriptDirs found, change nothing |
| `-ScriptDir D` | install into `D` only, instead of everything found |
| `-Clone P` | use the tree at `P` as the body instead of downloading |
| `-Version v1.2.3` | download this tag instead of the newest release; `main` downloads the branch as it stands |

## Updating

An install this script downloaded updates itself: `cdsint update` replaces
the body with the newest release, and every other `cdsint` command prints one
line on stderr when a newer one is out. It checks GitHub at most once a day,
says nothing under `--json` or when it cannot reach GitHub, and never checks
from a clone. The junctions need no change, because the body stays at the
same path. It refuses while any CODESYS-family IDE is running: an IDE that
has run one of the stubs keeps the old engine loaded.

A clone updates with `git pull`, and `cdsint update` says so.

## Requirements

Windows 10 or 11, PowerShell 5.1 or later, Python 3.11 or later on PATH, and
an internet connection unless you pass `-Clone`.

Python is not a new condition: cdsint's CLI is a Python program, and the
machine that installs it is the machine that runs it.

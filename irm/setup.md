# The setup script

`setup.ps1` gets a cdsint body onto the machine, puts it in the Scripts menu
of every CODESYS-family IDE, and pip-installs the `cdsint` command.

## How to run it

```powershell
irm https://raw.githubusercontent.com/kevin00156/cdsint/main/irm/setup.ps1 | iex
```

No Git needed — it downloads a release. To install against a clone you are
editing instead, run it from a file:

```powershell
.\irm\setup.ps1 -Clone C:\path\to\cdsint
```

Run through `iex` it never calls `exit`, because there it runs inside your own
shell and `exit` would close the window. Run from a file, its exit code is 0
when every IDE found is in the menu and 1 otherwise.

## What it does

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

**Runs `cdsint link` from that body**, by file path, since nothing is
pip-installed yet. `link` finds every IDE (`cdsint/installs.py`, the one
place that knows which directory each vendor scans for scripts, SPEC 5.3),
makes each one's `ScriptDir\cdsint` an NTFS junction onto the body's `stub\`,
and writes the body's location into `stub\body.path`, one line, no BOM. The
IDE scans ScriptDir recursively and menus every `.py` it finds, which is why
only the three stubs are reachable from there and everything else stays
outside. Downloaded or cloned, it is the same junction. The script used to do
this itself, in PowerShell with no tests; now an IDE installed later is added
by `cdsint link` alone, without downloading anything.

A directory that is already at `ScriptDir\cdsint` and is not a junction is
not deleted: it is somebody's, and `link` names it and moves on.

**Installs the command:** `python -m pip install -e <body>`. The `-e` is what
lets the command find `profiles\` and `stub\` beside its packages.

To see which IDEs and ScriptDirs it would use, without installing anything:

```powershell
.\irm\setup.ps1 -List
```

Run from a checkout, `-List` asks that checkout rather than downloading a
release.

An install counts only when its executable is there. These vendors put
shared targets, a gateway and an unversioned directory beside the real
installs, and going by directory name alone reports each of those as an IDE
with a ScriptDir of its own.

**What needs an elevated shell.** One thing: a ScriptDir under
`Program Files`, which is Delta's, because Delta keeps it inside the install.
Nothing else does. The machine-wide one is under `ProgramData`, whose default
rules let any user create things — measured on a real machine on 2026-09-06
by making the junction from an ordinary shell, which worked. Without an
elevated shell `link` says which ScriptDir it skipped and links the rest;
`cdsint link` from an elevated shell adds it later.

## Options

| | |
|---|---|
| `-List` | print the IDEs and ScriptDirs found, change nothing |
| `-ScriptDir D` | link `D` only, instead of everything found |
| `-Clone P` | use the tree at `P` as the body instead of downloading |
| `-Version v1.2.3` | download this tag instead of the newest release; `main` downloads the branch as it stands |

## Afterwards

An install this script downloaded keeps itself current, when asked:
`cdsint update` replaces the body with the newest release and links any IDE
installed since, and `cdsint link` does only the second half. Every other
command prints a line on stderr when either is due: a newer release, or an
IDE whose menu does not reach this body. It checks at most once a day, says
nothing under `--json` or when it cannot reach GitHub, and never checks from a
clone. `update` refuses while any CODESYS-family IDE is running: an IDE that
has run one of the stubs keeps the old engine loaded.

A clone updates with `git pull`, and `cdsint update` says so. `cdsint link`
works from a clone too, and points the menus at it.

## Requirements

Windows 10 or 11, PowerShell 5.1 or later, Python 3.11 or later on PATH, and
an internet connection unless you pass `-Clone`.

Python is not a new condition: cdsint's CLI is a Python program, and the
machine that installs it is the machine that runs it.

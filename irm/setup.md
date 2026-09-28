# The setup script

`setup.ps1` gets a cdsint body onto the machine, puts it in the Scripts menu
of every CODESYS-family IDE, and pip-installs the `cdsint` command.

## How to run it

```powershell
irm https://github.com/kevin00156/cdsint/releases/latest/download/setup.ps1 | iex
```

No Git needed — it downloads a release. The script comes from the newest
release too, so the installer and what it installs are the same version. The
copy on `main`, at
`https://raw.githubusercontent.com/kevin00156/cdsint/main/irm/setup.ps1`,
installs the same way.

Through `iex` there is no command line to put options on. To pass one, make
the download a script block and call that:

```powershell
& ([scriptblock]::Create((irm https://github.com/kevin00156/cdsint/releases/latest/download/setup.ps1))) -Version main
```

To install against a clone you are editing instead, run it from a file:

```powershell
.\irm\setup.ps1 -Clone C:\path\to\cdsint
```

Run through `iex` it never calls `exit`, because there it runs inside your own
shell and `exit` would close the window; a failure is thrown instead, so the
shell stays open and `$?` is false. Nor does it leave anything set in that
shell: `$ErrorActionPreference` is set inside a script block of its own, and
the console encoding is put back when it finishes. Run from a file, its exit
code is 0 when every IDE found is in the menu and 1 otherwise. Either way the
green "`cdsint --help` to start" line is printed only when everything worked;
when `link` could not reach every IDE, the last line says so instead.

## What it does

**Checks Python first.** It runs `python` and asks its version before
downloading anything, because being on PATH proves nothing: a stock Windows
has a `python.exe` that only opens the Microsoft Store. Without Python 3.11 or
later it stops and says where to get it, and how to turn that alias off
(Settings > Apps > Advanced app settings > App execution aliases).

**Installs the body.** Downloads the requested version (`-Version`, default
the newest release) into `%LOCALAPPDATA%\cdsint\body`, replacing whatever is
there rather than merging — a stub deleted upstream must not survive an
upgrade and keep showing in the menu. With `-Clone` it skips this and uses the
clone.

What it downloads is the archive the release job built from the commit the
tests passed on, `cdsint-<tag>.zip`, and it installs it only when its SHA-256
matches the `cdsint-<tag>.zip.sha256` published beside it. A release without
that file — one published before the release job made it — is refused, not
installed from GitHub's archive of the tag, which is whatever the tag points
at now. `-Version main` is the one exception: a branch has no release to
check it against, so it is downloaded as it stands and the script says it is
unverified.

The new tree is unpacked into `body.new`, beside the old one and so on the
same drive, and swapped in by two renames, as `cdsint update` does: a failed
download, a checksum that does not match, or a shell whose current directory
is inside the old body leaves that body whole. The old copy is deleted last;
if something holds it open, the install stands and the script names the
folder to delete by hand.

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

`-List` never downloads: run from a checkout it asks that checkout, and
otherwise the body already installed. With neither it says so and stops.

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
| `-Version v1.2.3` | download this release instead of the newest; `main` downloads the branch as it stands, unverified |

## Afterwards

An install this script downloaded keeps itself current, when asked:
`cdsint update` replaces the body with the newest release and links any IDE
installed since, and `cdsint link` does only the second half. `update`
checks the release's archive against its SHA-256 the same way, and the
linking after it is done by the new body's own `cdsint link`, not by the old
code still running the update. Every other
command prints a line on stderr when either is due: a newer release, or an
IDE whose menu does not reach this body. It checks at most once a day, says
nothing under `--json` or when it cannot reach GitHub, and never checks from a
clone. `update` refuses while any CODESYS-family IDE is running: an IDE that
has run one of the stubs keeps the old engine loaded. Running this script
again over an install refuses the same way; a first install does not ask.

A clone updates with `git pull`, and `cdsint update` says so. `cdsint link`
works from a clone too, and points the menus at it.

## Requirements

Windows 10 or 11, PowerShell 5.1 or later, Python 3.11 or later on PATH, and
an internet connection unless you pass `-Clone`.

Python is not a new condition: cdsint's CLI is a Python program, and the
machine that installs it is the machine that runs it.

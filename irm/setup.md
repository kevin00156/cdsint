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

**Finds the IDEs.** Each vendor scans a different directory for scripts, and
picking the wrong one is the usual reason nothing appears in the menu
(SPEC 5.3):

| IDE | ScriptDir |
|---|---|
| CODESYS 3.5 SP17–SP21 (all versions share one) | `%LOCALAPPDATA%\CODESYS\ScriptDir` |
| Lenze PLC Designer 4.x | `%LOCALAPPDATA%\PLCDesigner\ScriptDir` |
| Lenze PLC Designer 3.x | `C:\ProgramData\PLCDesigner\ScriptDir` |
| Delta DIADesigner-AX 1.8, 1.10 | `<install dir>\CODESYS\ScriptDir` |

An install counts only when its executable is there. These vendors put
shared targets, a gateway and an unversioned directory beside the real
installs, and going by directory name alone reports each of those as an IDE
with a ScriptDir of its own.

The last two rows are under `C:\ProgramData` and `C:\Program Files`, so they
need an elevated shell. Without one the script says which it skipped and
carries on with the rest; run it again as administrator to add them.

**Installs the body.** Downloads the requested version (`-Version`, default
`main`) into `%LOCALAPPDATA%\cdsint`, replacing whatever is there rather than
merging — a stub deleted upstream must not survive an upgrade and keep
showing in the menu. With `-Clone` it skips this and uses the clone.

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
| `-Version v1.2.3` | download this tag instead of `main` |

## Requirements

Windows 10 or 11, PowerShell 5.1 or later, and an internet connection unless
you pass `-Clone`.

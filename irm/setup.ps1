<#
.SYNOPSIS
    Install cdsint into every CODESYS-family IDE on this machine.

.DESCRIPTION
    The IDE builds its Scripts menu by scanning one directory tree for .py
    files, recursively, and it puts every one of them in the menu. So only
    three stubs go into that tree; the code they call lives somewhere else
    and the stubs are told where by a one-line file called body.path
    (SPEC 5.3).

    Which directory the IDE scans differs by vendor, and getting it wrong is
    the usual reason nothing appears in the menu. This script works it out
    from what is installed rather than asking.

.PARAMETER ScriptDir
    Install into this directory only, instead of every one found. The
    directory is the ScriptDir itself; the stubs land in a "cdsint"
    subdirectory of it.

.PARAMETER Clone
    Use this tree as the body instead of downloading one. Editing the clone
    then changes what the menu runs, because ScriptDir points at its stub\
    directory rather than holding a copy.

.PARAMETER Version
    Which tag to download, or "main". Ignored with -Clone.

.PARAMETER List
    Print the IDEs and ScriptDirs found, and change nothing.

.EXAMPLE
    irm https://raw.githubusercontent.com/kevin00156/cdsint/main/irm/setup.ps1 | iex

.EXAMPLE
    .\setup.ps1 -Clone C:\path\to\cdsint
#>
[CmdletBinding()]
param(
    [string] $ScriptDir,
    [string] $Clone,
    [string] $Version = "main",
    [switch] $List
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoUrl = "https://github.com/kevin00156/cdsint"
$StubNames = @("Project_export.py", "Project_import.py", "Project_watch.py")

# The subdirectory of ScriptDir the stubs live in. It is the product name,
# so the Scripts menu groups them under something recognisable.
$MenuFolder = "cdsint"


function Get-ScriptDirs {
    <#
        Ask a cdsint tree which ScriptDirs this machine has.

        Which directory an IDE scans is not guessable from its install path
        (SPEC 5.3), and this script used to answer that itself, from a copy
        of the table in cdsint/installs.py. The two disagreed for months
        about whether writing into the machine-wide one needs an elevated
        shell -- it does not -- and only one of them had tests. So there is
        one owner now, and this asks it.

        Run by file path rather than as the `cdsint` command: at this point
        in an install nothing has been pip-installed yet.

        Two IDEs of the same generation share one directory, so the answers
        are grouped: installing into it twice would report two successes for
        one junction.
    #>
    param([string] $Body)

    $entry = Join-Path $Body "cdsint\cli.py"
    if (-not (Test-Path $entry)) { throw "$Body is not a cdsint tree: no $entry" }
    $json = & python $entry installs --json
    if ($LASTEXITCODE -ne 0) {
        throw "python $entry installs failed. cdsint needs Python 3.11 or later on PATH."
    }
    $installs = $json | ConvertFrom-Json
    return $installs | Group-Object script_dir | ForEach-Object {
        [pscustomobject]@{
            Ide        = ($_.Group | ForEach-Object { $_.name }) -join " + "
            Path       = $_.Name
            NeedsAdmin = $_.Group[0].script_dir_needs_admin
        }
    }
}


function Test-Elevated {
    $me = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $me).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}


function Get-Body {
    <#
        Where the engine, cds and cdsint packages live after this runs.
        Downloads a release unless a clone was named.
    #>
    param([string] $Version)

    $root = Join-Path $env:LOCALAPPDATA "cdsint"
    $zip = Join-Path $env:TEMP "cdsint-$Version.zip"
    $unpacked = Join-Path $env:TEMP "cdsint-unpacked-$Version"

    if ($Version -eq "main") {
        $url = "$RepoUrl/archive/refs/heads/main.zip"
    } else {
        $url = "$RepoUrl/archive/refs/tags/$Version.zip"
    }

    Write-Host "[*] Downloading $Version from $RepoUrl" -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
        Expand-Archive -Path $zip -DestinationPath $unpacked -Force

        # GitHub wraps the tree in one directory named after the ref.
        $inner = Get-ChildItem $unpacked -Directory | Select-Object -First 1

        # Replace rather than merge: a file deleted upstream must not survive
        # an upgrade, or the Scripts menu keeps showing a stub that is gone.
        if (Test-Path $root) { Remove-Item $root -Recurse -Force }
        Move-Item -Path $inner.FullName -Destination $root
    } finally {
        if (Test-Path $zip) { Remove-Item $zip -Force }
        if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
    }
    Write-Host "[+] Body installed to $root" -ForegroundColor Green
    return $root
}


function Install-Stubs {
    <#
        Point the cdsint folder inside ScriptDir at the body's stub
        directory, and tell the stubs where the body is.

        A junction, not a copy, and the same junction whether the body was
        downloaded or is a clone you are editing. One mechanism means an
        upgrade cannot leave a stale stub behind in one IDE's ScriptDir and
        a fresh one in another's (SPEC D16), and it is what the by-hand
        instructions in readMe.md already describe.

        body.path is one line naming the body root. It is machine specific,
        which is why it is written here and gitignored rather than checked in.
    #>
    param([string] $ScriptDir, [string] $Body)

    $stubs = Join-Path $Body "stub"
    foreach ($name in $StubNames) {
        if (-not (Test-Path (Join-Path $stubs $name))) {
            throw "$stubs is missing $name"
        }
    }
    # Not Set-Content -Encoding utf8: PowerShell 5.1 writes a BOM, and the
    # stub would then insert "﻿C:\..." into sys.path and import nothing.
    [System.IO.File]::WriteAllText((Join-Path $stubs "body.path"), $Body,
                                   (New-Object System.Text.UTF8Encoding($false)))

    $menu = Join-Path $ScriptDir $MenuFolder
    if (Test-Path $menu) { Remove-Item $menu -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $ScriptDir | Out-Null
    New-Item -ItemType Junction -Path $menu -Target $stubs | Out-Null
}


# --- what to do -----------------------------------------------------------

Write-Host "--- cdsint setup ---" -ForegroundColor Cyan

# The body comes first now, because it is what answers "which IDEs are on
# this machine". -List has to reach one without downloading a release, and a
# checkout this script is being run from is the case where it can.
if ($Clone) {
    $body = (Resolve-Path $Clone).Path
    if (-not (Test-Path (Join-Path $body "stub"))) {
        Write-Host "[!] $body does not look like a cdsint clone: no stub folder." -ForegroundColor Red
        exit 1
    }
    Write-Host "[*] Using the clone at $body" -ForegroundColor Cyan
} elseif ($List -and $PSScriptRoot -and (Test-Path (Join-Path (Join-Path $PSScriptRoot "..") "stub"))) {
    $body = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Write-Host "[*] Listing from the checkout this script is in: $body" -ForegroundColor Cyan
} else {
    $body = Get-Body -Version $Version
}

if ($ScriptDir) {
    $targets = @([pscustomobject]@{ Ide = "(given on the command line)"
                                    Path = $ScriptDir
                                    NeedsAdmin = $false })
} else {
    $targets = @(Get-ScriptDirs -Body $body)
}

if ($targets.Count -eq 0) {
    Write-Host "[!] No CODESYS, Lenze PLC Designer or Delta DIADesigner-AX install found." -ForegroundColor Red
    Write-Host "    Pass -ScriptDir to install somewhere anyway." -ForegroundColor Red
    exit 1
}

Write-Host "`nScriptDirs to install into:" -ForegroundColor Cyan
foreach ($target in $targets) {
    $note = ""
    if ($target.NeedsAdmin) { $note = "  (needs an elevated shell)" }
    Write-Host ("  {0,-40} {1}{2}" -f $target.Ide, $target.Path, $note)
}
if ($List) { exit 0 }

$elevated = Test-Elevated
$failed = 0
foreach ($target in $targets) {
    if ($target.NeedsAdmin -and -not $elevated) {
        Write-Host ("[!] Skipped {0}: {1} needs an elevated shell. Re-run this script as administrator to add it." `
                    -f $target.Ide, $target.Path) -ForegroundColor Yellow
        $failed++
        continue
    }
    try {
        Install-Stubs -ScriptDir $target.Path -Body $body
        Write-Host ("[+] {0}: {1}\{2}" -f $target.Ide, $target.Path, $MenuFolder) -ForegroundColor Green
    } catch {
        Write-Host ("[!] {0}: {1}" -f $target.Ide, $_) -ForegroundColor Red
        $failed++
    }
}

Write-Host "`nRestart the IDE. Tools > Scripting > Scripts should list three entries." -ForegroundColor Cyan
Write-Host "For the CLI: python -m pip install -e `"$body`"" -ForegroundColor Cyan
if ($failed -gt 0) { exit 1 }

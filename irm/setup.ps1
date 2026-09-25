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
    the usual reason nothing appears in the menu. `cdsint link` works it out
    from what is installed; this script gets a body onto the machine, runs
    that, and pip-installs the command. An IDE installed later is added by
    `cdsint link` alone, and every command says when one is missing.

.PARAMETER ScriptDir
    Install into this directory only, instead of every one found. The
    directory is the ScriptDir itself; the stubs land in a "cdsint"
    subdirectory of it.

.PARAMETER Clone
    Use this tree as the body instead of downloading one. Editing the clone
    then changes what the menu runs, because ScriptDir points at its stub\
    directory rather than holding a copy.

.PARAMETER Version
    Which release tag to download, "latest" for the newest release, or
    "main" for the branch as it stands. Ignored with -Clone.

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
    [string] $Version = "latest",
    [switch] $List
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoUrl = "https://github.com/kevin00156/cdsint"
$LatestUrl = "https://api.github.com/repos/kevin00156/cdsint/releases/latest"


function Get-Body {
    <#
        Where the engine, cds and cdsint packages live after this runs.
        Downloads a release unless a clone was named.

        The body is a directory of its own inside %LOCALAPPDATA%\cdsint,
        not that directory itself: the registrations of the IDEs that are
        listening and the status window's position live there too, and
        replacing the body must not take them with it. cdsint/release.py
        names the same path; `cdsint update` replaces what is here.
    #>
    param([string] $Version)

    $appDir = Join-Path $env:LOCALAPPDATA "cdsint"
    $root = Join-Path $appDir "body"

    if ($Version -eq "latest") {
        $Version = (Invoke-RestMethod -Uri $LatestUrl -UseBasicParsing).tag_name
    }
    if ($Version -eq "main") {
        $url = "$RepoUrl/archive/refs/heads/main.zip"
    } else {
        $url = "$RepoUrl/archive/refs/tags/$Version.zip"
    }
    $zip = Join-Path $env:TEMP "cdsint-$Version.zip"
    $unpacked = Join-Path $env:TEMP "cdsint-unpacked-$Version"

    Write-Host "[*] Downloading $Version from $RepoUrl" -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
        Expand-Archive -Path $zip -DestinationPath $unpacked -Force

        # GitHub wraps the tree in one directory named after the ref.
        $inner = Get-ChildItem $unpacked -Directory | Select-Object -First 1

        Remove-FlatBody -AppDir $appDir -Tree $inner.FullName

        # Replace rather than merge: a file deleted upstream must not survive
        # an upgrade, or the Scripts menu keeps showing a stub that is gone.
        New-Item -ItemType Directory -Force -Path $appDir | Out-Null
        if (Test-Path $root) { Remove-Item $root -Recurse -Force }
        Move-Item -Path $inner.FullName -Destination $root
    } finally {
        if (Test-Path $zip) { Remove-Item $zip -Force }
        if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
    }
    Write-Host "[+] Body installed to $root" -ForegroundColor Green
    return $root
}


function Remove-FlatBody {
    <#
        0.0.1 unpacked the body straight into %LOCALAPPDATA%\cdsint, beside
        the state. Whatever there has the name of something at the top of a
        release is a leftover of that and goes; everything else is state and
        stays. Nothing matches once the body has its own directory.
    #>
    param([string] $AppDir, [string] $Tree)

    if (-not (Test-Path (Join-Path $AppDir "cdsint\cli.py"))) { return }
    Write-Host "[*] Removing the 0.0.1 layout from $AppDir" -ForegroundColor Cyan
    foreach ($entry in Get-ChildItem $Tree -Force) {
        $leftover = Join-Path $AppDir $entry.Name
        if (Test-Path $leftover) { Remove-Item $leftover -Recurse -Force }
    }
}


function Invoke-Cdsint {
    <#
        Run a command of the body's own cdsint, by file path: at this point
        in an install nothing has been pip-installed yet. Its output goes to
        the console, not down the pipeline, so the exit code is all that
        comes back.

        Python picks the console's encoding from the ANSI code page unless it
        is told, and the paths it prints can be anything a user name is.
    #>
    param([string] $Body, [string[]] $Arguments)

    $was = $env:PYTHONIOENCODING
    try {
        $env:PYTHONIOENCODING = "utf-8"
        & python (Join-Path $Body "cdsint\cli.py") @Arguments | Out-Host
    } finally {
        $env:PYTHONIOENCODING = $was
    }
    return $LASTEXITCODE
}


function Find-Body {
    <#
        The clone named, the checkout this script sits in when only listing,
        or a freshly downloaded release. $null when a named clone is not one.
        -List must not download a release, and a checkout is where it can
        avoid that.
    #>
    if ($Clone) {
        $found = (Resolve-Path $Clone).Path
        if (-not (Test-Path (Join-Path $found "stub"))) {
            Write-Host "[!] $found does not look like a cdsint clone: no stub folder." -ForegroundColor Red
            return $null
        }
        Write-Host "[*] Using the clone at $found" -ForegroundColor Cyan
        return $found
    }
    $checkout = if ($PSScriptRoot) { Join-Path $PSScriptRoot ".." } else { $null }
    if ($List -and $checkout -and (Test-Path (Join-Path $checkout "stub"))) {
        $found = (Resolve-Path $checkout).Path
        Write-Host "[*] Listing from the checkout this script is in: $found" -ForegroundColor Cyan
        return $found
    }
    return Get-Body -Version $Version
}


function Install-Cdsint {
    <#
        The whole install, as an exit code. A function rather than a script
        body because `irm ... | iex` runs this inside the user's own shell,
        where `exit` would close their window.
    #>
    Write-Host "--- cdsint setup ---" -ForegroundColor Cyan

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        # Checked rather than caught: with $ErrorActionPreference = "Stop" the
        # call throws CommandNotFound, and the sentence about needing Python
        # is never reached.
        Write-Host "[!] cdsint needs Python 3.11 or later on PATH; 'python' was not found." -ForegroundColor Red
        return 1
    }
    $body = Find-Body
    if (-not $body) { return 1 }
    if ($List) { return Invoke-Cdsint -Body $body -Arguments @("installs") }

    $linkArgs = @("link")
    if ($ScriptDir) { $linkArgs += @("--script-dir", $ScriptDir) }
    $linked = Invoke-Cdsint -Body $body -Arguments $linkArgs

    Write-Host "`n[*] Installing the cdsint command" -ForegroundColor Cyan
    & python -m pip install --quiet -e $body | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] pip failed; run: python -m pip install -e `"$body`"" -ForegroundColor Red
        return 1
    }
    Write-Host "[+] 'cdsint --help' to start; restart any IDE that was open." -ForegroundColor Green
    if (-not $Clone) {
        Write-Host "Later, 'cdsint update' replaces the body with the newest release." -ForegroundColor Cyan
    }
    return $linked
}


$code = Install-Cdsint
if ($PSCommandPath) { exit $code }

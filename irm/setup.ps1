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
    "main" for the branch as it stands. A release is installed only when its
    archive matches the checksum published with it; main has none and is
    installed unverified. Ignored with -Clone.

.PARAMETER List
    Print the IDEs and ScriptDirs found, and change nothing.

.EXAMPLE
    irm https://github.com/kevin00156/cdsint/releases/latest/download/setup.ps1 | iex

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

$RepoUrl = "https://github.com/kevin00156/cdsint"
$LatestUrl = "https://api.github.com/repos/kevin00156/cdsint/releases/latest"
$DownloadUrl = "https://github.com/kevin00156/cdsint/releases/download"


function Get-Body {
    <#
        Where the engine, cds and cdsint packages live after this runs.
        Downloads a release unless a clone was named.

        The body is a directory of its own inside %LOCALAPPDATA%\cdsint,
        not that directory itself: the registrations of the IDEs that are
        listening and the status window's position live there too, and
        replacing the body must not take them with it. cdsint/release.py
        names the same path; `cdsint update` replaces what is here.

        Replaced rather than merged, since a file deleted upstream must not
        survive an upgrade and keep a stub in the menu that is gone; and
        replaced the way cdsint/update.py does it. The new tree is unpacked
        beside the old one, on the same volume, and swapped in by two
        renames, so a failed download, a checksum that does not match, a
        running IDE, or a shell whose current directory is inside the body
        stops the install with the old body whole.
    #>
    param([string] $Version)

    $appDir = Join-Path $env:LOCALAPPDATA "cdsint"
    $root = Join-Path $appDir "body"
    $staging = "$root.new"
    $retired = "$root.old"

    if ($Version -eq "latest") {
        $Version = (Invoke-RestMethod -Uri $LatestUrl -UseBasicParsing).tag_name
    }
    foreach ($leftover in @($staging, $retired)) {
        if (Test-Path $leftover) { Remove-Item $leftover -Recurse -Force }
    }
    New-Item -ItemType Directory -Force -Path $staging | Out-Null

    Write-Host "[*] Downloading $Version from $RepoUrl" -ForegroundColor Cyan
    $zip = Save-Archive -Version $Version -Staging $staging
    $inner = Expand-Tree -Zip $zip -Destination (Join-Path $staging "unpacked")

    # Only an engine already here can be loaded in an IDE; a first install
    # has nothing to mix with, and must not be refused over an open IDE.
    if ((Test-Path $root) -or (Test-FlatBody -AppDir $appDir)) {
        Assert-NoIdeRunning -Tree $inner
    }
    if (Test-Path $root) {
        try {
            Rename-Item -Path $root -NewName (Split-Path $retired -Leaf)
        } catch {
            throw "Could not move $root aside, so nothing was changed: $($_.Exception.Message) Close whatever has a file open in it (a shell whose current directory is inside it, an editor) and run this again."
        }
    }
    try {
        Move-Item -Path $inner -Destination $root
    } catch {
        if (Test-Path $retired) { Rename-Item -Path $retired -NewName (Split-Path $root -Leaf) }
        throw
    }
    Remove-FlatBody -AppDir $appDir -Tree $root
    Remove-Leftover -Path $staging
    Remove-Leftover -Path $retired
    Write-Host "[+] Body installed to $root" -ForegroundColor Green
    return $root
}


function Save-Archive {
    <#
        The archive of $Version, downloaded into $Staging and, for a release,
        checked against the SHA-256 the release job published beside it;
        cdsint/release.py names the same two files. GitHub's own archive of
        a tag is whatever the tag points at when somebody asks, with nothing
        to check it against, so a release without the checksum is refused
        rather than installed from there. main is a branch, which no release
        job archived: it is the one download that goes unchecked, and it
        says so.
    #>
    param([string] $Version, [string] $Staging)

    $zip = Join-Path $Staging "cdsint-$Version.zip"
    if ($Version -eq "main") {
        Write-Host "[!] main is not a release and has no checksum; installing it unverified." -ForegroundColor Yellow
        Invoke-WebRequest -Uri "$RepoUrl/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
        return $zip
    }
    $url = "$DownloadUrl/$Version/cdsint-$Version.zip"
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        Invoke-WebRequest -Uri "$url.sha256" -OutFile "$zip.sha256" -UseBasicParsing
    } catch {
        throw "Could not download $url and its .sha256: $($_.Exception.Message) Only a release published with its checksum is installed, and releases older than that have none. -Version main installs the branch as it stands, unverified."
    }
    $published = [string] (Get-Content -Path "$zip.sha256" -Raw)
    $expected = @($published.Trim() -split '\s+')[0]
    $actual = (Get-FileHash -Path $zip -Algorithm SHA256).Hash
    if ($actual -ne $expected) {
        throw "$url does not match the SHA-256 published beside it; nothing was installed."
    }
    return $zip
}


function Expand-Tree {
    <#
        The one directory the archive holds, unpacked under $Destination.
        The release job and GitHub both wrap the tree in a directory named
        after the version; anything else is not an archive of this repo.
    #>
    param([string] $Zip, [string] $Destination)

    Expand-Archive -Path $Zip -DestinationPath $Destination -Force
    $top = @(Get-ChildItem $Destination -Force)
    if ($top.Count -ne 1 -or -not $top[0].PSIsContainer) {
        throw "$Zip does not hold one tree: $($top.Name -join ', ')"
    }
    return $top[0].FullName
}


function Remove-Leftover {
    <#
        Once the new body is in place the install stands. A copy that will
        not delete, held open by a virus scanner say, is named, not fatal.
    #>
    param([string] $Path)

    if (-not (Test-Path $Path)) { return }
    try {
        Remove-Item $Path -Recurse -Force -ErrorAction Stop
    } catch {
        Write-Host "[!] Could not delete $Path; delete it by hand." -ForegroundColor Yellow
    }
}


function Test-FlatBody {
    <# Is the 0.0.1 layout, the body straight in %LOCALAPPDATA%\cdsint, here? #>
    param([string] $AppDir)
    return (Test-Path (Join-Path $AppDir "cdsint\cli.py"))
}


function Assert-NoIdeRunning {
    <#
        The check `cdsint update` makes before its swap: an IDE that has run
        a cdsint script keeps the old engine loaded, and would mix it with
        the new one. Asked of the new tree's own cdsint/update.py, so the
        list of IDE executables is kept in one place; not knowing what runs
        is a refusal too, never "nothing runs".
    #>
    param([string] $Tree)

    $probe = "import sys; sys.path.insert(0, sys.argv[1]); from cdsint import update; print(', '.join(update.running_ides()))"
    $running = (& python -c $probe $Tree) -join ""
    if ($LASTEXITCODE -ne 0) {
        throw "Could not check whether a CODESYS-family IDE is running (it said why above), so nothing was changed."
    }
    if ($running) {
        throw "Close every CODESYS-family IDE first (running: $running). One that has run a cdsint script keeps the old engine loaded, and would mix it with the new one. Nothing was changed."
    }
}


function Remove-FlatBody {
    <#
        0.0.1 unpacked the body straight into %LOCALAPPDATA%\cdsint, beside
        the state. Whatever there has the name of something at the top of a
        release is a leftover of that and goes; everything else is state and
        stays. Nothing matches once the body has its own directory. Run only
        once the new body is in place: this deletes, and cannot be put back.
    #>
    param([string] $AppDir, [string] $Tree)

    if (-not (Test-FlatBody -AppDir $AppDir)) { return }
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


function Test-Python {
    <#
        Is the `python` on PATH one that can run cdsint? Asked of python
        itself, because being found proves nothing: a stock Windows has a
        python.exe in WindowsApps that only opens the Microsoft Store. Asked
        before anything is downloaded, so that a machine without it is told
        so rather than left with a body it cannot run.

        Get-Command first because with $ErrorActionPreference = "Stop" a
        missing command throws CommandNotFound. stderr is not redirected:
        in Windows PowerShell 5.1 a redirected native stderr line becomes an
        error record, which "Stop" turns into a throw.
    #>
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { return $false }
    try {
        & python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" | Out-Null
    } catch {
        return $false
    }
    return ($LASTEXITCODE -eq 0)
}


function Find-Body {
    <#
        The clone named; when only listing, the checkout this script sits in
        or else the body already installed; otherwise a freshly downloaded
        release. $null when a named clone is not one, or -List has nothing
        to list with. -List promises to change nothing, and downloading a
        release replaces the installed body, so it never downloads: run as
        a script block from irm there is no checkout around it.
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
    if (-not $List) { return Get-Body -Version $Version }
    $checkout = if ($PSScriptRoot) { Join-Path $PSScriptRoot ".." } else { $null }
    $installed = Join-Path $env:LOCALAPPDATA "cdsint\body"
    foreach ($candidate in @($checkout, $installed)) {
        if ($candidate -and (Test-Path (Join-Path $candidate "stub"))) {
            $found = (Resolve-Path $candidate).Path
            Write-Host "[*] Listing with the cdsint at $found" -ForegroundColor Cyan
            return $found
        }
    }
    Write-Host "[!] -List changes nothing, so it downloads nothing, and there is no checkout beside this script and no installed body to list with. Install first, or pass -Clone." -ForegroundColor Red
    return $null
}


function Install-Cdsint {
    <#
        The whole install, as an exit code. A function rather than a script
        body because `irm ... | iex` runs this inside the user's own shell,
        where `exit` would close their window.
    #>
    Write-Host "--- cdsint setup ---" -ForegroundColor Cyan

    if (-not (Test-Python)) {
        Write-Host "[!] cdsint needs Python 3.11 or later as 'python' on PATH, and the one there is missing, older, or the Microsoft Store alias." -ForegroundColor Red
        Write-Host "    Install Python 3.11 or later from https://www.python.org/downloads/ with 'Add python.exe to PATH' ticked, and turn 'python.exe' off under Settings > Apps > Advanced app settings > App execution aliases." -ForegroundColor Red
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
    if ($linked -ne 0) {
        Write-Host "[!] The cdsint command is installed, but 'cdsint link' did not put it in every IDE's Scripts menu; it said why above. Run 'cdsint link' again once that is fixed." -ForegroundColor Red
        return $linked
    }
    Write-Host "[+] 'cdsint --help' to start; restart any IDE that was open." -ForegroundColor Green
    if (-not $Clone) {
        Write-Host "Later, 'cdsint update' replaces the body with the newest release." -ForegroundColor Cyan
    }
    return 0
}


# A script block of its own, because `irm ... | iex` runs this in the
# caller's shell and a preference set out here would stay set there after
# the install. The console's encoding belongs to the process, not to a scope,
# so it is put back by hand. A failure under iex is thrown rather than
# exited: the shell stays open, and $? says it failed.
$code = & {
    $ErrorActionPreference = "Stop"
    $encoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        Install-Cdsint
    } finally {
        [Console]::OutputEncoding = $encoding
    }
}
if ($PSCommandPath) { exit $code }
if ($code -ne 0) { throw "cdsint setup did not finish; the lines above say what failed." }

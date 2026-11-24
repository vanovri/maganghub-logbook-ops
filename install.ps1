param(
    [string[]]$TargetDirs,
    [string]$InstallHome
)

$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:MAGANGHUB_LOGBOOK_OPS_REPO) { $env:MAGANGHUB_LOGBOOK_OPS_REPO } else { "https://github.com/vanovri/maganghub-logbook-ops.git" }
$ZipUrl = "https://github.com/vanovri/maganghub-logbook-ops/archive/refs/heads/main.zip"
if (-not $InstallHome) {
    $InstallHome = if ($env:MAGANGHUB_LOGBOOK_OPS_HOME) { $env:MAGANGHUB_LOGBOOK_OPS_HOME } else { Join-Path $env:LOCALAPPDATA "maganghub-logbook-ops" }
}
if (-not $TargetDirs -or $TargetDirs.Count -eq 0) {
    $TargetDirs = @(
        (Join-Path $env:USERPROFILE ".claude\skills"),
        (Join-Path $env:USERPROFILE ".agents\skills"),
        (Join-Path $env:USERPROFILE ".omp\agent\skills")
    )
}

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { $null }
if ($ScriptDir -and (Test-Path (Join-Path $ScriptDir "skills\maganghub-logbook-ops\SKILL.md"))) {
    $Src = Join-Path $ScriptDir "skills\maganghub-logbook-ops"
} else {
    $GitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($GitCmd) {
        if (Test-Path (Join-Path $InstallHome ".git")) {
            & git -C $InstallHome pull --ff-only
            if ($LASTEXITCODE -ne 0) { throw "git pull failed with exit code $LASTEXITCODE" }
        } else {
            $ParentDir = Split-Path -Parent $InstallHome
            if ($ParentDir) { New-Item -ItemType Directory -Force -Path $ParentDir | Out-Null }
            if (Test-Path $InstallHome) { Remove-Item -Recurse -Force $InstallHome }
            & git clone --depth 1 $RepoUrl $InstallHome
            if ($LASTEXITCODE -ne 0) { throw "git clone failed with exit code $LASTEXITCODE" }
        }
    } else {
        $TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("maganghub-logbook-ops-" + [System.Guid]::NewGuid().ToString("N"))
        $ZipPath = Join-Path $TmpDir "repo.zip"
        $ExtractDir = Join-Path $TmpDir "extract"
        New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
        try {
            Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
            Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force
            $Inner = Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1
            if (-not $Inner) { throw "Downloaded archive was empty." }
            if (Test-Path $InstallHome) { Remove-Item -Recurse -Force $InstallHome }
            $ParentDir = Split-Path -Parent $InstallHome
            if ($ParentDir) { New-Item -ItemType Directory -Force -Path $ParentDir | Out-Null }
            Copy-Item -Recurse -Force $Inner.FullName $InstallHome
        } finally {
            if (Test-Path $TmpDir) { Remove-Item -Recurse -Force $TmpDir }
        }
    }
    $Src = Join-Path $InstallHome "skills\maganghub-logbook-ops"
}

if (-not (Test-Path (Join-Path $Src "SKILL.md")) -or -not (Test-Path (Join-Path $Src "scripts\logbook_ops.py"))) {
    throw "Invalid skill package at $Src"
}

foreach ($Dir in $TargetDirs) {
    if (-not $Dir) { continue }
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $Dest = Join-Path $Dir "maganghub-logbook-ops"
    if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null

    Get-ChildItem -Path $Src -Recurse -Force | Where-Object {
        $_.FullName -notmatch '\\__pycache__(\\|$)' -and $_.Extension -ne '.pyc'
    } | ForEach-Object {
        $Rel = $_.FullName.Substring($Src.Length).TrimStart('\', '/')
        $TargetItem = Join-Path $Dest $Rel
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $TargetItem | Out-Null
        } else {
            $TargetParent = Split-Path -Parent $TargetItem
            if ($TargetParent) { New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null }
            Copy-Item -Force $_.FullName $TargetItem
        }
    }

    if (-not (Test-Path (Join-Path $Dest "SKILL.md")) -or -not (Test-Path (Join-Path $Dest "scripts\logbook_ops.py"))) {
        throw "Installation verification failed at $Dest"
    }
    Write-Output "Installed $Dest"
}

Write-Output "Done! Invoke /maganghub-logbook-ops in your agent."

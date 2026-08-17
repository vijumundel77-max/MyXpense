# Expenzo release build.
# 1. Generates the icon, 2. installs PyInstaller if missing,
# 3. builds the frozen app (dist/Expenzo/), 4. compiles the installer,
# 5. writes the GitHub-release metadata (dist/release.json + SHA256).
#
# Version is read from the CENTRAL source (services/version_service.py);
# override per build with -Version 1.0.1:
#   powershell.exe -ExecutionPolicy Bypass -File packaging\build_release.ps1 -Version 1.0.1
#
# Output installer: dist\ExpenzoSetup-<version>.exe
#
# Run from the repo root (Windows PowerShell or via WSL powershell.exe).

param([string]$Version = "")

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    throw "Windows venv python not found at $Py"
}

# --- Resolve the release version from the central source ------------------- #
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = (& $Py -c "from version_service import VERSION; print(VERSION)").Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Invalid version '$Version'; expected MAJOR.MINOR.PATCH (e.g. 1.0.1)."
}
$Env:EXPENZO_BUILD_VERSION = $Version

Write-Host "==> Building Expenzo $Version"

Write-Host "==> [1/5] Icon"
& $Py "packaging\make_icon.py"
if ($LASTEXITCODE -ne 0) { throw "make_icon failed" }

Write-Host "==> [2/5] PyInstaller"
& $Py -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pyinstaller..."
    & $Py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}

Write-Host "==> [3/5] Build frozen app"
& $Py -m PyInstaller "packaging\expenzo.spec" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Exe = Join-Path $RepoRoot "dist\Expenzo\Expenzo.exe"
if (-not (Test-Path $Exe)) { throw "Build output missing: $Exe" }

Write-Host "==> [4/5] Installer (Inno Setup)"
$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) {
    $ISCC = "C:\Program Files\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $ISCC)) {
    $ISCC = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $ISCC)) {
    throw "Inno Setup ISCC.exe not found"
}
& $ISCC "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }

$Setup = Join-Path $RepoRoot "dist\ExpenzoSetup-$Version.exe"
if (-not (Test-Path $Setup)) { throw "Installer output missing: $Setup" }

# --- GitHub Release metadata ---------------------------------------------- #
Write-Host "==> [5/5] Release metadata"
$Sha256 = (Get-FileHash $Setup -Algorithm SHA256).Hash.ToLowerInvariant()
$Repo = "vijumundel77-max/MyXpense"
$ReleaseJson = @{
    schema_version  = 1
    app             = "Expenzo"
    version         = $Version
    installer_name  = "ExpenzoSetup-$Version.exe"
    installer_url   = "https://github.com/$Repo/releases/download/v$Version/ExpenzoSetup-$Version.exe"
    release_notes   = ""
    published_at    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    sha256          = $Sha256
} | ConvertTo-Json
$MetadataPath = Join-Path $RepoRoot "dist\release.json"
$ReleaseJson | Set-Content -Path $MetadataPath -Encoding utf8

# Keep the repo-side latest.json in sync so the in-app update check has a
# stable URL on the default branch even before a GitHub Release is published.
$UpdatesDir = Join-Path $RepoRoot "updates"
New-Item -ItemType Directory -Force -Path $UpdatesDir | Out-Null
$RepoMeta = @{
    schema_version  = 1
    app             = "Expenzo"
    version         = $Version
    installer_name  = "ExpenzoSetup-$Version.exe"
    installer_url   = "https://github.com/$Repo/releases/download/v$Version/ExpenzoSetup-$Version.exe"
    release_notes   = ""
    published_at    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    sha256          = $Sha256
} | ConvertTo-Json
$RepoMeta | Set-Content -Path (Join-Path $UpdatesDir "latest.json") -Encoding utf8

Write-Host ""
Write-Host "BUILD OK"
Write-Host "  Version:    $Version"
Write-Host "  App:        $Exe"
Write-Host "  Installer:  $Setup"
Write-Host "  Metadata:   $MetadataPath"
Write-Host "  SHA256:     $Sha256"

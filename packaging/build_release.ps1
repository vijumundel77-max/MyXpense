# Expenzo 1.0.0 release build.
# 1. Generates the icon, 2. installs PyInstaller if missing,
# 3. builds the frozen app (dist/Expenzo/), 4. compiles the installer.
#
# Run from the repo root (Windows PowerShell or via WSL powershell.exe):
#   powershell.exe -ExecutionPolicy Bypass -File packaging\build_release.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    throw "Windows venv python not found at $Py"
}

Write-Host "==> [1/4] Icon"
& $Py "packaging\make_icon.py"
if ($LASTEXITCODE -ne 0) { throw "make_icon failed" }

Write-Host "==> [2/4] PyInstaller"
& $Py -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pyinstaller..."
    & $Py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}

Write-Host "==> [3/4] Build frozen app"
& $Py -m PyInstaller "packaging\expenzo.spec" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Exe = Join-Path $RepoRoot "dist\Expenzo\Expenzo.exe"
if (-not (Test-Path $Exe)) { throw "Build output missing: $Exe" }

Write-Host "==> [4/4] Installer (Inno Setup)"
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

$Setup = Join-Path $RepoRoot "dist\ExpenzoSetup-1.0.0.exe"
Write-Host ""
Write-Host "BUILD OK"
Write-Host "  App:      $Exe"
Write-Host "  Installer: $Setup"
Write-Host "  SHA256:   $((Get-FileHash $Setup -Algorithm SHA256).Hash)"

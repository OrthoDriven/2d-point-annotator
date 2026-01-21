# WindowsInstaller.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== 2D Point Annotator Installer ==="
Write-Host ""

# -----------------------------
# Configuration
# -----------------------------
$RepoZipUrl  = "https://github.com/OrthoDriven/2d-point-annotator/archive/refs/heads/ajj/andrew-fixes.zip"

# NOTE: installer may be run via `irm ... | iex`, so $PSScriptRoot is empty here.
# Use Documents folder if available; fall back to $HOME\Documents.
$Documents = [Environment]::GetFolderPath("MyDocuments")
if ([string]::IsNullOrWhiteSpace($Documents)) { $Documents = Join-Path $HOME "Documents" }

$InstallRoot = Join-Path $Documents "2D-Point-Annotator"
$ZipPath     = Join-Path $InstallRoot "annotator.zip"

# -----------------------------
# Create install directory
# -----------------------------
Write-Host "Creating install directory..."
if (Test-Path $InstallRoot) { Remove-Item -Recurse -Force $InstallRoot }
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Set-Location $InstallRoot

# -----------------------------
# Download ZIP
# -----------------------------
Write-Host "Downloading application files..."
Invoke-WebRequest -Uri $RepoZipUrl -OutFile $ZipPath

# -----------------------------
# Extract ZIP
# -----------------------------
Write-Host "Extracting files..."
Expand-Archive -Force $ZipPath $InstallRoot
Remove-Item $ZipPath

# -----------------------------
# Find actual project directory
# -----------------------------
$ProjectDir = Get-ChildItem -Directory -Recurse | Where-Object {
    Test-Path (Join-Path $_.FullName "pixi.toml")
} | Select-Object -First 1

if (-not $ProjectDir) {
    Write-Host "ERROR: Could not locate project directory."
    Pause
    exit 1
}

Write-Host "Project directory found: $($ProjectDir.FullName)"

# -----------------------------
# Move project to stable app dir (InstallRoot\app)
# -----------------------------
$AppDir = Join-Path $InstallRoot "app"
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
Move-Item -Force $ProjectDir.FullName $AppDir

# -----------------------------
# Write config.ps1 into InstallRoot (single source of truth for updater)
# -----------------------------
$ConfigPath = Join-Path $InstallRoot "config.ps1"
$ConfigContent = @"
`$Owner  = "OrthoDriven"
`$Repo   = "2d-point-annotator"
`$Branch = "ajj/andrew-fixes"

# Install root anchored to the folder containing these scripts
`$InstallRoot = `$PSScriptRoot
`$AppDir      = Join-Path `$InstallRoot "app"

`$StatePath = Join-Path `$InstallRoot "update_state.json"
`$TempDir   = Join-Path `$InstallRoot "_tmp"

`$UserAgent               = "2d-point-annotator-updater"
`$MinCheckIntervalSeconds = 15
`$RequestTimeoutSec       = 3

`$ZipUrl = "https://github.com/`$Owner/`$Repo/archive/refs/heads/`$([uri]::EscapeDataString(`$Branch)).zip"
`$ApiUrl = "https://api.github.com/repos/`$Owner/`$Repo/commits/`$([uri]::EscapeDataString(`$Branch))?per_page=1"
"@
$ConfigContent | Set-Content -Path $ConfigPath -Encoding UTF8

# -----------------------------
# Install Pixi if needed
# -----------------------------
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Pixi..."
    irm -useb https://pixi.sh/install.ps1 | iex
    Write-Host "Pixi installed."
}

# -----------------------------
# Create the Launcher on the Desktop
# -----------------------------
Write-Host "Creating desktop launcher..."
$DesktopPath  = [Environment]::GetFolderPath("Desktop")
$LauncherPath = Join-Path $DesktopPath "Run_Annotator.bat"

# Use the actual resolved install root (do NOT guess %USERPROFILE%\Documents)
$BatchContent = @"
@echo off
SET "PATH=%PATH%;%USERPROFILE%\.pixi\bin"
set "INSTALL_ROOT=$InstallRoot"
set "APP_DIR=%INSTALL_ROOT%\app"

REM 1) Run update check (non-fatal)
powershell -ExecutionPolicy Bypass -NoProfile -File "%APP_DIR%\update_check.ps1" || echo [warn] update check failed

REM 2) Launch from stable app dir
if not exist "%APP_DIR%\pixi.toml" (
  echo ERROR: Could not locate pixi.toml under %APP_DIR%.
  pause
  exit /b 1
)
cd /d "%APP_DIR%"
echo Starting 2D Point Annotator...
pixi run annotator
if %ERRORLEVEL% neq 0 pause
"@

$BatchContent | Set-Content -Path $LauncherPath -Encoding ASCII

# -----------------------------
# Finish
# -----------------------------
Write-Host ""
Write-Host "Installation complete."
Write-Host "A launcher named 'Run_Annotator' has been created on your Desktop."
Write-Host ""
Pause

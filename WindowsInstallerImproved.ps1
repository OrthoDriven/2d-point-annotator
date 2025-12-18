$ErrorActionPreference = "Stop"

Write-Host "=== 2D Point Annotator Installer ==="
Write-Host ""

# -----------------------------
# Configuration
# -----------------------------
$RepoZipUrl = "https://github.com/OrthoDriven/2d-point-annotator/archive/refs/heads/ajj/andrew-fixes.zip"
$InstallRoot = "$HOME\Documents\2D-Point-Annotator"
$ZipPath = "$InstallRoot\annotator.zip"

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
    Test-Path "$($_.FullName)\pixi.toml"
} | Select-Object -First 1

if (-not $ProjectDir) {
    Write-Host "ERROR: Could not locate project directory."
    Pause
    exit 1
}

Write-Host "Project directory found: $($ProjectDir.FullName)"

# -----------------------------
# Install Pixi if needed
# -----------------------------
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Pixi..."
    # We use -useb for a cleaner download
    irm -useb https://pixi.sh/install.ps1 | iex
    Write-Host "Pixi installed."
}

# -----------------------------
# Create the Launcher on the Desktop
# -----------------------------
Write-Host "Creating desktop launcher..."
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$LauncherPath = Join-Path $DesktopPath "Run_Annotator.bat"

# We add the SET "PATH..." line to ensure it works immediately after install
$BatchContent = @"
@echo off
SET "PATH=%PATH%;%USERPROFILE%\.pixi\bin"
cd /d "$($ProjectDir.FullName)"
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

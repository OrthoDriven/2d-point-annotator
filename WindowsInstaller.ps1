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

Write-Host "Project directory found:"
Write-Host "  $($ProjectDir.FullName)"
Write-Host ""

# -----------------------------
# Install Pixi if needed
# -----------------------------
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Pixi..."
    irm https://pixi.sh/install.ps1 | iex
    Write-Host "Pixi installed."
    Write-Host ""
}

# -----------------------------
# Create the Launcher on the Desktop
# -----------------------------
# This finds the desktop regardless of OneDrive
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$LauncherPath = Join-Path $DesktopPath "Run_Annotator.bat"

# This creates a 3-line file that lives on the desktop
@"
@echo off
cd /d "$($ProjectDir.FullName)"
pixi run annotator
pause
"@ | Set-Content -Path $LauncherPath -Encoding ASCII

Write-Host "Launcher created on your Desktop."

# -----------------------------
# Finish
# -----------------------------
Write-Host ""
Write-Host "Installation complete."
Write-Host "Use the '2D Point Annotator' icon on your desktop to launch the app."
Pause

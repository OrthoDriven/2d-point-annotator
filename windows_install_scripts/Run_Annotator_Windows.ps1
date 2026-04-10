$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$AppDir = Split-Path -Parent $ScriptDir
$InstallRoot = Split-Path -Parent $AppDir
$EnvPath = Join-Path $InstallRoot "app.env"
$UpdateCheck = Join-Path $ScriptDir "update_check.ps1"
$PixiBin = Join-Path $HOME ".pixi\bin"

if (-not ($env:PATH -split ';' | Where-Object { $_ -eq $PixiBin })) {
    $env:PATH = "$env:PATH;$PixiBin"
}

if (Test-Path $EnvPath) {
    $env:APP_ENV_FILE = $EnvPath
}

if (Test-Path $UpdateCheck) {
    try {
        & $UpdateCheck
    }
    catch {
        Write-Warning "Update check failed: $($_.Exception.Message)"
    }
}

if (-not (Test-Path (Join-Path $AppDir "pixi.toml"))) {
    Write-Host "ERROR: Could not locate pixi.toml under $AppDir"
    Pause
    exit 1
}

Set-Location $AppDir
Write-Host "Starting 2D Point Annotator..."
pixi run annotator
if ($LASTEXITCODE -ne 0) {
    Pause
    exit $LASTEXITCODE
}

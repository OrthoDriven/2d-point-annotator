$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$AppDir = Split-Path -Parent $ScriptDir
$EnvPath = Join-Path $AppDir.Parent.FullName "app.env"
$UpdateScript = Join-Path $AppDir "install_scripts\update.py"
$PixiBin = Join-Path $HOME ".pixi\bin"

if (-not (Test-Path $UpdateScript)) {
    throw "Missing updater script: $UpdateScript"
}

if (Test-Path $EnvPath) {
    $env:APP_ENV_FILE = $EnvPath
}

if (-not ($env:PATH -split ';' | Where-Object { $_ -eq $PixiBin })) {
    $env:PATH = "$env:PATH;$PixiBin"
}

pixi run -m $AppDir python $UpdateScript

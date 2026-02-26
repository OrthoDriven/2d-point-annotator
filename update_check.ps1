# update_check.ps1
$ErrorActionPreference = "Stop"

# # ---------- Config ----------
$appdir = Split-Path -parent $PSCommandPath
$update_script = Join-Path $appdir "./install_scripts/update.py"

pixi run -m $appdir python $update_script

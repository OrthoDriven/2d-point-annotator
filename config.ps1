$Documents = [Environment]::GetFolderPath("MyDocuments")
if ([string]::IsNullOrWhiteSpace($Documents)) { $Documents = Join-Path $HOME "Documents" }
$InstallRoot = Join-Path $Documents "2D-Point-Annotator"

# config.ps1 — single source of truth for paths + repo identity

$Owner  = "OrthoDriven"
$Repo   = "2d-point-annotator"
$Branch = "ajj/andrew-fixes"

# Install root anchored under user profile
$AppDir      = Join-Path $InstallRoot "app"

# Updater state + temp
$StatePath = Join-Path $InstallRoot "update_state.json"
$TempDir   = Join-Path $InstallRoot "_tmp"

# URLs
$ZipUrl = "https://github.com/$Owner/$Repo/archive/refs/heads/$([uri]::EscapeDataString($Branch)).zip"
$ApiUrl = "https://api.github.com/repos/$Owner/$Repo/commits/$([uri]::EscapeDataString($Branch))?per_page=1"

# Behavior knobs
$UserAgent               = "2d-point-annotator-updater"
$MinCheckIntervalSeconds = 15
$RequestTimeoutSec       = 3

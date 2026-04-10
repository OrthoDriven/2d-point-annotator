$Owner  = "OrthoDriven"
$Repo   = "2d-point-annotator"
$Branch = "new-prototype"

$InstallRoot = Join-Path $HOME "2d-point-annotator"
$AppDir      = Join-Path $InstallRoot "app"
$StatePath   = Join-Path $InstallRoot "update_state.json"
$TempDir     = Join-Path $InstallRoot "_tmp"

$UserAgent               = "2d-point-annotator-updater"
$MinCheckIntervalSeconds = 15
$RequestTimeoutSec       = 15

$ZipUrl = "https://github.com/$Owner/$Repo/archive/refs/heads/$([uri]::EscapeDataString($Branch)).zip"
$ApiUrl = "https://api.github.com/repos/$Owner/$Repo/commits/$([uri]::EscapeDataString($Branch))"
$EnvPath = Join-Path $InstallRoot "app.env"

Set-Location $PSScriptRoot

# Find project directory dynamically
$project = Get-ChildItem -Directory -Recurse | Where-Object {
    Test-Path "$($_.FullName)\pixi.toml"
} | Select-Object -First 1

if (-not $project) {
    Write-Host "ERROR: Project folder not found."
    Pause
    exit 1
}

Set-Location $project.FullName
pixi run annotator

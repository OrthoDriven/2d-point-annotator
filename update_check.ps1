# update_check.ps1
$ErrorActionPreference = "Stop"

# ---------- Config ----------
. (Join-Path $PSScriptRoot "config.ps1")

# ---------- Helpers ----------
function Get-State {
  if (Test-Path $StatePath) {
    try { return Get-Content $StatePath -Raw | ConvertFrom-Json } catch { }
  }
  return @{ sha = ""; etag = ""; lastCheckUtc = "1970-01-01T00:00:00Z" }
}

function Set-State([string]$sha, [string]$etag) {
  $now = [DateTimeOffset]::UtcNow.ToString("o")
  $obj = [ordered]@{
    sha          = $sha
    etag         = $etag
    updatedUtc   = $now
    lastCheckUtc = $now
  }
  ($obj | ConvertTo-Json) | Set-Content -Encoding UTF8 -Path $StatePath
}

function Touch-LastCheck($state) {
  $state.lastCheckUtc = [DateTimeOffset]::UtcNow.ToString("o")
  ($state | ConvertTo-Json) | Set-Content -Encoding UTF8 -Path $StatePath
}

function Get-LatestSha([string]$etag) {
  $headers = @{ 'User-Agent' = $UserAgent }
  if ($etag) { $headers['If-None-Match'] = $etag }

  try {
    $resp = Invoke-WebRequest -Uri $ApiUrl -Headers $headers -UseBasicParsing -TimeoutSec $RequestTimeoutSec -ErrorAction Stop
    $commit = ($resp.Content | ConvertFrom-Json)
    if ($commit -is [System.Array]) { $commit = $commit[0] }
    return @{ sha = $commit.sha; etag = $resp.Headers['ETag']; notModified = $false }
  } catch {
    # PowerShell 7+ often throws HttpResponseException; Windows PowerShell may throw WebException.
    $resp = $_.Exception.Response
    $statusCode = $null
    if ($resp) {
      try { $statusCode = [int]$resp.StatusCode } catch { }
      if ($statusCode -eq 304) {
        return @{ sha = $null; etag = $etag; notModified = $true }
      }
    }
    Write-Host "[warn] Could not query GitHub: $($_.Exception.Message)"
    return $null
  }
}

# ---------- Main ----------
$state = Get-State
try {
    $last = [DateTimeOffset]::Parse($state.lastCheckUtc).UtcDateTime
    $now  = (Get-Date).ToUniversalTime()

    $delta = $now - $last
    $secs  = [Math]::Round($delta.TotalSeconds, 3)

    Write-Host "[debug] lastCheckUtc = $($last.ToString('o'))"
    Write-Host "[debug] now          = $($now.ToString('o'))"
    Write-Host "[debug] delta        = $secs seconds"
    Write-Host "[debug] min interval = $MinCheckIntervalSeconds seconds"

    if ($delta.TotalSeconds -lt 0) {
        Write-Host "[warn] lastCheckUtc is in the future; resetting lastCheckUtc to now."
        Touch-LastCheck $state
        $delta = [TimeSpan]::Zero
        $secs  = 0
    }

    if ($delta.TotalSeconds -lt $MinCheckIntervalSeconds) {
        $remaining = [Math]::Round($MinCheckIntervalSeconds - $delta.TotalSeconds, 3)
        Write-Host "[info] Skipping update check ($secs s since last, $remaining s remaining)"
        return
    }
}
catch {
    Write-Host "[warn] Could not parse lastCheckUtc, forcing check: $($_.Exception.Message)"
}

$result = Get-LatestSha -etag $state.etag
if (-not $result) { Touch-LastCheck $state; return }
if ($result.notModified) { Touch-LastCheck $state; Write-Host "[info] Already up-to-date ($($state.sha))"; return }

$newSha = $result.sha
if ([string]::IsNullOrEmpty($newSha)) { Touch-LastCheck $state; return }

if ($state.sha -eq $newSha) {
  Touch-LastCheck $state
  Write-Host "[info] Already up-to-date ($newSha)"
  return
}

Write-Host "[info] New version detected ($newSha). Updating..."

# Prepare temp workspace
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
$ZipPath = Join-Path $TempDir "annotator.zip"

# Download archive
Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -Headers @{ 'User-Agent' = $UserAgent } -TimeoutSec $RequestTimeoutSec

# Extract
Expand-Archive -Force $ZipPath -DestinationPath $TempDir
Remove-Item $ZipPath -Force

# Locate extracted project root (first folder containing pixi.toml)
$NewProjectDir = Get-ChildItem -Directory -Path $TempDir -Recurse | Where-Object { Test-Path (Join-Path $_.FullName 'pixi.toml') } | Select-Object -First 1
if (-not $NewProjectDir) { throw "Cannot find project root in downloaded archive." }

# Atomic-ish swap using rename (same volume)
$NewPath = Join-Path $InstallRoot "app.new"
if (Test-Path $NewPath) { Remove-Item -Recurse -Force $NewPath }
Move-Item -Force $NewProjectDir.FullName $NewPath

$OldPath = "$AppDir.old"
try {
  if (Test-Path $AppDir) { Rename-Item -Path $AppDir -NewName $OldPath -Force }
  Rename-Item -Path $NewPath -NewName $AppDir -Force
  if (Test-Path $OldPath) { Remove-Item -Recurse -Force $OldPath }
} catch {
  Write-Host "[error] Swap failed: $($_.Exception.Message)"
  # Roll back if needed
  if ((-not (Test-Path $AppDir)) -and (Test-Path $OldPath)) {
    try { Rename-Item -Path $OldPath -NewName $AppDir -Force } catch { }
  }
  throw
}

# Clean temp and persist state
Remove-Item -Recurse -Force $TempDir
Set-State -sha $newSha -etag $result.etag
Write-Host "[info] Update complete -> $newSha"

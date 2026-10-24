param([switch]$SkipStation)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Get-Content "$root\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

Push-Location "$root\backend"
& ".\venv\Scripts\python.exe" -m pytest -q
$backendExit = $LASTEXITCODE
Pop-Location
if ($backendExit -ne 0) { throw "FAILED: backend tests" }

if (-not $SkipStation) {
    Push-Location "$root\station"
    & ".\.venv\Scripts\python.exe" -m pytest -q
    $stationExit = $LASTEXITCODE
    Pop-Location
    if ($stationExit -ne 0) { throw "FAILED: station tests" }
}
Write-Host "All tests passed."

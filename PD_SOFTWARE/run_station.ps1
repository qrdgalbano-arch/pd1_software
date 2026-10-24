$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\install_windows.ps1 first." }

$url = (& $py -c "from station.config import get_settings as g; s=g(); print(f'http://{s.station_host}:{s.station_port}/')").Trim()

Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 4; Start-Process $u } -ArgumentList $url | Out-Null

Write-Host "Station UI: $url (press Ctrl+C to stop)"
& $py -m station

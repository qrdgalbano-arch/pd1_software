param([string]$Py = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path $Py)) { throw "Run .\install_windows.ps1 first, or pass -Py <path to python.exe>." }
$env:STATION_HOST = "127.0.0.1"
$env:STATION_PORT = "18081"
$env:PYTHONPATH = $PSScriptRoot
& $Py .\seed_offline.py
Start-Process "http://127.0.0.1:18081/"
& $Py -X utf8 -m uvicorn station.server:app --host 127.0.0.1 --port 18081
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:STATION_PORT = "18080"
$env:STATION_HOST = "127.0.0.1"
$env:DATABASE_PATH = Join-Path $PSScriptRoot "data\station.db"
$env:POSE_MODEL_PATH = Join-Path $PSScriptRoot "models\pose_landmarker_full.task"
$env:PYTHONPATH = $PSScriptRoot
$Python = 'C:\Users\fafal\Documents\pd1_software\PD_SOFTWARE\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw "Original shared Python environment was moved or removed."
}
Write-Host "PD1 Design B: http://127.0.0.1:18080/"
Write-Host "Run only one application on port 18080 at a time."
& $Python -X utf8 -m uvicorn station.server:app --host 127.0.0.1 --port 18080

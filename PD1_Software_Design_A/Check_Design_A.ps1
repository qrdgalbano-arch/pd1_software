param([string]$Py = ".\.venv\Scripts\python.exe")
$ProgressPreference = "SilentlyContinue"
Set-Location $PSScriptRoot
$env:STATION_HOST = "127.0.0.1"
$env:STATION_PORT = "18080"
$env:PYTHONPATH = $PSScriptRoot
$env:BACKEND_URL = "http://127.0.0.1:1"
& $Py .\scripts\verify_install.py
& $Py .\seed_offline.py
& $Py -m pytest tests -q
$p = Start-Process $Py -ArgumentList "-X","utf8","-m","uvicorn","station.server:app","--host","127.0.0.1","--port","18080" -PassThru -WindowStyle Hidden
Start-Sleep 12
$base = "http://127.0.0.1:18080"
foreach ($u in "/","/api/status","/api/patients","/api/exercises","/api/patients/1/prescriptions","/static/app.js") {
  try { $c = (Invoke-WebRequest "$base$u" -UseBasicParsing -TimeoutSec 8).StatusCode } catch { $c = "FAIL" }
  "$u -> $c"
}
(Invoke-RestMethod "$base/api/patients/1/prescriptions").prescriptions | ForEach-Object { "Exercise: " + $_.exercise.name }
Stop-Process -Id $p.Id -Force

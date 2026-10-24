$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Check($step) { if ($LASTEXITCODE -ne 0) { throw "FAILED: $step" } }

$ThreeVersion = "0.170.0"
$PoseModelUrl = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
$Cdn = "https://cdn.jsdelivr.net/npm/three@$ThreeVersion"

Write-Host "==> Python virtual environment"
if (-not (Test-Path ".venv")) { python -m venv .venv; Check "venv" }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip; Check "pip upgrade"
& $py -m pip install -r requirements.txt; Check "pip install"

Write-Host "==> MediaPipe BlazePose Full model"
New-Item -ItemType Directory -Force models, data, avatar | Out-Null
if (-not (Test-Path "models\pose_landmarker_full.task")) {
    Invoke-WebRequest -Uri $PoseModelUrl -OutFile "models\pose_landmarker_full.task"
}

Write-Host "==> Three.js $ThreeVersion"
$dirs = "web\vendor\three\build", "web\vendor\three\examples\jsm\loaders", "web\vendor\three\examples\jsm\controls", "web\vendor\three\examples\jsm\utils"
$dirs | ForEach-Object { New-Item -ItemType Directory -Force $_ | Out-Null }
$files = @{
    "web\vendor\three\build\three.module.js"                     = "$Cdn/build/three.module.js"
    "web\vendor\three\examples\jsm\loaders\GLTFLoader.js"        = "$Cdn/examples/jsm/loaders/GLTFLoader.js"
    "web\vendor\three\examples\jsm\controls\OrbitControls.js"    = "$Cdn/examples/jsm/controls/OrbitControls.js"
    "web\vendor\three\examples\jsm\utils\BufferGeometryUtils.js" = "$Cdn/examples/jsm/utils/BufferGeometryUtils.js"
}
foreach ($f in $files.GetEnumerator()) {
    if (-not (Test-Path $f.Key)) { Invoke-WebRequest -Uri $f.Value -OutFile $f.Key }
}

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

Write-Host "==> Verifying installation"
& $py ".\scripts\verify_install.py"; Check "verify"

Write-Host "Done. Run: .\station\run_station.ps1"

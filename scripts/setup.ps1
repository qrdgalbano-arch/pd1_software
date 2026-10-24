$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Check($step) { if ($LASTEXITCODE -ne 0) { throw "FAILED: $step" } }

$pgBin = Get-ChildItem "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "bin" } |
    Where-Object { Test-Path "$_\psql.exe" } | Select-Object -First 1
if ($pgBin -and ($env:Path -notlike "*$pgBin*")) { $env:Path += ";$pgBin" }

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

$u = $env:POSTGRES_USER
$p = $env:POSTGRES_PASSWORD
$d = $env:POSTGRES_DB

$sec = Read-Host "Enter PostgreSQL 'postgres' admin password" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))

$roleExists = (psql -U postgres -h localhost -tAc "SELECT 1 FROM pg_roles WHERE rolname='$u'") -join ""
Check "role lookup"
if ($roleExists.Trim() -eq "1") {
    psql -U postgres -h localhost -c "ALTER USER $u WITH PASSWORD '$p';"; Check "alter user"
} else {
    psql -U postgres -h localhost -c "CREATE USER $u WITH PASSWORD '$p';"; Check "create user"
}

$dbExists = (psql -U postgres -h localhost -tAc "SELECT 1 FROM pg_database WHERE datname='$d'") -join ""
Check "database lookup"
if ($dbExists.Trim() -ne "1") {
    psql -U postgres -h localhost -c "CREATE DATABASE $d OWNER $u;"; Check "create database"
}
Remove-Item Env:PGPASSWORD

Set-Location "$root\backend"
if (-not (Test-Path "venv")) { python -m venv venv; Check "venv" }
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip; Check "pip upgrade"
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt; Check "pip install"
& ".\venv\Scripts\python.exe" -m alembic upgrade head; Check "alembic"

Write-Host "Setup complete. Run: .\scripts\run.ps1"

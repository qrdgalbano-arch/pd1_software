$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Import-DotEnv($path) {
    Get-Content $path | ForEach-Object {
        if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Import-DotEnv ".env"

$pgAdminPass = Read-Host "Enter PostgreSQL 'postgres' admin password" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgAdminPass))

$u = $env:POSTGRES_USER
$p = $env:POSTGRES_PASSWORD
$d = $env:POSTGRES_DB

psql -U postgres -h localhost -tc "SELECT 1 FROM pg_roles WHERE rolname='$u'" | Select-String "1" | Out-Null
if (-not $?) { psql -U postgres -h localhost -c "CREATE USER $u WITH PASSWORD '$p';" }
psql -U postgres -h localhost -tc "SELECT 1 FROM pg_database WHERE datname='$d'" | Select-String "1" | Out-Null
if (-not $?) { psql -U postgres -h localhost -c "CREATE DATABASE $d OWNER $u;" }
Remove-Item Env:PGPASSWORD

Set-Location "$root\backend"
if (-not (Test-Path "venv")) { python -m venv venv }
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\venv\Scripts\python.exe" -m alembic upgrade head

Write-Host "Setup complete. Run: .\scripts\run.ps1"

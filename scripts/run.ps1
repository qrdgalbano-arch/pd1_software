param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$Reload
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Get-Content "$root\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

Set-Location "$root\backend"
& ".\venv\Scripts\python.exe" -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "FAILED: alembic" }

$uvArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", $Port, "--proxy-headers")
if ($Reload) { $uvArgs += "--reload" }
& ".\venv\Scripts\python.exe" @uvArgs

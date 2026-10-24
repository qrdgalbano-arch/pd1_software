# Deployment Guide

## Purpose

This guide documents running the QMMC PD1 proof of concept as a single native application, without Docker.

The system is a rehabilitation monitoring POC. It intentionally excludes AI, pose estimation, camera capture, deep learning, wearable devices, sensor inputs, continuous video streaming, and raw video storage.

## Prerequisites

- Windows with PowerShell.
- Python 3.12 or newer.
- PostgreSQL 16 or newer, running as a service.
- A TLS-capable reverse proxy or load balancer before exposing the app outside a controlled internal network.
- A dedicated Android release/upload keystore before distributing the mobile app outside internal testing.

## Environment File

1. Create the environment file from the template:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Replace every placeholder value, including `POSTGRES_PASSWORD`, `DATABASE_URL`, and `JWT_SECRET_KEY`.

3. Generate a strong JWT secret:

   ```powershell
   -join ((48..57 + 97..102) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
   ```

4. Keep `DATABASE_URL` pointed at `localhost`:

   ```text
   DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/DBNAME
   ```

5. For production, set the deployed origin and host name:

   ```text
   CORS_ORIGINS=https://dashboard.example.com
   TRUSTED_HOSTS=dashboard.example.com
   ```

6. Keep `.env` and `.env.production` private. Both are ignored by Git.

## First-Time Setup

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

The script creates the database role and database, creates the Python virtual environment, installs dependencies, and applies Alembic migrations.

## Start the App

```powershell
.\scripts\run.ps1
```

For development with auto-reload:

```powershell
.\scripts\run.ps1 -Reload
```

The app serves the API, the staff dashboard, and the health endpoint from one process on port 8000:

| Path | Purpose |
|---|---|
| `http://localhost:8000/docs` | API documentation |
| `http://localhost:8000/staff-dashboard` | Staff dashboard |
| `http://localhost:8000/health` | Health check |

`run.ps1` applies pending Alembic migrations before starting Uvicorn. Check migration status:

```powershell
cd backend
.\venv\Scripts\python.exe -m alembic current
.\venv\Scripts\python.exe -m alembic heads
cd ..
```

The current expected revision is `7c1d2e3f4a5b`.

## Health Check

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response fields include `status: healthy` and `service: qmmc-pd1-backend`.

## HTTPS

The app serves plain HTTP. Before exposing patient or staff traffic outside a controlled internal network:

- Terminate TLS at a managed load balancer or reverse proxy.
- Redirect HTTP traffic to HTTPS.
- Configure a valid certificate for the deployed DNS name.
- Set `CORS_ORIGINS` and `TRUSTED_HOSTS` to the deployed HTTPS host name only.
- Do not use placeholder example domains or default example secrets.

## Database Backup and Restore

Create a backup:

```powershell
$env:Path += ";C:\Program Files\PostgreSQL\18\bin"
$env:PGPASSWORD = "<POSTGRES_PASSWORD>"
pg_dump -U <POSTGRES_USER> -h localhost -F c -f "qmmc_pd1_$(Get-Date -Format yyyy-MM-dd).dump" <POSTGRES_DB>
Remove-Item Env:PGPASSWORD
```

Restore only after stopping the app and verifying the target database:

```powershell
$env:PGPASSWORD = "<POSTGRES_PASSWORD>"
pg_restore -U <POSTGRES_USER> -h localhost -d <POSTGRES_DB> --clean --if-exists "qmmc_pd1_YYYY-MM-DD.dump"
Remove-Item Env:PGPASSWORD
```

Test restoration in a separate non-production environment before relying on this procedure.

## Upgrade and Rollback

For an upgrade:

```powershell
git fetch origin
git checkout <approved-release-tag>
.\scripts\setup.ps1
.\scripts\run.ps1
```

Review migrations and take a verified backup before every upgrade.

For rollback:

1. Stop the app.
2. Check out the previously deployed release tag.
3. Restore the pre-upgrade database backup if the migration is not backward compatible.
4. Start the app with `.\scripts\run.ps1`.
5. Verify `/health`, authentication, dashboard access, and console output.

Database rollback is not automatic. Treat schema migrations as operationally significant changes.

## Android Release Build

The current `flutter build apk --release` command completes successfully, producing an APK for internal validation. The current Gradle configuration uses the Android debug signing key for release builds.

Before store, managed-device, or external distribution:

- Create and protect a dedicated release or upload keystore.
- Add an untracked `mobile/android/key.properties` file with keystore configuration.
- Configure the Android `release` build type to use that signing configuration.
- Keep keystores, passwords, aliases, and `key.properties` out of version control.
- Build and test a signed release APK or app bundle on representative target devices.

## Validation Checklist

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall .\app
cd ..\mobile
flutter test
flutter analyze
cd ..
node --check .\backend\app\web\static\js\staff_dashboard.js
```

## POC Limits and Follow-up Work

This POC is not ready for real clinical or public production use without additional work, including:

- TLS enforcement, certificate renewal, and HTTP-to-HTTPS redirects.
- Secure secrets storage and rotation.
- Dedicated release signing for Android.
- PostgreSQL integration tests and backup-restore drills.
- Centralized logging, monitoring, alerting, and incident response procedures.
- Rate limiting, audit logging, account lifecycle controls, password-reset flows, and stronger session/token revocation.
- A security and privacy review appropriate to the intended health-data jurisdiction.
- Accessibility testing on representative budget Android devices.
- Formal clinical validation and institutional approval.

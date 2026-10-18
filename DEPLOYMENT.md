# Deployment Guide

## Purpose

This guide documents deployment preparation for the QMMC PD1 proof of concept.

The system is a rehabilitation monitoring POC. It intentionally excludes AI, pose estimation, camera capture, deep learning, wearable devices, sensor inputs, continuous video streaming, and raw video storage.

The production Compose configuration is designed for a single-host POC deployment. It is not, by itself, a complete healthcare-production deployment.

## Prerequisites

- Docker Engine and Docker Compose v2 on a Linux host or supported server environment.
- A DNS name for the staff dashboard, such as `dashboard.example.com`.
- A TLS certificate and HTTPS-capable edge proxy, load balancer, or Nginx TLS configuration.
- A private network or firewall policy that exposes only HTTPS to approved clients.
- A secure location for production environment variables and database backups.
- A dedicated Android release/upload keystore before distributing the mobile app outside internal testing.

## Production Environment File

1. Copy the template without committing the resulting file:

   ```sh
   cp .env.production.example .env.production
   chmod 600 .env.production
   ```

2. Replace every placeholder value.

3. Generate a strong JWT secret, for example:

   ```sh
   openssl rand -hex 32
   ```

4. Set a unique database password.

5. Set the deployed dashboard origin and host name:

   ```text
   CORS_ORIGINS=https://dashboard.example.com
   TRUSTED_HOSTS=dashboard.example.com
   ```

6. Keep `.env.production` private. It is ignored by Git and must never be committed, emailed, or placed in screenshots.

## Start Deployment

Run from the repository root:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

The deployment starts three containers:

| Service | Exposure | Responsibility |
|---|---|---|
| PostgreSQL | Internal Docker network only | Persistent application database |
| FastAPI backend | Internal Docker network only | API, staff dashboard, migration startup, health endpoint |
| Nginx | Host port 80 | Reverse proxy for the dashboard, API, and health endpoint |

The backend entrypoint runs `alembic upgrade head` before starting Uvicorn. Confirm migration status after startup:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml exec backend alembic current
docker compose --env-file .env.production -f docker-compose.production.yml exec backend alembic heads
```

The current expected revision is `30bd78166036`.

## Health and Logs

Check service state:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

Check the proxied health endpoint:

```sh
curl -i http://localhost/health
```

Check logs:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 backend
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 nginx
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 db
```

Expected health response fields include `status: healthy`, `service: qmmc-pd1-backend`, and `environment: production`.

## HTTPS

The committed Nginx configuration listens on HTTP port 80 only. Before exposing patient or staff traffic outside a controlled internal network:

- Terminate TLS at a managed load balancer, reverse proxy, or an extended Nginx TLS configuration.
- Redirect HTTP traffic to HTTPS.
- Configure a valid certificate for the deployed DNS name.
- Set `CORS_ORIGINS` and `TRUSTED_HOSTS` to the deployed HTTPS host name only.
- Do not use placeholder example domains or default example secrets.

## Database Backup and Restore

Create a compressed logical backup:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > qmmc_pd1_$(date +%F).sql.gz
```

Restore only after stopping application writes and verifying the target database:

```sh
gzip -dc qmmc_pd1_YYYY-MM-DD.sql.gz | \
  docker compose --env-file .env.production -f docker-compose.production.yml exec -T db \
  psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

Test backup restoration in a separate non-production environment before relying on this procedure.

## Upgrade and Rollback

For an upgrade:

```sh
git fetch origin
git checkout <approved-release-tag>
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

The backend applies pending Alembic migrations at startup. Review migrations and take a verified backup before every upgrade.

For rollback:

1. Stop the deployment.
2. Restore the previously deployed image/tag.
3. Restore the pre-upgrade database backup if the migration is not backward compatible.
4. Start the previous release.
5. Verify `/health`, authentication, dashboard access, and logs.

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

Run before an approved POC deployment:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml config
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
curl -i http://localhost/health
```

Also run the repository validation suite before creating a release:

```sh
docker compose exec backend python -m pytest -q
docker compose exec backend python -m compileall /app/app
cd mobile && flutter test && flutter analyze
node --check backend/app/web/static/js/staff_dashboard.js
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

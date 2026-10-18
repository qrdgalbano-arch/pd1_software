# Testing and Validation

## Scope

This document records the automated and manual validation completed for the QMMC PD1 proof of concept.

The POC is a rehabilitation monitoring system. It intentionally excludes AI, camera capture, pose estimation, deep learning, and raw video upload.

## Automated Backend Tests

Run from the repository root:

```powershell
docker compose exec backend python -m pytest -q
```

Current result:

```text
33 passed
```

The backend suite uses FastAPI `TestClient` and a separate in-memory SQLite database. Tests override the application database dependency, create the SQLAlchemy model tables for each test, and do not read or write the Docker PostgreSQL demo database.

### Coverage

| Area | Validated behavior |
|---|---|
| Authentication | Valid login, invalid credentials, inactive-user rejection, access-token identity lookup, refresh-token issuance, invalid refresh-token rejection |
| Authorization | Unauthenticated staff requests rejected, patient role blocked from staff routes, staff role blocked from patient-only route |
| Patient prescriptions | Patient can retrieve only their own active prescriptions with exercise context |
| Exercise catalog | Staff lists active exercises, creates exercises, and receives a conflict for duplicate names |
| Prescription assignment | Staff creates prescriptions; non-patient targets and inactive exercises are rejected; invalid payloads receive validation errors |
| Dashboard summary | Active patient, active prescription, recent session, unresolved-flag, status-count, and activity-count summaries |
| Dashboard patients | Patient list and name/email search |
| Dashboard detail | Prescription exercise context, session prescription/exercise context, session limits, patient flag filtering, dashboard-wide flag patient context |
| Error paths | Unknown or non-patient IDs return `404` for patient-detail dashboard routes |

## Flutter Validation

Run from the Flutter project directory:

```powershell
Push-Location .\mobile
flutter test
flutter analyze
Pop-Location
```

Current results:

```text
flutter test: 4 passed
flutter analyze: No issues found
```

Existing Flutter tests validate enriched prescription JSON parsing, duration formatting, invalid prescription payload handling, and unauthenticated application routing to the login screen.

## Runtime Smoke Tests

Run from the repository root:

```powershell
docker compose up -d --build
docker compose exec backend python -m compileall /app/app
node --check .\backend\app\web\static\js\staff_dashboard.js
```

Manual staff dashboard smoke-test URL:

```text
http://localhost:8000/staff-dashboard
```

Verify staff login, dashboard summary cards, session-status chart, patient search, prescriptions, session history, compliance flags, and sign-out.

## Known Warnings

- Starlette/AnyIO emits a `BlockingPortal` deprecation warning from the installed dependency stack.
- Python 3.12 warns that `datetime.utcnow()` is deprecated. The current models, dashboard summary query, and test fixture use naive UTC timestamps. A future maintenance change should migrate to timezone-aware UTC timestamps after reviewing Alembic migrations and PostgreSQL compatibility.
- Flutter reports newer package versions are available but outside the current dependency constraints. This is not a test failure.

## POC Limitations

- The current backend does not yet expose an exercise-session ingestion endpoint, so automated API synchronization and server-side compliance-rule tests cannot be added until that API exists.
- The current Flutter source tree does not contain an implemented ObjectBox queue or WorkManager synchronization module, so offline-queue behavior is not currently testable in this repository state.
- The test database is SQLite for fast isolated API tests. PostgreSQL-specific behavior should be validated in a future integration-test environment before production deployment.
- Automated browser end-to-end tests are not included; the staff dashboard has been validated through manual browser smoke testing.

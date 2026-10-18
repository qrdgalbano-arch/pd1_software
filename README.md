# QMMC PD1 Proof of Concept

## Project Description

This repository contains the proof-of-concept implementation of a mobile and web-based rehabilitation monitoring system for osteoarthritis patients.

The proof of concept demonstrates the non-AI components of the planned system:

- Patient mobile application workflow
- Dummy exercise-session recording
- Exercise prescriptions
- Local session-log storage
- Offline pending-log queue
- Synchronization when internet connectivity returns
- Staff monitoring dashboard
- Compliance and missed-session flags
- Authentication and role-based access control

## Scope Limitation

This proof of concept does not yet include:

- Camera pose estimation
- Deep learning or machine learning models
- Wearable devices
- Sensors
- Physical markers
- Continuous video streaming
- Raw video storage

The final pose-estimation component may be integrated in a later development phase.

## Planned Technology Stack

- Flutter and Dart
- Riverpod
- ObjectBox
- Dio
- FastAPI and Python
- PostgreSQL
- SQLAlchemy and Alembic
- Bootstrap 5
- Chart.js
- Docker and Docker Compose
- Nginx
- Git and GitHub

## Development Approach

The system will be developed in the following order:

1. Repository setup
2. Backend foundation
3. Database models
4. Authentication and security
5. Prescription management
6. Flutter mobile application shell
7. Dummy exercise-session module
8. Local database and offline queue
9. API synchronization
10. Notifications and compliance checking
11. Staff dashboard
12. Testing and validation
13. Production and deployment preparation

## Developer

- REAGAN

## Repository

qrdgalbano-arch/qmmc_pd1_poc
## Validation and Deployment

- See [TESTING.md](TESTING.md) for automated backend tests, Flutter checks, runtime smoke tests, and POC test limitations.
- See [DEPLOYMENT.md](DEPLOYMENT.md) for production-environment setup, Docker Compose deployment, backups, rollback, HTTPS requirements, Android signing, and deployment limitations.
- Use `docker-compose.production.yml` only with a private, untracked `.env.production` created from `.env.production.example`.

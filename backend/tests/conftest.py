from collections.abc import Generator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.security import hash_password
from app.database.session import Base
from app.main import app
from app.models import (
    Exercise,
    ExerciseSession,
    FlagType,
    Prescription,
    SessionStatus,
    StaffFlag,
    SyncStatus,
    User,
    UserRole,
)

TEST_DATABASE_URL = "sqlite://"


@pytest.fixture(scope="session")
def engine():
    test_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )()

    try:
        yield testing_session
    finally:
        testing_session.close()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(
        app,
        base_url="http://localhost",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_data(db: Session) -> dict[str, object]:
    staff = User(
        full_name="Demo Rehabilitation Staff",
        email="staff@example.com",
        password_hash=hash_password("staff-password"),
        role=UserRole.staff,
        is_active=True,
    )
    patient = User(
        full_name="Demo Patient",
        email="patient@example.com",
        password_hash=hash_password("patient-password"),
        role=UserRole.patient,
        is_active=True,
    )
    other_patient = User(
        full_name="Other Patient",
        email="other.patient@example.com",
        password_hash=hash_password("other-password"),
        role=UserRole.patient,
        is_active=True,
    )
    inactive_patient = User(
        full_name="Inactive Patient",
        email="inactive.patient@example.com",
        password_hash=hash_password("inactive-password"),
        role=UserRole.patient,
        is_active=False,
    )
    exercise = Exercise(
        name="Seated Knee Extension",
        description="Sit upright, straighten one knee, then lower it.",
        default_repetitions=10,
        default_duration_seconds=90,
        is_active=True,
    )
    inactive_exercise = Exercise(
        name="Archived Exercise",
        description="This exercise is inactive.",
        default_repetitions=5,
        default_duration_seconds=30,
        is_active=False,
    )

    db.add_all(
        [
            staff,
            patient,
            other_patient,
            inactive_patient,
            exercise,
            inactive_exercise,
        ]
    )
    db.flush()

    active_prescription = Prescription(
        patient_id=patient.id,
        staff_id=staff.id,
        exercise_id=exercise.id,
        repetitions_target=10,
        duration_limit_seconds=90,
        scheduled_days="Monday, Wednesday, Friday",
        is_active=True,
    )
    inactive_prescription = Prescription(
        patient_id=patient.id,
        staff_id=staff.id,
        exercise_id=exercise.id,
        repetitions_target=5,
        duration_limit_seconds=60,
        scheduled_days="Tuesday",
        is_active=False,
    )
    other_prescription = Prescription(
        patient_id=other_patient.id,
        staff_id=staff.id,
        exercise_id=exercise.id,
        repetitions_target=8,
        duration_limit_seconds=75,
        scheduled_days="Thursday",
        is_active=True,
    )

    db.add_all(
        [
            active_prescription,
            inactive_prescription,
            other_prescription,
        ]
    )
    db.flush()

    now = datetime.utcnow()
    db.add_all(
        [
            ExerciseSession(
                client_session_id="test-completed-session",
                patient_id=patient.id,
                prescription_id=active_prescription.id,
                status=SessionStatus.completed,
                repetitions_completed=10,
                duration_seconds=88,
                error_count=0,
                error_summary="",
                device_recorded_at=now - timedelta(days=1),
                server_received_at=now - timedelta(days=1),
                sync_status=SyncStatus.synced,
            ),
            ExerciseSession(
                client_session_id="test-incomplete-session",
                patient_id=patient.id,
                prescription_id=active_prescription.id,
                status=SessionStatus.incomplete,
                repetitions_completed=6,
                duration_seconds=55,
                error_count=2,
                error_summary="Keep the knee aligned.",
                device_recorded_at=now - timedelta(days=2),
                server_received_at=now - timedelta(days=2),
                sync_status=SyncStatus.synced,
            ),
            ExerciseSession(
                client_session_id="test-cancelled-session",
                patient_id=other_patient.id,
                prescription_id=other_prescription.id,
                status=SessionStatus.cancelled,
                repetitions_completed=0,
                duration_seconds=12,
                error_count=0,
                error_summary="",
                device_recorded_at=now - timedelta(days=3),
                server_received_at=now - timedelta(days=3),
                sync_status=SyncStatus.synced,
            ),
        ]
    )
    db.add_all(
        [
            StaffFlag(
                patient_id=patient.id,
                flag_type=FlagType.incomplete_session,
                message="Session ended before the repetition target.",
                is_resolved=False,
            ),
            StaffFlag(
                patient_id=patient.id,
                flag_type=FlagType.repeated_error,
                message="Repeated form errors were recorded.",
                is_resolved=False,
            ),
            StaffFlag(
                patient_id=other_patient.id,
                flag_type=FlagType.missed_session,
                message="A scheduled session was missed.",
                is_resolved=True,
            ),
        ]
    )
    db.commit()

    return {
        "staff": staff,
        "patient": patient,
        "other_patient": other_patient,
        "inactive_patient": inactive_patient,
        "exercise": exercise,
        "inactive_exercise": inactive_exercise,
        "active_prescription": active_prescription,
        "inactive_prescription": inactive_prescription,
    }


@pytest.fixture()
def login(client: TestClient):
    def login_user(email: str, password: str) -> dict[str, str]:
        response = client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return login_user


@pytest.fixture()
def staff_headers(seeded_data, login) -> dict[str, str]:
    tokens = login("staff@example.com", "staff-password")
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture()
def patient_headers(seeded_data, login) -> dict[str, str]:
    tokens = login("patient@example.com", "patient-password")
    return {"Authorization": f"Bearer {tokens['access_token']}"}

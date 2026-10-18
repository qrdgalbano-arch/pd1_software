from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.session import SessionLocal
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


def main() -> None:
    with SessionLocal() as db:
        staff = db.scalar(
            select(User).where(User.email == "staff@example.com")
        )
        patient = db.scalar(
            select(User).where(User.email == "patient@example.com")
        )

        if staff is None or patient is None:
            raise RuntimeError(
                "Run scripts/seed_demo_users.py before seeding dashboard data."
            )

        exercise = db.scalar(
            select(Exercise).where(
                Exercise.name == "Seated Knee Extension"
            )
        )

        if exercise is None:
            exercise = Exercise(
                name="Seated Knee Extension",
                description=(
                    "Sit upright. Slowly straighten one knee, "
                    "then lower it."
                ),
                default_repetitions=10,
                default_duration_seconds=90,
                is_active=True,
            )
            db.add(exercise)
            db.flush()

        prescription = db.scalar(
            select(Prescription).where(
                Prescription.patient_id == patient.id,
                Prescription.exercise_id == exercise.id,
            )
        )

        if prescription is None:
            prescription = Prescription(
                patient_id=patient.id,
                staff_id=staff.id,
                exercise_id=exercise.id,
                repetitions_target=10,
                duration_limit_seconds=90,
                scheduled_days="Monday, Wednesday, Friday",
                is_active=True,
            )
            db.add(prescription)
            db.flush()

        existing_session = db.scalar(
            select(ExerciseSession).where(
                ExerciseSession.client_session_id
                == "dashboard-demo-session-1"
            )
        )

        if existing_session is None:
            now = datetime.utcnow()

            sessions = [
                ExerciseSession(
                    client_session_id="dashboard-demo-session-1",
                    patient_id=patient.id,
                    prescription_id=prescription.id,
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
                    client_session_id="dashboard-demo-session-2",
                    patient_id=patient.id,
                    prescription_id=prescription.id,
                    status=SessionStatus.incomplete,
                    repetitions_completed=6,
                    duration_seconds=55,
                    error_count=2,
                    error_summary="Keep the knee aligned during extension.",
                    device_recorded_at=now - timedelta(days=3),
                    server_received_at=now - timedelta(days=3),
                    sync_status=SyncStatus.synced,
                ),
                ExerciseSession(
                    client_session_id="dashboard-demo-session-3",
                    patient_id=patient.id,
                    prescription_id=prescription.id,
                    status=SessionStatus.cancelled,
                    repetitions_completed=0,
                    duration_seconds=12,
                    error_count=0,
                    error_summary="",
                    device_recorded_at=now - timedelta(days=5),
                    server_received_at=now - timedelta(days=5),
                    sync_status=SyncStatus.synced,
                ),
            ]

            db.add_all(sessions)

        existing_flag = db.scalar(
            select(StaffFlag).where(
                StaffFlag.message
                == "Repeated form errors were recorded during knee extension."
            )
        )

        if existing_flag is None:
            db.add_all(
                [
                    StaffFlag(
                        patient_id=patient.id,
                        flag_type=FlagType.repeated_error,
                        message=(
                            "Repeated form errors were recorded during "
                            "knee extension."
                        ),
                        is_resolved=False,
                    ),
                    StaffFlag(
                        patient_id=patient.id,
                        flag_type=FlagType.incomplete_session,
                        message=(
                            "The most recent knee extension session "
                            "ended before the repetition target."
                        ),
                        is_resolved=False,
                    ),
                ]
            )

        db.commit()
        print("Dashboard demo data is ready.")


if __name__ == "__main__":
    main()
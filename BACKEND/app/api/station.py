"""Session ingestion API for the Component Twin exercise station.

The station (Ubuntu Mini PC + camera) records exercise sessions locally and
uploads them here when connectivity is available. Uploads are idempotent:
re-sending the same ``client_session_id`` returns the stored record.
"""

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_staff
from app.database.session import get_db
from app.models import (
    ExerciseSession,
    FlagType,
    Prescription,
    SessionStatus,
    StaffFlag,
    SyncStatus,
    User,
    UserRole,
)
from app.schemas.dashboard import ExerciseSessionResponse
from app.schemas.sessions import ExerciseSessionIngest

REPEATED_ERROR_THRESHOLD = 3

router = APIRouter(
    prefix="/staff",
    tags=["station"],
    dependencies=[Depends(require_staff)],
)


def _load_session(db: Session, session_id: int) -> ExerciseSession:
    return db.scalar(
        select(ExerciseSession)
        .options(
            joinedload(ExerciseSession.prescription).joinedload(
                Prescription.exercise
            )
        )
        .where(ExerciseSession.id == session_id)
    )


def _create_flags(
    db: Session,
    record: ExerciseSession,
    exercise_name: str,
) -> None:
    if record.status == SessionStatus.incomplete:
        db.add(
            StaffFlag(
                patient_id=record.patient_id,
                flag_type=FlagType.incomplete_session,
                message=(
                    f"{exercise_name}: session ended with "
                    f"{record.valid_repetitions} valid repetitions."
                )[:300],
            )
        )

    if record.invalid_repetitions >= REPEATED_ERROR_THRESHOLD:
        db.add(
            StaffFlag(
                patient_id=record.patient_id,
                flag_type=FlagType.repeated_error,
                message=(
                    f"{exercise_name}: {record.invalid_repetitions} invalid "
                    f"repetitions. {record.error_summary}"
                )[:300],
            )
        )


@router.post(
    "/sessions",
    response_model=ExerciseSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_session(
    payload: ExerciseSessionIngest,
    response: Response,
    db: Session = Depends(get_db),
) -> ExerciseSession:
    existing = db.scalar(
        select(ExerciseSession).where(
            ExerciseSession.client_session_id == payload.client_session_id
        )
    )

    if existing is not None:
        if existing.patient_id != payload.patient_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="client_session_id already belongs to another patient",
            )
        response.status_code = status.HTTP_200_OK
        return _load_session(db, existing.id)

    patient = db.scalar(
        select(User).where(
            User.id == payload.patient_id,
            User.role == UserRole.patient,
        )
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    prescription = db.scalar(
        select(Prescription)
        .options(joinedload(Prescription.exercise))
        .where(Prescription.id == payload.prescription_id)
    )

    if prescription is None or prescription.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found for this patient",
        )

    recorded_at = payload.device_recorded_at
    if recorded_at.tzinfo is not None:
        recorded_at = recorded_at.astimezone(timezone.utc).replace(tzinfo=None)

    record = ExerciseSession(
        **payload.model_dump(exclude={"device_recorded_at"}),
        device_recorded_at=recorded_at,
        sync_status=SyncStatus.synced,
    )
    db.add(record)
    db.flush()

    _create_flags(db, record, prescription.exercise.name)
    db.commit()

    return _load_session(db, record.id)

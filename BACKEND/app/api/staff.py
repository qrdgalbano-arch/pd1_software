from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_staff
from app.database.session import get_db
from app.models import (
    Exercise,
    ExerciseSession,
    Prescription,
    SessionStatus,
    StaffFlag,
    User,
    UserRole,
)
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    ExerciseSessionResponse,
    RecentSessionActivity,
    SessionStatusCount,
    StaffFlagResponse,
    StaffPrescriptionResponse,
)
from app.schemas.exercises import ExerciseCreate, ExerciseResponse
from app.schemas.prescriptions import PrescriptionCreate, PrescriptionResponse
from app.schemas.users import PatientSummary

router = APIRouter(
    prefix="/staff",
    tags=["staff"],
    dependencies=[Depends(require_staff)],
)


def get_patient_or_404(patient_id: int, db: Session) -> User:
    patient = db.scalar(
        select(User).where(
            User.id == patient_id,
            User.role == UserRole.patient,
        )
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return patient


@router.get("/patients", response_model=list[PatientSummary])
def list_patients(
    query: str | None = Query(default=None, min_length=1, max_length=150),
    db: Session = Depends(get_db),
) -> list[User]:
    statement = select(User).where(User.role == UserRole.patient)

    if query:
        statement = statement.where(
            func.lower(User.full_name).contains(query.lower())
            | func.lower(User.email).contains(query.lower())
        )

    return list(db.scalars(statement.order_by(User.full_name)))


@router.get(
    "/patients/{patient_id}/prescriptions",
    response_model=list[StaffPrescriptionResponse],
)
def list_patient_prescriptions(
    patient_id: int,
    db: Session = Depends(get_db),
) -> list[Prescription]:
    get_patient_or_404(patient_id, db)

    return list(
        db.scalars(
            select(Prescription)
            .options(joinedload(Prescription.exercise))
            .where(Prescription.patient_id == patient_id)
            .order_by(Prescription.is_active.desc(), Prescription.created_at.desc())
        )
    )


@router.get(
    "/patients/{patient_id}/sessions",
    response_model=list[ExerciseSessionResponse],
)
def list_patient_sessions(
    patient_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ExerciseSession]:
    get_patient_or_404(patient_id, db)

    return list(
        db.scalars(
            select(ExerciseSession)
            .options(
                joinedload(ExerciseSession.prescription).joinedload(
                    Prescription.exercise
                )
            )
            .where(ExerciseSession.patient_id == patient_id)
            .order_by(ExerciseSession.device_recorded_at.desc())
            .limit(limit)
        )
    )


@router.get(
    "/patients/{patient_id}/flags",
    response_model=list[StaffFlagResponse],
)
def list_patient_flags(
    patient_id: int,
    include_resolved: bool = False,
    db: Session = Depends(get_db),
) -> list[StaffFlag]:
    get_patient_or_404(patient_id, db)

    statement = (
        select(StaffFlag)
        .options(joinedload(StaffFlag.patient))
        .where(StaffFlag.patient_id == patient_id)
    )

    if not include_resolved:
        statement = statement.where(StaffFlag.is_resolved.is_(False))

    return list(db.scalars(statement.order_by(StaffFlag.created_at.desc())))


@router.get("/flags", response_model=list[StaffFlagResponse])
def list_flags(
    include_resolved: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[StaffFlag]:
    statement = select(StaffFlag).options(joinedload(StaffFlag.patient))

    if not include_resolved:
        statement = statement.where(StaffFlag.is_resolved.is_(False))

    return list(
        db.scalars(
            statement.order_by(StaffFlag.created_at.desc()).limit(limit)
        )
    )


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
)
def get_dashboard_summary(
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    since = datetime.utcnow() - timedelta(days=7)

    patient_count = db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role == UserRole.patient,
            User.is_active.is_(True),
        )
    ) or 0

    active_prescription_count = db.scalar(
        select(func.count())
        .select_from(Prescription)
        .where(Prescription.is_active.is_(True))
    ) or 0

    recent_session_count = db.scalar(
        select(func.count())
        .select_from(ExerciseSession)
        .where(ExerciseSession.device_recorded_at >= since)
    ) or 0

    unresolved_flag_count = db.scalar(
        select(func.count())
        .select_from(StaffFlag)
        .where(StaffFlag.is_resolved.is_(False))
    ) or 0

    status_rows = db.execute(
        select(
            ExerciseSession.status,
            func.count(ExerciseSession.id),
        )
        .where(ExerciseSession.device_recorded_at >= since)
        .group_by(ExerciseSession.status)
        .order_by(ExerciseSession.status)
    ).all()

    activity_rows = db.execute(
        select(
            func.date(ExerciseSession.device_recorded_at),
            func.count(ExerciseSession.id),
        )
        .where(ExerciseSession.device_recorded_at >= since)
        .group_by(func.date(ExerciseSession.device_recorded_at))
        .order_by(func.date(ExerciseSession.device_recorded_at))
    ).all()

    return DashboardSummaryResponse(
        patient_count=patient_count,
        active_prescription_count=active_prescription_count,
        recent_session_count=recent_session_count,
        unresolved_flag_count=unresolved_flag_count,
        session_status_counts=[
            SessionStatusCount(status=row[0], count=row[1])
            for row in status_rows
        ],
        recent_session_activity=[
            RecentSessionActivity(date=str(row[0]), count=row[1])
            for row in activity_rows
        ],
    )


@router.post(
    "/exercises",
    response_model=ExerciseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_exercise(
    payload: ExerciseCreate,
    db: Session = Depends(get_db),
) -> Exercise:
    existing = db.scalar(
        select(Exercise).where(Exercise.name == payload.name)
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exercise name already exists",
        )

    exercise = Exercise(**payload.model_dump())
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


@router.get("/exercises", response_model=list[ExerciseResponse])
def list_exercises(
    db: Session = Depends(get_db),
) -> list[Exercise]:
    return list(
        db.scalars(
            select(Exercise)
            .where(Exercise.is_active.is_(True))
            .order_by(Exercise.name)
        )
    )


@router.post(
    "/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prescription(
    payload: PrescriptionCreate,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Prescription:
    get_patient_or_404(payload.patient_id, db)

    exercise = db.get(Exercise, payload.exercise_id)

    if exercise is None or not exercise.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active exercise not found",
        )

    prescription = Prescription(
        **payload.model_dump(),
        staff_id=staff.id,
    )

    db.add(prescription)
    db.commit()

    created_prescription = db.scalar(
        select(Prescription)
        .options(joinedload(Prescription.exercise))
        .where(Prescription.id == prescription.id)
    )

    return created_prescription
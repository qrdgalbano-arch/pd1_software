from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import FlagType, SessionStatus, SyncStatus
from app.schemas.prescriptions import ExerciseSummaryResponse


class StaffPrescriptionResponse(BaseModel):
    id: int
    patient_id: int
    staff_id: int
    exercise_id: int
    repetitions_target: int
    duration_limit_seconds: int
    scheduled_days: str
    is_active: bool
    created_at: datetime
    exercise: ExerciseSummaryResponse

    model_config = ConfigDict(from_attributes=True)


class PatientReference(BaseModel):
    id: int
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class SessionPrescriptionReference(BaseModel):
    id: int
    exercise: ExerciseSummaryResponse

    model_config = ConfigDict(from_attributes=True)


class ExerciseSessionResponse(BaseModel):
    id: int
    client_session_id: str
    patient_id: int
    prescription_id: int
    status: SessionStatus
    repetitions_completed: int
    duration_seconds: int
    error_count: int
    error_summary: str
    valid_repetitions: int = 0
    invalid_repetitions: int = 0
    incomplete_repetitions: int = 0
    arom_classification: str | None = None
    peak_rom_degrees: float | None = None
    affected_side: str | None = None
    device_recorded_at: datetime
    server_received_at: datetime
    sync_status: SyncStatus
    prescription: SessionPrescriptionReference

    model_config = ConfigDict(from_attributes=True)


class StaffFlagResponse(BaseModel):
    id: int
    patient_id: int
    flag_type: FlagType
    message: str
    is_resolved: bool
    created_at: datetime
    patient: PatientReference

    model_config = ConfigDict(from_attributes=True)


class SessionStatusCount(BaseModel):
    status: SessionStatus
    count: int


class RecentSessionActivity(BaseModel):
    date: str
    count: int


class DashboardSummaryResponse(BaseModel):
    patient_count: int
    active_prescription_count: int
    recent_session_count: int
    unresolved_flag_count: int
    session_status_counts: list[SessionStatusCount]
    recent_session_activity: list[RecentSessionActivity]
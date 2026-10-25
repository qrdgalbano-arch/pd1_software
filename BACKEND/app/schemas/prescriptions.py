from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExerciseSummaryResponse(BaseModel):
    id: int
    name: str
    description: str

    model_config = ConfigDict(from_attributes=True)


class PrescriptionCreate(BaseModel):
    patient_id: int = Field(gt=0)
    exercise_id: int = Field(gt=0)
    repetitions_target: int = Field(ge=1, le=1000)
    duration_limit_seconds: int = Field(ge=1, le=86400)
    scheduled_days: str = Field(min_length=3, max_length=100)


class PrescriptionResponse(BaseModel):
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
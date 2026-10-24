from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models import SessionStatus

AromClassification = Literal[
    "Within Normal Limits",
    "Decreased Range of Motion",
    "Excessive Range of Motion",
    "Tracking unavailable",
]


class ExerciseSessionIngest(BaseModel):
    """Session record uploaded by the Component Twin exercise station."""

    client_session_id: str = Field(min_length=8, max_length=100)
    patient_id: int = Field(gt=0)
    prescription_id: int = Field(gt=0)
    status: SessionStatus
    repetitions_completed: int = Field(ge=0, le=1000)
    duration_seconds: int = Field(ge=0, le=86400)
    error_count: int = Field(default=0, ge=0, le=10000)
    error_summary: str = Field(default="", max_length=2000)
    valid_repetitions: int = Field(default=0, ge=0, le=1000)
    invalid_repetitions: int = Field(default=0, ge=0, le=1000)
    incomplete_repetitions: int = Field(default=0, ge=0, le=1000)
    arom_classification: AromClassification | None = None
    peak_rom_degrees: float | None = Field(default=None, ge=0, le=360)
    affected_side: Literal["left", "right"] | None = None
    device_recorded_at: datetime

    @model_validator(mode="after")
    def check_counts(self) -> "ExerciseSessionIngest":
        if self.repetitions_completed != self.valid_repetitions:
            raise ValueError(
                "repetitions_completed must equal valid_repetitions"
            )
        return self

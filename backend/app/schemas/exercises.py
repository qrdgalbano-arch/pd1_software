from pydantic import BaseModel, ConfigDict, Field


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=2)
    default_repetitions: int = Field(default=10, ge=1, le=1000)
    default_duration_seconds: int = Field(default=60, ge=1, le=86400)


class ExerciseResponse(ExerciseCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

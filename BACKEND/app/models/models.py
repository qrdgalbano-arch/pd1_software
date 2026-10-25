import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class UserRole(str, enum.Enum):
    patient = "patient"
    staff = "staff"


class SyncStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"


class SessionStatus(str, enum.Enum):
    completed = "completed"
    incomplete = "incomplete"
    cancelled = "cancelled"


class FlagType(str, enum.Enum):
    missed_session = "missed_session"
    repeated_error = "repeated_error"
    incomplete_session = "incomplete_session"
    low_compliance = "low_compliance"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    patient_prescriptions = relationship(
        "Prescription",
        foreign_keys="Prescription.patient_id",
        back_populates="patient",
    )
    staff_prescriptions = relationship(
        "Prescription",
        foreign_keys="Prescription.staff_id",
        back_populates="staff",
    )


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(150),
        unique=True,
    )
    description: Mapped[str] = mapped_column(Text)
    default_repetitions: Mapped[int] = mapped_column(
        Integer,
        default=10,
    )
    default_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        default=60,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
    )
    staff_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id"),
    )
    repetitions_target: Mapped[int] = mapped_column(Integer)
    duration_limit_seconds: Mapped[int] = mapped_column(Integer)
    scheduled_days: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    patient = relationship(
        "User",
        foreign_keys=[patient_id],
        back_populates="patient_prescriptions",
    )
    staff = relationship(
        "User",
        foreign_keys=[staff_id],
        back_populates="staff_prescriptions",
    )
    exercise = relationship("Exercise")


class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_session_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
    )
    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id"),
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus),
    )
    repetitions_completed: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    error_summary: Mapped[str] = mapped_column(
        Text,
        default="",
    )
    valid_repetitions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    invalid_repetitions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    incomplete_repetitions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    arom_classification: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        default=None,
    )
    peak_rom_degrees: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
    )
    affected_side: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        default=None,
    )
    device_recorded_at: Mapped[datetime] = mapped_column(DateTime)
    server_received_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus),
        default=SyncStatus.synced,
    )

    patient = relationship(
        "User",
        foreign_keys=[patient_id],
    )
    prescription = relationship("Prescription")


class StaffFlag(Base):
    __tablename__ = "staff_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
    )
    flag_type: Mapped[FlagType] = mapped_column(
        Enum(FlagType),
    )
    message: Mapped[str] = mapped_column(String(300))
    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    patient = relationship(
        "User",
        foreign_keys=[patient_id],
    )
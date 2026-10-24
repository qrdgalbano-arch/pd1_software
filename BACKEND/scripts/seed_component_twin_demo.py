"""Seed the three dirty-prototype exercises, the station staff account,
and demo prescriptions for the Component Twin exercise station.

Run after scripts.seed_demo_users:
    cd backend; .\venv\Scripts\python.exe -m scripts.seed_component_twin_demo
"""

import os

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import Exercise, Prescription, User, UserRole

EXERCISES = [
    {
        "name": "Straight Leg Raising",
        "description": (
            "Lie on your back. Keep the knee straight and lift the leg "
            "to the prescribed height, then lower it slowly. "
            "Reference ROM: hip flexion 0-80 degrees."
        ),
        "default_repetitions": 10,
        "default_duration_seconds": 180,
    },
    {
        "name": "Side Leg Lifts",
        "description": (
            "Lie on your side. Keep the top leg straight and lift it "
            "sideways, then lower it slowly. "
            "Reference ROM: hip abduction 0-45 degrees."
        ),
        "default_repetitions": 10,
        "default_duration_seconds": 180,
    },
    {
        "name": "Prone Leg Flexion",
        "description": (
            "Lie on your stomach. Keep the thigh on the mat and bend the "
            "knee to bring the heel toward the buttocks, then lower it. "
            "Reference ROM: knee flexion 0-135 degrees."
        ),
        "default_repetitions": 10,
        "default_duration_seconds": 180,
    },
]

STATION_EMAIL = os.getenv("STATION_STAFF_EMAIL", "station@example.com")
STATION_PASSWORD = os.getenv("STATION_STAFF_PASSWORD", "StationDemo123!")


def main() -> None:
    with SessionLocal() as db:
        patient = db.scalar(select(User).where(User.email == "patient@example.com"))
        staff = db.scalar(select(User).where(User.email == "staff@example.com"))

        if patient is None or staff is None:
            raise RuntimeError("Run scripts.seed_demo_users first.")

        station = db.scalar(select(User).where(User.email == STATION_EMAIL))
        if station is None:
            station = User(
                full_name="Component Twin Exercise Station",
                email=STATION_EMAIL,
                password_hash=hash_password(STATION_PASSWORD),
                role=UserRole.staff,
                is_active=True,
            )
            db.add(station)
            print(f"Created station staff user: {STATION_EMAIL}")

        for item in EXERCISES:
            exercise = db.scalar(select(Exercise).where(Exercise.name == item["name"]))
            if exercise is None:
                exercise = Exercise(**item, is_active=True)
                db.add(exercise)
                db.flush()
                print(f"Created exercise: {exercise.name}")

            prescription = db.scalar(
                select(Prescription).where(
                    Prescription.patient_id == patient.id,
                    Prescription.exercise_id == exercise.id,
                    Prescription.is_active.is_(True),
                )
            )
            if prescription is None:
                db.add(
                    Prescription(
                        patient_id=patient.id,
                        staff_id=staff.id,
                        exercise_id=exercise.id,
                        repetitions_target=10,
                        duration_limit_seconds=180,
                        scheduled_days="Monday, Wednesday, Friday",
                        is_active=True,
                    )
                )
                print(f"Created prescription: {exercise.name}")

        db.commit()


if __name__ == "__main__":
    main()

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import User, UserRole


def create_user(
    full_name: str,
    email: str,
    password: str,
    role: UserRole,
) -> None:
    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(User.email == email)
        )

        if existing:
            print(f"User already exists: {email}")
            return

        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )

        db.add(user)
        db.commit()
        print(f"Created {role.value} user: {email}")


create_user(
    full_name="Demo Rehabilitation Staff",
    email="staff@example.com",
    password="StaffDemo123!",
    role=UserRole.staff,
)

create_user(
    full_name="Demo Patient",
    email="patient@example.com",
    password="PatientDemo123!",
    role=UserRole.patient,
)


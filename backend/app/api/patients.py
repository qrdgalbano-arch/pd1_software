from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_patient
from app.database.session import get_db
from app.models import Prescription, User
from app.schemas.prescriptions import PrescriptionResponse

router = APIRouter(
    prefix="/patients",
    tags=["patients"],
    dependencies=[Depends(require_patient)],
)


@router.get("/me/prescriptions", response_model=list[PrescriptionResponse])
def list_my_prescriptions(
    patient: User = Depends(require_patient),
    db: Session = Depends(get_db),
) -> list[Prescription]:
    return list(
        db.scalars(
            select(Prescription)
            .options(joinedload(Prescription.exercise))
            .where(
                Prescription.patient_id == patient.id,
                Prescription.is_active.is_(True),
            )
            .order_by(Prescription.created_at.desc())
        )
    )
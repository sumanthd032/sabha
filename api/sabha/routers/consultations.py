"""Read endpoints for consultations and their statement pool."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from sabha.db import get_session
from sabha.models import Consultation, Statement
from sabha.schemas import ConsultationOut, StatementOut

router = APIRouter(prefix="/api/consultations", tags=["consultations"])


def get_consultation_or_404(consultation_id: int, session: Session) -> Consultation:
    consultation = session.get(Consultation, consultation_id)
    if consultation is None:
        raise HTTPException(status_code=404, detail="consultation not found")
    return consultation


@router.get("", response_model=list[ConsultationOut])
def list_consultations(session: Session = Depends(get_session)) -> list[Consultation]:
    return list(session.exec(select(Consultation)).all())


@router.get("/{consultation_id}", response_model=ConsultationOut)
def get_consultation(
    consultation_id: int, session: Session = Depends(get_session)
) -> Consultation:
    return get_consultation_or_404(consultation_id, session)


@router.get("/{consultation_id}/statements", response_model=list[StatementOut])
def list_statements(
    consultation_id: int, session: Session = Depends(get_session)
) -> list[Statement]:
    get_consultation_or_404(consultation_id, session)
    return list(
        session.exec(select(Statement).where(Statement.consultation_id == consultation_id)).all()
    )

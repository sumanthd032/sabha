"""The ledger's public read view: every autonomous action this
consultation's filing and escalation layer has taken, in order.

Read only by construction, there is deliberately no endpoint anywhere
in this codebase that writes a LedgerEntry directly; every row comes
from services/ledger.record, called from inside the service that took
the action it is documenting.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from sabha.db import get_session
from sabha.routers.consultations import get_consultation_or_404
from sabha.schemas import LedgerEntryOut, LedgerOut
from sabha.services.ledger import ledger_for_consultation

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["ledger"])


@router.get("/ledger", response_model=LedgerOut)
def get_ledger(consultation_id: int, session: Session = Depends(get_session)) -> LedgerOut:
    get_consultation_or_404(consultation_id, session)
    entries = ledger_for_consultation(session, consultation_id)
    return LedgerOut(
        entries=[
            LedgerEntryOut(
                id=entry.id,
                occurred_at=entry.occurred_at,
                action=entry.action,
                reason=entry.reason,
                policy_state=entry.policy_state,
                filing_id=entry.filing_id,
                consultation_id=entry.consultation_id,
            )
            for entry in entries
            if entry.id is not None
        ]
    )

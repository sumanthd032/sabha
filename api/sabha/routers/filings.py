"""Endpoints for filing a clause set, recording a department's reply,
and manually triggering an escalation sweep.

The escalation scheduler itself ticks on a background loop, per
services/escalation.EscalationScheduler, so nothing here is required
for escalation to happen; the sweep endpoint exists so a demo can
trigger a check on cue rather than narrating over a silent wait for
the next tick.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from sabha.config import settings
from sabha.db import get_session
from sabha.models import Filing
from sabha.routers.consultations import get_consultation_or_404
from sabha.schemas import (
    FileClauseSetRequest,
    FilingOut,
    ReplyOut,
    ReplyRequest,
)
from sabha.services.escalation import run_escalation_sweep
from sabha.services.filing import (
    HumanGateRequiredError,
    file_clause_set,
    record_reply,
    resolve_channel,
)

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["filings"])
escalation_router = APIRouter(prefix="/api/escalation", tags=["filings"])


def _filing_out(filing: Filing) -> FilingOut:
    assert filing.id is not None
    return FilingOut(
        id=filing.id,
        consultation_id=filing.consultation_id,
        department=filing.department,
        channel=filing.channel,
        artefact=filing.artefact,
        stage=filing.stage,
        submitted_at=filing.submitted_at,
        statutory_deadline=filing.statutory_deadline,
        created_at=filing.created_at,
    )


@router.get("/filings", response_model=list[FilingOut])
def list_filings(consultation_id: int, session: Session = Depends(get_session)) -> list[FilingOut]:
    get_consultation_or_404(consultation_id, session)
    filings = session.exec(select(Filing).where(Filing.consultation_id == consultation_id)).all()
    return [_filing_out(filing) for filing in filings]


@router.post("/filings", response_model=FilingOut)
def create_filing(
    consultation_id: int,
    payload: FileClauseSetRequest,
    session: Session = Depends(get_session),
) -> FilingOut:
    """File the given clauses to a department through the sandboxed
    channel this build's FILING_MODE resolves to.

    409, with the department name in the response, when this is the
    first filing to that department and confirmed_new_department was
    not passed: section 9's human gate before any first filing.
    """
    get_consultation_or_404(consultation_id, session)
    channel = resolve_channel(settings.filing_mode, settings.filing_live_confirmation)
    try:
        filing = file_clause_set(
            session, consultation_id, payload.department, payload.clause_ids,
            channel, confirmed_new_department=payload.confirmed_new_department,
        )
    except HumanGateRequiredError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "department": error.department,
                "detail": (
                    "this is the first filing to this department; "
                    "resend with confirmed_new_department set to true"
                ),
            },
        ) from None
    return _filing_out(filing)


@router.post("/filings/{filing_id}/replies", response_model=ReplyOut)
def create_reply(
    consultation_id: int,
    filing_id: int,
    payload: ReplyRequest,
    session: Session = Depends(get_session),
) -> ReplyOut:
    """Record a department's reply and stop that filing's escalation
    clock. 404 if the filing does not exist or belongs to a different
    consultation.
    """
    get_consultation_or_404(consultation_id, session)
    filing = session.get(Filing, filing_id)
    if filing is None or filing.consultation_id != consultation_id:
        raise HTTPException(status_code=404, detail="filing not found")
    reply = record_reply(session, filing, payload.received_text)
    assert reply.id is not None
    return ReplyOut(
        id=reply.id,
        filing_id=reply.filing_id,
        received_text=reply.received_text,
        engagement_score=reply.engagement_score,
        template_cluster=reply.template_cluster,
        received_at=reply.received_at,
    )


@escalation_router.post("/sweep", response_model=list[FilingOut])
def run_sweep(session: Session = Depends(get_session)) -> list[FilingOut]:
    """Run one escalation sweep now, across every open filing regardless
    of consultation, and return every filing it touched.
    """
    updated = run_escalation_sweep(session, demo_clock_scale=settings.demo_clock_scale)
    return [_filing_out(filing) for filing in updated]

"""Endpoints for drafted clauses and their jurisdiction routing."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from sabha.db import get_session
from sabha.llm.client import GenaiClient
from sabha.models import Clause, ClauseStatementLink
from sabha.routers.consultations import get_consultation_or_404
from sabha.routers.generation import get_genai_client, get_quota_guard
from sabha.schemas import (
    ClauseDraftOut,
    ClauseOut,
    HumanReviewQueueOut,
    RouteClausesOut,
    RouteClausesRequest,
    RoutingDecisionOut,
)
from sabha.services.clause_drafting import ClauseDraftingParams, draft_clauses
from sabha.services.model_run import latest_model_run, result_from_model_run
from sabha.services.quota import QuotaExhaustedError, QuotaGuard
from sabha.services.routing import RoutingParams, clauses_awaiting_human_review, route_clauses

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["clauses"])


def _statement_ids_for_clause(session: Session, clause_id: int) -> list[int]:
    ids = session.exec(
        select(ClauseStatementLink.statement_id).where(
            ClauseStatementLink.clause_id == clause_id
        )
    ).all()
    return [statement_id for statement_id in ids if statement_id is not None]


def _clause_out(session: Session, clause: Clause) -> ClauseOut:
    assert clause.id is not None
    return ClauseOut(
        id=clause.id,
        text=clause.text,
        statement_ids=_statement_ids_for_clause(session, clause.id),
        certificate_figures=clause.certificate_figures,
    )


@router.get("/clauses", response_model=list[ClauseOut])
def list_clauses(
    consultation_id: int, session: Session = Depends(get_session)
) -> list[ClauseOut]:
    get_consultation_or_404(consultation_id, session)
    clauses = session.exec(select(Clause).where(Clause.consultation_id == consultation_id)).all()
    return [_clause_out(session, clause) for clause in clauses]


@router.post("/clauses/draft", response_model=ClauseDraftOut)
def draft(
    consultation_id: int,
    session: Session = Depends(get_session),
    quota: QuotaGuard = Depends(get_quota_guard),
    genai_client: GenaiClient = Depends(get_genai_client),
) -> ClauseDraftOut:
    """Draft a clause for each of the current bridging ranking's leaders
    that clears the participant coverage bar, in a single batched call.

    404 before the first model run. 503 when the quota guard has
    nothing left today.
    """
    get_consultation_or_404(consultation_id, session)
    model_run = latest_model_run(session, consultation_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="no model run yet for this consultation")
    result = result_from_model_run(model_run)

    try:
        clauses = draft_clauses(
            session, quota, consultation_id, model_run, result,
            ClauseDraftingParams(), genai_client,
        )
    except QuotaExhaustedError:
        raise HTTPException(
            status_code=503, detail="generation paused, daily quota reached"
        ) from None

    return ClauseDraftOut(clauses=[_clause_out(session, clause) for clause in clauses])


@router.post("/clauses/route", response_model=RouteClausesOut)
def route(
    consultation_id: int,
    payload: RouteClausesRequest,
    session: Session = Depends(get_session),
    quota: QuotaGuard = Depends(get_quota_guard),
    genai_client: GenaiClient = Depends(get_genai_client),
) -> RouteClausesOut:
    """Route the given clauses, or every clause in this consultation
    when clause_ids is omitted, in a single batched call.

    503 when the quota guard has nothing left today.
    """
    get_consultation_or_404(consultation_id, session)
    if payload.clause_ids is not None:
        clauses = list(
            session.exec(select(Clause).where(col(Clause.id).in_(payload.clause_ids))).all()
        )
    else:
        clauses = list(
            session.exec(select(Clause).where(Clause.consultation_id == consultation_id)).all()
        )

    try:
        decisions = route_clauses(session, quota, clauses, RoutingParams(), genai_client)
    except QuotaExhaustedError:
        raise HTTPException(
            status_code=503, detail="generation paused, daily quota reached"
        ) from None

    return RouteClausesOut(
        decisions=[
            RoutingDecisionOut(
                id=decision.id,
                clause_id=decision.clause_id,
                department=decision.department,
                citation=decision.citation,
                confidence=decision.confidence,
                rationale=decision.rationale,
                needs_human_review=decision.needs_human_review,
            )
            for decision in decisions
            if decision.id is not None
        ]
    )


@router.get("/clauses/human-queue", response_model=HumanReviewQueueOut)
def human_queue(
    consultation_id: int, session: Session = Depends(get_session)
) -> HumanReviewQueueOut:
    """Every clause in this consultation with no confident route: no
    routing decision at all, or every decision recorded for it flagged
    needs_human_review. Section 6.5: never filed on a guess.
    """
    get_consultation_or_404(consultation_id, session)
    raw_ids = session.exec(
        select(Clause.id).where(Clause.consultation_id == consultation_id)
    ).all()
    clause_ids = [clause_id for clause_id in raw_ids if clause_id is not None]
    awaiting = clauses_awaiting_human_review(session, clause_ids)
    return HumanReviewQueueOut(clause_ids=awaiting)

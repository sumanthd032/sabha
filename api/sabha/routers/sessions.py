"""Join a consultation, request the next statement, and cast a vote.

Statement selection defers to services/selection.py once a model run
exists. Before the first refit there is nothing to locate or refine
against, so a brand new consultation instead serves statements chosen
uniformly at random: adaptive selection is a refinement over an
otherwise workable random order, not a precondition for voting at all.
"""

import secrets

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from sabha.db import get_session
from sabha.models import ModerationState, Participant, Statement, Vote
from sabha.routers.consultations import get_consultation_or_404
from sabha.routers.live import get_live_manager
from sabha.schemas import JoinResponse, StatementOut, VoteRequest, VoteResponse
from sabha.services.live import LiveSessionManager
from sabha.services.model_run import latest_model_run, result_from_model_run
from sabha.services.selection import SelectionParams, select_next_statement

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["sessions"])


def _get_participant_or_404(session_token: str, session: Session) -> Participant:
    participant = session.exec(
        select(Participant).where(Participant.session_token == session_token)
    ).first()
    if participant is None:
        raise HTTPException(status_code=404, detail="unknown session token")
    return participant


@router.post("/join", response_model=JoinResponse)
def join(consultation_id: int, session: Session = Depends(get_session)) -> JoinResponse:
    get_consultation_or_404(consultation_id, session)
    token = secrets.token_urlsafe(24)
    participant = Participant(consultation_id=consultation_id, session_token=token)
    session.add(participant)
    session.commit()
    session.refresh(participant)
    assert participant.id is not None
    return JoinResponse(participant_id=participant.id, session_token=token)


@router.get("/statements/next", response_model=StatementOut | None)
def next_statement(
    consultation_id: int,
    session_token: str,
    session: Session = Depends(get_session),
) -> Statement | None:
    get_consultation_or_404(consultation_id, session)
    participant = _get_participant_or_404(session_token, session)
    assert participant.id is not None

    all_statements = session.exec(
        select(Statement).where(
            Statement.consultation_id == consultation_id,
            Statement.moderation_state == ModerationState.APPROVED,
        )
    ).all()
    by_id = {s.id: s for s in all_statements if s.id is not None}

    voted_statement_ids = {
        v.statement_id
        for v in session.exec(select(Vote).where(Vote.participant_id == participant.id)).all()
    }

    model_run = latest_model_run(session, consultation_id)
    rng = np.random.default_rng()

    if model_run is None:
        candidates = [sid for sid in by_id if sid not in voted_statement_ids]
        if not candidates:
            return None
        return by_id[int(rng.choice(candidates))]

    result = result_from_model_run(model_run)
    candidate_statement_ids = [sid for sid in result.statement_ids if sid in by_id]
    vote_rows = session.exec(
        select(Vote).where(col(Vote.statement_id).in_(candidate_statement_ids))
    ).all()
    vote_counts: dict[int, int] = {}
    for vote in vote_rows:
        vote_counts[vote.statement_id] = vote_counts.get(vote.statement_id, 0) + 1

    chosen_id = select_next_statement(
        result,
        candidate_statement_ids,
        voted_statement_ids,
        vote_counts,
        SelectionParams(),
        rng,
    )
    return by_id[chosen_id] if chosen_id is not None else None


@router.post("/votes", response_model=VoteResponse)
async def cast_vote(
    consultation_id: int,
    payload: VoteRequest,
    session: Session = Depends(get_session),
    live_manager: LiveSessionManager = Depends(get_live_manager),
) -> Vote:
    get_consultation_or_404(consultation_id, session)
    participant = _get_participant_or_404(payload.session_token, session)
    assert participant.id is not None

    statement = session.get(Statement, payload.statement_id)
    if statement is None or statement.consultation_id != consultation_id:
        raise HTTPException(status_code=404, detail="statement not found in this consultation")

    existing = session.exec(
        select(Vote).where(
            Vote.participant_id == participant.id, Vote.statement_id == payload.statement_id
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="already voted on this statement")

    vote = Vote(
        participant_id=participant.id, statement_id=payload.statement_id, value=payload.value
    )
    session.add(vote)
    session.commit()
    session.refresh(vote)

    live_manager.notify_vote_cast(consultation_id)

    return vote

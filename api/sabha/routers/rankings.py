"""The bridging and majority rankings, and the latest model run summary."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from sabha.db import get_session
from sabha.models import Statement, Vote
from sabha.routers.consultations import get_consultation_or_404
from sabha.schemas import ModelRunOut, RankingEntry, RankingsOut
from sabha.services.model_run import latest_model_run, result_from_model_run
from sabha.services.rankings import RankedStatement, build_rankings

router = APIRouter(prefix="/api/consultations/{consultation_id}", tags=["rankings"])


def _to_entries(ranked: list[RankedStatement]) -> list[RankingEntry]:
    return [
        RankingEntry(
            statement_id=r.statement_id, code=r.code, text=r.text, score=r.score, rank=r.rank
        )
        for r in ranked
    ]


@router.get("/rankings", response_model=RankingsOut)
def get_rankings(consultation_id: int, session: Session = Depends(get_session)) -> RankingsOut:
    get_consultation_or_404(consultation_id, session)
    model_run = latest_model_run(session, consultation_id)
    if model_run is None:
        return RankingsOut(model_run_id=None, model_run_created_at=None, bridging=[], majority=[])

    result = result_from_model_run(model_run)
    statements = {
        s.id: s
        for s in session.exec(
            select(Statement).where(Statement.consultation_id == consultation_id)
        ).all()
        if s.id is not None
    }
    vote_rows = session.exec(
        select(Vote).where(col(Vote.statement_id).in_(result.statement_ids))
    ).all()
    votes = [(v.participant_id, v.statement_id, v.value) for v in vote_rows]

    bridging, majority = build_rankings(result, votes, statements)
    return RankingsOut(
        model_run_id=model_run.id,
        model_run_created_at=model_run.created_at,
        bridging=_to_entries(bridging),
        majority=_to_entries(majority),
    )


@router.get("/model-runs/latest", response_model=ModelRunOut)
def get_latest_model_run(
    consultation_id: int, session: Session = Depends(get_session)
) -> ModelRunOut:
    get_consultation_or_404(consultation_id, session)
    model_run = latest_model_run(session, consultation_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="no model run yet")
    assert model_run.id is not None
    return ModelRunOut(
        id=model_run.id,
        consultation_id=model_run.consultation_id,
        k_clusters=model_run.k_clusters,
        created_at=model_run.created_at,
        participant_count=len(model_run.participant_biases),
        statement_count=len(model_run.statement_intercepts),
    )

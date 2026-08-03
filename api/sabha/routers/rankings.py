"""The bridging and majority rankings, the latest model run summary, the
opinion map, and the consensus certificate.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from sabha.db import get_session
from sabha.models import Participant, Statement, Vote
from sabha.routers.consultations import get_consultation_or_404
from sabha.schemas import (
    CertificateOut,
    ClusterSupportOut,
    ModelRunOut,
    OpinionMapOut,
    OpinionMapPoint,
    RankingEntry,
    RankingsOut,
    StatementOut,
)
from sabha.services.certificate import build_certificate_figures
from sabha.services.model_run import latest_model_run, result_from_model_run
from sabha.services.opinion_map import build_opinion_map
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


@router.get("/opinion-map", response_model=OpinionMapOut)
def get_opinion_map(
    consultation_id: int,
    session_token: str | None = None,
    session: Session = Depends(get_session),
) -> OpinionMapOut:
    get_consultation_or_404(consultation_id, session)
    model_run = latest_model_run(session, consultation_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="no model run yet")
    assert model_run.id is not None

    self_participant_id = None
    if session_token:
        participant = session.exec(
            select(Participant).where(Participant.session_token == session_token)
        ).first()
        if participant is not None:
            self_participant_id = participant.id

    points = build_opinion_map(model_run, self_participant_id)
    return OpinionMapOut(
        model_run_id=model_run.id,
        k_clusters=model_run.k_clusters,
        points=[
            OpinionMapPoint(
                participant_id=p.participant_id,
                factor=p.factor,
                cluster=p.cluster,
                is_self=p.is_self,
            )
            for p in points
        ],
    )


@router.get("/certificate", response_model=CertificateOut)
def get_certificate(
    consultation_id: int, session: Session = Depends(get_session)
) -> CertificateOut:
    """The certificate for the statement currently ranked highest by the
    bridging score. Clause drafting over several statements at once is a
    later step; until then, the certified text is the statement's own.
    """
    get_consultation_or_404(consultation_id, session)
    model_run = latest_model_run(session, consultation_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="no model run yet")
    assert model_run.id is not None

    result = result_from_model_run(model_run)
    mu_scores = result.mu_by_statement()
    if not mu_scores:
        raise HTTPException(status_code=404, detail="no statements have been fitted yet")
    top_statement_id = max(mu_scores, key=lambda sid: mu_scores[sid])

    statement = session.get(Statement, top_statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="the certified statement no longer exists")
    assert statement.id is not None

    vote_rows = session.exec(select(Vote).where(Vote.statement_id == top_statement_id)).all()
    votes_for_statement = [(v.participant_id, v.value) for v in vote_rows]
    figures = build_certificate_figures(model_run, votes_for_statement)

    return CertificateOut(
        model_run_id=model_run.id,
        statement=StatementOut(
            id=statement.id,
            code=statement.code,
            text=statement.text,
            language=statement.language,
            author_type=statement.author_type,
            parent_statement_id=statement.parent_statement_id,
            is_synthetic=statement.is_synthetic,
        ),
        participant_count=figures.participant_count,
        clusters=[
            ClusterSupportOut(
                cluster=c.cluster,
                participant_count=c.participant_count,
                agree_count=c.agree_count,
                agree_fraction=c.agree_fraction,
            )
            for c in figures.clusters
        ],
    )

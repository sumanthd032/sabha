"""Fits the bridging factorisation model against a consultation's stored
votes and persists the result as a model_run snapshot.

A row is inserted fresh on every call, never updated, so a figure shown
to the public against one run's id can always be reproduced later by
refitting with that run's own params, rather than trusting a mutable
row that might have moved on since.
"""

from dataclasses import asdict

from sqlmodel import Session, col, select

from sabha.models import ModelRun, Participant, Statement, Vote
from sabha.services.clustering import choose_k
from sabha.services.factorisation import FactorisationParams, fit


def fit_and_persist(
    session: Session,
    consultation_id: int,
    params: FactorisationParams | None = None,
) -> ModelRun:
    """Fit on every observed vote for one consultation and store the snapshot."""
    params = params or FactorisationParams()

    participants = session.exec(
        select(Participant).where(Participant.consultation_id == consultation_id)
    ).all()
    statements = session.exec(
        select(Statement).where(Statement.consultation_id == consultation_id)
    ).all()
    participant_ids = [p.id for p in participants if p.id is not None]
    statement_ids = [s.id for s in statements if s.id is not None]

    vote_rows = session.exec(
        select(Vote).where(
            col(Vote.participant_id).in_(participant_ids),
            col(Vote.statement_id).in_(statement_ids),
        )
    ).all()
    votes = [(v.participant_id, v.statement_id, v.value) for v in vote_rows]

    result = fit(participant_ids, statement_ids, votes, params)
    k_clusters, labels = choose_k(result.f)

    model_run = ModelRun(
        consultation_id=consultation_id,
        params=asdict(params),
        statement_intercepts={str(sid): mu for sid, mu in result.mu_by_statement().items()},
        participant_factors={
            str(pid): factor for pid, factor in result.factor_by_participant().items()
        },
        statement_loadings={
            str(sid): result.g[j].tolist() for j, sid in enumerate(statement_ids)
        },
        participant_biases={
            str(pid): float(result.b[i]) for i, pid in enumerate(participant_ids)
        },
        cluster_assignments={
            str(pid): int(label) for pid, label in zip(participant_ids, labels, strict=True)
        },
        k_clusters=k_clusters,
    )
    session.add(model_run)
    session.commit()
    session.refresh(model_run)
    return model_run

"""Clause drafting: turn statements the room broadly agreed on into
formal clause text, with the certificate figures and statement
provenance that back it kept alongside.

Section 6 of the project description: the output is a drafted clause
set, each clause carrying the support figures that back it. Each of
the current bridging ranking's leaders, with enough participant
coverage to certify, becomes its own one statement group; the group
shape is kept general enough that a caller wanting to merge more than
one related statement into a single clause can build a larger group,
though nothing in this build does that yet. Drafting happens in one
batched call across every group, and a drafted clause's reported
statement_ids are validated against the group it was actually drafted
from: an id the model reports that was never offered to it is dropped
rather than trusted, the same defensive check jurisdiction routing
applies to its own citations.
"""

from dataclasses import asdict, dataclass
from typing import Any

from sqlmodel import Session, col, select

from sabha.llm.client import GenaiClient, call_structured, load_prompt
from sabha.llm.schemas import ClauseDraftBatch
from sabha.models import Clause, ClauseStatementLink, Consultation, ModelRun, Statement, Vote
from sabha.services.certificate import CertificateFigures, build_certificate_figures
from sabha.services.factorisation import FactorisationResult
from sabha.services.quota import QuotaGuard


@dataclass(frozen=True)
class ClauseDraftingParams:
    max_candidates: int = 5
    min_participant_count: int = 10


def select_clause_candidates(
    result: FactorisationResult,
    statements: dict[int, Statement],
    model_run: ModelRun,
    votes_by_statement: dict[int, list[tuple[int, int]]],
    params: ClauseDraftingParams,
) -> list[tuple[int, CertificateFigures]]:
    """The top bridging statements with enough participant coverage to
    certify, best mu first, each its own one statement group.
    """
    mu_by_id = result.mu_by_statement()
    candidates: list[tuple[int, CertificateFigures]] = []
    for statement_id in result.statement_ids:
        if statement_id not in statements:
            continue
        figures = build_certificate_figures(model_run, votes_by_statement.get(statement_id, []))
        if figures.participant_count < params.min_participant_count:
            continue
        candidates.append((statement_id, figures))
    candidates.sort(key=lambda pair: mu_by_id[pair[0]], reverse=True)
    return candidates[: params.max_candidates]


def _format_groups_block(
    candidates: list[tuple[int, CertificateFigures]], statements: dict[int, Statement]
) -> str:
    blocks = []
    for statement_id, figures in candidates:
        support = ", ".join(
            f"cluster {cluster.cluster}: {cluster.agree_fraction:.0%} of "
            f"{cluster.participant_count}"
            for cluster in figures.clusters
        )
        blocks.append(
            f'Group with statement id {statement_id}:\n"{statements[statement_id].text}"\n'
            f"Support: {support}"
        )
    return "\n\n".join(blocks)


def draft_clauses(
    session: Session,
    quota: QuotaGuard,
    consultation_id: int,
    model_run: ModelRun,
    result: FactorisationResult,
    params: ClauseDraftingParams | None = None,
    genai_client: GenaiClient | None = None,
) -> list[Clause]:
    """Draft one clause per candidate group in a single batched call.

    Makes no call, spending no quota, when no statement clears the
    participant coverage bar in select_clause_candidates.
    """
    params = params or ClauseDraftingParams()
    assert model_run.id is not None

    statements = {
        s.id: s
        for s in session.exec(
            select(Statement).where(Statement.consultation_id == consultation_id)
        ).all()
        if s.id is not None
    }
    vote_rows = session.exec(
        select(Vote).where(col(Vote.statement_id).in_(list(statements.keys())))
    ).all()
    votes_by_statement: dict[int, list[tuple[int, int]]] = {}
    for vote in vote_rows:
        votes_by_statement.setdefault(vote.statement_id, []).append(
            (vote.participant_id, vote.value)
        )

    candidates = select_clause_candidates(result, statements, model_run, votes_by_statement, params)
    if not candidates:
        return []

    consultation = session.get(Consultation, consultation_id)
    assert consultation is not None
    prompt = load_prompt(
        "draft_clause",
        consultation_question=consultation.question,
        groups=_format_groups_block(candidates, statements),
    )
    batch = call_structured(
        session, quota, prompt, ClauseDraftBatch, "ClauseDraftBatch", genai_client=genai_client
    )

    figures_by_id = dict(candidates)
    offered_ids = set(figures_by_id.keys())
    clauses: list[Clause] = []
    for draft in batch.drafts:
        used_ids = [sid for sid in draft.statement_ids if sid in offered_ids]
        if not used_ids:
            continue
        clause = Clause(
            consultation_id=consultation_id,
            model_run_id=model_run.id,
            text=draft.text,
            certificate_figures=_figures_to_dict(figures_by_id[used_ids[0]]),
        )
        session.add(clause)
        session.flush()
        assert clause.id is not None
        for statement_id in used_ids:
            session.add(ClauseStatementLink(clause_id=clause.id, statement_id=statement_id))
        clauses.append(clause)

    session.commit()
    for clause in clauses:
        session.refresh(clause)
    return clauses


def _figures_to_dict(figures: CertificateFigures) -> dict[str, Any]:
    return asdict(figures)

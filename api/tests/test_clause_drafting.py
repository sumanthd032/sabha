"""Tests for clause drafting: candidate selection by bridging score and
participant coverage, batched drafting, and statement provenance."""

from dataclasses import dataclass, field
from typing import NoReturn

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, col, create_engine, select

from sabha.models import Clause, ClauseStatementLink, ModelRun, Statement, Vote
from sabha.seed.loader import load_seed
from sabha.services.clause_drafting import (
    ClauseDraftingParams,
    draft_clauses,
    select_clause_candidates,
)
from sabha.services.factorisation import FactorisationParams
from sabha.services.model_run import fit_and_persist, result_from_model_run
from sabha.services.quota import QuotaGuard


def _fresh_engine() -> Engine:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_and_fit(session: Session, num_participants: int = 300, seed: int = 5) -> ModelRun:
    load_seed(session, num_participants=num_participants, seed=seed)
    return fit_and_persist(session, consultation_id=1, params=FactorisationParams(iterations=30))


def _votes_by_statement(
    session: Session, statement_ids: list[int]
) -> dict[int, list[tuple[int, int]]]:
    vote_rows = session.exec(select(Vote).where(col(Vote.statement_id).in_(statement_ids))).all()
    grouped: dict[int, list[tuple[int, int]]] = {}
    for vote in vote_rows:
        grouped.setdefault(vote.statement_id, []).append((vote.participant_id, vote.value))
    return grouped


def test_select_clause_candidates_orders_by_bridging_score_with_coverage() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session)
        result = result_from_model_run(model_run)
        statements = {
            s.id: s
            for s in session.exec(select(Statement).where(Statement.consultation_id == 1)).all()
            if s.id is not None
        }
        votes_by_statement = _votes_by_statement(session, list(statements.keys()))

        params = ClauseDraftingParams(max_candidates=4, min_participant_count=10)
        candidates = select_clause_candidates(
            result, statements, model_run, votes_by_statement, params
        )

        assert 0 < len(candidates) <= 4
        mu_by_id = result.mu_by_statement()
        scores = [mu_by_id[sid] for sid, _ in candidates]
        assert scores == sorted(scores, reverse=True)
        assert all(figures.participant_count >= 10 for _, figures in candidates)


def test_select_clause_candidates_excludes_statements_below_coverage() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session)
        result = result_from_model_run(model_run)
        statements = {
            s.id: s
            for s in session.exec(select(Statement).where(Statement.consultation_id == 1)).all()
            if s.id is not None
        }
        votes_by_statement = _votes_by_statement(session, list(statements.keys()))

        params = ClauseDraftingParams(max_candidates=4, min_participant_count=1_000_000)
        candidates = select_clause_candidates(
            result, statements, model_run, votes_by_statement, params
        )

        assert candidates == []


@dataclass
class _FakeGenerateResult:
    text: str | None


@dataclass
class _FakeModels:
    text: str = "{}"
    calls: int = 0
    seen_prompts: list[str] = field(default_factory=list)

    def generate_content(self, *, model: str, contents: str, config: object) -> _FakeGenerateResult:
        self.calls += 1
        self.seen_prompts.append(contents)
        return _FakeGenerateResult(text=self.text)

    def embed_content(self, *, model: str, contents: str) -> NoReturn:
        raise NotImplementedError


@dataclass
class _FakeClient:
    models: _FakeModels


def test_draft_clauses_makes_no_call_when_nothing_clears_the_bar() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session)
        result = result_from_model_run(model_run)
        fake = _FakeClient(models=_FakeModels())

        clauses = draft_clauses(
            session, QuotaGuard(rpm=5, rpd=5), 1, model_run, result,
            params=ClauseDraftingParams(min_participant_count=1_000_000), genai_client=fake,
        )

    assert clauses == []
    assert fake.models.calls == 0


def test_draft_clauses_persists_only_offered_statement_ids() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session)
        result = result_from_model_run(model_run)
        statements = {
            s.id: s
            for s in session.exec(select(Statement).where(Statement.consultation_id == 1)).all()
            if s.id is not None
        }
        votes_by_statement = _votes_by_statement(session, list(statements.keys()))
        params = ClauseDraftingParams(max_candidates=2, min_participant_count=10)
        candidates = select_clause_candidates(
            result, statements, model_run, votes_by_statement, params
        )
        assert candidates

        first_id = candidates[0][0]
        response_json = (
            '{"drafts": ['
            f'{{"statement_ids": [{first_id}], "text": "The relevant ministry shall act."}},'
            '{"statement_ids": [999999], "text": "Should never be persisted."}'
            "]}"
        )
        fake = _FakeClient(models=_FakeModels(text=response_json))

        clauses = draft_clauses(
            session, QuotaGuard(rpm=5, rpd=5), 1, model_run, result,
            params=params, genai_client=fake,
        )

        assert fake.models.calls == 1
        assert len(clauses) == 1
        assert clauses[0].text == "The relevant ministry shall act."
        assert clauses[0].certificate_figures["participant_count"] > 0

        links = session.exec(
            select(ClauseStatementLink).where(ClauseStatementLink.clause_id == clauses[0].id)
        ).all()
        assert {link.statement_id for link in links} == {first_id}

        persisted_clauses = session.exec(select(Clause)).all()
        assert len(persisted_clauses) == 1

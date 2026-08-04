"""Tests for the generation loop: target selection, batched injection,
and the significance test that decides whether a variant is retained.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NoReturn

import numpy as np
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, col, create_engine, select

from sabha.models import (
    AuthorType,
    Consultation,
    LedgerEntry,
    ModelRun,
    ModerationState,
    Statement,
    Vote,
)
from sabha.seed.loader import load_seed
from sabha.seed.statements import STATEMENTS
from sabha.services.factorisation import FactorisationParams, FactorisationResult
from sabha.services.generation import (
    GenerationParams,
    evaluate_pending_variants,
    prepare_generation_prompt,
    run_generation_cycle,
    select_generation_targets,
)
from sabha.services.model_run import fit_and_persist, result_from_model_run
from sabha.services.quota import QuotaGuard

FACTIONAL_INDEX = next(i for i, s in enumerate(STATEMENTS) if s.leaning != "bridging")
BRIDGING_INDEX = next(i for i, s in enumerate(STATEMENTS) if s.leaning == "bridging")


def _fresh_engine() -> Engine:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _statement(
    statement_id: int,
    author_type: AuthorType = AuthorType.PARTICIPANT,
    moderation_state: ModerationState = ModerationState.APPROVED,
) -> Statement:
    statement = Statement(
        consultation_id=1,
        code=f"S-{statement_id:04d}",
        text=f"statement {statement_id}",
        language="en",
        author_type=author_type,
        moderation_state=moderation_state,
    )
    statement.id = statement_id
    return statement


def _hand_result(statement_ids: list[int], mu_values: list[float]) -> FactorisationResult:
    """A FactorisationResult with chosen mu and zero loadings, for tests
    that need exact control over vote counts and mu rather than a real
    fit's incidental values.
    """
    params = FactorisationParams()
    return FactorisationResult(
        participant_ids=[],
        statement_ids=statement_ids,
        mu=np.array(mu_values),
        b=np.array([]),
        f=np.zeros((0, params.num_factors)),
        g=np.zeros((len(statement_ids), params.num_factors)),
        params=params,
    )


# --- select_generation_targets ------------------------------------------------


def test_select_generation_targets_prefers_low_mu_and_high_loading() -> None:
    statement_ids = [1, 2, 3, 4]
    params = FactorisationParams()
    mu = np.array([0.9, 0.1, 0.5, 0.5])
    g = np.array([[0.1, 0.0], [0.9, 0.0], [0.1, 0.0], [0.6, 0.0]])
    result = FactorisationResult(
        participant_ids=[], statement_ids=statement_ids, mu=mu, b=np.array([]),
        f=np.zeros((0, params.num_factors)), g=g, params=params,
    )
    statements = {sid: _statement(sid) for sid in statement_ids}

    targets = select_generation_targets(
        result, statements, {}, generated_count=0, pool_size=4,
        params=GenerationParams(max_targets_per_cycle=1, pool_fraction_cap=1.0),
    )

    assert targets == [2]


def test_select_generation_targets_excludes_generated_and_pending() -> None:
    statement_ids = [1, 2, 3]
    params = FactorisationParams()
    # Statement 1 is the most divisive by mu/loading, but is itself
    # generated; statement 2 is equally divisive but has a pending
    # child; only statement 3 should be selectable.
    mu = np.array([0.0, 0.0, 0.2])
    g = np.array([[1.0, 0.0], [1.0, 0.0], [0.8, 0.0]])
    result = FactorisationResult(
        participant_ids=[], statement_ids=statement_ids, mu=mu, b=np.array([]),
        f=np.zeros((0, params.num_factors)), g=g, params=params,
    )
    statements = {
        1: _statement(1, author_type=AuthorType.GENERATED),
        2: _statement(2, author_type=AuthorType.PARTICIPANT),
        3: _statement(3, author_type=AuthorType.PARTICIPANT),
    }

    targets = select_generation_targets(
        result, statements, pending_children_by_parent={2: 1}, generated_count=0, pool_size=3,
        params=GenerationParams(max_targets_per_cycle=2, pool_fraction_cap=10.0),
    )

    assert targets == [3]


def test_select_generation_targets_respects_the_pool_fraction_cap() -> None:
    statement_ids = [1, 2]
    params = FactorisationParams()
    result = FactorisationResult(
        participant_ids=[], statement_ids=statement_ids, mu=np.array([0.0, 0.0]),
        b=np.array([]), f=np.zeros((0, params.num_factors)),
        g=np.array([[1.0, 0.0], [1.0, 0.0]]), params=params,
    )
    statements = {sid: _statement(sid) for sid in statement_ids}

    # pool_fraction_cap=0.2 of a pool of 10 leaves a budget of 2, which
    # is not enough room for one target's full batch of four variants.
    targets = select_generation_targets(
        result, statements, {}, generated_count=0, pool_size=10,
        params=GenerationParams(pool_fraction_cap=0.2),
    )

    assert targets == []


# --- run_generation_cycle / prepare_generation_prompt --------------------------


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


def _seed_and_fit(session: Session, num_participants: int = 300, seed: int = 3) -> ModelRun:
    load_seed(session, num_participants=num_participants, seed=seed)
    model_run = fit_and_persist(
        session, consultation_id=1, params=FactorisationParams(iterations=30)
    )
    return model_run


def test_run_generation_cycle_makes_no_call_when_there_is_no_budget() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session)
        result = result_from_model_run(model_run)
        fake = _FakeClient(models=_FakeModels())

        created = run_generation_cycle(
            session, QuotaGuard(rpm=5, rpd=5), consultation_id=1, model_run=model_run,
            result=result, params=GenerationParams(pool_fraction_cap=0.0), genai_client=fake,
        )

    assert created == []
    assert fake.models.calls == 0


def test_run_generation_cycle_injects_only_the_selected_targets_variants() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session)
        result = result_from_model_run(model_run)

        prepared = prepare_generation_prompt(session, 1, model_run, result, GenerationParams())
        assert prepared is not None
        target_ids, _, _ = prepared
        assert target_ids

        response_json = (
            '{"target_variants": ['
            + ",".join(
                f'{{"target_statement_id": {tid}, "variants": '
                f'[{{"text": "reformulation of {tid}", "axis": "narrow_scope"}}]}}'
                for tid in target_ids
            )
            # a stray target id the model was never asked about must be
            # dropped rather than injected.
            + ',{"target_statement_id": 999999, "variants": '
            '[{"text": "should not be injected", "axis": "narrow_scope"}]}'
            "]}"
        )
        fake = _FakeClient(models=_FakeModels(text=response_json))
        quota = QuotaGuard(rpm=5, rpd=5)

        created = run_generation_cycle(
            session, quota, consultation_id=1, model_run=model_run, result=result,
            params=GenerationParams(), genai_client=fake,
        )

        assert fake.models.calls == 1
        assert {s.parent_statement_id for s in created} == set(target_ids)
        assert all(s.author_type == AuthorType.GENERATED for s in created)
        assert all(s.moderation_state == ModerationState.APPROVED for s in created)
        assert all(s.code.startswith("S-") for s in created)
        assert not any(s.parent_statement_id == 999999 for s in created)

        # the pool now genuinely contains these rows, not just the
        # in-memory return value.
        persisted = session.exec(
            select(Statement).where(col(Statement.id).in_([s.id for s in created]))
        ).all()
        assert len(persisted) == len(created)


# --- evaluate_pending_variants --------------------------------------------------


def _bare_consultation(session: Session) -> None:
    now = datetime.now(UTC)
    session.add(Consultation(id=1, title="t", question="q", opens_at=now, closes_at=now))
    session.commit()


def _set_parent(session: Session, statement_id: int, parent_id: int) -> None:
    statement = session.get(Statement, statement_id)
    assert statement is not None
    statement.parent_statement_id = parent_id
    session.add(statement)
    session.commit()


def _moderation_state(session: Session, statement_id: int) -> ModerationState:
    statement = session.get(Statement, statement_id)
    assert statement is not None
    return statement.moderation_state


def test_evaluate_pending_variants_skips_a_variant_below_the_vote_threshold() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        _bare_consultation(session)
        session.add(_statement(1))
        session.add(_statement(2, author_type=AuthorType.GENERATED))
        session.commit()
        _set_parent(session, 2, 1)

        for i in range(30):
            session.add(Vote(participant_id=i, statement_id=1, value=1))
        for i in range(5):
            session.add(Vote(participant_id=1000 + i, statement_id=2, value=1))
        session.commit()

        result = _hand_result([1, 2], [0.0, 0.9])
        outcomes = evaluate_pending_variants(session, 1, result, GenerationParams())

        assert outcomes == []
        assert _moderation_state(session, 2) == ModerationState.APPROVED
        assert session.exec(select(LedgerEntry)).first() is None


def test_evaluate_pending_variants_retires_a_variant_that_does_not_beat_its_parent() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        _bare_consultation(session)
        session.add(_statement(1))
        session.add(_statement(2, author_type=AuthorType.GENERATED))
        session.commit()
        _set_parent(session, 2, 1)

        for i in range(30):
            session.add(Vote(participant_id=i, statement_id=1, value=1))
        for i in range(25):
            session.add(Vote(participant_id=1000 + i, statement_id=2, value=1))
        session.commit()

        result = _hand_result([1, 2], [0.0, 0.05])
        outcomes = evaluate_pending_variants(session, 1, result, GenerationParams())

        assert len(outcomes) == 1
        assert outcomes[0].retained is False
        assert _moderation_state(session, 2) == ModerationState.REJECTED
        ledger_entry = session.exec(select(LedgerEntry)).one()
        assert ledger_entry.action == "generation_variant_retired"


def test_evaluate_pending_variants_retains_a_variant_that_clearly_beats_its_parent() -> None:
    engine = _fresh_engine()
    with Session(engine) as session:
        _bare_consultation(session)
        session.add(_statement(1))
        session.add(_statement(2, author_type=AuthorType.GENERATED))
        session.commit()
        _set_parent(session, 2, 1)

        for i in range(30):
            session.add(Vote(participant_id=i, statement_id=1, value=1))
        for i in range(25):
            session.add(Vote(participant_id=1000 + i, statement_id=2, value=1))
        session.commit()

        result = _hand_result([1, 2], [0.0, 0.8])
        outcomes = evaluate_pending_variants(session, 1, result, GenerationParams())

        assert len(outcomes) == 1
        assert outcomes[0].retained is True
        assert outcomes[0].z_score > GenerationParams().significance_z
        assert _moderation_state(session, 2) == ModerationState.APPROVED
        ledger_entry = session.exec(select(LedgerEntry)).one()
        assert ledger_entry.action == "generation_variant_retained"


def test_a_generated_variant_beats_its_parent_on_seed_data() -> None:
    """The CLAUDE.md acceptance bullet for step 9: on the real seed
    corpus, relabel an already bridging statement as though it were a
    generated reformulation of a factional one, and confirm the
    significance test would retain it. The planted structure guarantees
    the bridging statement's mu is well above the factional one's, per
    test_bridging_statements_rank_above_factional_with_a_clear_margin.
    """
    engine = _fresh_engine()
    with Session(engine) as session:
        model_run = _seed_and_fit(session, num_participants=400, seed=7)
        result = result_from_model_run(model_run)

        parent_id = FACTIONAL_INDEX + 1
        variant_id = BRIDGING_INDEX + 1
        variant = session.get(Statement, variant_id)
        assert variant is not None
        variant.author_type = AuthorType.GENERATED
        variant.parent_statement_id = parent_id
        session.add(variant)
        session.commit()

        outcomes = evaluate_pending_variants(session, 1, result, GenerationParams())

    matching = [o for o in outcomes if o.variant_id == variant_id]
    assert len(matching) == 1
    outcome = matching[0]
    assert outcome.retained is True
    assert outcome.variant_mu > outcome.parent_mu
    assert outcome.z_score > GenerationParams().significance_z

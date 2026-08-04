"""Tests for jurisdiction routing: embedding retrieval, citation
validation against the offered candidates, and the human review queue.
"""

from dataclasses import dataclass

from sqlmodel import Session, SQLModel, create_engine, select

from sabha.models import AllocationRule, Clause, RoutingDecision
from sabha.services.quota import QuotaGuard
from sabha.services.routing import (
    RoutingParams,
    clauses_awaiting_human_review,
    retrieve_candidates,
    route_clauses,
)


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _rule(department: str, citation: str, embedding: list[float]) -> AllocationRule:
    return AllocationRule(
        department=department, citation=citation, mandate_text=f"mandate for {department}",
        embedding=embedding,
    )


def _clause(session: Session, text: str) -> Clause:
    clause = Clause(consultation_id=1, model_run_id=1, text=text, certificate_figures={})
    session.add(clause)
    session.commit()
    session.refresh(clause)
    return clause


def test_retrieve_candidates_ranks_by_cosine_similarity() -> None:
    labour = _rule("Labour", "cite-labour", [1.0, 0.0])
    meity = _rule("MeitY", "cite-meity", [0.0, 1.0])
    params = RoutingParams(top_k_candidates=1)

    candidates = retrieve_candidates([0.9, 0.1], [labour, meity], params)

    assert candidates == [labour]


def test_retrieve_candidates_returns_empty_for_an_empty_index() -> None:
    assert retrieve_candidates([1.0, 0.0], [], RoutingParams()) == []


@dataclass
class _FakeGenerateResult:
    text: str | None


@dataclass
class _FakeEmbedding:
    values: list[float] | None


@dataclass
class _FakeEmbedResult:
    embeddings: list[_FakeEmbedding] | None


@dataclass
class _FakeModels:
    embed_vector: list[float]
    generate_text: str = "{}"
    generate_calls: int = 0
    embed_calls: int = 0

    def generate_content(self, *, model: str, contents: str, config: object) -> _FakeGenerateResult:
        self.generate_calls += 1
        return _FakeGenerateResult(text=self.generate_text)

    def embed_content(self, *, model: str, contents: str) -> _FakeEmbedResult:
        self.embed_calls += 1
        return _FakeEmbedResult(embeddings=[_FakeEmbedding(values=self.embed_vector)])


@dataclass
class _FakeClient:
    models: _FakeModels


def test_route_clauses_persists_only_decisions_matching_an_offered_candidate() -> None:
    with _fresh_session() as session:
        labour = _rule("Ministry of Labour and Employment", "cite-labour", [1.0, 0.0])
        session.add(labour)
        session.commit()
        session.refresh(labour)

        clause = _clause(session, "Platforms shall contribute to a gig worker welfare fund.")

        response_json = (
            '{"routings": ['
            f'{{"clause_id": {clause.id}, "department": "Ministry of Labour and Employment", '
            f'"citation": "cite-labour", "confidence": 0.9, "rationale": "matches mandate"}},'
            f'{{"clause_id": {clause.id}, "department": "Made Up Ministry", '
            f'"citation": "cite-invented", "confidence": 0.9, "rationale": "hallucinated"}}'
            "]}"
        )
        fake = _FakeClient(models=_FakeModels(embed_vector=[1.0, 0.0], generate_text=response_json))
        quota = QuotaGuard(rpm=5, rpd=5)

        decisions = route_clauses(session, quota, [clause], genai_client=fake)

        assert len(decisions) == 1
        assert decisions[0].department == "Ministry of Labour and Employment"
        assert decisions[0].citation == "cite-labour"
        assert decisions[0].needs_human_review is False
        assert fake.models.generate_calls == 1

        persisted = session.exec(select(RoutingDecision)).all()
        assert len(persisted) == 1


def test_route_clauses_flags_low_confidence_as_needing_human_review() -> None:
    with _fresh_session() as session:
        labour = _rule("Ministry of Labour and Employment", "cite-labour", [1.0, 0.0])
        session.add(labour)
        session.commit()
        session.refresh(labour)

        clause = _clause(session, "An ambiguous clause.")
        response_json = (
            '{"routings": ['
            f'{{"clause_id": {clause.id}, "department": "Ministry of Labour and Employment", '
            f'"citation": "cite-labour", "confidence": 0.2, "rationale": "weak match"}}'
            "]}"
        )
        fake = _FakeClient(models=_FakeModels(embed_vector=[1.0, 0.0], generate_text=response_json))
        quota = QuotaGuard(rpm=5, rpd=5)

        decisions = route_clauses(
            session, quota, [clause],
            params=RoutingParams(confidence_threshold=0.6), genai_client=fake,
        )

        assert len(decisions) == 1
        assert decisions[0].needs_human_review is True


def test_route_clauses_makes_no_call_when_the_index_is_empty() -> None:
    with _fresh_session() as session:
        clause = _clause(session, "Nothing to route against.")
        fake = _FakeClient(models=_FakeModels(embed_vector=[1.0, 0.0]))
        quota = QuotaGuard(rpm=5, rpd=5)

        decisions = route_clauses(session, quota, [clause], genai_client=fake)

        assert decisions == []
        assert fake.models.embed_calls == 0
        assert fake.models.generate_calls == 0


def test_clauses_awaiting_human_review() -> None:
    with _fresh_session() as session:
        rule = _rule("Ministry of Labour and Employment", "cite-labour", [1.0, 0.0])
        session.add(rule)
        session.commit()
        session.refresh(rule)
        assert rule.id is not None

        confident_clause = _clause(session, "confidently routed")
        uncertain_clause = _clause(session, "only a weak match")
        unrouted_clause = _clause(session, "never routed at all")

        session.add(
            RoutingDecision(
                clause_id=confident_clause.id, allocation_rule_id=rule.id,
                department=rule.department, citation=rule.citation, confidence=0.9,
                rationale="strong", needs_human_review=False,
            )
        )
        session.add(
            RoutingDecision(
                clause_id=uncertain_clause.id, allocation_rule_id=rule.id,
                department=rule.department, citation=rule.citation, confidence=0.1,
                rationale="weak", needs_human_review=True,
            )
        )
        session.commit()

        clause_ids = [confident_clause.id, uncertain_clause.id, unrouted_clause.id]
        assert clause_ids == [c for c in clause_ids if c is not None]
        known_ids = [cid for cid in clause_ids if cid is not None]
        awaiting = clauses_awaiting_human_review(session, known_ids)

        assert set(awaiting) == {uncertain_clause.id, unrouted_clause.id}

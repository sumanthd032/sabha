"""Tests for the Allocation of Business Rules seed loader."""

from dataclasses import dataclass, field
from typing import NoReturn

from sqlmodel import Session, SQLModel, create_engine, select

from sabha.models import AllocationRule
from sabha.seed.allocation_rules import ALLOCATION_RULES, load_allocation_rules
from sabha.services.quota import QuotaGuard


@dataclass
class _FakeEmbedding:
    values: list[float] | None


@dataclass
class _FakeEmbedResult:
    embeddings: list[_FakeEmbedding] | None


@dataclass
class _FakeModels:
    calls: int = 0
    seen: list[str] = field(default_factory=list)

    def generate_content(self, *, model: str, contents: str, config: object) -> NoReturn:
        raise NotImplementedError

    def embed_content(self, *, model: str, contents: str) -> _FakeEmbedResult:
        self.calls += 1
        self.seen.append(contents)
        return _FakeEmbedResult(embeddings=[_FakeEmbedding(values=[0.1, 0.2])])


@dataclass
class _FakeClient:
    models: _FakeModels


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_load_allocation_rules_inserts_every_seed_entry_once() -> None:
    fake = _FakeClient(models=_FakeModels())
    quota = QuotaGuard(rpm=100, rpd=100)
    with _fresh_session() as session:
        inserted = load_allocation_rules(session, quota, genai_client=fake)

        assert inserted == len(ALLOCATION_RULES)
        assert fake.models.calls == len(ALLOCATION_RULES)
        rows = session.exec(select(AllocationRule)).all()
        assert len(rows) == len(ALLOCATION_RULES)
        assert all(row.embedding == [0.1, 0.2] for row in rows)
        departments = {row.department for row in rows}
        assert "Ministry of Labour and Employment" in departments
        assert "Ministry of Electronics and Information Technology" in departments


def test_load_allocation_rules_is_idempotent_and_makes_no_further_calls() -> None:
    fake = _FakeClient(models=_FakeModels())
    quota = QuotaGuard(rpm=100, rpd=100)
    with _fresh_session() as session:
        load_allocation_rules(session, quota, genai_client=fake)
        first_call_count = fake.models.calls

        inserted_again = load_allocation_rules(session, quota, genai_client=fake)

        assert inserted_again == 0
        assert fake.models.calls == first_call_count
        rows = session.exec(select(AllocationRule)).all()
        assert len(rows) == len(ALLOCATION_RULES)

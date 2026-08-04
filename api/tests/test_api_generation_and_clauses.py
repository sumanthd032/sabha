"""API level tests for the generation, clause drafting, and jurisdiction
routing endpoints. Every test overrides the quota guard and Gemini
client dependencies so no test ever reaches the network.
"""

import re
from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from sabha.main import app
from sabha.models import AllocationRule
from sabha.routers.generation import get_genai_client, get_quota_guard
from sabha.seed.loader import load_seed
from sabha.services.factorisation import FactorisationParams
from sabha.services.model_run import fit_and_persist
from sabha.services.quota import QuotaGuard


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
    generate_text: str = "{}"
    embed_vector: list[float] = field(default_factory=lambda: [1.0, 0.0])
    auto_variants: bool = False
    generate_calls: int = 0
    embed_calls: int = 0

    def generate_content(self, *, model: str, contents: str, config: object) -> _FakeGenerateResult:
        self.generate_calls += 1
        if self.auto_variants:
            return _FakeGenerateResult(text=_variant_batch_echoing(contents))
        return _FakeGenerateResult(text=self.generate_text)

    def embed_content(self, *, model: str, contents: str) -> _FakeEmbedResult:
        self.embed_calls += 1
        return _FakeEmbedResult(embeddings=[_FakeEmbedding(values=self.embed_vector)])


@dataclass
class _FakeClient:
    models: _FakeModels


def _variant_batch_echoing(prompt: str) -> str:
    """A VariantBatch response for whichever target ids the real
    endpoint actually selected: read straight off the rendered prompt
    rather than guessed ahead of time, since target selection depends
    on the real fitted model run.
    """
    target_ids = [int(match) for match in re.findall(r"Target statement id (\d+):", prompt)]
    entries = ",".join(
        f'{{"target_statement_id": {tid}, "variants": '
        f'[{{"text": "auto variant of {tid}", "axis": "narrow_scope"}}]}}'
        for tid in target_ids
    )
    return '{"target_variants": [' + entries + "]}"


def _seed_and_fit(engine: Engine, num_participants: int = 200, seed: int = 1) -> int:
    with Session(engine) as session:
        load_seed(session, num_participants=num_participants, seed=seed)
        fit_and_persist(session, consultation_id=1, params=FactorisationParams())
    return 1


def _override_llm(fake: _FakeClient, quota: QuotaGuard) -> None:
    app.dependency_overrides[get_genai_client] = lambda: fake
    app.dependency_overrides[get_quota_guard] = lambda: quota


def test_run_generation_returns_404_before_the_first_model_run(client: TestClient) -> None:
    response = client.post("/api/consultations/1/generation/run")
    assert response.status_code == 404


def test_run_generation_injects_variants_and_labels_them_generated(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_and_fit(test_engine)
    fake = _FakeClient(models=_FakeModels(auto_variants=True))
    _override_llm(fake, QuotaGuard(rpm=5, rpd=5))
    try:
        response = client.post(f"/api/consultations/{consultation_id}/generation/run")
    finally:
        app.dependency_overrides.pop(get_genai_client, None)
        app.dependency_overrides.pop(get_quota_guard, None)

    assert response.status_code == 200
    body = response.json()
    assert fake.models.generate_calls == 1
    assert len(body["injected"]) > 0
    assert all(s["author_type"] == "generated" for s in body["injected"])
    assert all(s["parent_statement_id"] is not None for s in body["injected"])


def test_run_generation_returns_503_when_the_quota_is_exhausted(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_and_fit(test_engine)
    fake = _FakeClient(models=_FakeModels())
    _override_llm(fake, QuotaGuard(rpm=0, rpd=0))
    try:
        response = client.post(f"/api/consultations/{consultation_id}/generation/run")
    finally:
        app.dependency_overrides.pop(get_genai_client, None)
        app.dependency_overrides.pop(get_quota_guard, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "generation paused, daily quota reached"


def test_draft_list_and_route_clauses_end_to_end(client: TestClient, test_engine: Engine) -> None:
    consultation_id = _seed_and_fit(test_engine, num_participants=300)

    with Session(test_engine) as session:
        session.add(
            AllocationRule(
                department="Ministry of Labour and Employment",
                citation="Code on Social Security, 2020, section 2(61)",
                mandate_text="Defines a platform worker.",
                embedding=[1.0, 0.0],
            )
        )
        session.commit()

    draft_fake = _FakeClient(models=_FakeModels(generate_text="{}"))
    _override_llm(draft_fake, QuotaGuard(rpm=10, rpd=10))
    try:
        # discover a real candidate statement id by drafting with an
        # empty response first is wasteful; instead read the ranking
        # directly to build a response the schema will accept.
        rankings = client.get(f"/api/consultations/{consultation_id}/rankings").json()
        top_statement_id = rankings["bridging"][0]["statement_id"]
        draft_fake.models.generate_text = (
            '{"drafts": [{"statement_ids": ['
            f"{top_statement_id}"
            '], "text": "The relevant ministry shall act on this consensus."}]}'
        )

        draft_response = client.post(f"/api/consultations/{consultation_id}/clauses/draft")
        assert draft_response.status_code == 200
        drafted = draft_response.json()["clauses"]
        assert len(drafted) == 1
        clause_id = drafted[0]["id"]
        assert drafted[0]["statement_ids"] == [top_statement_id]

        list_response = client.get(f"/api/consultations/{consultation_id}/clauses")
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        draft_fake.models.generate_text = (
            '{"routings": [{"clause_id": '
            f"{clause_id}"
            ', "department": "Ministry of Labour and Employment", '
            '"citation": "Code on Social Security, 2020, section 2(61)", '
            '"confidence": 0.95, "rationale": "direct match"}]}'
        )
        route_response = client.post(
            f"/api/consultations/{consultation_id}/clauses/route", json={}
        )
        assert route_response.status_code == 200
        decisions = route_response.json()["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["needs_human_review"] is False

        queue_response = client.get(f"/api/consultations/{consultation_id}/clauses/human-queue")
        assert queue_response.status_code == 200
        assert queue_response.json()["clause_ids"] == []
    finally:
        app.dependency_overrides.pop(get_genai_client, None)
        app.dependency_overrides.pop(get_quota_guard, None)


def test_a_clause_with_no_confident_route_reaches_the_human_queue(
    client: TestClient, test_engine: Engine
) -> None:
    consultation_id = _seed_and_fit(test_engine, num_participants=300)

    with Session(test_engine) as session:
        session.add(
            AllocationRule(
                department="Ministry of Labour and Employment",
                citation="Code on Social Security, 2020, section 2(61)",
                mandate_text="Defines a platform worker.",
                embedding=[1.0, 0.0],
            )
        )
        session.commit()

    fake = _FakeClient(models=_FakeModels())
    _override_llm(fake, QuotaGuard(rpm=10, rpd=10))
    try:
        rankings = client.get(f"/api/consultations/{consultation_id}/rankings").json()
        top_statement_id = rankings["bridging"][0]["statement_id"]
        fake.models.generate_text = (
            '{"drafts": [{"statement_ids": ['
            f"{top_statement_id}"
            '], "text": "A clause nobody confidently owns."}]}'
        )
        clause_id = client.post(
            f"/api/consultations/{consultation_id}/clauses/draft"
        ).json()["clauses"][0]["id"]

        fake.models.generate_text = (
            '{"routings": [{"clause_id": '
            f"{clause_id}"
            ', "department": "Ministry of Labour and Employment", '
            '"citation": "Code on Social Security, 2020, section 2(61)", '
            '"confidence": 0.1, "rationale": "weak match"}]}'
        )
        client.post(f"/api/consultations/{consultation_id}/clauses/route", json={})

        queue_response = client.get(f"/api/consultations/{consultation_id}/clauses/human-queue")
        assert queue_response.json()["clause_ids"] == [clause_id]
    finally:
        app.dependency_overrides.pop(get_genai_client, None)
        app.dependency_overrides.pop(get_quota_guard, None)

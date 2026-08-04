"""Tests for the Gemini client: cache first, quota guarded, structured.

Every test supplies a fake GenaiClient so no test ever reaches the
network. The fake satisfies llm.client.GenaiClient structurally, since
that Protocol is declared against the narrow shape this module actually
reads off a response rather than the real SDK classes.
"""

from dataclasses import dataclass, field

import pytest
from google.genai import errors
from sqlmodel import Session, SQLModel, create_engine

from sabha.llm.client import call_embedding, call_structured
from sabha.llm.schemas import GeneratedVariant, TargetVariants, VariantBatch
from sabha.services.quota import QuotaExhaustedError, QuotaGuard


@dataclass
class _FakeEmbedding:
    values: list[float] | None


@dataclass
class _FakeEmbedResult:
    embeddings: list[_FakeEmbedding] | None


@dataclass
class _FakeGenerateResult:
    text: str | None


@dataclass
class _FakeModels:
    generate_calls: int = 0
    embed_calls: int = 0
    generate_text: str = "{}"
    embed_vector: list[float] = field(default_factory=lambda: [0.1, 0.2, 0.3])
    embed_error: Exception | None = None

    def generate_content(self, *, model: str, contents: str, config: object) -> _FakeGenerateResult:
        self.generate_calls += 1
        return _FakeGenerateResult(text=self.generate_text)

    def embed_content(self, *, model: str, contents: str) -> _FakeEmbedResult:
        self.embed_calls += 1
        if self.embed_error is not None:
            raise self.embed_error
        return _FakeEmbedResult(embeddings=[_FakeEmbedding(values=self.embed_vector)])


@dataclass
class _FakeClient:
    models: _FakeModels


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


_VARIANT_JSON = (
    '{"target_variants": [{"target_statement_id": 1, "variants": '
    '[{"text": "narrower text", "axis": "narrow_scope"}]}]}'
)


def test_a_cache_miss_calls_the_model_and_stores_the_result() -> None:
    fake = _FakeClient(models=_FakeModels(generate_text=_VARIANT_JSON))
    quota = QuotaGuard(rpm=5, rpd=5)
    with _fresh_session() as session:
        result = call_structured(
            session, quota, "prompt", VariantBatch, "VariantBatch", genai_client=fake
        )
    assert fake.models.generate_calls == 1
    assert result == VariantBatch(
        target_variants=[
            TargetVariants(
                target_statement_id=1,
                variants=[GeneratedVariant(text="narrower text", axis="narrow_scope")],
            )
        ]
    )


def test_a_cache_hit_never_calls_the_model_or_the_quota_guard() -> None:
    fake = _FakeClient(models=_FakeModels(generate_text=_VARIANT_JSON))
    quota = QuotaGuard(rpm=1, rpd=1)
    with _fresh_session() as session:
        call_structured(session, quota, "prompt", VariantBatch, "VariantBatch", genai_client=fake)
        assert fake.models.generate_calls == 1

        # A second identical call must be a pure cache hit: the quota is
        # already exhausted by rpd=1, so a real call here would raise.
        result = call_structured(
            session, quota, "prompt", VariantBatch, "VariantBatch", genai_client=fake
        )
    assert fake.models.generate_calls == 1
    assert result.target_variants[0].variants[0].axis == "narrow_scope"


def test_a_refused_reservation_never_reaches_the_model() -> None:
    fake = _FakeClient(models=_FakeModels(generate_text=_VARIANT_JSON))
    quota = QuotaGuard(rpm=0, rpd=5)
    with _fresh_session() as session, pytest.raises(QuotaExhaustedError):
        call_structured(
            session, quota, "prompt", VariantBatch, "VariantBatch", genai_client=fake
        )
    assert fake.models.generate_calls == 0


def test_embedding_cache_hit_never_calls_the_model() -> None:
    fake = _FakeClient(models=_FakeModels())
    quota = QuotaGuard(rpm=1, rpd=1)
    with _fresh_session() as session:
        first = call_embedding(session, quota, "some clause text", genai_client=fake)
        second = call_embedding(session, quota, "some clause text", genai_client=fake)
    assert fake.models.embed_calls == 1
    assert first == second == [0.1, 0.2, 0.3]


def test_a_404_that_also_fails_on_the_fallback_model_still_raises() -> None:
    """The fallback is tried exactly once, not looped: a 404 on the
    fallback model itself must propagate rather than recurse forever.
    """
    not_found = errors.ClientError(code=404, response_json={"error": {"message": "gone"}})
    fake = _FakeClient(models=_FakeModels(embed_error=not_found))
    quota = QuotaGuard(rpm=5, rpd=5)
    with _fresh_session() as session, pytest.raises(errors.ClientError):
        call_embedding(session, quota, "text", genai_client=fake)
    assert fake.models.embed_calls == 2


def test_embedding_falls_back_and_succeeds_when_only_the_primary_model_404s() -> None:
    calls: list[str] = []

    class _SwitchingModels(_FakeModels):
        def embed_content(self, *, model: str, contents: str) -> _FakeEmbedResult:
            calls.append(model)
            if model == "primary-model":
                raise errors.ClientError(code=404, response_json={"error": {"message": "gone"}})
            return _FakeEmbedResult(embeddings=[_FakeEmbedding(values=[9.0])])

    fake = _FakeClient(models=_SwitchingModels())
    quota = QuotaGuard(rpm=5, rpd=5)
    with _fresh_session() as session:
        vector = call_embedding(session, quota, "text", model="primary-model", genai_client=fake)
    assert vector == [9.0]
    assert calls[0] == "primary-model"
    assert calls[1] != "primary-model"


def test_a_non_404_embedding_error_is_not_retried() -> None:
    server_error = errors.ClientError(code=500, response_json={"error": {"message": "oops"}})
    fake = _FakeClient(models=_FakeModels(embed_error=server_error))
    quota = QuotaGuard(rpm=5, rpd=5)
    with _fresh_session() as session, pytest.raises(errors.ClientError):
        call_embedding(session, quota, "text", genai_client=fake)
    assert fake.models.embed_calls == 1

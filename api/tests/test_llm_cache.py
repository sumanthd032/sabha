"""Tests for the language model response and embedding cache."""

from sqlmodel import Session, SQLModel, create_engine

from sabha.llm.cache import (
    embedding_cache_key,
    get_cached_embedding,
    get_cached_response,
    response_cache_key,
    store_embedding,
    store_response,
)


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_response_cache_is_empty_before_anything_is_stored() -> None:
    with _fresh_session() as session:
        key = response_cache_key("gemini-2.5-flash", "prompt", "Schema")
        assert get_cached_response(session, key) is None


def test_response_cache_round_trips_the_stored_json() -> None:
    with _fresh_session() as session:
        key = response_cache_key("gemini-2.5-flash", "prompt text", "VariantList")
        store_response(
            session, key, "gemini-2.5-flash", "VariantList", "prompt text", {"variants": []}
        )
        assert get_cached_response(session, key) == {"variants": []}


def test_response_cache_key_differs_by_model_prompt_or_schema() -> None:
    base = response_cache_key("gemini-2.5-flash", "same prompt", "Schema")
    different_model = response_cache_key("gemini-3.5-flash", "same prompt", "Schema")
    different_prompt = response_cache_key("gemini-2.5-flash", "other prompt", "Schema")
    different_schema = response_cache_key("gemini-2.5-flash", "same prompt", "OtherSchema")

    assert len({base, different_model, different_prompt, different_schema}) == 4


def test_embedding_cache_round_trips_the_stored_vector() -> None:
    with _fresh_session() as session:
        key = embedding_cache_key("gemini-embedding-001", "some clause text")
        assert get_cached_embedding(session, key) is None

        store_embedding(session, key, "gemini-embedding-001", [0.1, 0.2, 0.3])
        assert get_cached_embedding(session, key) == [0.1, 0.2, 0.3]


def test_embedding_cache_key_differs_by_model() -> None:
    key_a = embedding_cache_key("gemini-embedding-001", "text")
    key_b = embedding_cache_key("gemini-embedding-2", "text")
    assert key_a != key_b

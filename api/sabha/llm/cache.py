"""Response and embedding caching for the language model layer.

Checked before every call, always: a cache hit costs zero requests
against the free tier's daily budget, which is what makes a
development rerun of the same generation, drafting, routing, or
evaluation prompt safe to repeat as many times as needed.
"""

import hashlib
from typing import Any

from sqlmodel import Session, select

from sabha.models import EmbeddingCache, LlmCache


def response_cache_key(model: str, prompt: str, schema_name: str) -> str:
    """sha256(model + prompt + schema), per section 4.2 of the build
    instructions."""
    digest_input = f"{model}\n{schema_name}\n{prompt}".encode()
    return hashlib.sha256(digest_input).hexdigest()


def get_cached_response(session: Session, cache_key: str) -> dict[str, Any] | None:
    row = session.exec(select(LlmCache).where(LlmCache.cache_key == cache_key)).first()
    return row.response_json if row is not None else None


def store_response(
    session: Session,
    cache_key: str,
    model: str,
    schema_name: str,
    prompt: str,
    response_json: dict[str, Any],
) -> None:
    session.add(
        LlmCache(
            cache_key=cache_key,
            model=model,
            schema_name=schema_name,
            prompt=prompt,
            response_json=response_json,
        )
    )
    session.commit()


def embedding_cache_key(model: str, content: str) -> str:
    """sha256(model + content): the same text under a different model is
    a different embedding and gets its own row."""
    return hashlib.sha256(f"{model}\n{content}".encode()).hexdigest()


def get_cached_embedding(session: Session, content_hash: str) -> list[float] | None:
    row = session.exec(
        select(EmbeddingCache).where(EmbeddingCache.content_hash == content_hash)
    ).first()
    return row.vector if row is not None else None


def store_embedding(session: Session, content_hash: str, model: str, vector: list[float]) -> None:
    session.add(EmbeddingCache(content_hash=content_hash, model=model, vector=vector))
    session.commit()

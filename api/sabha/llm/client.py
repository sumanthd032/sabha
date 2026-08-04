"""The single Gemini client used everywhere in this codebase.

Both model identifiers live here, per section 4.1 of the build
instructions, read from settings so an override never requires a code
change. Every call is cache first and quota guarded, in that order: a
cache hit is returned before the quota guard is ever consulted, so a
repeated development prompt costs zero requests, and a cache miss
reserves one request from the guard before the network call is
attempted, never after, so a reservation that is refused because the
quota is exhausted never gets charged for a call that did not happen.

Structured output is mandatory on every generating call:
response_json_schema is set from the caller's schema class, so the
reply parses directly into that schema with no regex and no retry on a
malformed shape. See docs/decisions/0004-structured-output-schema-mechanism.md
for why response_json_schema is used over response_schema, and
docs/decisions/0003-gemini-model-verification.md for the verified
model identifiers and quota figures.
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from string import Template
from typing import Protocol, TypeVar

from google import genai
from google.genai import errors, types
from sqlmodel import Session, SQLModel

from sabha.config import settings
from sabha.llm.cache import (
    embedding_cache_key,
    get_cached_embedding,
    get_cached_response,
    response_cache_key,
    store_embedding,
    store_response,
)
from sabha.services.quota import QuotaGuard

GENERATION_MODEL = settings.gemini_model
EMBEDDING_MODEL = settings.gemini_embed_model
EMBEDDING_MODEL_FALLBACK = settings.gemini_embed_model_fallback

logger = logging.getLogger("sabha.llm")

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, **values: str) -> str:
    """Render a prompt template from llm/prompts/{name}.txt.

    Prompts live as files rather than inline strings so a wording change
    is not a code change. $-style substitution, not str.format, since a
    prompt is free text that may itself contain literal braces.
    """
    template = Template((_PROMPTS_DIR / f"{name}.txt").read_text())
    return template.substitute(**values)

SchemaT = TypeVar("SchemaT", bound=SQLModel)


class _GenerateResult(Protocol):
    """A property, not a plain attribute: GenerateContentResponse.text is
    itself a read only property, and a protocol attribute declared as
    settable does not accept a read only one.
    """

    @property
    def text(self) -> str | None: ...


class _Embedding(Protocol):
    @property
    def values(self) -> list[float] | None: ...


class _EmbedResult(Protocol):
    """Both members are properties, and `embeddings` is a `Sequence`
    rather than a `list`: a plain, settable attribute is matched
    invariantly, which would reject
    `google.genai.types.EmbedContentResponse` here even though its
    `embeddings: list[ContentEmbedding]` structurally satisfies
    `_Embedding` element by element. A read only property is matched
    covariantly instead, which accepts it.
    """

    @property
    def embeddings(self) -> Sequence[_Embedding] | None: ...


class _Models(Protocol):
    def generate_content(
        self, *, model: str, contents: str, config: types.GenerateContentConfig
    ) -> _GenerateResult: ...

    def embed_content(self, *, model: str, contents: str) -> _EmbedResult: ...


class GenaiClient(Protocol):
    """The slice of google.genai.Client this module calls.

    Declared as a Protocol against the narrowest shape actually read
    from a response, rather than the concrete client and response
    classes, so a test can supply a plain fake that never touches the
    network instead of constructing real SDK response objects. `models`
    is a read only property here because google.genai.Client's own
    `models` is read only; a plain mutable attribute would not conform.
    """

    @property
    def models(self) -> _Models: ...


_client: genai.Client | None = None


def default_client() -> GenaiClient:
    """The process-wide genai.Client, constructed lazily on first use so
    importing this module never requires a valid API key.
    """
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def call_structured(
    session: Session,
    quota: QuotaGuard,
    prompt: str,
    schema_cls: type[SchemaT],
    schema_name: str,
    model: str = GENERATION_MODEL,
    genai_client: GenaiClient | None = None,
) -> SchemaT:
    """Return schema_cls parsed from a cached or freshly generated reply.

    A cold call and a warm call of the same (model, prompt, schema_name)
    produce an identical parsed result, since the warm call validates the
    same stored JSON the cold call wrote.
    """
    cache_key = response_cache_key(model, prompt, schema_name)
    cached = get_cached_response(session, cache_key)
    if cached is not None:
        logger.info("llm generate model=%s schema=%s cache=hit cost=0", model, schema_name)
        return schema_cls.model_validate(cached)

    quota.reserve(session)
    client = genai_client if genai_client is not None else default_client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema_cls.model_json_schema(),
        ),
    )
    data = json.loads(response.text or "{}")
    store_response(session, cache_key, model, schema_name, prompt, data)
    logger.info("llm generate model=%s schema=%s cache=miss cost=1", model, schema_name)
    return schema_cls.model_validate(data)


def call_embedding(
    session: Session,
    quota: QuotaGuard,
    content: str,
    model: str = EMBEDDING_MODEL,
    genai_client: GenaiClient | None = None,
) -> list[float]:
    """Return content's embedding, from cache or a fresh call.

    Falls back once to EMBEDDING_MODEL_FALLBACK on a 404 from the
    primary model, under its own cache key, since a model identifier
    verified working today can be retired without notice the way
    text-embedding-004 already was.
    """
    cache_key = embedding_cache_key(model, content)
    cached = get_cached_embedding(session, cache_key)
    if cached is not None:
        logger.info("llm embed model=%s cache=hit cost=0", model)
        return cached

    quota.reserve(session)
    client = genai_client if genai_client is not None else default_client()
    try:
        response = client.models.embed_content(model=model, contents=content)
    except errors.ClientError as error:
        if error.code == 404 and model != EMBEDDING_MODEL_FALLBACK:
            logger.warning(
                "llm embed model=%s not found, falling back to %s",
                model,
                EMBEDDING_MODEL_FALLBACK,
            )
            return call_embedding(
                session, quota, content, model=EMBEDDING_MODEL_FALLBACK, genai_client=genai_client
            )
        raise

    if not response.embeddings or response.embeddings[0].values is None:
        raise RuntimeError(f"embedding response from {model} carried no values")
    vector = list(response.embeddings[0].values)
    store_embedding(session, cache_key, model, vector)
    logger.info("llm embed model=%s cache=miss cost=1", model)
    return vector

"""Environment configuration, read once at import time.

Every setting comes from an environment variable, per docs/deployment.md.
Required variables with no sensible default raise at import time rather than
at first use, so a missing variable is a startup failure, not a runtime
surprise three requests into a demo.
"""

import os
from dataclasses import dataclass

_REQUIRED = ("DATABASE_URL", "GEMINI_API_KEY", "QUOTA_RPM", "QUOTA_RPD")

_DEFAULTS = {
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GEMINI_EMBED_MODEL": "gemini-embedding-001",
    "GEMINI_EMBED_MODEL_FALLBACK": "gemini-embedding-2",
    "FILING_MODE": "mock",
    "DEMO_CLOCK_SCALE": "1",
}


@dataclass(frozen=True)
class Settings:
    """Typed, validated view of the process environment."""

    database_url: str
    gemini_api_key: str
    quota_rpm: int
    quota_rpd: int
    gemini_model: str
    gemini_embed_model: str
    gemini_embed_model_fallback: str
    filing_mode: str
    demo_clock_scale: float


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build a Settings instance from the given mapping, or os.environ.

    Raises RuntimeError naming every missing required variable, so a
    misconfigured deployment fails with an actionable message.
    """
    source = env if env is not None else os.environ
    missing = [name for name in _REQUIRED if not source.get(name)]
    if missing:
        raise RuntimeError(
            "missing required environment variables: " + ", ".join(missing)
        )
    values = {name: source[name] for name in _REQUIRED}
    for name, default in _DEFAULTS.items():
        values[name] = source.get(name) or default
    return Settings(
        database_url=values["DATABASE_URL"],
        gemini_api_key=values["GEMINI_API_KEY"],
        quota_rpm=int(values["QUOTA_RPM"]),
        quota_rpd=int(values["QUOTA_RPD"]),
        gemini_model=values["GEMINI_MODEL"],
        gemini_embed_model=values["GEMINI_EMBED_MODEL"],
        gemini_embed_model_fallback=values["GEMINI_EMBED_MODEL_FALLBACK"],
        filing_mode=values["FILING_MODE"],
        demo_clock_scale=float(values["DEMO_CLOCK_SCALE"]),
    )


settings = load_settings()

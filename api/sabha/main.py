"""FastAPI application entry point.

Serves the API under /api and, when a built frontend is present, the static
bundle at every other path, with a catch-all returning index.html so client
side routing works. One origin means no CORS layer and a same-origin
WebSocket for the live session channel.
"""

import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from sabha.config import settings
from sabha.db import engine, get_session, init_db
from sabha.routers import (
    clauses,
    consultations,
    filings,
    generation,
    ledger,
    live,
    rankings,
    sessions,
)
from sabha.services.escalation import EscalationScheduler

APP_VERSION = "0.1.0"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = _REPO_ROOT / "static"


def _read_commit() -> str:
    """Resolve the running build's commit hash.

    Checked in order: an explicit override, the commit Render injects into
    every deployed service at runtime, then a live git lookup for local
    development. Falls back to "unknown" rather than failing, since a
    missing commit hash should never take the app down. Deliberately not
    baked in at Docker build time: Render's remote builder does not include
    .git in the context it hands to the image, so that only ever works in
    a local docker build and silently reports "unknown" in production.
    """
    env_commit = os.environ.get("GIT_COMMIT_SHA") or os.environ.get("RENDER_GIT_COMMIT")
    if env_commit:
        return env_commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


_COMMIT = _read_commit()
_STARTED_AT = datetime.now(UTC)

_escalation_scheduler = EscalationScheduler(
    engine=engine, demo_clock_scale=settings.demo_clock_scale
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    _escalation_scheduler.start()
    yield
    await _escalation_scheduler.stop()


app = FastAPI(title="Sabha", lifespan=_lifespan)


@app.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    """Report build metadata and confirm the database answers a query,
    so the prewarm check docs/deployment.md describes can wake a
    suspended Neon database and verify the deployed commit in one call.
    """
    try:
        session.exec(select(1))
        database = "ok"
    except Exception:
        database = "unreachable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "commit": _COMMIT,
        "version": APP_VERSION,
        "started_at": _STARTED_AT.isoformat(),
        "database": database,
    }


app.include_router(consultations.router)
app.include_router(sessions.router)
app.include_router(rankings.router)
app.include_router(live.router)
app.include_router(generation.router)
app.include_router(clauses.router)
app.include_router(filings.router)
app.include_router(filings.escalation_router)
app.include_router(ledger.router)


if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        """Serve the built single page app for any non-API path."""
        return FileResponse(_STATIC_DIR / "index.html")

"""FastAPI application entry point.

Serves the API under /api and, when a built frontend is present, the static
bundle at every other path, with a catch-all returning index.html so client
side routing works. One origin means no CORS layer and a same-origin
WebSocket once the live session channel lands in step 6.
"""

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP_VERSION = "0.1.0"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMMIT_FILE = _REPO_ROOT / "COMMIT_SHA"
_STATIC_DIR = _REPO_ROOT / "static"


def _read_commit() -> str:
    """Resolve the running build's commit hash.

    Checked in order: an explicit environment variable, a file baked into
    the Docker image by the commit capture build stage, then a live git
    lookup for local development. Falls back to "unknown" rather than
    failing, since a missing commit hash should never take the app down.
    """
    env_commit = os.environ.get("GIT_COMMIT_SHA")
    if env_commit:
        return env_commit
    if _COMMIT_FILE.exists():
        return _COMMIT_FILE.read_text().strip()
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

app = FastAPI(title="Sabha")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Report build metadata, so a deployed instance can be verified."""
    return {
        "status": "ok",
        "commit": _COMMIT,
        "version": APP_VERSION,
        "started_at": _STARTED_AT.isoformat(),
    }


if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        """Serve the built single page app for any non-API path."""
        return FileResponse(_STATIC_DIR / "index.html")

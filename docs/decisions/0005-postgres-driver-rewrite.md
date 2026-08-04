# 0005: rewrite DATABASE_URL to name the psycopg driver explicitly

## Context

Neon, like every managed Postgres provider, hands out a connection
string with the bare `postgresql://` scheme. SQLAlchemy resolves that
scheme to the `psycopg2` driver by default, but section 4's stack list
names `psycopg`, version 3, never `psycopg2`, and `pyproject.toml`
installs only the former. Every deploy from this build's fourth commit
onward crashed on startup with `ModuleNotFoundError: No module named
'psycopg2'` before `uvicorn` could bind a port, which Render's health
checks and this project's own `deploy.yml` had no way to catch: the
deploy hook only confirms Render accepted the trigger, not that the
new container came up, so the platform kept serving whichever earlier
build had last started successfully while every later one failed
silently in the background.

## Decision

`db.py` rewrites a bare `postgresql://` or `postgres://` URL to
`postgresql+psycopg://` before calling `create_engine`, and leaves any
URL that already names a driver, or a local `sqlite://` URL, untouched.
The rewrite happens in code rather than by asking whoever pastes the
connection string into Render's environment settings to edit the
scheme by hand, since Neon's own dashboard never shows the
`+psycopg` form and there is no reason to expect an operator to know
to add it.

## Consequence

A connection string copied verbatim from Neon now works without
manual editing. The health endpoint's own database check, added
alongside this fix, is what actually would have caught this
immediately had it existed from the start: a request that never
reaches a crashed container reports nothing, but a request that
reaches a healthy one and fails its own query would have. Prewarming
before every future deploy, not just before a demonstration, is the
practical lesson.

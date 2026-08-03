# Sabha

A consensus engine for public consultation. Participants vote on short
statements. A factorisation model separates broad agreement from factional
agreement and ranks statements by the former, so the interface shows what
people agree on across factional lines rather than what the largest bloc
wants. A generation loop proposes better framings for divisive statements
and keeps the ones that measurably bridge. The output is a drafted clause
set, routed to the ministry with legal jurisdiction and filed against a
statutory reply clock.

The full specification is in `docs/project.md`.

The seed corpus for this build is on platform and gig work regulation, and
is synthetic: generated rather than collected, and labelled as such
throughout the interface and the data.

## Running it

Requires Python 3.11 and Node 20.

```
cp .env.example .env          # fill in the values, see comments in the file
cd api && pip install -e ".[dev]"
uvicorn sabha.main:app --reload --port 8000
```

In a second terminal:

```
cd web && npm install && npm run dev
```

The frontend dev server proxies `/api` to `localhost:8000`, so open the
Vite URL it prints.

## Checks

```
cd api && ruff check . && mypy . && pytest
cd web && npm run build && npm run test
```

All four must pass before any commit lands.

## Current state

Step 1 of the build: repository scaffold, tooling, and documentation
skeleton. The API exposes `/api/health`, returning build metadata including
the running commit hash. The frontend builds and tests but has no screens
yet. Deployment follows once the hosting accounts are wired up.

See `docs/architecture.md` and `docs/algorithms.md` as later steps land.

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
Vite URL it prints. Visit `/system` for the design token and component
reference page.

To load the synthetic seed corpus into your local database:

```
cd api && python -m sabha.seed.loader
```

This creates one consultation, 70 statements in English and Hindi on
platform and gig work regulation, and a synthetic population of
participants voting from a planted opinion structure. Every row it
writes is marked `is_synthetic`.

## Checks

```
cd api && ruff check . && mypy . && pytest
cd web && npm run build && npm run test
```

All four must pass before any commit lands.

## Current state

Steps 1 to 7 of the build. The API exposes `/api/health`, returning build
metadata including the running commit hash, and is deployed live at
[sabha-n4f7.onrender.com](https://sabha-n4f7.onrender.com). The frontend has
a design token library and base component set, with a working reference at
`/system`.

The data model covers every entity in `docs/project.md`, with a synthetic
seed corpus and vote generator whose planted opinion structure is
recoverable by construction. The bridging factorisation model is fit by
hand with alternating least squares, ranks statements by an intercept that
resists a majority bloc's pull, and clusters participants by silhouette
scored k-means. Adaptive statement selection and coordination detection
sit on top of that fit: a participant's opinion position is located and
then a statement's own score is refined, and a synthetic brigade is
detected and downweighted without being removed. The REST API and a
WebSocket live session expose all of it: joining, adaptive voting,
rankings, and a debounced refit broadcast to everyone in the room.

The voting screen is the primary consultation flow: one statement at a
time, fully keyboard operable with agree, disagree, and skip, and
completable end to end without a mouse. A vote is recorded locally the
instant it is cast and reconciles with the server afterwards, so a slow
or interrupted connection never blocks voting, only delays syncing, which
the screen shows honestly rather than hiding.

See `docs/architecture.md`, `docs/algorithms.md`, and `docs/api.md` for the
detail behind each of these.

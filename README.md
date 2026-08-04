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

All ten steps of the build. `/api/health` returns build metadata and a
live database check, and the app is deployed at
[sabha-n4f7.onrender.com](https://sabha-n4f7.onrender.com). The frontend
has a design token library and base component set, referenced at `/system`.

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
connection never blocks voting, only delays syncing, shown honestly.

A results screen shows the opinion map as a field of tally strokes, the
faction legend and its accessible text alternative, the bridging ranking
beside the majority ranking so their disagreement is visible, and the
consensus certificate: the only element in the interface permitted the
reserved consensus green and the only one with a 2px border. It stays
live over the same WebSocket channel, so a refit triggered by anyone's
vote updates the screen without a reload, and the one orchestrated
motion moment, a stroke settling into position as its statement's
figure rolls to its new value, is wired here.

The language model layer sits behind a response cache and a free tier
quota guard, checked before any feature call, per
`docs/decisions/0003-gemini-model-verification.md`. On top of that: a
generation loop that proposes reformulations of a statement's real
fault lines in one batched call, injects them labelled as generated
with their parent visible, and retires a variant that does not
significantly beat its parent on a two sample z-test;
clause drafting with statement provenance and the certificate figures
behind it; jurisdiction routing over an indexed subset of the
Allocation of Business Rules, grounded in embedding retrieval so every
citation is checkable, with a low confidence route queued for a human
rather than filed; and reply evaluation, scoring engagement and
detecting templated replies across a department's filings by near
duplicate clustering. Every call is cached and quota guarded before it
reaches the network, so a rerun of the same generation, drafting,
routing, or evaluation costs zero requests.

A filing adapter ships pointed at a mock endpoint only, gated by human
confirmation before any first filing to a new department. An
escalation scheduler solves when to escalate by backward induction on
the RTI Act's three stage structure, on a compressible demonstration
clock with a per-department rate limit, every action landing in an
append-only ledger with the policy behind it. `make prepare-demo` and
`make prewarm` prepare and check a deployment; see `docs/demo-script.md`.

See `docs/architecture.md`, `docs/algorithms.md`, and `docs/api.md` for the
detail behind each of these.

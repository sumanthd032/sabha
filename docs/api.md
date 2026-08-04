# API

Every endpoint is under `/api`. There is no separate host or port for
the frontend: one origin means no CORS configuration and a same-origin
WebSocket, per `docs/decisions/0002-free-hosting-targets.md`.

A participant is identified by a `session_token`, issued by `join` and
supplied on every later call. There is no other authentication: a
session is anonymous by design, and a token is not a secret worth more
than the vote it is attached to.

## Health

### `GET /api/health`

Build metadata and a database connectivity check, for the prewarm
described in `docs/deployment.md`. Returns:

```
{
  "status": "ok" | "degraded",
  "database": "ok" | "unreachable",
  "commit": "9a74961",
  "version": "0.1.0",
  "started_at": "2026-01-01T00:00:00Z"
}
```

`database` runs a trivial query against whatever DATABASE_URL points
at on every call, so a request here is also what wakes a suspended
Neon database. `status` reads `degraded` whenever `database` does not
read `ok`; the process itself never goes down over this.

## Consultations

### `GET /api/consultations`

Lists every consultation. Returns `ConsultationOut[]`:

```
{
  "id": 1,
  "title": "...",
  "question": "...",
  "department": "..." | null,
  "is_synthetic": true,
  "opens_at": "2026-01-01T00:00:00Z",
  "closes_at": "2026-01-31T00:00:00Z"
}
```

### `GET /api/consultations/{consultation_id}`

One consultation. `404` if the id does not exist.

## Statements

### `GET /api/consultations/{consultation_id}/statements`

The full statement pool for a consultation, in no particular order;
this is the raw pool, not a ranking. Returns `StatementOut[]`:

```
{
  "id": 12,
  "code": "S-0012",
  "text": "...",
  "language": "en",
  "author_type": "participant" | "generated",
  "parent_statement_id": 4 | null,
  "is_synthetic": true
}
```

### `GET /api/consultations/{consultation_id}/statements/next?session_token=...`

The next statement chosen for this participant, or `null` if every
statement has already been voted on or is exposure capped.

Before the first model run exists for a consultation, a statement is
chosen uniformly at random from whatever this participant has not yet
voted on: adaptive selection has nothing to locate or refine against
until at least one fit exists. Once a run exists, selection follows
`services/selection.py`: while this participant's own opinion posterior
is wide, the statement with the largest loading norm is served; once it
narrows, the statement with the widest posterior on its own intercept
is served instead. See `docs/algorithms.md`.

## Votes

### `POST /api/consultations/{consultation_id}/votes`

Request:

```
{ "session_token": "...", "statement_id": 12, "value": 1 }
```

`value` is `1` for agree or `-1` for disagree; there is no encoding for
a skip, since a skip is the absence of a row, never a stored value.
Returns the created `VoteResponse`:

```
{ "id": 501, "statement_id": 12, "value": 1, "created_at": "..." }
```

`404` for an unknown session token or a statement outside this
consultation. `409` if this participant has already voted on this
statement: a vote is immutable, so casting again is rejected rather
than silently overwriting it.

A successful vote schedules a debounced refit for the whole
consultation. See "Refit flow" in `docs/architecture.md`.

## Model runs

### `GET /api/consultations/{consultation_id}/model-runs/latest`

The most recent fitted snapshot's metadata. `404` before the first
refit. Returns `ModelRunOut`:

```
{
  "id": 7,
  "consultation_id": 1,
  "k_clusters": 3,
  "created_at": "...",
  "participant_count": 214,
  "statement_count": 68
}
```

The fitted figures themselves, statement intercepts, participant
factors and biases, and cluster assignments, are not exposed as raw
JSON here; they are what "Rankings", "Opinion map", and "Consensus
certificate" below are built from.

## Rankings

### `GET /api/consultations/{consultation_id}/rankings`

The bridging ranking beside the majority ranking, so the two are always
compared rather than only the bridging one ever shown in isolation.
Before the first model run, both lists are empty rather than an error,
since an unranked pool is a valid, if uninteresting, state.

```
{
  "model_run_id": 7 | null,
  "model_run_created_at": "..." | null,
  "bridging": [ { "statement_id": 12, "code": "S-0012", "text": "...", "score": 0.91, "rank": 1 }, ... ],
  "majority": [ { "statement_id": 30, "code": "S-0030", "text": "...", "score": 0.62, "rank": 1 }, ... ]
}
```

`bridging` is sorted by each statement's intercept `mu(j)`, highest
first. `majority` is sorted by the mean vote value, the naive score
every consultation tool defaults to. The two lists are expected to
disagree; see `docs/algorithms.md` for why.

## Opinion map

### `GET /api/consultations/{consultation_id}/opinion-map?session_token=...`

Every participant's fitted position, for the tally stroke map. `404`
before the first model run. `session_token` is optional; when given
and valid, that participant's point is marked `is_self` so their own
stroke can be drawn distinctly. An unknown or omitted token simply
means no point is marked self, not an error.

```
{
  "model_run_id": 7,
  "k_clusters": 3,
  "points": [
    { "participant_id": 42, "factor": [0.81, -0.4], "cluster": 1, "is_self": false },
    ...
  ]
}
```

`factor` is always the first two dimensions of the fitted `f(i)`: the
map is a two dimensional plot regardless of how many factors a given
fit used. `cluster` is the k-means label from the same model run, a
display grouping only, per `docs/algorithms.md`.

## Consensus certificate

### `GET /api/consultations/{consultation_id}/certificate`

The certificate for whichever statement currently ranks first in the
bridging ranking. `404` before the first model run. Returns
`CertificateOut`:

```
{
  "model_run_id": 7,
  "statement": { "id": 12, "code": "S-0012", "text": "...", ... },
  "participant_count": 214,
  "clusters": [
    { "cluster": 0, "participant_count": 71, "agree_count": 65, "agree_fraction": 0.915 },
    { "cluster": 1, "participant_count": 68, "agree_count": 60, "agree_fraction": 0.882 },
    { "cluster": 2, "participant_count": 75, "agree_count": 70, "agree_fraction": 0.933 }
  ]
}
```

Until the generation loop lands, the certified text is the statement's
own text rather than a drafted multi-statement clause; the certificate
component's job is to display whatever text it is given next to these
figures, so this is a substitution, not a different shape.

## Live session

### `WS /api/consultations/{consultation_id}/live`

Join the consultation's live channel. The server pushes a message every
time a debounced refit completes, whether the vote that triggered it
came from this connection's own participant or anyone else in the
consultation:

```
{
  "type": "rankings",
  "model_run_id": 8,
  "bridging": [ { "statement_id": 12, "code": "S-0012", "text": "...", "score": 0.91, "rank": 1 }, ... ],
  "majority": [ ... ]
}
```

The client sends nothing meaningful; the socket exists to receive
pushes, not to carry requests. Refits are not run on every vote. A vote
(re)schedules a single timer per consultation, so a burst of concurrent
votes collapses into one refit rather than one per vote. See "Refit
flow" in `docs/architecture.md`.

## Generation

### `POST /api/consultations/{consultation_id}/generation/run`

Selects this consultation's current fault lines, per
`docs/algorithms.md`, and proposes their reformulations in a single
batched call to the language model. No request body. Returns
`GenerationRunOut`:

```
{
  "injected": [
    { "id": 71, "code": "S-0071", "text": "...", "language": "en",
      "author_type": "generated", "parent_statement_id": 12, "is_synthetic": true }
  ]
}
```

`injected` is empty, with no call made, when there is no eligible
target or no room left under the generation pool fraction cap. `404`
before the first model run: there is nothing to locate a fault line
against yet. `503` when the daily quota is exhausted, with the body
`{ "detail": "generation paused, daily quota reached" }`, the exact
copy section 4.2 requires the interface to show.

A generated statement's own significance test against its parent runs
automatically on every debounced refit, not from an endpoint: it costs
no language model call, so there is nothing here to trigger it with.

## Clauses

### `GET /api/consultations/{consultation_id}/clauses`

Every clause drafted so far for this consultation. Returns
`ClauseOut[]`:

```
{
  "id": 4,
  "text": "...",
  "statement_ids": [12, 19],
  "certificate_figures": {
    "participant_count": 214,
    "clusters": [ { "cluster": 0, "participant_count": 71, "agree_count": 65, "agree_fraction": 0.915 }, ... ]
  }
}
```

`certificate_figures` is the same shape `services/certificate.py`
builds for the consensus certificate, captured at drafting time.

### `POST /api/consultations/{consultation_id}/clauses/draft`

Drafts a clause for each of the current bridging ranking's leaders
that clears the participant coverage bar, in a single batched call. No
request body. Returns `ClauseDraftOut`, `{ "clauses": ClauseOut[] }`,
containing only the clauses drafted by this call. `404` before the
first model run. `503` on daily quota exhaustion, same body as
generation above.

### `POST /api/consultations/{consultation_id}/clauses/route`

Routes the given clauses against the indexed Allocation of Business
Rules subset, per `docs/algorithms.md`. Request:

```
{ "clause_ids": [4, 5] }
```

`clause_ids` omitted or `null` routes every clause in the
consultation. Returns `RouteClausesOut`:

```
{
  "decisions": [
    { "id": 9, "clause_id": 4, "department": "Ministry of Labour and Employment",
      "citation": "Code on Social Security, 2020, section 2(61)",
      "confidence": 0.91, "rationale": "...", "needs_human_review": false }
  ]
}
```

A clause can receive more than one decision, one per department whose
mandate plausibly covers it. `503` on daily quota exhaustion, same
body as generation above.

### `GET /api/consultations/{consultation_id}/clauses/human-queue`

Every clause in this consultation with no confident route: no routing
decision at all, or every decision recorded for it flagged
`needs_human_review`. Returns `HumanReviewQueueOut`,
`{ "clause_ids": [7] }`. Section 6.5: a low confidence route is queued
for a human rather than filed on a guess.

Reply evaluation, `services/reply_evaluation.py`, has no endpoint of
its own: it runs automatically wherever a reply already exists, and
`POST .../filings/{filing_id}/replies` below is what creates one.

## Filings

### `GET /api/consultations/{consultation_id}/filings`

Every filing for this consultation. Returns `FilingOut[]`:

```
{
  "id": 3,
  "consultation_id": 1,
  "department": "Ministry of Labour and Employment",
  "channel": "mock",
  "artefact": "MOCK-000003",
  "stage": "awaiting_reply",
  "submitted_at": "2026-01-01T00:00:00Z",
  "statutory_deadline": "2026-01-31T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z"
}
```

`stage` is one of `drafted`, `filed`, `awaiting_reply`,
`escalated_appellate`, `escalated_commission`, `replied`, `closed`.

### `POST /api/consultations/{consultation_id}/filings`

Files the given clauses to a department through the channel
`FILING_MODE` resolves to, mock in every configuration this build
ships. Request:

```
{ "department": "...", "clause_ids": [4, 5], "confirmed_new_department": false }
```

`409` when this is the first filing to that department and
`confirmed_new_department` was not passed, the human gate section 9
requires, with the department named in the body:

```
{ "detail": { "department": "...", "detail": "this is the first filing to this department; resend with confirmed_new_department set to true" } }
```

Returns `FilingOut` on success, stage `filed`.

### `POST /api/consultations/{consultation_id}/filings/{filing_id}/replies`

Records a department's reply and moves the filing to stage `replied`,
stopping its escalation clock. Request `{ "received_text": "..." }`.
Returns `ReplyOut`. `404` if the filing does not exist in this
consultation. The only path in this codebase that creates a `Reply`
row.

### `POST /api/escalation/sweep`

Runs one escalation sweep now, across every open filing in every
consultation, per `docs/algorithms.md`'s "Escalation as optimal
stopping". Exists so a demonstration can trigger a check on cue;
`services/escalation.EscalationScheduler` already ticks this on its
own on a background interval, so nothing here is required for
escalation to happen on its own. Returns `FilingOut[]`, every filing
the sweep touched.

## Ledger

### `GET /api/consultations/{consultation_id}/ledger`

The append-only public record of every autonomous action taken for
this consultation's filings, oldest first. Returns `LedgerOut`:

```
{
  "entries": [
    {
      "id": 12, "occurred_at": "2026-01-01T00:00:00Z",
      "action": "escalated_to_escalated_appellate",
      "reason": "Ministry of Labour and Employment did not reply within the modelled window",
      "policy_state": { "elapsed_effective_days": 30.4, "demo_clock_scale": 1.0 },
      "filing_id": 3, "consultation_id": 1
    }
  ]
}
```

Read only: there is no endpoint anywhere that writes a `LedgerEntry`
directly, every row comes from `services/ledger.record`, called from
inside whichever service took the action it documents.

# API

Every endpoint is under `/api`. There is no separate host or port for
the frontend: one origin means no CORS configuration and a same-origin
WebSocket, per `docs/decisions/0002-free-hosting-targets.md`.

A participant is identified by a `session_token`, issued by `join` and
supplied on every later call. There is no other authentication: a
session is anonymous by design, and a token is not a secret worth more
than the vote it is attached to.

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
JSON here; they are what "Rankings" below is built from, and what the
consensus certificate in a later step reads directly from the database.

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

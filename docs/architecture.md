# Architecture

## Request flow

One FastAPI application serves the REST API under `/api`, the WebSocket
channel at `/api/consultations/{id}/live`, and, once built, the static
frontend bundle at every other path. One origin, one process: no CORS
layer and no separate WebSocket host to keep in sync with the API host.

A request touching the database depends on `sabha.db.get_session`,
which yields one SQLModel `Session` scoped to that request. Every
router, `consultations`, `sessions`, `rankings`, `live`, is a plain
`APIRouter` included once in `main.py`; none of them hold state of
their own beyond what they read from the database on each call.

The one exception is `services/live.py`'s `LiveSessionManager`, held as
a process wide singleton in `routers/live.py`. It keeps the in-memory
registry of open WebSocket connections per consultation and the pending
debounce timer, described below. This state is deliberately not in the
database: a WebSocket connection is only ever meaningful to the process
holding the socket, and this deployment is one process.

## Refit flow

Casting a vote does not refit the model inline. With fifty participants
voting in the same second, fifty alternating least squares passes back
to back would make every one of those votes slow for no benefit; the
sixty-ninth vote in a burst needs the same fit as the fiftieth.

Instead, `POST .../votes` does three things and returns immediately:
validates the vote, inserts it, and calls
`LiveSessionManager.notify_vote_cast(consultation_id)`. That call
cancels whichever refit timer was already pending for this
consultation, if any, and starts a new one on a fixed debounce interval
(`services/live.DEBOUNCE_SECONDS`, two seconds in production). Only the
last vote in a burst survives to actually start a refit; every earlier
one in the same window just resets the clock.

When a timer finally fires, the refit itself, `factorisation.fit`
followed by `clustering.choose_k`, runs inside `asyncio.to_thread`, off
the event loop. This is the second half of "does not stall": the event
loop stays free to accept new joins, statement requests, and votes
while that computation runs in a worker thread. The refit opens its own
database session, since a session is not safe to share with the request
that scheduled it.

Once the refit finishes, it persists a new `model_run` row, per
`services/model_run.fit_and_persist`, rows are inserted fresh and never
updated, so a figure shown to the public can always be reproduced by
refitting with that run's own parameters, then sweeps for any generated
statement that has crossed the minimum vote threshold with
`services/generation.evaluate_pending_variants`, retiring the ones that
do not significantly beat their parent, before building both rankings
with `services/rankings.build_rankings`. The evaluation step is pure
computation over the fit that just happened, no language model call,
which is why it rides along on every refit rather than needing its own
trigger. That message is broadcast to every WebSocket connected to the
consultation, and it is the only path by which a client learns a refit
happened; there is no separate polling endpoint for "has anything
changed".

```
POST /votes ---> insert vote ---> notify_vote_cast
                                        |
                                   (re)start debounce timer
                                        |
                                   timer fires (2s of quiet)
                                        |
                                   asyncio.to_thread(refit)
                                        |
                                   fit_and_persist -> model_run row
                                        |
                                   build_rankings
                                        |
                                   broadcast to every open WebSocket
```

A brand new consultation with no model run yet is not blocked on this
pipeline: `GET .../statements/next` falls back to a uniformly random,
not yet voted, statement until the first run exists, so a participant
can always start voting immediately.

## Escalation flow

Unlike the refit, nothing about escalation is triggered by a request.
A filing's statutory clock runs on wall time whether or not anyone is
voting, so `main.py`'s lifespan starts one process wide
`services.escalation.EscalationScheduler` alongside the app and stops
it on shutdown, the same singleton shape `routers/live.py` uses for
its own manager, but ticking on a fixed interval rather than a
per-vote debounce.

```
app startup ---> EscalationScheduler.start()
                        |
                   asyncio.sleep(interval)  (repeats)
                        |
                   asyncio.to_thread(sweep)
                        |
                   run_escalation_sweep: every open filing,
                   grouped by department so each department's
                   backward induction policy is computed once
                        |
                   run_escalation_check per filing: start the
                   clock, wait, escalate, or close, each a
                   ledger entry
```

The sweep runs in a worker thread on its own database session, exactly
the refit's own reasoning: the event loop stays free to answer
requests, and a session is not safe to share with the thread that
scheduled it. `POST /api/escalation/sweep` runs the same sweep
on demand, so a demonstration can trigger a check on cue instead of
narrating over a silent wait for the next tick; nothing about
escalation depends on that endpoint ever being called.

## Deployment shape

See `docs/deployment.md` and `docs/decisions/0002-free-hosting-targets.md`
for the hosting target and its tradeoffs. In short: one Docker image,
Render's free web service tier, Neon Postgres, no CORS layer and no
separate WebSocket origin because the frontend and the API are the same
origin by construction.

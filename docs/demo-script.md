# Demo script

Five minutes, run in this order, on the deployed URL, never localhost.
The prewarm is step zero and must complete before anyone speaks.

Filing and the ledger have no dedicated screen in this build. They are
shown through the interactive API documentation at `/docs` on the
deployed URL, or through the curl commands below typed live. Read the
narration for each as what to say while the request is on screen.

## Before the day

Run once, whenever the seed corpus, generation prompts, or the
allocation rule index changes. Point DATABASE_URL at the same database
the deployed instance uses, since the database this populates is the
seeded snapshot the live demo loads from, there is no separate
snapshot file.

```
DATABASE_URL=<the deployed connection string> \
GEMINI_API_KEY=<key> QUOTA_RPM=<rpm> QUOTA_RPD=<rpd> \
make prepare-demo
```

This seeds the consultation, fits a model, runs one generation cycle,
drafts and routes a clause, and files it to a department through the
mock channel. Every language model and embedding call it makes is
cached by content hash, so running it again costs no further quota,
and the live run afterward makes at most one call, per section 4.2.

## Ten minutes before presenting

```
make prewarm URL=https://sabha-n4f7.onrender.com COMMIT=<expected short commit>
```

Confirms `/api/health` reports `status: ok` and `database: ok`, and
that the deployed commit matches what was just pushed. Neon
autosuspends when idle; this call is what wakes it, so the room never
sees that latency. If it fails, do not proceed, fix the deployment
first.

## The five minutes

1. A statement with real disagreement is on screen with a QR code to
   the voting URL (`/`). The audience votes for three minutes on their
   own phones.

2. Switch to `/results`. The opinion map builds live as strokes settle
   into position and factions separate. Point out that most
   participants were placed after roughly eight votes, the adaptive
   selection policy working rather than luck.

3. Point at the majority ranking beside the bridging ranking, on the
   same screen. They disagree: the statement the room actually agreed
   on across factions is not the one with the most votes. Say this out
   loud, it is the moment the idea lands, and it lands harder because
   the room is the dataset.

4. Trigger one generation cycle:

   ```
   curl -X POST https://.../api/consultations/1/generation/run
   ```

   Narrate that a model has proposed a reformulation of the most
   divisive statement and it has entered the pool. Have a few
   participants vote on it from their phones, then point at `/results`
   again: a machine just wrote something the room agreed on more than
   anything a human in the room wrote.

5. Draft, route, file, escalate, and close on the ledger:

   ```
   curl -X POST https://.../api/consultations/1/clauses/draft
   curl -X POST https://.../api/consultations/1/clauses/route
   curl -X POST https://.../api/consultations/1/filings \
     -d '{"department": "Ministry of Labour and Employment", "clause_ids": [<id>], "confirmed_new_department": true}'
   ```

   State out loud, before this last call, that the filing endpoint is
   sandboxed and that this confirmation is exactly what section 9
   requires before a first filing to a new department, live, on
   screen. Volunteering that is the detail that makes an audience trust
   the rest.

   Then, with `DEMO_CLOCK_SCALE` set well above 1 on the deployed
   instance so the statutory clock is compressed for this
   demonstration:

   ```
   curl -X POST https://.../api/escalation/sweep
   curl https://.../api/consultations/1/ledger
   ```

   The sweep response and the ledger's `policy_state` both carry the
   `demo_clock_scale` value in force, so read it aloud: the compression
   is never hidden. Close by scrolling the ledger: every action taken,
   in order, with the policy behind it.

## Network conditions

Run this entire sequence once beforehand with the browser devtools
network throttled to "slow 3G", against the deployed URL, not
localhost, to catch anything that only breaks on a real network.

## Fallback

Record a full successful run as a screen capture before presenting,
and have it ready to play if the live network fails on the day.

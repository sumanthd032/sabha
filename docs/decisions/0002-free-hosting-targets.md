# 0002: free hosting targets

## Context

Sabha needs to run live, on a public URL, in front of a demo audience, with
no card on file for any service. The original choice here was a Hugging
Face Space on the Docker SDK, for 2 vCPU and 16 GB of RAM that only sleeps
after prolonged inactivity. That plan lasted exactly as long as it took to
create the Space: Hugging Face now requires a paid PRO subscription for
any Space that runs on compute, Docker included, and only static,
no-backend Spaces remain free. A card was not something either the build
instructions or the person running this build were willing to enter, so
the hosting target had to change before step 1 could finish deploying.

## Decision

The application, api and built frontend together, runs on Render's free
web service tier instead, built from the same Dockerfile. No card is
required to create the service. The tradeoff is real and was already
anticipated even in the Hugging Face plan: a free Render service spins
down after fifteen minutes without inbound traffic and takes about a
minute to wake back up, which is why step 10 already builds a prewarm
check that hits the deployed URL ten minutes before any demonstration.
That same check now covers Render's cold start alongside Neon's
autosuspend, rather than needing a separate mechanism for each.

The container listens on the `PORT` environment variable Render assigns
at runtime rather than a fixed port, since that is how Render routes
traffic to a Docker web service. The database remains Neon Postgres,
which autosuspends but wakes in about a second. Continuous integration
and deployment run on GitHub Actions against a public repository, which
keeps Actions minutes unlimited. Deployment itself is a `curl` to a
Render deploy hook once the checks pass, rather than a git push to a
provider-specific remote. Fonts stay self-hosted through `@fontsource`
rather than fetched from Google Fonts at request time.

## Consequence

The image must stay small enough to build quickly, which is the reason
section 4 of the build instructions forbids torch, `sentence-transformers`,
and local model weights: embeddings and generation both go through the
Gemini API instead. The tradeoff is a hard dependency on an external model
API being reachable during the demo, mitigated by pre-generating and
caching everything the demo script needs ahead of time, per section 4.2.

Free tier pricing changes without notice, from any provider. Do not treat
this file, or section 10 of the build instructions, as a permanent
guarantee: if Render's terms change before the demo, verify again rather
than assuming the plan still holds.

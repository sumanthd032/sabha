# 0002: free hosting targets

## Context

Sabha needs to run live, on a public URL, in front of a demo audience, with
no card on file for any service. The obvious default for a small FastAPI
application is Render's free web service, but that tier caps at 512 MB of
memory and spins down after fifteen minutes of inactivity, with a cold
start close to a minute. A consultation demo that opens on a dead server is
a worse failure than any bug in the application itself.

## Decision

The application, api and built frontend together, runs on a Hugging Face
Space using the Docker SDK, which gives 2 vCPU and 16 GB of RAM on the free
tier and only sleeps after prolonged inactivity, not after fifteen minutes.
The database is Neon Postgres, which autosuspends but wakes in about a
second, well inside what a prewarm check ten minutes before a demo can
absorb. Continuous integration and deployment run on GitHub Actions against
a public repository, which keeps Actions minutes unlimited. Fonts are
self-hosted through `@fontsource` rather than fetched from Google Fonts at
request time.

## Consequence

The image must stay small enough to build quickly on the Space's shared
infrastructure, which is the reason section 4 of the build instructions
forbids torch, `sentence-transformers`, and local model weights: embeddings
and generation both go through the Gemini API instead. The tradeoff is a
hard dependency on an external model API being reachable during the demo,
mitigated by pre-generating and caching everything the demo script needs
ahead of time, per section 4.2.

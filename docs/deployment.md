# Deployment

## Targets

One Docker image, built in two stages: the first runs `npm ci` and
`npm run build` for the frontend, the second installs the Python
dependencies and copies the built assets in. FastAPI serves the API
under `/api` and the built frontend at every other path, with a
catch-all returning `index.html` so client side routing works. One
origin means no CORS layer and a same-origin WebSocket.

| Concern | Service | Note |
|---|---|---|
| Application | Render, free web service | see `docs/decisions/0002-free-hosting-targets.md` for why Render rather than Hugging Face Spaces |
| Database | Neon Postgres | 0.5 GB free tier, autosuspends and wakes in about a second |
| Language model and embeddings | Google AI Studio, Gemini free tier | per-minute and per-day request limits, see `services/quota.py` |
| Continuous integration and deploy | GitHub Actions, public repository | `ci.yml` on every push, `deploy.yml` on merge to `main` |

`deploy.yml` runs the checks, then calls Render's deploy hook URL,
stored as the `RENDER_DEPLOY_HOOK_URL` secret. Render rebuilds the
image from the same `Dockerfile` a local `docker build` uses, so a
local build reproduces production exactly.

## Operating notes

- The free Render service sleeps after prolonged inactivity and takes
  a noticeable moment to wake on the next request. Run
  `make prewarm URL=<deployed url> COMMIT=<expected short commit>`
  ten minutes before any demo: it hits `/api/health`, which now also
  runs a trivial query against the database, confirms `status` and
  `database` both read `ok`, and checks the deployed commit matches.
- Neon autosuspends on its own schedule independent of Render's. The
  first query after either has gone idle costs about a second; the
  prewarm check above is what absorbs that cost before anyone is
  watching.
- The container filesystem is not persistent across deploys. Nothing
  durable is ever written to disk, which is why Postgres is not
  optional and why `make prepare-demo` seeds the database itself
  rather than a file the demo would load separately.
- Gemini free tier quota is shared across development and production.
  Every response is cached by content hash in `llm_cache` and every
  embedding in `embedding_cache`, so a rerun of the same call costs
  nothing, but a careless loop still can. `services/quota.py`'s guard
  is the actual protection; caching is what makes reruns free, not a
  substitute for the guard.
- Keep the repository public so GitHub Actions minutes stay free. No
  secret ever enters the repository as a result; secrets are set in
  Render's and Neon's own dashboards.

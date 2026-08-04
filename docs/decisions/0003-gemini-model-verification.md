# 0003: Gemini model identifiers and free tier limits, verified

## Context

Section 4.1 of the build instructions requires verifying both model
identifiers and the current free tier limits against Google's own
documentation and account dashboard before the first call in step 9,
since defaults written months earlier can go stale. They had.

`gemini-2.5-flash` was checked against the live `generateContent`
endpoint and against `ListModels`: it responds correctly and is not
flagged deprecated, alongside newer 3.x flash models that exist now
but were not the specification's choice. `gemini-embedding-001` was
checked against `embedContent` the same way and also still works.
`text-embedding-004`, the specified fallback embedding model, returns
a 404 not found from `embedContent`: it has been removed. `ListModels`
shows exactly three embedding capable models: `gemini-embedding-001`,
`gemini-embedding-2`, and `gemini-embedding-2-preview`.

Google no longer publishes a universal per tier RPM or RPD table for
the generation API. The rate limits documentation page and the pricing
page both defer to a per project dashboard at
`aistudio.google.com/rate-limit`, and third party sources quoting fixed
numbers disagreed with each other by an order of magnitude, one citing
a quota reduction on 7 December 2025 of 50 to 80 per cent as the
likely cause. Guessing a figure here, per section 9's own instruction,
was not acceptable; the dashboard for this project's account was
checked directly instead.

## Decision

`GEMINI_MODEL` stays `gemini-2.5-flash`. `GEMINI_EMBED_MODEL` stays
`gemini-embedding-001`. The fallback embedding identifier changes from
`text-embedding-004`, which is gone, to `gemini-embedding-2`, the
current stable non-preview alternative.

`QUOTA_RPM=5` and `QUOTA_RPD=20`, read directly off the project's own
rate limit dashboard for Gemini 2.5 Flash text output, which also
shows a 250,000 TPM ceiling not tracked separately here since a
statement length prompt is nowhere near it before RPD binds first.

## Consequence

Twenty requests a day is a very small number against roughly seventy
statements needing generation loop attention, jurisdiction routing,
and reply evaluation. It is the reason section 4.2's cache and quota
guard are built before any feature that calls the model, not after,
and the reason `make prepare-demo` in step 10 exists at all: the
demo's entire request budget for the day may be spent generating and
caching everything the demo script needs, hours before anyone is in
the room. A development session that is not careful about cache hits
can exhaust a whole day's quota by lunchtime.

Free tier limits change without notice and are assigned per project,
not published as a fixed table. Do not treat the numbers above as
permanent; if they stop matching what the API actually enforces,
check the dashboard again rather than assuming this file still holds.

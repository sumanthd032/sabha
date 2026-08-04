#!/usr/bin/env bash
# Confirms a deployed instance is awake and its database is reachable,
# to run ten minutes before presenting per docs/demo-script.md.
#
# Neon autosuspends when idle, so the first query after a while takes
# about a second; the health endpoint runs that query itself, so one
# request here is enough to wake it and check it.

set -euo pipefail

url="${1:?usage: scripts/prewarm.sh https://your-deployed-url}"
expected_commit="${2:-}"

response="$(curl --fail --silent --show-error "${url%/}/api/health")"
echo "$response"

status="$(echo "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "missing"))')"
database="$(echo "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("database", "missing"))')"
commit="$(echo "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("commit", "missing"))')"

if [ "$status" != "ok" ] || [ "$database" != "ok" ]; then
  echo "prewarm failed: status=$status database=$database" >&2
  exit 1
fi

if [ -n "$expected_commit" ] && [ "${commit#"$expected_commit"}" = "$commit" ]; then
  echo "prewarm failed: deployed commit $commit does not start with expected $expected_commit" >&2
  exit 1
fi

echo "prewarm ok: commit=$commit database=$database"

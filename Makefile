.PHONY: prepare-demo prewarm check

# Generates and caches every language model response the demo needs,
# and leaves the database in an already interesting state. Point
# DATABASE_URL at whatever the demo will actually run against before
# calling this: there is no separate snapshot file, the database it
# populates is the snapshot.
prepare-demo:
	cd api && python -m sabha.seed.prepare_demo

# Confirms a deployed instance is awake and its database is reachable,
# ten minutes before presenting. URL is required; COMMIT is optional
# and checked as a prefix of the deployed commit hash.
prewarm:
	bash scripts/prewarm.sh "$(URL)" "$(COMMIT)"

# The same checks CI runs, before a commit.
check:
	cd api && ruff check . && mypy . && pytest -q
	cd web && npm run build && npm run test -- --run

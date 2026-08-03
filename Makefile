.PHONY: dev sync db ask help

help:
	@echo "Targets:"
	@echo "  make dev  - sync deps, ensure DB, launch interactive CLI"
	@echo "  make sync - install Python dependencies"
	@echo "  make db   - build ./bse_nlq.db if missing"
	@echo "  make ask  - one-shot: make ask Q='your question'"

sync:
	uv sync --group dev

db:
	@if [ ! -f bse_nlq.db ]; then \
		uv run python -m bse_nlq.db.build ./bse_nlq.db; \
	else \
		echo "bse_nlq.db already present"; \
	fi

# Interactive happy path: pick an example or type your own.
# Loads .env into this recipe only when present (never commits it).
dev: sync db
	@if [ -f .env ]; then set -a && . ./.env && set +a; fi; \
	uv run bse-nlq ask

# One-shot ask. Example: make ask Q='What is the average ticket price?'
ask: sync db
	@if [ -z "$(Q)" ]; then echo "Usage: make ask Q='your question'"; exit 2; fi
	@if [ -f .env ]; then set -a && . ./.env && set +a; fi; \
	uv run bse-nlq ask "$(Q)"

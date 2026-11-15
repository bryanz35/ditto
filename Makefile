# Commands are documented in CLAUDE.md.
API_PORT ?= 8000
WEB_PORT ?= 5173
export API_PORT WEB_PORT

ENV_FILE := $(if $(wildcard .env),--env-file .env)

.PHONY: setup test test-slow test-live lint types dev

setup:
	uv sync
	cd frontend && npm ci
	command -v pio >/dev/null || uv tool install platformio

# pytest exits 5 when it collects no tests; that's not a failure while an area has none yet.
test:
	uv run pytest -m "not slow and not live" || [ $$? -eq 5 ]
	cd frontend && npm test

test-slow:
	uv run pytest -m "not live" || [ $$? -eq 5 ]
	cd frontend && npm test

test-live:
	uv run $(ENV_FILE) pytest -m live || [ $$? -eq 5 ]

lint:
	uv run ruff check .
	uv run ruff format --check .
	cd frontend && npm run typecheck && npm run lint

# Integrator only: Pydantic models -> JSON Schema -> frontend/src/contracts/*.ts (exporter added in T01).
types:
	uv run python -m backend.contracts.export_types

dev:
	trap 'kill 0' EXIT; \
	uv run uvicorn backend.app.main:app --reload --reload-dir backend --port $(API_PORT) $(ENV_FILE) & \
	cd frontend && npm run dev

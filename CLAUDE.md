# CLAUDE.md — Prompt-to-Device

`docs/PROJECT_PLAN.md` holds the technical design; `README.md` has the repo layout, setup and env vars.

## What we're building (one paragraph)

A web app that turns a text prompt, sketch or short video into a buildable physical project: a
3D-printed object, a microcontroller device (ESP32, Arduino Uno/Nano, Raspberry Pi Pico), or both. For a
device it makes a parts list with prices, a wiring plan, compiled Arduino firmware and a printable case
(a plain box, or a model-written custom body around it); for a print-only object (`mcu: null`) just the
printed parts, from build123d code the model writes and plain code runs and checks. A deepagents
orchestrator delegates to sub-agents (parts and pins, firmware, enclosure). **Every model output is
checked by plain code before the UI shows it.** The project spec (`ProjectSpec`) is the single source
of truth: every other output is generated from it.

## Rules

1. **Import across areas only through `backend/contracts/` and each tool module's single public function.**
   Never import another area's private helpers.
2. **No network in unit tests.** Use fixtures and mocks. Mark slow tests `@pytest.mark.slow`
   (PlatformIO compiles, build123d builds) and tests that call real APIs `@pytest.mark.live`.
3. **Never commit secrets.** Keys live in `.env` (copied from `.env.example`, gitignored).

## Contracts

`backend/contracts/` is authoritative; each module's docstrings state its rules. Read `base.py`
(coordinate frames) before touching geometry and `runner.py` (who runs what) before touching the run flow.
Every tool returns a `ToolResult` and never raises for expected failures; error messages are read by an
LLM, so make them specific and actionable.

`frontend/src/contracts/` is generated: after changing a Pydantic model, run `make types` (never edit
it by hand) and update `fixtures/` so the contract tests in `tests/contract/` still pass.

## Commands

| Command | What it does |
| --- | --- |
| `make setup` | `uv sync` + `npm ci` in `frontend/` + PlatformIO (`uv tool install platformio`, if `pio` is missing) |
| `make test` | Fast unit + contract tests (must pass before every PR) |
| `make test-slow` | Adds PlatformIO compiles and CAD builds |
| `make test-live` | Calls real APIs (needs `.env`; costs money: run sparingly) |
| `make lint` | `ruff check`, `ruff format --check`, `tsc -b` (type check), `oxlint` |
| `make types` | Regenerates `frontend/src/contracts/` from the Pydantic models |
| `make dev` | API on `$API_PORT` (default 8000) and web on `$WEB_PORT` (default 5173) |
| `P2D_RUNNER=fake make dev` | API replays a recorded run (no model calls): for frontend work |

The web dev server proxies `/api/*` to the API with the prefix stripped: the UI fetches `/api/runs/...`,
the API serves `/runs/...`.

## Code conventions

- Python 3.12+, `uv`, Pydantic v2, type hints everywhere, `ruff` defaults. Pure functions where possible:
  tools take models and paths, return `ToolResult`, and write files only inside the given `out_dir`.
- Deterministic output: same spec in, same files out (sort keys, no timestamps inside generated files).
- Frontend: Vite + React + TypeScript strict, `@react-three/fiber` for 3D, `vitest` for tests.
  Import types only from `src/contracts/`.
- Model name comes from `P2D_MODEL`; never hard-code it.
- Generated firmware must `#include "pins.h"`, use only `PIN_*` macros for pin numbers, and print
  `P2D_READY` on serial at the end of `setup()` (the firmware lint in `backend/tools/firmware.py`
  enforces both; the simulator waits for it).

## Hardware may not be available

`handoff/HARDWARE.md` records whether we have parts and a printer, which sets the demo mode (P, E or
V; see "Hardware availability" in `docs/PROJECT_PLAN.md`). `backend/contracts/hardware.py` reads it.
Never make a test depend on physical hardware. Until it's filled in, assume mode V: datasheet
dimensions, the `generic` printer profile, simulation available.

## Git and PRs

- Branch from `main` as `feat/<slug>` or `fix/<slug>`. Small commits, conventional messages.
- Before opening a PR: rebase on `main`, then `make lint test` (and `make test-slow` if you touched
  firmware or CAD).
- PR description: what changed, how to test, anything you stubbed.

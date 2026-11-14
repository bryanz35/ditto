# Prompt-to-Device

A web app that turns a text prompt, a sketch or a short video into a buildable ESP32 device:

- a parts list with prices (reusing parts you already own),
- a wiring plan,
- compiled Arduino firmware (optionally run in the Wokwi simulator),
- a 3D-printable enclosure and an assembly preview.

An AI orchestrator plans the device and delegates to sub-agents. Plain code checks every model output
before the UI shows it. The project spec (`ProjectSpec`) is the single source of truth: everything else
is generated from it, so an edit like "add a buzzer" updates firmware, wiring, BOM and enclosure together.

## How it fits together

```
prompt / sketch / video
        │
        ▼
  preprocess_input ──► agent (orchestrator + sub-agents) ──► ProjectSpec
                                                                │
        ┌───────────────┬───────────────┬───────────────┬──────┴────────┐
        ▼               ▼               ▼               ▼               ▼
   validate +       layout +        firmware        wiring +        pricing /
   cross-checks     enclosure +     (pins.h,        simulation       BOM
                    assembly        compile, lint)  (Wokwi)
        └───────────────┴───────────────┴───────────────┴───────────────┘
                                        │
                              events + files in runs/<id>/
                                        │
                                        ▼
                               web UI (live progress)
```

Each stage emits events (`queued`, `running`, `passed`, `failed`, `skipped`, ...) that the UI streams.
A stage whose dependency (an API key, PlatformIO, a simulator token) is missing reports `skipped`
instead of failing the run.

## Components

| Path | What it is |
| --- | --- |
| `backend/contracts/` | Shared Pydantic models: `ProjectSpec`, part/board definitions, tool results, events, run files. Every area talks to the others through these. |
| `backend/agent/` | The orchestrator and its sub-agents (parts and pins, firmware, enclosure), prompts and tool wrappers. Model is chosen by `P2D_MODEL`. |
| `backend/tools/` | Deterministic tools, each returning a `ToolResult`: spec validation and cross-checks, layout, enclosure build and check, firmware generation and compile, pricing, input preprocessing, simulation. `toolbox.py` bundles them; `fakes.py` has stand-ins for tests. |
| `backend/cad/` | build123d geometry: the box-and-lid enclosure and the assembly preview (`assembly.glb`). |
| `backend/parts/` | Part library (YAML per part), code snippets, printer profiles and cached prices. |
| `backend/runtime/` | Run engine: executes stages, writes `runs/<id>/`, handles edits (re-runs only affected stages), replays recorded runs. |
| `backend/app/` | FastAPI app: runs, run files, part memory (owned parts, budget) and device routes. |
| `backend/memory/` | Persistent store for owned parts, budget and rejected choices. |
| `firmware_templates/` | PlatformIO project templates the firmware tool fills in. |
| `frontend/` | Vite + React + TypeScript UI with a 3D viewer (`@react-three/fiber`). Types come from `src/contracts/`, generated from the Pydantic models. |
| `fixtures/` | Example specs and recorded runs used by tests and the fake runner. |
| `tests/` | Unit, contract, integration and end-to-end tests. |
| `evals/` | Prompt evals for the agent. |
| `scripts/` | Dev tooling: worktree setup, the coordination board (`board.py`), price prefetch. |
| `docs/PROJECT_PLAN.md` | The technical design. |
| `handoff/` | Build plan, task graph, runbook and hardware availability for the team building this repo. |

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- PlatformIO (installed by `make setup` if missing) to compile firmware

## Setup

```sh
make setup            # uv sync, npm ci in frontend/, PlatformIO
cp .env.example .env  # then fill in the keys you have
```

Keys in `.env` (all optional; tools without their key report `skipped`):

| Variable | Used for |
| --- | --- |
| `ANTHROPIC_API_KEY`, `P2D_MODEL` | The agent (e.g. `P2D_MODEL=claude-sonnet-5-5`) |
| `NEXAR_CLIENT_ID`, `NEXAR_CLIENT_SECRET` | Live part prices |
| `WOKWI_CLI_TOKEN` | Firmware simulation |
| `P2D_TRANSCRIBE` (`whisper`, `openai`, `off`), `P2D_TRANSCRIBE_MODEL`, `OPENAI_API_KEY` | Video input transcription |

## Run it

```sh
make dev                    # API on :8000, web on :5173 (open http://localhost:5173)
P2D_RUNNER=fake make dev    # replay a recorded run: no model calls, no keys needed
```

`P2D_RUNNER` picks the runner: `real` (default, the agent), `fake` (the fixture run) or
`replay:<run_dir>` (replay a previous run). Run output goes to `runs/` (override with `P2D_RUNS_DIR`).
Ports come from `.env.worktree` when present (`API_PORT`, `WEB_PORT`). The web dev server proxies
`/api/*` to the API.

## Test and lint

```sh
make test       # fast unit + contract tests (backend and frontend)
make test-slow  # adds PlatformIO compiles and CAD builds
make test-live  # calls real APIs: needs .env, costs money
make lint       # ruff, tsc, oxlint
```

## Contributing

This repo is built by several agents in parallel, each in its own git worktree. Read `CLAUDE.md` first:
it covers path ownership, frozen contracts, and the coordination board (`python3 scripts/board.py next`).

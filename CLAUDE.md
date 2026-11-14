# CLAUDE.md — Prompt-to-Device

Read this file fully before doing anything. Then read your task card in `handoff/BUILD_PLAN.md`, and the
parts of `docs/PROJECT_PLAN.md` (the technical design) that your card mentions.
Several Claude Code agents build this repo **at the same time**, each in its own git worktree.
These rules exist so that parallel work merges cleanly. Follow them even when a shortcut looks harmless.

## What we're building (one paragraph)

A web app that turns a text prompt, sketch or short video into a buildable ESP32 device: a parts list
with prices, a wiring plan, compiled Arduino firmware and a 3D-printable enclosure. A deepagents
orchestrator delegates to sub-agents (parts and pins, firmware, enclosure). **Every model output is
checked by plain code before the UI shows it.** The project spec (`ProjectSpec`) is the single source
of truth: every other output is generated from it.

## The coordination board: always know your next step

You never have to guess what to do next or wait for a human to relay messages. Run:

```
python3 scripts/board.py next
```

It reads who you are from `.env.worktree` (the main checkout is the Integrator) and prints one ACTION
with exact instructions: `START`, `WORK`, `SUBMIT`-related steps, `FIX_REVIEW`, `REVIEW`, `SIGNOFF`,
`REBASE`, `QA_UPDATE`, `MERGE`, `DECIDE_CONTRACT`, `WAIT` or `DONE`.
The board knows the dependency graph, who consumes whose output, every review verdict and sign-off
(tied to the exact commit they were given for), and every merge.

- **Run `next` at the start of a session, after every step you finish, and whenever you're unsure.**
  Do the action it prints, then run it again.
- **Record every change of state through the board, never by hand:** `board.py start`, `submit`,
  `block --on <TASK>`, `unblock`, `request --file ... --summary ...`. The Reviewer runs `review`,
  consumers run `signoff`, the Integrator runs `merged`, `done`, `decide`, `announce`. Each command
  checks preconditions (for example, `submit` refuses unpushed or un-rebased work).
- **Waiting is automatic.** Your human starts `/loop` in your session after approving your plan;
  `.claude/loop.md` makes each wake-up run `next` and act on it, so you pick up review results,
  sign-off requests and "rebase now" notices on your own.
- The live state is on the `coord` git branch. Never check it out, edit it or merge it.
- Humans see everything with `python3 scripts/board.py status`.

## Golden rules

1. **Work only on your task card.** Your task ID is in `.env.worktree` (`P2D_TASK`) and in your branch name.
2. **Edit only the paths your task owns** (see the ownership map below and your card's "Owns" list).
   Need a change elsewhere? Don't make it. Write it under **Requests** in your status file and work
   around it locally (a fake or a stub behind the contract).
3. **Contracts are frozen** after Gate G0 (`backend/contracts/`, `fixtures/`, `frontend/src/contracts/`).
   To change one, write `handoff/contract-requests/<TASK>-<slug>.md` (what, why, who it affects) and keep going
   with the current contract. The Integrator decides and lands contract changes on `main`.
4. **Import across areas only through `backend/contracts/` and each tool module's single public function.**
   Never import another area's private helpers.
5. **No network in unit tests.** Use fixtures and mocks. Mark slow tests `@pytest.mark.slow`
   (PlatformIO compiles, build123d builds) and tests that call real APIs `@pytest.mark.live`.
6. **Never commit secrets.** Keys live in `.env` (copied from `.env.example`, symlinked into every worktree, gitignored).
7. **Keep the board and your notes current.** State changes go through `scripts/board.py`; your status
   file (`handoff/status/<TASK>.md`) holds your plan, progress notes and test commands, updated at every commit you'd
   want a teammate to know about. It's how the Integrator and humans see progress without interrupting you.
8. **Don't merge to `main`.** Push your branch, open a PR, and run `board.py submit`. Only the Integrator merges.

## Ownership map

| Path | Owner task | Notes |
| --- | --- | --- |
| `backend/contracts/`, `fixtures/` (except `fixtures/firmware/`), `frontend/src/contracts/`, `tests/contract/` | T01 (Integrator) | Frozen after G0 |
| `backend/tools/toolbox.py`, `backend/tools/fakes.py`, `handoff/MERGES.md` | T01, T20 (Integrator) | |
| `pyproject.toml`, `Makefile`, `frontend/package.json`, `scripts/` (except `prefetch_prices.py`), CI | T00 (Integrator) | Need a dependency? Request it |
| `backend/tools/validate_spec.py`, `backend/tools/cross_checks.py` | T10, T21 | |
| `backend/tools/layout.py`, `backend/tools/build_enclosure.py`, `backend/tools/check_enclosure.py`, `backend/cad/` (except `assembly.py`), `backend/parts/printers/` | T11 | |
| `backend/cad/assembly.py` | T25 | Assembly preview (`assembly.glb`) |
| `backend/tools/simulation.py` | T26 | Wokwi diagram + simulator run |
| `handoff/HARDWARE.md` | Humans only | Parts/printer availability and demo mode |
| `backend/tools/firmware.py`, `firmware_templates/`, `fixtures/firmware/` | T12 | pins header, project generation, compile, lint, golden firmware |
| `backend/agent/` | T13 | orchestrator, sub-agents, prompts, tool wrappers |
| `backend/app/main.py`, `backend/app/routers/runs.py`, `backend/app/routers/files.py`, `backend/runtime/` | T14, then T22 | API, run engine, `deps.py`, replay runner, edit flow |
| `frontend/` (except `src/contracts/`) | T15, T24, T32 | |
| `backend/tools/pricing.py`, `backend/memory/`, `backend/app/routers/memory.py`, `scripts/prefetch_prices.py`, `backend/parts/prices.json` | T16 | |
| `backend/tools/preprocess_input.py` | T17 | |
| `backend/parts/library/*.yaml`, `backend/parts/snippets/` | T18 (the 5 plant-monitor parts: T01) | |
| `tests/integration/`, `tests/e2e/`, `evals/` | T19, T30 (QA) | Builders own `tests/unit/<area>/` |
| `backend/app/routers/device.py`, `device/` | T31 | Showcase device is a placeholder until chosen |
| `README.md`, `docs/` (except `docs/PROJECT_PLAN.md`) | T33 | |
| `docs/PROJECT_PLAN.md`, `handoff/BUILD_PLAN.md`, `handoff/RUNBOOK.md`, `handoff/tasks.json`, `CLAUDE.md`, `.claude/loop.md` | Integrator + humans | The plan itself; `tasks.json` is the task graph the board reads |
| `coord` branch (board state) | `scripts/board.py` only | Never edited, checked out or merged by hand |
| `handoff/status/<TASK>.md` | that task | One file per task: no conflicts |
| `handoff/contract-requests/<TASK>-*.md` | the requesting task | |

Files are created as stubs in T00/T01 so that no two tasks ever create the same file.

## Contracts (summary; the code in `backend/contracts/` is authoritative)

- `base.py`: the `Model` base class (unknown fields are errors) and the **coordinate frames** for parts
  and the enclosure (origin at the front-left-bottom corner, mm). Read it before touching geometry.
- `spec.py`: `ProjectSpec` (has `rev: int`), `PartInstance` (with `i2c_address` for I2C parts),
  `Connection`, `EnclosureSpec`, `FirmwareSpec`, `UserContext` (`owned`: part id -> quantity),
  `Placement`, `Layout` (the mcu gets a placement too). Refs are lowercase letters and digits (they
  become `PIN_<REF>_<PIN>`).
- `parts.py`: `PartDef` (pins with MCU-side types, `i2c_address_pin`, `mounting: inside | external`,
  features, Wokwi mapping), `BoardDef` (adds `reserved_pins`, `input_only_pins`, `strapping_pins`,
  `adc1_pins`, `adc2_pins`, `pio_board`, `power_budget_ma`), `PartLibrary` with `load_library()`,
  `get()`, `pin_type(part_id, pin)`.
- `results.py`: `ToolError(code, message, field=None, hint=None, severity="error")` and
  `ToolResult(ok, errors, artifacts, data, log)`. **Every tool returns a `ToolResult`; tools never raise
  for expected failures.** Error messages are read by an LLM, so make them specific and actionable
  ("GPIO34 is input-only but drives buzzer1.SIG; free output pins: GPIO4, GPIO16, GPIO17").
  `artifacts` holds absolute paths. Error codes `not_implemented` and `skipped` mean the stage didn't
  run (`result.skipped`): emit it as `skipped`, never retry it. Each tool lists its own codes in its
  module docstring; consumers never branch on a specific code.
- `events.py`: `Event(run_id, seq, ts, stage, status, message, spec_rev, artifacts, errors, data)`.
  Stages: `plan, validate, layout, enclosure, assembly, firmware, wiring, simulate, bom, checks, done`.
  Statuses: `queued, running, passed, failed, stale, skipped, waiting` (`waiting` = a question for the
  user). `data` carries `todos` (list of `Todo`), `question` (`Question`) and `attempt`.
- `artifacts.py`: shapes of the shared run files: `RunManifest` (`manifest.json`), `Wiring`, `Bom`,
  `EnclosureManifest` (`cad/manifest.json`).
- `runner.py`: **who runs what** (read its docstring), the run directory layout, `RunRequest`,
  `EditRequest`, `AnswerRequest`, `Emit` (sync, thread-safe), the async `Runner` protocol (`run`, `edit`,
  `answer`: model work only) and `StageRunner` (T14's `run_stages`, the only code that executes
  stages; the engine passes it to the runner, so T13 never imports `backend/runtime/`).
- `tools.py`: the signatures of every tool function (`Protocol`s) and the `ToolBox` that bundles them,
  so the agent and API can swap stubs, fakes and real tools. Tools that make files take an `out_dir`.
- `hardware.py`: `load_hardware()` reads `handoff/HARDWARE.md` (mode, printer, whether to simulate).

## Commands

| Command | What it does |
| --- | --- |
| `make setup` | `uv sync` + `npm ci` in `frontend/` + PlatformIO (`uv tool install platformio`, if `pio` is missing) |
| `make test` | Fast unit + contract tests (must pass before every PR) |
| `make test-slow` | Adds PlatformIO compiles and CAD builds |
| `make test-live` | Calls real APIs (needs `.env`; costs money: run sparingly) |
| `make lint` | `ruff check`, `ruff format --check`, `tsc -b` (type check), `oxlint` |
| `make types` | Regenerates `frontend/src/contracts/` from the Pydantic models (Integrator only) |
| `make dev` | API on `$API_PORT` and web on `$WEB_PORT` from `.env.worktree` |
| `P2D_RUNNER=fake make dev` | API replays a recorded run (no model calls): for frontend work |

Ports differ per worktree so several dev servers can run at once. The web dev server proxies `/api/*` to the
API with the prefix stripped: the UI fetches `/api/runs/...`, the API serves `/runs/...`.

## Code conventions

- Python 3.12+, `uv`, Pydantic v2, type hints everywhere, `ruff` defaults. Pure functions where possible:
  tools take models and paths, return `ToolResult`, and write files only inside the given `out_dir`.
- Deterministic output: same spec in, same files out (sort keys, no timestamps inside generated files).
- Frontend: Vite + React + TypeScript strict, `@react-three/fiber` for 3D, `vitest` for tests.
  Import types only from `src/contracts/`.
- Model name comes from `P2D_MODEL`; never hard-code it.
- Generated firmware must `#include "pins.h"`, use only `PIN_*` macros for pin numbers, and print
  `P2D_READY` on serial at the end of `setup()` (the T12 lint enforces both; the simulator waits for it).

## Hardware may not be available

We may have no parts or no 3D printer at the event (`handoff/HARDWARE.md`, section 0 of the build plan).
Never make a test or acceptance criterion depend on physical hardware. Until `HARDWARE.md` is filled in,
assume mode V: datasheet dimensions, the `generic` printer profile, simulation available.

## Git and PRs

- Branch: `feat/<TASK>-<slug>` (already created by `scripts/setup_worktrees.sh`). Small commits, conventional messages.
- Before opening a PR: `git fetch` (if remote) and `git rebase main`, then `make lint test` (and `make test-slow` if your card says so).
- PR description: what changed, how to test, which contract items you rely on, anything you stubbed, open requests.
- When `main` gets a merge you depend on, rebase at your next stopping point. Worktrees share refs, so
  `git rebase main` sees merges immediately; no fetch needed for local branches.

## Status file format (`handoff/status/<TASK>.md`)

Your task's *state* lives on the board, not here. This file is for notes a teammate or reviewer needs.

```
# <TASK> <title>
Updated: <hour of hackathon or time>
Plan:
- ...
Done:
- ...
Next:
- ...
Requests: <contract requests you filed with board.py request>
How to test: <exact commands>
```

## Definition of done (every task)

- Acceptance criteria on the card all met, each covered by a test where the card says so.
- `make lint test` green after rebasing on `main`; slow tests green if the card lists them.
- No edits outside owned paths; no contract edits.
- Status file has exact test commands; `board.py submit` accepted the branch.
- The board shows the review approved and every consumer signed off at your latest commit.

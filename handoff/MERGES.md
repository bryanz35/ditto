# Merges to main

The Integrator appends one line per merge or contract change. Builders: rebase on `main` when a task
you depend on appears here.

| Hour | Commit | Task | Note |
| --- | --- | --- | --- |
| 1 | 05cd429 | T00 | Repo scaffold: uv project, Makefile, frontend skeleton, empty packages, CI |
| 2 | 4e5ce65 | T01 | Contracts, stubs, fixtures; G0 review fixes (StageRunner, i2c_address, owned qty, edit fixture). Contracts frozen at CONTRACT_VERSION 1 |
| 2 | baaed0c | T13 | AgentRunner (run/edit/answer), orchestrator + 3 sub-agents, tool wrappers with code-enforced 3-retry limit; deepagents 0.7.38. Live smoke pending T10 + keys |
| 6 | 1cbf4b6 | T14 | API (FastAPI runs/files), run engine with `run_stages`, deps, replay runner. Contract tests on Windows still fail only on symlinked fixtures (pre-existing) |
| 6 | dc91bcf | T11 | Layout, build123d enclosure (base/lid STEP+STL, cad/manifest.json), check_enclosure (watertight, fits printer). First slow run after uv sync failed once in _build (cold build123d import?); 3 reruns green - QA watch for flakiness |
| 6 | 351542d | T10 | validate_spec: ref/pin/type checks, input-only, strapping, ADC2-vs-WiFi, I2C address clashes, power budget; invalid fixtures each fail with their code |
| 6 | 1f0810e | T16 | price_bom (Nexar live -> prices.json cache -> manual price; owned parts free; over_budget/price_missing), prefetch_prices script, memory store + /memory router |
| 6 | 07ed525 | CR#1 | Integrator applied T18's request to T16's test_prefetch (library pinned to esp32_devkitc). Test-only, no contract change, CONTRACT_VERSION unchanged |
| 6 | cf64363 | T12 | pins.h, PlatformIO project generation, lint (pins.h include, P2D_READY, no numeric pins), compile with parsed file:line:col errors. Golden compile verified by B-fw; on the Integrator machine Smart App Control blocks pio.exe (WinError 4551). Follow-up for B-fw (T23): compile_firmware raises OSError when pio can't be executed; should return a ToolResult error |
| 6 | 205ea2e | T15 | Frontend shell: Vite + React app, run state from events, typed against src/contracts |
| 6 | 0915335 | T19 | QA suite: integration pipeline (xfail per pending task), invariant helpers (pins.h/cutouts/BOM/spec_rev), e2e plant monitor + edits (live), evals skeleton. test_write_firmware_project_and_lint now XPASSes (T12 merged) |
| 6 | f6a252a | CR#2 | pillow>=13 direct dep; P2D_TRANSCRIBE, P2D_TRANSCRIBE_MODEL, OPENAI_API_KEY in .env.example (T17). No contract change |
| 6 | 3ecbd87 | T01 | Run fixture spec.json/events.jsonl are real copies, not symlinks (Windows); test_run_fixture_copies_match_their_sources keeps them in sync. Content unchanged, CONTRACT_VERSION unchanged |
| 6 | 4f97b28 | CR#3 | Invariant helpers moved to backend/contracts/invariants.py (tests/integration/invariants.py re-exports). CONTRACT_VERSION 2. T21 switches its import; Q may switch to the new path |
| 6 | b58c7f8 | T25 | Assembly preview: build_assembly writes cad/assembly.glb (enclosure + placed parts from the layout) |
| 6 | bfdc238 | T17 | preprocess_input: images upright/flattened/capped at 1568 px; video -> up to 8 ffmpeg keyframes + transcript (P2D_TRANSCRIBE whisper/openai/off). Slow video test needs ffmpeg (not on the Integrator machine; follow-up: skip when ffmpeg is missing; ffmpeg is a system dependency make setup doesn't install) |
| 6 | 2ab6ce1 | T18 | Parts library expanded to 19 parts (MPNs for pricing, snippets); prefetch test fixed via CR#1 |
| 6 | b76fa7b | T21 | cross_checks over a run dir (pins.h vs connections, cutouts, placements in cavity, BOM vs parts, stale spec_rev). Still imports tests.integration.invariants (works via the CR#3 re-export); T21 follow-up: import backend.contracts.invariants |
| 8 | 12d380a | T23 | Every library snippet linted and compiled on esp32_devkitc (tests/unit/firmware/test_snippets.py, slow) |
| 8 | d6452c7 | T21 | Follow-up: cross_checks imports backend.contracts.invariants (CR#3), no longer tests.integration |
| 9 | 0e1b1bf | T26 | Simulation: build_simulation writes Wokwi diagram.json from spec + layout and runs wokwi-cli (waits for P2D_READY); live run passed |
| 9 | 684793e | T22 | Edit flow: edits rerun only affected stages (deps.py), every affected stage marked stale first |

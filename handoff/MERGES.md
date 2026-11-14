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

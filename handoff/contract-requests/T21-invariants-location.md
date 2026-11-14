# T21: move Q's invariant helpers from tests/ to a backend module
What: move `tests/integration/invariants.py` to `backend/contracts/invariants.py` (or another backend
path the Integrator picks), leaving `tests/integration/invariants.py` as `from backend.contracts.invariants import *`
so Q's tests and evals keep working unchanged.
Why: `backend/tools/cross_checks.py` (production code, run in every `checks` stage) reuses these helpers
instead of duplicating them, so the backend now imports from `tests/`. That works from the repo root
but ties the running app to the test folder, and goes against golden rule 4 (cross-area imports only
through `backend/contracts/` and tools' public functions).
Affects: T19/T30 (Q: one import line), T21 (one import line in cross_checks.py). No behaviour change.
Workaround until decided: cross_checks.py imports `tests.integration.invariants`, marked with a
`shortcut:` comment.

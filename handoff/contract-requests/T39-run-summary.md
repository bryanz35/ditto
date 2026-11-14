# T39: add `RunSummary`, the item model of GET /runs
What: add to `backend/contracts/runner.py`, and add it to `MODELS` in `backend/contracts/export_types.py`:
```python
class RunSummary(Model):
    """One item of GET /runs (newest first by ts)."""

    run_id: str
    title: str = ""
    """spec.title; "" until the runner saves spec.json."""
    stage: Stage
    """The latest event's stage."""
    status: Status
    """The latest event's status."""
    ts: float
    """The latest event's ts."""
    spec_rev: int
```
No new event status: a cancelled run ends with stage `done`, status `failed`, message
"Cancelled by the user" (POST /runs/{id}/cancel).
Why: Recent projects (B-web) needs a typed list of runs that works across browsers; `make types`
only exports models listed in the contracts.
Affects: T39 (GET /runs response model), T40/B-web (Recent projects, Stop button). No change to existing models.
Workaround until decided: the same model is defined in `backend/runtime/runs.py`; switched to the
contract import once it lands.

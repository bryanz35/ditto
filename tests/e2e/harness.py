"""Drive the real API in-process: start a run or an edit and read its events until `done`.

Shared by the e2e tests and evals/run_evals.py. Uses only documented surface: POST /runs (form fields
prompt and user_context), POST /runs/{id}/edit (EditRequest), GET /runs/{id}/spec, and
runs/<id>/events.jsonl (backend/contracts/runner.py). Events are read from the file rather than SSE
because httpx's in-process transport buffers streaming responses.
"""

import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from backend.contracts.events import Event
from backend.contracts.runner import EditRequest, run_dir_for
from backend.contracts.spec import ProjectSpec, UserContext

TIMEOUT_S = float(os.environ.get("P2D_E2E_TIMEOUT_S", "900"))


@asynccontextmanager
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    """The app with whatever P2D_RUNNER and P2D_RUNS_DIR are set (the e2e conftest sets both)."""
    from backend.app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://p2d", timeout=TIMEOUT_S
    ) as client:
        yield client


async def start_run(
    client: httpx.AsyncClient, prompt: str, user: UserContext | None = None
) -> str:
    form = {"prompt": prompt, "user_context": (user or UserContext()).model_dump_json()}
    response = await client.post("/runs", data=form)
    response.raise_for_status()
    return response.json()["run_id"]


async def start_edit(client: httpx.AsyncClient, run_id: str, instruction: str) -> None:
    body = EditRequest(instruction=instruction).model_dump()
    response = await client.post(f"/runs/{run_id}/edit", json=body)
    response.raise_for_status()


def read_events(run_id: str) -> list[Event]:
    """Complete lines of events.jsonl (a line still being written is left for the next read)."""
    path = run_dir_for(run_id) / "events.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().split("\n")[:-1]
    return [Event.model_validate_json(line) for line in lines if line.strip()]


async def wait_for_done(
    run_id: str, after_seq: int = 0, timeout_s: float = TIMEOUT_S
) -> list[Event]:
    """Every event of the run, once a `done` event newer than after_seq is recorded."""
    deadline = time.monotonic() + timeout_s
    while True:
        events = read_events(run_id)
        if any(e.stage == "done" and e.seq > after_seq for e in events):
            return events
        if time.monotonic() > deadline:
            last = events[-1] if events else None
            raise TimeoutError(
                f"run {run_id}: no done event after seq {after_seq} in {timeout_s:.0f} s; last event: {last}"
            )
        await asyncio.sleep(1)


def saved_spec(run_id: str) -> ProjectSpec:
    return ProjectSpec.model_validate_json(
        (run_dir_for(run_id) / "spec.json").read_text()
    )

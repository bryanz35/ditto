"""Runs API: list runs, start one, stream its events (SSE), edit it, answer its questions, ask about
the build, cancel it."""

import asyncio
import uuid
from functools import cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import ValidationError
from sse_starlette import EventSourceResponse

from backend.app.routers.files import existing_run_dir
from backend.contracts.runner import (
    AnswerRequest,
    AskReply,
    AskRequest,
    EditRequest,
    RunRequest,
    RunSummary,
    run_dir_for,
)
from backend.contracts.spec import UserContext
from backend.runtime.runs import (
    RunEngine,
    engine_from_env,
    list_runs,
    read_events,
)

router = APIRouter()


@cache
def get_engine() -> RunEngine:
    return engine_from_env()


Engine = Annotated[RunEngine, Depends(get_engine)]


@router.get("/runs")
def get_runs() -> list[RunSummary]:
    """Every run with events, newest first, read from the run directories."""
    return list_runs()


@router.post("/runs")
async def create_run(
    engine: Engine,
    prompt: Annotated[str, Form()],
    files: Annotated[list[UploadFile] | None, File()] = None,
    user_context: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    """Multipart: prompt, optional files, optional user_context (UserContext as JSON)."""
    try:
        user = UserContext.model_validate_json(user_context or "{}")
    except ValidationError as exc:
        raise HTTPException(422, f"user_context: {exc}") from exc
    run_id = uuid.uuid4().hex[:12]
    input_dir = run_dir_for(run_id) / "input"
    input_dir.mkdir(parents=True)
    saved = []
    for i, upload in enumerate(files or []):
        name = Path(upload.filename or "").name
        # index prefix: pasted images all arrive as image.png
        name = f"{i}-{name if name not in ('', '.', '..') else 'upload'}"
        (input_dir / name).write_bytes(await upload.read())
        saved.append(f"input/{name}")
    engine.start(RunRequest(run_id=run_id, prompt=prompt, files=saved, user=user))
    return {"run_id": run_id}


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    last_event_id: Annotated[int, Header(alias="Last-Event-ID")] = 0,
) -> EventSourceResponse:
    """SSE (id = seq). Resumes after Last-Event-ID and ends once the latest event is `done`; a
    client that reconnects after that waits for the next events (an edit)."""
    existing_run_dir(run_id)

    async def stream():
        after = last_event_id
        while True:
            # shortcut: polls events.jsonl every 0.2 s; use a per-run asyncio.Condition if latency matters
            events = read_events(run_id, after)
            for event in events:
                after = event.seq
                yield {"id": str(event.seq), "data": event.model_dump_json()}
            # close only at the latest done, so a fresh client after an edit gets the whole run
            if events and events[-1].stage == "done":
                return
            await asyncio.sleep(0.2)

    return EventSourceResponse(stream())


@router.post("/runs/{run_id}/edit", status_code=202)
async def edit_run(run_id: str, request: EditRequest, engine: Engine) -> dict[str, str]:
    existing_run_dir(run_id)
    if engine.busy(run_id):
        raise HTTPException(409, "The run is still working; edit after its done event")
    engine.edit(run_id, request)
    return {"run_id": run_id}


@router.post("/runs/{run_id}/answer")
async def answer_question(
    run_id: str, request: AnswerRequest, engine: Engine
) -> dict[str, bool]:
    existing_run_dir(run_id)
    await engine.runner.answer(run_id, request)
    return {"ok": True}


@router.post("/runs/{run_id}/ask")
async def ask_about_build(run_id: str, request: AskRequest, engine: Engine) -> AskReply:
    """A question from the build guide. Read-only, so it's fine while the run works."""
    if not (existing_run_dir(run_id) / "spec.json").is_file():
        raise HTTPException(409, "The run has no spec yet; ask once the plan is done")
    try:
        return AskReply(answer=await engine.runner.ask(run_id, request))
    except Exception as exc:  # the model failed for good (key, quota, overload)
        raise HTTPException(502, f"Ditto couldn't answer: {exc}") from exc


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(run_id: str, engine: Engine) -> dict[str, str]:
    """Stops the run; its stream ends with a failed `done` event ("Cancelled by the user")."""
    existing_run_dir(run_id)
    if not engine.busy(run_id):
        raise HTTPException(409, "The run isn't working; nothing to cancel")
    engine.cancel(run_id)
    return {"run_id": run_id}

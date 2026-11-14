"""Runs API (T14). Until T14 merges, this stub streams the fixture run for any run id so the frontend
has a live event stream to develop against."""

import asyncio
from pathlib import Path

from fastapi import APIRouter
from sse_starlette import EventSourceResponse

from backend.contracts.events import Event

router = APIRouter()
FIXTURE_EVENTS = (
    Path(__file__).resolve().parents[3] / "fixtures" / "events" / "plant_monitor.jsonl"
)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> EventSourceResponse:
    async def stream():
        for line in FIXTURE_EVENTS.read_text().splitlines():
            event = Event.model_validate_json(line)
            yield {"id": str(event.seq), "data": line}
            await asyncio.sleep(0.3)

    return EventSourceResponse(stream())

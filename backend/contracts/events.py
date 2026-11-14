"""Run events, streamed to the UI over SSE and stored one per line in runs/<id>/events.jsonl.

`data` conventions (keys are optional):
- "todos": list[Todo], the agent's current plan (on "plan" events).
- "question": Question, on events with status "waiting".
- "attempt": int, 1-based retry counter on validate/firmware/enclosure stages.
"""

from typing import Any, Literal, get_args

from backend.contracts.base import Model
from backend.contracts.results import ToolError

Stage = Literal[
    "plan",
    "validate",
    "layout",
    "enclosure",
    "assembly",
    "firmware",
    "wiring",
    "simulate",
    "bom",
    "checks",
    "done",
]
STAGES: tuple[str, ...] = get_args(Stage)

Status = Literal["queued", "running", "passed", "failed", "stale", "skipped", "waiting"]


class Todo(Model):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class Question(Model):
    id: str
    text: str
    options: list[str] = []
    """Suggested answers; the user may also type free text."""
    timeout_s: float | None = None
    """After this the agent states an assumption and continues."""


class Event(Model):
    run_id: str
    seq: int = 0
    """Set by the run engine when it records the event: 1, 2, 3... per run (the SSE id)."""
    ts: float = 0.0
    """Unix time in seconds, set by the run engine."""
    stage: Stage
    status: Status
    message: str = ""
    spec_rev: int = 0
    artifacts: dict[str, str] = {}
    """Artifact name -> path relative to the run directory."""
    errors: list[ToolError] = []
    data: dict[str, Any] = {}

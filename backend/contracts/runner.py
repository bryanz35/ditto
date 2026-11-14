"""How the API drives a run, so the agent runner, the replay runner and fakes are interchangeable.

Run directory (runs/<id>/, under $P2D_RUNS_DIR):
    spec.json        latest ProjectSpec (written by the runner's write_spec)
    events.jsonl     every Event, one per line (run engine)
    manifest.json    RunManifest (run engine)
    input/           uploads and preprocess_input output
    cad/             layout.json, base/lid .stl/.step, manifest.json (EnclosureManifest), assembly.glb
    firmware/        PlatformIO project: platformio.ini, include/pins.h, src/main.cpp
    sim/             diagram.json, wokwi.toml, serial.log, screenshot.png
    wiring.json      Wiring
    bom.json         Bom
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from backend.contracts.base import Model
from backend.contracts.events import Event
from backend.contracts.spec import ProjectSpec, UserContext

Emit = Callable[[Event], None]
"""Records and streams one event. The run engine sets seq and ts. Must be safe to call from any
thread, including tool code running in a worker thread."""


def runs_root() -> Path:
    return Path(os.environ.get("P2D_RUNS_DIR", "runs")).resolve()


def run_dir_for(run_id: str) -> Path:
    return runs_root() / run_id


class RunRequest(Model):
    run_id: str
    prompt: str
    files: list[str] = []
    """Uploaded files, relative to the run directory (input/...)."""
    user: UserContext = UserContext()


class EditRequest(Model):
    """Body of POST /runs/{id}/edit."""

    instruction: str
    """e.g. "add a buzzer", "make the walls 3 mm"."""


class AnswerRequest(Model):
    """Body of POST /runs/{id}/answer: the user's reply to a "waiting" event's question."""

    question_id: str
    answer: str


class Runner(Protocol):
    async def run(self, request: RunRequest, emit: Emit) -> ProjectSpec:
        """Design a device from scratch; ends with a "done" event."""
        ...

    async def edit(self, run_id: str, request: EditRequest, emit: Emit) -> ProjectSpec:
        """Patch the spec (rev + 1) and rerun only the affected stages, in the same thread of
        conversation as the original run."""
        ...

    async def answer(self, run_id: str, request: AnswerRequest) -> None:
        """Deliver an answer to a pending question; unknown or expired ids are ignored."""
        ...

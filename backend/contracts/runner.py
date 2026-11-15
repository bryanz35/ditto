"""How the API drives a run, so the agent runner, the replay runner and fakes are interchangeable.

Who does what (one owner per job):
- The Runner (T13's AgentRunner) does the model work only. run() writes a validated spec.json and
  firmware/src/main.cpp; edit() patches the spec (rev + 1, saved) and rewrites main.cpp only when
  firmware behaviours or parts changed. Its sub-agents check their work by calling the StageRunner
  they were given, so tool feedback and retries see real results.
- The StageRunner (T14's backend/runtime/stages.py: run_stages) is the only code that executes
  stages: it calls the ToolBox with each stage's out_dir and emits running/passed/failed/skipped
  events with run-relative artifact paths. The firmware stage uses the main.cpp already in the run
  directory and never calls the model.
- Runner.ask answers a build-guide question from the saved run files: read-only, no events.
- The run engine (T14; edits in T22) owns the pipeline. After runner.run() or runner.edit() returns,
  it emits `stale` for the stages the change affects (edits only), runs every stage that hasn't
  passed at the current spec rev through the StageRunner, then `checks`, then emits `done`.

Run directory (runs/<id>/, under $P2D_RUNS_DIR):
    spec.json        latest ProjectSpec (written by the runner)
    specs/<rev>.json every saved rev (the engine compares them to skip stages a change didn't affect)
    events.jsonl     every Event, one per line (run engine)
    manifest.json    RunManifest (run engine)
    input/           uploads and preprocess_input output
    cad/             layout.json, base/lid .stl/.step, manifest.json (EnclosureManifest), assembly.glb;
                     for template "custom" also model.py and one .stl/.step per printed part
    firmware/        PlatformIO project: platformio.ini, include/pins.h, src/main.cpp
    sim/             diagram.json, wokwi.toml, serial.log, screenshot.png
    wiring.json      Wiring
    bom.json         Bom
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field

from backend.contracts.base import Model
from backend.contracts.events import Event, Stage, Status
from backend.contracts.results import ToolResult
from backend.contracts.spec import ProjectSpec, UserContext

Emit = Callable[[Event], None]
"""Records and streams one event. The run engine sets seq and ts. Must be safe to call from any
thread, including tool code running in a worker thread."""


def runs_root() -> Path:
    return Path(os.environ.get("P2D_RUNS_DIR", "runs")).resolve()


def run_dir_for(run_id: str) -> Path:
    return runs_root() / run_id


def save_spec(path: Path, spec: ProjectSpec) -> None:
    """Write spec.json whole or not at all (readers in other threads, and a process killed
    mid-write, never see half a file), and keep a copy as specs/<rev>.json."""
    text = spec.model_dump_json(indent=2) + "\n"
    (path.parent / "specs").mkdir(parents=True, exist_ok=True)
    (path.parent / "specs" / f"{spec.rev}.json").write_text(text)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text)
    tmp.replace(path)


class StageRunner(Protocol):
    def __call__(
        self, run_id: str, stages: list[Stage], spec: ProjectSpec, emit: Emit
    ) -> dict[str, ToolResult]:
        """Run the given stages in pipeline order for this run's directory and return each stage's
        result. Blocking: call it with asyncio.to_thread from async code. The engine binds the
        ToolBox and the PartLibrary before handing it to a Runner."""
        ...


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


class ChatTurn(Model):
    role: Literal["user", "ditto"]
    text: str = Field(max_length=8000)


class AskRequest(Model):
    """Body of POST /runs/{id}/ask: a question about the build. Read-only: never changes the spec."""

    question: str = Field(min_length=1, max_length=2000)
    step: str = ""
    """The step the user is on, as the guide shows it (title, body, wires with colours)."""
    history: list[ChatTurn] = Field([], max_length=40)
    """Earlier turns of this chat, oldest first. The UI keeps them; the API is stateless."""


class AskReply(Model):
    """Reply of POST /runs/{id}/ask."""

    answer: str
    """Markdown."""


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


class NoSpec(Exception):
    """Raised by Runner.run when the agent ended without a validated spec on purpose (it asked
    something or said why in a "chat" event): the engine doesn't retry, the user's reply restarts it."""


class Runner(Protocol):
    async def run(self, request: RunRequest, emit: Emit) -> ProjectSpec:
        """Model work for a new run: write a validated spec.json and firmware/src/main.cpp.
        Doesn't emit "done"; the engine finishes the pipeline. Raises NoSpec when the agent ends
        without a spec."""
        ...

    async def edit(self, run_id: str, request: EditRequest, emit: Emit) -> ProjectSpec:
        """Patch the spec (rev + 1, saved) in the same conversation thread as the run, and rewrite
        main.cpp if firmware behaviours or parts changed. Doesn't run the other stages. Returns the
        unchanged spec when the agent only answered, or couldn't make the change (its reply says)."""
        ...

    async def answer(self, run_id: str, request: AnswerRequest) -> None:
        """Deliver an answer to a pending question; unknown or expired ids are ignored."""
        ...

    async def ask(self, run_id: str, request: AskRequest) -> str:
        """Answer a question about the build (markdown) from the run's saved files. Never writes
        files or emits events, so it's safe while the run works."""
        ...

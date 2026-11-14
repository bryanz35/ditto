"""The run engine: owns the pipeline (backend/contracts/runner.py) and records every event.

After runner.run() or runner.edit() returns, it runs every stage that hasn't passed at the current
spec rev through the StageRunner, then `checks`, then emits `done`. Events go to
runs/<id>/events.jsonl (seq and ts set here); passed artifacts go to runs/<id>/manifest.json.
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from backend.contracts.artifacts import ArtifactInfo, RunManifest
from backend.contracts.events import Event
from backend.contracts.parts import load_library
from backend.contracts.runner import (
    EditRequest,
    Emit,
    Runner,
    RunRequest,
    StageRunner,
    run_dir_for,
)
from backend.contracts.spec import ProjectSpec
from backend.runtime.deps import ORDER
from backend.runtime.replay_runner import ReplayRunner
from backend.runtime.stages import run_stages

log = logging.getLogger(__name__)
ModelWork = Callable[[Emit], Awaitable[ProjectSpec]]


def read_events(run_id: str, after: int = 0) -> list[Event]:
    path = run_dir_for(run_id) / "events.jsonl"
    if not path.is_file():
        return []
    events = (Event.model_validate_json(line) for line in path.read_text().splitlines())
    return [e for e in events if e.seq > after]


class RunEngine:
    def __init__(self, runner: Runner, stage_runner: StageRunner):
        self.runner, self.stage_runner = runner, stage_runner
        self._lock = threading.Lock()
        self._seq: dict[str, int] = {}
        self._passed: dict[
            tuple[str, str], int
        ] = {}  # (run_id, stage) -> rev it passed at
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, request: RunRequest) -> None:
        self._spawn(request.run_id, lambda emit: self.runner.run(request, emit))

    def edit(self, run_id: str, request: EditRequest) -> None:
        self._spawn(run_id, lambda emit: self.runner.edit(run_id, request, emit))

    def busy(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def emitter(self, run_id: str) -> Emit:
        return partial(self._emit, run_id)

    def _spawn(self, run_id: str, work: ModelWork) -> None:
        self._tasks[run_id] = asyncio.create_task(self._pipeline(run_id, work))

    async def _pipeline(self, run_id: str, work: ModelWork) -> None:
        emit = self.emitter(run_id)
        rev = 0
        try:
            spec = await work(emit)
            rev = spec.rev
            stages = [s for s in ORDER if self._passed.get((run_id, s)) != rev]
            results = await asyncio.to_thread(
                self.stage_runner, run_id, [*stages, "checks"], spec, emit
            )
            failed = [s for s, r in results.items() if not r.ok and not r.skipped]
            status, message = "passed", "Ready to build"
            if failed:
                status, message = (
                    "failed",
                    f"Finished with failures: {', '.join(failed)}",
                )
        except Exception as exc:
            log.exception("run %s failed", run_id)
            status, message = "failed", f"Run stopped: {exc!r}"
        emit(
            Event(
                run_id=run_id,
                stage="done",
                status=status,
                message=message,
                spec_rev=rev,
            )
        )

    def _emit(self, run_id: str, event: Event) -> None:
        run_dir = run_dir_for(run_id)
        with self._lock:
            if run_id not in self._seq:
                events = read_events(run_id)
                self._seq[run_id] = events[-1].seq if events else 0
            self._seq[run_id] += 1
            event = event.model_copy(
                update={"run_id": run_id, "seq": self._seq[run_id], "ts": time.time()}
            )
            run_dir.mkdir(parents=True, exist_ok=True)
            with (run_dir / "events.jsonl").open("a") as f:
                f.write(event.model_dump_json() + "\n")
            if event.status == "passed" and event.stage in ORDER:
                self._passed[(run_id, event.stage)] = event.spec_rev
            elif event.stage in ORDER:
                self._passed.pop((run_id, event.stage), None)
            _update_manifest(run_dir, event)


def _update_manifest(run_dir: Path, event: Event) -> None:
    path = run_dir / "manifest.json"
    manifest = (
        RunManifest.model_validate_json(path.read_text())
        if path.is_file()
        else RunManifest(spec_rev=0, artifacts={})
    )
    if event.spec_rev <= manifest.spec_rev and not (
        event.status == "passed" and event.artifacts
    ):
        return
    manifest.spec_rev = max(manifest.spec_rev, event.spec_rev)
    if event.status == "passed":
        for name, rel in event.artifacts.items():
            manifest.artifacts[name] = ArtifactInfo(
                path=rel, stage=event.stage, spec_rev=event.spec_rev
            )
    path.write_text(manifest.model_dump_json(indent=2) + "\n")


def engine_from_env() -> RunEngine:
    """P2D_RUNNER=fake (the fixture run), replay:<run_dir>, or real (the default: T13's agent)."""
    from backend.tools.fakes import fake_toolbox
    from backend.tools.toolbox import real_toolbox

    mode = os.environ.get("P2D_RUNNER", "real")
    lib = load_library()
    if mode == "fake" or mode.startswith("replay:"):
        source = Path(mode.removeprefix("replay:")) if mode != "fake" else None
        stage_runner = partial(run_stages, toolbox=fake_toolbox(), lib=lib)
        return RunEngine(ReplayRunner(source), stage_runner)
    if mode != "real":
        raise ValueError(f"P2D_RUNNER={mode!r}: use fake, replay:<run_dir> or real")
    try:
        from backend.agent import AgentRunner
    except ImportError as exc:
        raise RuntimeError(
            "P2D_RUNNER=real needs backend.agent.AgentRunner (T13); "
            "use P2D_RUNNER=fake until it merges"
        ) from exc
    toolbox = real_toolbox()
    stage_runner = partial(run_stages, toolbox=toolbox, lib=lib)
    return RunEngine(AgentRunner(toolbox, None, stage_runner, lib=lib), stage_runner)

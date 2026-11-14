"""The run engine: owns the pipeline (backend/contracts/runner.py) and records every event.

After runner.run() or runner.edit() returns, it runs every stage that hasn't passed at the current
spec rev through the StageRunner, then `checks`, then emits `done`. After an edit, only the stages the
changed spec fields affect (deps.stages_to_rerun) are marked `stale` and rerun; the others carry
their artifacts forward to the new rev. Events go to runs/<id>/events.jsonl (seq and ts set here);
passed artifacts go to runs/<id>/manifest.json. cancel() stops a run and ends it with a failed
`done` event; list_runs() summarises every run directory for GET /runs.
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from backend.contracts.artifacts import ArtifactInfo, RunManifest
from backend.contracts.base import Model
from backend.contracts.events import Event, Stage, Status
from backend.contracts.parts import load_library
from backend.contracts.runner import (
    EditRequest,
    Emit,
    Runner,
    RunRequest,
    StageRunner,
    run_dir_for,
    runs_root,
)
from backend.contracts.spec import ProjectSpec
from backend.runtime.deps import ORDER, changed_fields, stages_to_rerun
from backend.runtime.replay_runner import ReplayRunner
from backend.runtime.stages import run_stages

log = logging.getLogger(__name__)
ModelWork = Callable[[Emit], Awaitable[ProjectSpec]]
RUN_ID = re.compile(r"[A-Za-z0-9_-]+")
CANCELLED = "Cancelled by the user"


class RunCancelled(Exception):
    """Raised by a cancelled pipeline's emit, so a stage thread stops at its next event."""


# shortcut: until contract request T39-run-summary lands; then import it from contracts/runner.py
class RunSummary(Model):
    """One item of GET /runs (newest first by ts)."""

    run_id: str
    title: str = ""
    """spec.title; "" until the runner saves spec.json."""
    stage: Stage
    status: Status
    ts: float
    spec_rev: int


def read_events(run_id: str, after: int = 0) -> list[Event]:
    path = run_dir_for(run_id) / "events.jsonl"
    if not path.is_file():
        return []
    events = (Event.model_validate_json(line) for line in path.read_text().splitlines())
    return [e for e in events if e.seq > after]


def list_runs() -> list[RunSummary]:
    """Every run directory that has events, newest first (by its latest event)."""
    root = runs_root()
    runs = []
    for run_dir in root.iterdir() if root.is_dir() else []:
        if not RUN_ID.fullmatch(run_dir.name):
            continue
        # shortcut: reads each events.jsonl in full; read only the tail if runs pile up
        try:
            events = read_events(run_dir.name)
            spec = _saved_spec(run_dir) or {}
        except (OSError, ValueError):  # mid-write: skip it, don't fail the list
            continue
        if events:
            last = events[-1]
            runs.append(
                RunSummary(
                    run_id=run_dir.name,
                    title=spec.get("title", ""),
                    stage=last.stage,
                    status=last.status,
                    ts=last.ts,
                    spec_rev=last.spec_rev,
                )
            )
    return sorted(runs, key=lambda r: r.ts, reverse=True)


class RunEngine:
    def __init__(self, runner: Runner, stage_runner: StageRunner):
        self.runner, self.stage_runner = runner, stage_runner
        self._lock = threading.Lock()
        self._seq: dict[str, int] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._stops: dict[str, threading.Event] = {}

    def start(self, request: RunRequest) -> None:
        self._spawn(request.run_id, lambda emit: self.runner.run(request, emit))

    def edit(self, run_id: str, request: EditRequest) -> None:
        self._spawn(
            run_id, lambda emit: self.runner.edit(run_id, request, emit), edit=True
        )

    def busy(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def cancel(self, run_id: str) -> None:
        """Stop a busy run: its pipeline emits a failed `done` and its stage thread stops at its
        next event. shortcut: a tool call already under way (e.g. a compile) runs to its end."""
        self._stops[run_id].set()
        self._tasks[run_id].cancel()

    def emitter(self, run_id: str, stop: threading.Event | None = None) -> Emit:
        """stop: once set, emitting raises RunCancelled instead of recording the event."""
        return partial(self._emit, run_id, stop=stop)

    def _spawn(self, run_id: str, work: ModelWork, edit: bool = False) -> None:
        self._stops[run_id] = stop = threading.Event()
        self._tasks[run_id] = asyncio.create_task(
            self._pipeline(run_id, work, edit, stop)
        )

    async def _pipeline(
        self, run_id: str, work: ModelWork, edit: bool, stop: threading.Event
    ) -> None:
        emit = self.emitter(run_id, stop)
        run_dir = run_dir_for(run_id)
        rev = _saved_rev(run_dir)
        try:
            old = _saved_spec(run_dir) if edit else None
            spec = await work(emit)
            rev = spec.rev
            stages = self._stale_stages(run_id, old, spec, emit)
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
        except (asyncio.CancelledError, RunCancelled):
            status, message = "failed", CANCELLED
        except Exception as exc:
            log.exception("run %s failed", run_id)
            status, message = "failed", f"Run stopped: {exc!r}"
        self._emit(  # not `emit`: after a cancel only this event gets through
            run_id,
            Event(
                run_id=run_id,
                stage="done",
                status=status,
                message=message,
                spec_rev=rev,
            ),
        )

    def _stale_stages(
        self, run_id: str, old: dict | None, spec: ProjectSpec, emit: Emit
    ) -> list[str]:
        """The stages to run now. After an edit, emits `stale` for the affected ones (then their
        passed event again if runner.edit() already passed them at the new rev) and carries the
        unaffected settled ones forward to the new rev."""
        last = {e.stage: e for e in read_events(run_id) if e.stage in ORDER}
        passed = {s: e.spec_rev for s, e in last.items() if e.status == "passed"}
        if (
            old is None
        ):  # a new run (or one that never saved a spec): all must pass at this rev
            return [s for s in ORDER if passed.get(s) != spec.rev]
        changed = changed_fields(old, spec.model_dump(mode="json")) - {"rev"}
        # shortcut: a passed or skipped stage counts as current unless this edit affects it; a crash
        # between runner.edit() saving the spec and the stale events would leave it looking current
        settled = {s for s, e in last.items() if e.status in ("passed", "skipped")}
        # stages that didn't settle earlier rerun too, with everything downstream of them
        rerun = [
            s
            for s in stages_to_rerun(changed | (set(ORDER) - settled))
            if passed.get(s) != spec.rev  # runner.edit() may have rerun some already
        ]
        with self._lock:
            _carry_forward(
                run_dir_for(run_id), [s for s in ORDER if s not in rerun], spec.rev
            )
        affected = stages_to_rerun(changed)
        message = f"{', '.join(sorted(changed))} changed"
        for stage in affected:
            emit(
                Event(
                    run_id=run_id,
                    stage=stage,
                    status="stale",
                    message=message,
                    spec_rev=spec.rev,
                )
            )
            if (
                stage not in rerun
            ):  # a sub-agent already passed it at this rev during the edit
                emit(
                    last[stage].model_copy(
                        update={"message": "Checked during the edit"}
                    )
                )
        return rerun

    def _emit(
        self, run_id: str, event: Event, stop: threading.Event | None = None
    ) -> None:
        run_dir = run_dir_for(run_id)
        with self._lock:
            # checked under the lock, so no event of a cancelled pipeline lands after its done
            if stop is not None and stop.is_set():
                raise RunCancelled(run_id)
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
            _update_manifest(run_dir, event)


def _update_manifest(run_dir: Path, event: Event) -> None:
    path = run_dir / "manifest.json"
    manifest = (
        RunManifest.model_validate_json(path.read_text())
        if path.is_file()
        else RunManifest(spec_rev=0, artifacts={})
    )
    # the saved spec's rev, not the event's: a draft checked at rev N+1 may never be saved
    rev = _saved_rev(run_dir, manifest.spec_rev)
    if rev == manifest.spec_rev and not (event.status == "passed" and event.artifacts):
        return
    manifest.spec_rev = rev
    if event.status == "passed":
        for name, rel in event.artifacts.items():
            manifest.artifacts[name] = ArtifactInfo(
                path=rel, stage=event.stage, spec_rev=event.spec_rev
            )
    path.write_text(manifest.model_dump_json(indent=2) + "\n")


def _carry_forward(run_dir: Path, stages: list[str], rev: int) -> None:
    """Restamp the artifacts of stages an edit didn't affect: their manifest entries and the
    top-level spec_rev of their JSON files (bom.json, wiring.json, cad/manifest.json)."""
    path = run_dir / "manifest.json"
    if not stages or not path.is_file():
        return
    manifest = RunManifest.model_validate_json(path.read_text())
    for info in manifest.artifacts.values():
        if info.stage not in stages or info.spec_rev == rev:
            continue
        info.spec_rev = rev
        file = run_dir / info.path
        if file.suffix == ".json" and file.is_file():
            content = json.loads(file.read_text())
            if isinstance(content, dict) and "spec_rev" in content:
                content["spec_rev"] = rev
                file.write_text(
                    json.dumps(content, indent=2, ensure_ascii=False) + "\n"
                )
    manifest.spec_rev = _saved_rev(run_dir, manifest.spec_rev)
    path.write_text(manifest.model_dump_json(indent=2) + "\n")


def _saved_spec(run_dir: Path) -> dict | None:
    """The saved spec as JSON; None if the run never saved one (an edit then reruns everything)."""
    path = run_dir / "spec.json"
    return json.loads(path.read_text()) if path.is_file() else None


def _saved_rev(run_dir: Path, default: int = 0) -> int:
    try:
        return json.loads((run_dir / "spec.json").read_text())["rev"]
    except (OSError, ValueError, KeyError):  # not written yet, or mid-write
        return default


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

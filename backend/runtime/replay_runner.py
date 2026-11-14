"""ReplayRunner: a Runner that replays a recorded run directory (the plant-monitor fixture by
default) with realistic delays, so the UI works with no model and no API keys (P2D_RUNNER=fake)."""

import asyncio
import shutil
from pathlib import Path

from backend.contracts.events import Event
from backend.contracts.runner import (
    AnswerRequest,
    EditRequest,
    Emit,
    RunRequest,
    run_dir_for,
)
from backend.contracts.spec import ProjectSpec

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
MAX_DELAY_S = 3.0


class ReplayRunner:
    def __init__(
        self,
        source: Path | None = None,
        events: Path | None = None,
        spec: Path | None = None,
        delay_scale: float = 1.0,
    ):
        """source: a run directory (its events.jsonl and spec.json unless given). With no source,
        the fixture run. delay_scale: 1 replays the recorded gaps (capped at 3 s), 0 is instant."""
        if source is None:
            source = FIXTURES / "runs" / "plant_monitor"
            events = events or FIXTURES / "events" / "plant_monitor.jsonl"
            spec = spec or FIXTURES / "specs" / "plant_monitor.json"
        self.source = Path(source)
        self.events = Path(events or self.source / "events.jsonl")
        self.spec = Path(spec or self.source / "spec.json")
        self.delay_scale = delay_scale

    async def run(self, request: RunRequest, emit: Emit) -> ProjectSpec:
        """Copy the recorded files, then re-emit the recorded events except checks and done
        (the engine runs those)."""
        run_dir = run_dir_for(request.run_id)
        skip = shutil.ignore_patterns("events.jsonl", "manifest.json", "input")
        shutil.copytree(self.source, run_dir, ignore=skip, dirs_exist_ok=True)
        spec = ProjectSpec.model_validate_json(self.spec.read_text())
        _save(run_dir, spec)
        prev_ts = None
        for line in self.events.read_text().splitlines():
            event = Event.model_validate_json(line)
            if event.stage in ("checks", "done"):
                continue
            if prev_ts is not None:
                gap = max(event.ts - prev_ts, 0) * self.delay_scale
                await asyncio.sleep(min(gap, MAX_DELAY_S))
            prev_ts = event.ts
            emit(event.model_copy(update={"run_id": request.run_id}))
        return spec

    async def edit(self, run_id: str, request: EditRequest, emit: Emit) -> ProjectSpec:
        """No model: whatever the instruction, toggle the walls between 2 and 3 mm (the recorded
        fixture edit), bump rev and save, so the engine reruns the enclosure stages with the fake tools."""
        run_dir = run_dir_for(run_id)
        spec = ProjectSpec.model_validate_json((run_dir / "spec.json").read_text())
        emit(
            Event(
                run_id=run_id,
                stage="plan",
                status="running",
                message=f"Edit: {request.instruction}",
                spec_rev=spec.rev,
            )
        )
        old_wall = spec.enclosure.wall_mm
        wall = 3.0 if old_wall != 3.0 else 2.0
        enclosure = spec.enclosure.model_copy(update={"wall_mm": wall})
        spec = spec.model_copy(update={"rev": spec.rev + 1, "enclosure": enclosure})
        _save(run_dir, spec)
        emit(
            Event(
                run_id=run_id,
                stage="plan",
                status="passed",
                message=f"Spec rev {spec.rev}: enclosure.wall_mm {old_wall} -> {wall} (replay)",
                spec_rev=spec.rev,
                artifacts={"spec": "spec.json"},
            )
        )
        return spec

    async def answer(self, run_id: str, request: AnswerRequest) -> None:
        """Recorded runs don't wait for answers."""


def _save(run_dir: Path, spec: ProjectSpec) -> None:
    (run_dir / "spec.json").write_text(spec.model_dump_json(indent=2) + "\n")

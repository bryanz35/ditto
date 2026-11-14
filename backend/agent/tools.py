"""Agent tools: thin wrappers that let the model act only through checked code.

Real artifacts reach the run directory only through these: spec.json is saved after the validate
stage passes, enclosure changes after layout and enclosure pass. Every stage tool shares one retry
guard: after MAX_FAILURES failures in a row (1 try + 3 retries) it refuses without running the stage.
Stage events come from the StageRunner; the guard only adds data.attempt to them.
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from backend.contracts.events import Event, Stage
from backend.contracts.parts import BoardDef, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.runner import Emit, StageRunner, run_dir_for
from backend.contracts.spec import EnclosureSpec, ProjectSpec, UserContext

MAX_FAILURES = 4
"""1 try + 3 retries, enforced here rather than in the prompt."""


@dataclass
class RunContext:
    """What the tools of one run() or edit() call share."""

    run_id: str
    emit: Emit
    run_stages: StageRunner
    lib: PartLibrary
    prompt: str
    user: UserContext | None = None
    """Forced onto every spec written in run(); None in edit() so the model may change it."""
    failures: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    """Serialises spec writes (firmware and enclosure sub-agents run in parallel)."""

    @property
    def spec_path(self) -> Path:
        return run_dir_for(self.run_id) / "spec.json"

    def load_spec(self) -> ProjectSpec | None:
        p = self.spec_path
        return ProjectSpec.model_validate_json(p.read_text()) if p.exists() else None

    def save_spec(self, spec: ProjectSpec) -> None:
        self.spec_path.parent.mkdir(parents=True, exist_ok=True)
        self.spec_path.write_text(spec.model_dump_json(indent=2) + "\n")

    def next_rev(self) -> int:
        saved = self.load_spec()
        return saved.rev + 1 if saved else 1


def _limit(key: str) -> str:
    return (
        f"Retry limit reached: {key} failed {MAX_FAILURES} times. Don't call this tool again; "
        "call request_change or report the failure in your final answer."
    )


def _report(results: dict[str, ToolResult]) -> str:
    """What the model reads back: per stage, ok + errors + the log tail."""
    return json.dumps(
        {
            stage: r.model_dump(mode="json", include={"ok", "errors", "log"})
            for stage, r in results.items()
        }
    )


def guarded(
    ctx: RunContext,
    key: str,
    stages: list[Stage],
    spec: ProjectSpec,
    on_pass: Callable[[], None] = lambda: None,
) -> str:
    """Run stages through the StageRunner under the retry limit for `key`."""
    attempt = ctx.failures.get(key, 0) + 1
    if attempt > MAX_FAILURES:
        return _limit(key)

    def emit(e: Event) -> None:
        ctx.emit(e.model_copy(update={"data": {**e.data, "attempt": attempt}}))

    results = ctx.run_stages(ctx.run_id, stages, spec, emit)
    if any(not r.ok and not r.skipped for r in results.values()):
        ctx.failures[key] = attempt
        left = MAX_FAILURES - attempt
        return f"FAILED (attempt {attempt}, {left} retries left). Fix these and try again: {_report(results)}"
    ctx.failures[key] = 0
    on_pass()
    return f"PASSED: {_report(results)}"


def _schema_failure(ctx: RunContext, key: str, stage: Stage, err: Exception) -> str:
    """A draft that isn't even a valid model counts as a failed attempt of its stage."""
    attempt = ctx.failures.get(key, 0) + 1
    if attempt > MAX_FAILURES:
        return _limit(key)
    ctx.failures[key] = attempt
    error = ToolError(code="schema", message=str(err))
    ctx.emit(
        Event(
            run_id=ctx.run_id,
            stage=stage,
            status="failed",
            message="The draft doesn't match the schema",
            errors=[error],
            data={"attempt": attempt},
        )
    )
    return f"FAILED (attempt {attempt}, {MAX_FAILURES - attempt} retries left): {err}"


_PART_FIELDS = {"id", "name", "category", "pins", "logic_voltage", "supply_voltage"}
_PART_FIELDS |= {"max_current_ma", "i2c_addresses", "i2c_address_pin", "mounting"}
_PART_FIELDS |= {"manual_price_usd", "owned_alternatives", "board_mm"}
_BOARD_FIELDS = {"reserved_pins", "input_only_pins", "strapping_pins", "adc1_pins"}
_BOARD_FIELDS |= {"adc2_pins", "power_budget_ma"}


def make_tools(ctx: RunContext) -> dict[str, BaseTool]:
    @tool
    def search_parts(query: str = "") -> str:
        """List library parts whose id, name or category contains `query` (empty = all), with
        their pins and electrical facts. Only these part ids are allowed in a spec."""
        q = query.lower()
        hits = [
            p.model_dump(
                mode="json",
                include=_PART_FIELDS
                | (_BOARD_FIELDS if isinstance(p, BoardDef) else set()),
            )
            for p in ctx.lib.parts.values()
            if q in f"{p.id} {p.name} {p.category}".lower()
        ]
        return (
            json.dumps(hits)
            if hits
            else f"No part matches {query!r}; try an empty query."
        )

    @tool
    def write_spec(spec_json: str) -> str:
        """Save the full project spec (ProjectSpec JSON). Code checks it (pins, voltages, I2C,
        power) and saves it only if it passes; otherwise you get the errors to fix."""
        with ctx.lock:
            try:
                draft = ProjectSpec.model_validate_json(spec_json)
            except ValidationError as e:
                return _schema_failure(ctx, "validate", "validate", e)
            spec = draft.model_copy(
                update={
                    "rev": ctx.next_rev(),
                    "prompt": ctx.prompt,
                    "user": ctx.user or draft.user,
                }
            )
            return guarded(
                ctx, "validate", ["validate"], spec, lambda: ctx.save_spec(spec)
            )

    @tool
    def write_firmware(main_cpp: str, behaviors: list[str] | None = None) -> str:
        """Save src/main.cpp for the saved spec, then generate pins.h, lint and compile it.
        Pass `behaviors` only when the user changed what the device does: it replaces the
        spec's firmware.behaviors (saved if the firmware compiles)."""
        spec = ctx.load_spec()
        if spec is None:
            return (
                "No validated spec yet: the parts-and-pins agent must save one first."
            )
        main = run_dir_for(ctx.run_id) / "firmware/src/main.cpp"
        main.parent.mkdir(parents=True, exist_ok=True)
        main.write_text(main_cpp)
        if behaviors is None or behaviors == spec.firmware.behaviors:
            # No lock: the compile runs in parallel with the enclosure build.
            return guarded(ctx, "firmware", ["firmware"], spec)
        with ctx.lock:
            spec = ctx.load_spec() or spec
            firmware = spec.firmware.model_copy(update={"behaviors": behaviors})
            spec = spec.model_copy(update={"rev": spec.rev + 1, "firmware": firmware})
            return guarded(
                ctx, "firmware", ["firmware"], spec, lambda: ctx.save_spec(spec)
            )

    @tool
    def set_enclosure(
        wall_mm: float = 2.0, clearance_mm: float = 1.0, extras: list[str] | None = None
    ) -> str:
        """Set the enclosure parameters, then compute the layout and build and check the case.
        Saved only if it builds. Geometry comes from the parts library and the template."""
        with ctx.lock:
            spec = ctx.load_spec()
            if spec is None:
                return "No validated spec yet: the parts-and-pins agent must save one first."
            try:
                enclosure = EnclosureSpec(
                    wall_mm=wall_mm, clearance_mm=clearance_mm, extras=extras or []
                )
            except ValidationError as e:
                return _schema_failure(ctx, "enclosure", "enclosure", e)
            spec = spec.model_copy(update={"rev": spec.rev + 1, "enclosure": enclosure})
            return guarded(
                ctx,
                "enclosure",
                ["layout", "enclosure"],
                spec,
                lambda: ctx.save_spec(spec),
            )

    @tool
    def price_bom() -> str:
        """Price the saved spec's parts list (owned parts are free) and compare it to the budget."""
        spec = ctx.load_spec()
        if spec is None:
            return "No validated spec yet."
        return guarded(ctx, "bom", ["bom"], spec)

    @tool
    def request_change(field: str, reason: str, options: list[str]) -> str:
        """Ask for a change outside your own section of the spec (e.g. a different pin or part).
        Don't make the change yourself."""
        return (
            f"Change request for {field!r} recorded. Stop now and end your final answer with: "
            f"CHANGE REQUEST {field}: {reason}. Options: {'; '.join(options)}"
        )

    @tool
    def ask_user(
        question: str, options: list[str], stage: Literal["plan", "bom"] = "plan"
    ) -> str:
        """Ask the user one short question (at most two per run; "bom" to approve an
        over-budget parts list). If nobody answers in time you'll be told to assume."""
        return (
            "No answer: state your assumption in the spec's assumptions and continue."
        )

    tools = [
        search_parts,
        write_spec,
        write_firmware,
        set_enclosure,
        price_bom,
        request_change,
        ask_user,
    ]
    return {t.name: t for t in tools}

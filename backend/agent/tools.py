"""Agent tools: thin wrappers that let the model act only through checked code.

Real artifacts reach the run directory only through these: spec.json is saved after the validate
stage passes, enclosure changes (parameters, or model-written build123d code) after layout and
enclosure pass. Every stage tool shares one retry
guard: after MAX_FAILURES failures in a row (1 try + 3 retries) it refuses without running the stage.
Stage events come from the StageRunner; the guard adds data.attempt to them, and holds a layout or
enclosure draft's passed events with files until the draft is saved (sent without files if it isn't).
"""

import json
import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from backend.contracts.events import Event, Stage
from backend.contracts.parts import PARTS_DIR, BoardDef, PartLibrary, pin_code
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.runner import Emit, StageRunner, run_dir_for, save_spec
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
    kept_main: str | None = None
    """main.cpp to put back when a firmware draft fails: the code this turn started with, then the
    last draft that passed. None in a run's first turn: a failed draft stays for the model to fix."""

    def __post_init__(self) -> None:
        main = run_dir_for(self.run_id) / "firmware/src/main.cpp"
        self.kept_main = main.read_text() if main.is_file() else None

    @property
    def spec_path(self) -> Path:
        return run_dir_for(self.run_id) / "spec.json"

    def load_spec(self) -> ProjectSpec | None:
        p = self.spec_path
        return ProjectSpec.model_validate_json(p.read_text()) if p.exists() else None

    def save_spec(self, spec: ProjectSpec) -> None:
        save_spec(self.spec_path, spec)

    def pin_macros(self) -> str:
        """The board and the PIN_* macros pins.h defines for the saved spec (T12's rule: signal
        pins only, see pin_code)."""
        spec = self.load_spec()
        if spec is None or spec.mcu is None:
            return "No device spec is saved yet, so pins.h has no macros."
        macros = sorted(
            {
                f"- PIN_{c.part_ref.upper()}_{c.part_pin.upper()} ({c.mcu_pin})"
                for c in spec.connections
                if pin_code(c.mcu_pin)
            }
        )
        board = self.lib.parts.get(spec.mcu.part_id)
        about = ""
        if isinstance(board, BoardDef):
            about = (
                f"The board is {board.name} (PlatformIO platform {board.pio_platform}"
            )
            about += ")." if board.has_wifi else ", no Wi-Fi)."
            if board.bus_pins:
                about += (
                    " Its I2C and SPI pins are fixed: call Wire.begin() and SPI.begin() "
                    "without pin arguments."
                )
            about += "\n"
        return (
            about
            + "pins.h for the saved spec defines exactly these macros; use no others:\n"
            + ("\n".join(macros) or "(none)")
            + self._examples(spec)
        )

    def _examples(self, spec: ProjectSpec) -> str:
        """Each part's libraries and known-good snippet (compiled by T23), so the model starts
        from working library calls instead of guessing them."""
        lib = self.lib.with_parts(spec.custom_parts)
        out, seen = [], set()
        for inst in spec.parts:
            part = lib.parts.get(inst.part_id)
            if part is None or part.id in seen:
                continue
            seen.add(part.id)
            if part.pio_lib_deps:
                out.append(
                    f"{inst.ref} ({part.name}) libraries: {', '.join(part.pio_lib_deps)}"
                )
            snippet = PARTS_DIR / part.snippet if part.snippet else None
            if snippet and snippet.is_file():
                out.append(
                    f"Known-good example for {inst.ref} ({part.name}). Its macros use the "
                    "library's default ref: use the macro names listed above.\n"
                    f"```cpp\n{snippet.read_text().strip()}\n```"
                )
        return "".join(f"\n\n{o}" for o in out)

    def next_rev(self) -> int:
        saved = self.load_spec()
        return saved.rev + 1 if saved else 1


def _limit(key: str) -> str:
    return (
        f"Retry limit reached: {key} failed {MAX_FAILURES} times. Don't call this tool again; "
        "call request_change, or return your report with status failed and the errors."
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

    # layout and enclosure build into cad/ in place, then check: a draft that fails (or is
    # cancelled) after building must leave the saved spec's files there
    cad = run_dir_for(ctx.run_id) / "cad"
    draft = bool({"layout", "enclosure"} & set(stages))
    held: list[Event] = []

    def emit(e: Event) -> None:
        e = e.model_copy(update={"data": {**e.data, "attempt": attempt}})
        if draft and e.status == "passed" and e.artifacts:
            # its files are the draft's: announced only once the draft is saved
            held.append(e)
        elif draft and e.artifacts:
            # a failed draft's files are thrown away (cad/ is restored): don't point the UI at them
            ctx.emit(e.model_copy(update={"artifacts": {}}))
        else:
            ctx.emit(e)

    with tempfile.TemporaryDirectory() as tmp:
        saved = Path(tmp) / "cad"
        if draft and cad.is_dir():
            shutil.copytree(cad, saved)
        passed = False
        try:
            results = ctx.run_stages(ctx.run_id, stages, spec, emit)
            passed = not any(not r.ok and not r.skipped for r in results.values())
        finally:
            if draft and not passed:
                shutil.rmtree(cad, ignore_errors=True)
                if saved.is_dir():
                    shutil.copytree(saved, cad)
    if not passed:
        # the stage passed, but its files were thrown away with the draft
        for e in held:
            note = f"{e.message}; not kept, the rest of the draft failed"
            ctx.emit(e.model_copy(update={"artifacts": {}, "message": note}))
        ctx.failures[key] = attempt
        left = MAX_FAILURES - attempt
        return f"FAILED (attempt {attempt}, {left} retries left). Fix these and try again: {_report(results)}"
    ctx.failures[key] = 0
    on_pass()
    for e in held:
        ctx.emit(e)
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
_BOARD_FIELDS |= {"adc2_pins", "power_budget_ma", "has_wifi", "bus_pins"}


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
        if spec.firmware is None:
            return "This project has no electronics, so it has no firmware to write."
        if ctx.failures.get("firmware", 0) >= MAX_FAILURES:
            return _limit(
                "firmware"
            )  # before writing: main.cpp must stay the last checked code
        main = run_dir_for(ctx.run_id) / "firmware/src/main.cpp"
        main.parent.mkdir(parents=True, exist_ok=True)
        main.write_text(main_cpp)
        reply = ""
        try:
            if behaviors is None or behaviors == spec.firmware.behaviors:
                # No lock: the compile runs in parallel with the enclosure build.
                reply = guarded(ctx, "firmware", ["firmware"], spec)
            else:
                with ctx.lock:
                    spec = ctx.load_spec() or spec
                    firmware = spec.firmware.model_copy(update={"behaviors": behaviors})
                    spec = spec.model_copy(
                        update={"rev": spec.rev + 1, "firmware": firmware}
                    )
                    reply = guarded(
                        ctx, "firmware", ["firmware"], spec, lambda: ctx.save_spec(spec)
                    )
        finally:  # failed or cancelled: an edit's draft doesn't replace code that compiled
            if reply.startswith("PASSED"):
                ctx.kept_main = main_cpp
            elif ctx.kept_main is not None:
                main.write_text(ctx.kept_main)
        return reply

    @tool
    def set_enclosure(wall_mm: float = 2.0, clearance_mm: float = 1.0) -> str:
        """Use the plain box case for a device: set its parameters, then compute the layout and
        build and check the case. Saved only if it builds. Geometry comes from the parts library and
        the template, which has no extras (clips, mounts): only the walls and the clearance change.
        Replaces any custom shape from write_model."""
        with ctx.lock:
            spec = ctx.load_spec()
            if spec is None:
                return "No validated spec yet: the parts-and-pins agent must save one first."
            if spec.mcu is None:
                return (
                    "This project has no electronics, so there is no case to size: describe "
                    "its shape with write_model."
                )
            try:
                enclosure = EnclosureSpec(wall_mm=wall_mm, clearance_mm=clearance_mm)
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
    def write_model(code: str, wall_mm: float | None = None) -> str:
        """Save build123d Python for the printed parts, then build and check them (watertight, one
        piece each, fits the printer, flat on the bed). Saved only if every check passes.
        Print-only project: the code sets `parts = {"name": shape}`. Device: the code sets `body`,
        a shape built around the predefined BAY (the electronics' case) that code joins to the case,
        and/or `parts` for pieces printed separately (knob, arm link, clip), with `assembled` (where
        each goes) and `mounts` (external parts the printed parts hold, such as servos).
        wall_mm: the case wall thickness for a device (keeps the current one when omitted)."""
        with ctx.lock:
            spec = ctx.load_spec()
            if spec is None:
                return "No validated spec yet: the parts-and-pins agent must save one first."
            fields = spec.enclosure.model_dump()
            fields |= {"template": "custom", "code": code}
            if wall_mm is not None:
                fields["wall_mm"] = wall_mm
            try:
                enclosure = EnclosureSpec.model_validate(fields)
            except ValidationError as e:
                return _schema_failure(ctx, "enclosure", "enclosure", e)
            spec = spec.model_copy(update={"rev": spec.rev + 1, "enclosure": enclosure})
            stages: list[Stage] = ["layout", "enclosure"] if spec.mcu else ["enclosure"]
            return guarded(ctx, "enclosure", stages, spec, lambda: ctx.save_spec(spec))

    @tool
    def read_model() -> str:
        """Return the saved build123d code for the printed parts (the last version that passed),
        to edit it and send the full code back to write_model."""
        spec = ctx.load_spec()
        if spec is None:
            return (
                "No validated spec yet: the parts-and-pins agent must save one first."
            )
        if not spec.enclosure.code:  # the spec only allows code with template "custom"
            return "No saved model code: the case is the plain box. Start one with write_model."
        return spec.enclosure.code

    @tool
    def price_bom() -> str:
        """Price the saved spec's parts list (owned parts are free) and compare it to the budget."""
        spec = ctx.load_spec()
        if spec is None:
            return "No validated spec yet."
        if spec.mcu is None:
            return "This project has no electronics, so there are no parts to price."
        return guarded(ctx, "bom", ["bom"], spec)

    @tool
    def request_change(field: str, reason: str, options: list[str]) -> str:
        """Ask for a change outside your own section of the spec (e.g. a different pin or part).
        Don't make the change yourself."""
        return (
            f"Change request for {field!r} recorded. Stop now and return your report with status "
            f"change_request and change_request = {{field: {field!r}, reason: {reason!r}, "
            f"options: {options!r}}}."
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
        write_model,
        read_model,
        price_bom,
        request_change,
        ask_user,
    ]
    return {t.name: t for t in tools}

"""run_stages: the StageRunner (backend/contracts/runner.py), the only code that executes stages.
The engine binds toolbox, lib (and optionally hardware) with functools.partial.

Error codes this module adds to tool results:
- skipped: the stage didn't run (the hardware mode doesn't need it, or an input stage didn't pass).
- missing_main_cpp: the firmware stage found no firmware/src/main.cpp in the run directory.
- exception: a tool raised; the message names the stage and the exception.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from backend.contracts.events import Event, Stage
from backend.contracts.hardware import Hardware, load_hardware
from backend.contracts.parts import PartLibrary
from backend.contracts.results import SKIP_CODES, ToolError, ToolResult
from backend.contracts.runner import Emit, run_dir_for
from backend.contracts.spec import Layout, ProjectSpec
from backend.contracts.tools import ToolBox
from backend.runtime.deps import ORDER

PIPELINE = [*ORDER, "checks"]
SIM_TIMEOUT_MS = 15_000
log = logging.getLogger(__name__)


def run_stages(
    run_id: str,
    stages: list[Stage],
    spec: ProjectSpec,
    emit: Emit,
    *,
    toolbox: ToolBox,
    lib: PartLibrary,
    hardware: Hardware | None = None,
) -> dict[str, ToolResult]:
    hw = hardware or load_hardware()
    run_dir = run_dir_for(run_id)
    results: dict[str, ToolResult] = {}
    for stage in [s for s in PIPELINE if s in stages]:
        emit(Event(run_id=run_id, stage=stage, status="running", spec_rev=spec.rev))
        try:
            result = _run(stage, spec, toolbox, lib, hw, run_dir, results)
        except Exception as exc:
            log.exception("stage %s crashed", stage)
            result = _error("exception", f"{stage} crashed: {exc!r}")
        results[stage] = result
        emit(_finished(run_id, stage, spec, result, run_dir))
    return results


def _run(
    stage: str,
    spec: ProjectSpec,
    tb: ToolBox,
    lib: PartLibrary,
    hw: Hardware,
    run_dir: Path,
    done: dict[str, ToolResult],
) -> ToolResult:
    cad, fw, sim = run_dir / "cad", run_dir / "firmware", run_dir / "sim"
    if stage == "validate":
        return tb.validate_spec(spec, lib)
    if stage == "layout":
        return tb.compute_layout(spec, lib, cad)
    if stage in ("enclosure", "assembly"):
        layout_file = cad / "layout.json"
        if not _input_ok(done, "layout") or not layout_file.is_file():
            return _skip(f"{stage} needs a layout, and the layout stage didn't pass")
        layout = Layout.model_validate_json(layout_file.read_text())
        if stage == "assembly":
            return tb.build_assembly(spec, layout, lib, cad)
        printer = spec.user.printer or hw.printer_model
        return _chain(
            lambda: tb.build_enclosure(spec, layout, lib, cad),
            lambda: tb.check_enclosure(spec, layout, lib, cad, printer),
        )
    if stage == "firmware":
        main_cpp = fw / "src" / "main.cpp"
        if not main_cpp.is_file():
            return _error("missing_main_cpp", "firmware/src/main.cpp wasn't written")
        return _chain(
            lambda: tb.write_firmware_project(spec, lib, main_cpp.read_text(), fw),
            lambda: tb.lint_firmware(fw),
            lambda: tb.compile_firmware(fw),
        )
    if stage == "wiring":
        return tb.build_wiring(spec, lib, run_dir)
    if stage == "simulate":
        if not hw.simulate:
            return _skip(f"mode {hw.mode} doesn't simulate (handoff/HARDWARE.md)")
        if not _input_ok(done, "firmware") or not (fw / "platformio.ini").is_file():
            return _skip("simulate needs firmware, and the firmware stage didn't pass")
        return _chain(
            lambda: tb.build_simulation(spec, lib, fw, sim),
            lambda: tb.run_simulation(sim, SIM_TIMEOUT_MS, "P2D_READY"),
        )
    if stage == "bom":
        return tb.price_bom(spec, lib, None, run_dir)
    if stage == "checks":
        return tb.cross_checks(run_dir, spec, lib)
    raise ValueError(f"unknown stage {stage}")


def _input_ok(done: dict[str, ToolResult], stage: str) -> bool:
    """An input stage run in this call must have passed; otherwise its files are from earlier."""
    return stage not in done or done[stage].ok


def _chain(*steps: Callable[[], ToolResult]) -> ToolResult:
    """Run steps in order, stop at the first that doesn't pass, merge what they returned."""
    merged = ToolResult(ok=True)
    for step in steps:
        r = step()
        merged = ToolResult(
            ok=r.ok,
            errors=merged.errors + r.errors,
            artifacts={**merged.artifacts, **r.artifacts},
            data={**merged.data, **r.data},
            log=r.log or merged.log,
        )
        if not r.ok:
            break
    return merged


def _error(code: str, message: str) -> ToolResult:
    return ToolResult(ok=False, errors=[ToolError(code=code, message=message)])


def _skip(message: str) -> ToolResult:
    return _error("skipped", message)


def _finished(
    run_id: str, stage: str, spec: ProjectSpec, result: ToolResult, run_dir: Path
) -> Event:
    artifacts = {}
    for name, path in result.artifacts.items():
        p = Path(path).resolve()
        if p.is_relative_to(run_dir.resolve()):
            artifacts[name] = p.relative_to(run_dir.resolve()).as_posix()
    errors = [e for e in result.errors if e.severity == "error"]
    if result.skipped:
        status = "skipped"
        message = next(e.message for e in result.errors if e.code in SKIP_CODES)
    elif result.ok:
        status, message = "passed", f"{stage} passed"
        if stage == "validate":
            artifacts["spec"] = "spec.json"
    else:
        status = "failed"
        message = f"{len(errors)} error(s): {errors[0].message}" if errors else "failed"
    warnings = len(result.errors) - len(errors)
    if status == "passed" and warnings:
        message += f" with {warnings} warning(s)"
    return Event(
        run_id=run_id,
        stage=stage,
        status=status,
        message=message,
        spec_rev=spec.rev,
        artifacts=artifacts,
        errors=result.errors,
    )

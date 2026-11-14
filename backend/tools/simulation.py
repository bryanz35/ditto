"""Wokwi diagram generation and simulator run (T26).

build_simulation writes sim/diagram.json and sim/wokwi.toml from the spec; run_simulation runs
`wokwi-cli`, which uploads the compiled firmware to Wokwi's servers (needs WOKWI_CLI_TOKEN and
internet access).

Error codes:
- no_wokwi_part (warning): a part has no Wokwi model and is left out of the diagram (build).
- skipped: the board has no Wokwi model (build), or WOKWI_CLI_TOKEN or wokwi-cli is missing (run).
- firmware_missing: the firmware wokwi.toml points at hasn't been compiled (run).
- sim_timeout: the firmware never printed the expected text within the timeout (run).
- sim_error: wokwi-cli failed for another reason; the message carries its output (run).
"""

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from backend.contracts.parts import BoardDef, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import ProjectSpec

WIRE_COLORS = {"power": "red", "gnd": "black"}
TIMEOUT_EXIT_CODE = 42  # wokwi-cli's default --timeout-exit-code
# shortcut: only the display types our library uses; add a type when a library display gets one
DISPLAY_TYPES = {"board-ssd1306"}


def build_simulation(
    spec: ProjectSpec, lib: PartLibrary, project_dir: Path, out_dir: Path
) -> ToolResult:
    """artifacts: diagram_json, wokwi_toml"""
    board = lib.get(spec.mcu.part_id)
    assert isinstance(board, BoardDef)
    if not board.wokwi_board:
        return _skip(
            f"Wokwi has no model of the board {board.id}, so the simulation can't run"
        )
    mcu = spec.mcu.ref
    parts = [{"type": board.wokwi_board, "id": mcu, "top": 0, "left": 0, "attrs": {}}]
    connections = []
    if {"TX", "RX"} <= set(board.wokwi_pins.values()):
        connections += [
            [f"{mcu}:TX", "$serialMonitor:RX", "", []],
            [f"{mcu}:RX", "$serialMonitor:TX", "", []],
        ]
    warnings = []
    included = {}
    for inst in spec.parts:
        part = lib.get(inst.part_id)
        if not part.wokwi_type:
            warnings.append(
                ToolError(
                    code="no_wokwi_part",
                    message=f"{inst.ref} ({inst.part_id}) has no Wokwi model; it is left out "
                    "of the simulation and the firmware won't find it there",
                    severity="warning",
                )
            )
            continue
        attrs = dict(part.wokwi_attrs)
        if inst.i2c_address:
            attrs["i2cAddress"] = inst.i2c_address.lower()
        top = 100 * len(included) - 120  # one column right of the board
        parts.append(
            {
                "type": part.wokwi_type,
                "id": inst.ref,
                "top": top,
                "left": 200,
                "attrs": attrs,
            }
        )
        included[inst.ref] = part
    for c in spec.connections:
        part = included.get(c.part_ref)
        if part is None:
            continue
        color = WIRE_COLORS.get(lib.pin_type(part.id, c.part_pin) or "", "green")
        connections.append(
            [
                f"{c.part_ref}:{part.wokwi_pins.get(c.part_pin, c.part_pin)}",
                f"{mcu}:{board.wokwi_pins.get(c.mcu_pin, c.mcu_pin)}",
                color,
                [],
            ]
        )
    diagram = {
        "version": 1,
        "author": "Prompt-to-Device",
        "editor": "wokwi",
        "parts": parts,
        "connections": connections,
        "dependencies": {},
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    # Wokwi runs an ESP32's flash image; AVR and RP2040 boards run straight from the ELF
    firmware = "firmware.bin" if board.pio_platform == "espressif32" else "firmware.elf"
    build = Path(
        os.path.relpath(project_dir / ".pio" / "build" / board.pio_board, out_dir)
    ).as_posix()
    files = {
        "diagram_json": (
            out_dir / "diagram.json",
            json.dumps(diagram, indent=2) + "\n",
        ),
        "wokwi_toml": (
            out_dir / "wokwi.toml",
            f'[wokwi]\nversion = 1\nfirmware = "{build}/{firmware}"\n'
            + f'elf = "{build}/firmware.elf"\n',
        ),
    }
    for path, text in files.values():
        path.write_text(text, newline="\n")
    return ToolResult(
        ok=True,
        errors=warnings,
        artifacts={name: str(path.resolve()) for name, (path, _) in files.items()},
    )


def run_simulation(
    sim_dir: Path, timeout_ms: int, expect_text: str = "P2D_READY"
) -> ToolResult:
    """artifacts: serial_log, screenshot (when the diagram has a display)"""
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        return _skip("WOKWI_CLI_TOKEN isn't set, so the Wokwi simulator can't run")
    cli = shutil.which("wokwi-cli")
    if not cli:
        return _skip(
            "wokwi-cli isn't installed (https://docs.wokwi.com/wokwi-ci/cli-installation)"
        )
    sim_dir = sim_dir.resolve()
    config = tomllib.loads((sim_dir / "wokwi.toml").read_text())["wokwi"]
    missing = [
        config[k] for k in ("firmware", "elf") if not (sim_dir / config[k]).is_file()
    ]
    if missing:
        return _fail(
            "firmware_missing",
            f"compiled firmware not found: {', '.join(missing)} (relative to {sim_dir}); "
            "compile the firmware project before simulating",
        )

    serial_log = sim_dir / "serial.log"
    screenshot = sim_dir / "screenshot.png"
    for stale in (serial_log, screenshot):
        stale.unlink(missing_ok=True)
    cmd = [
        cli,
        str(sim_dir),
        "--timeout", str(timeout_ms),
        "--expect-text", expect_text,
        "--serial-log-file", str(serial_log),
        "-q",
    ]  # fmt: skip
    diagram = json.loads((sim_dir / "diagram.json").read_text())
    display = next(
        (p["id"] for p in diagram["parts"] if p["type"] in DISPLAY_TYPES), None
    )
    if display:
        # the CLI waits for the screenshot even after the expected text shows up
        cmd += [
            "--screenshot-part", display,
            "--screenshot-time", str(timeout_ms),
            "--screenshot-file", str(screenshot),
        ]  # fmt: skip
    # upload time plus a simulator slower than real time
    wall_s = timeout_ms / 1000 * 3 + 60
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            cwd=sim_dir,
            capture_output=True,
            text=True,
            timeout=wall_s,
        )
        code, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        code, output = TIMEOUT_EXIT_CODE, ""
    serial = serial_log.read_text(errors="replace") if serial_log.is_file() else ""
    outputs = {"serial_log": serial_log, "screenshot": screenshot}
    artifacts = {name: str(path) for name, path in outputs.items() if path.is_file()}
    if code == 0:
        return ToolResult(ok=True, artifacts=artifacts, log=_tail(output))
    if code == TIMEOUT_EXIT_CODE:
        error = _error(
            "sim_timeout",
            f"the firmware never printed {expect_text} within {timeout_ms} ms of simulation; "
            f"last serial lines:\n{_tail(serial, 10) or '(no serial output)'}",
            hint=f"print {expect_text} at the end of setup() and don't block before it",
        )
    else:
        error = _error(
            "sim_error", f"wokwi-cli exited with {code}:\n{_tail(output, 10)}"
        )
    return ToolResult(ok=False, errors=[error], artifacts=artifacts, log=_tail(output))


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _error(code: str, message: str, hint: str | None = None) -> ToolError:
    return ToolError(code=code, message=message, hint=hint)


def _fail(code: str, message: str) -> ToolResult:
    return ToolResult(ok=False, errors=[_error(code, message)])


def _skip(message: str) -> ToolResult:
    return _fail("skipped", message)

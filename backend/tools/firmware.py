"""Firmware project generation, lint and compile (T12).

A project is a PlatformIO folder: platformio.ini, include/pins.h (generated from the spec's
connections) and src/main.cpp (written by the firmware agent).

Error codes:
- unknown_part: the spec names a part_id the library doesn't have (write_firmware_project).
- missing_pins_include: main.cpp doesn't `#include "pins.h"` (lint).
- missing_ready: main.cpp never prints P2D_READY (lint).
- numeric_pin: a pin argument is a number instead of a PIN_* macro (lint).
- missing_main: src/main.cpp doesn't exist (lint, compile).
- compile_error: a compiler error, or a failed build with no parseable error line (compile).
- compile_timeout: the build took longer than COMPILE_TIMEOUT_S (compile).
- pio_missing: PlatformIO isn't installed (compile).
- pio_failed: PlatformIO is installed but couldn't be started (compile).
"""

import re
import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from backend.contracts.parts import BoardDef, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import ProjectSpec

TEMPLATES = Path(__file__).resolve().parents[2] / "firmware_templates"
COMPILE_TIMEOUT_S = 600
LOG_LINES = 40

_jinja = Environment(
    loader=FileSystemLoader(TEMPLATES),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)

# The core's USB device library (USB.h, USBHIDKeyboard.h, USBHIDGamepad.h, ...): ESP32-S3 native USB.
_NATIVE_USB = re.compile(r'^\s*#\s*include\s*[<"]USB', re.MULTILINE)

# Calls whose first argument is a pin number (ledcAttach and tone: Arduino core 3 names for PWM).
_PIN_CALL = re.compile(
    r"\b(pinMode|digitalWrite|digitalRead|analogRead|ledcAttachPin|ledcAttach|tone|noTone)"
    r"\s*\(\s*(\d+)\s*[,)]"
)
_WIRE_BEGIN = re.compile(r"\bWire1?\s*\.\s*begin\s*\(([^)]*)\)")
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_COMPILER_ERROR = re.compile(
    r"^(?P<file>(?:[A-Za-z]:)?[^\s:][^:\n]*):(?P<line>\d+):(?P<col>\d+): (?:fatal )?error: (?P<msg>.+)$",
    re.MULTILINE,
)
# gcc: "'X' was not declared in this scope"; clang: "use of undeclared identifier 'X'"
_UNDECLARED_PIN = re.compile(
    r"'(PIN_\w+)' was not declared|undeclared identifier '(PIN_\w+)'"
)


def pins_header(spec: ProjectSpec) -> str:
    """`#define PIN_<REF>_<PIN> <n>` for every connection to a GPIO, sorted by macro name."""
    defines = sorted(
        {
            f"#define PIN_{c.part_ref.upper()}_{c.part_pin.upper()} "
            + c.mcu_pin.removeprefix("GPIO")
            for c in spec.connections
            if c.mcu_pin.startswith("GPIO")
        }
    )
    return (
        "\n".join(
            ["#pragma once", "// generated from spec.json: do not edit", *defines]
        )
        + "\n"
    )


def write_firmware_project(
    spec: ProjectSpec, lib: PartLibrary, main_cpp: str, out_dir: Path
) -> ToolResult:
    """artifacts: platformio_ini, pins_h, main_cpp"""
    instances = [spec.mcu, *spec.parts]
    unknown = [
        ToolError(
            code="unknown_part",
            message=f"{p.ref} uses part_id {p.part_id!r}, which isn't in the parts library",
            field="mcu.part_id" if p is spec.mcu else f"parts[{i - 1}].part_id",
        )
        for i, p in enumerate(instances)
        if p.part_id not in lib
    ]
    if unknown:
        return ToolResult(ok=False, errors=unknown)
    board = lib.get(spec.mcu.part_id)
    if not isinstance(board, BoardDef):
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="unknown_part",
                    message=f"mcu {spec.mcu.ref} uses {spec.mcu.part_id!r}, which isn't a board",
                    field="mcu.part_id",
                )
            ],
        )
    lib_deps = sorted({d for p in instances for d in lib.get(p.part_id).pio_lib_deps})
    ini = _jinja.get_template("platformio.ini.j2").render(
        pio_board=board.pio_board,
        lib_deps=lib_deps,
        native_usb=_NATIVE_USB.search(main_cpp) is not None,
    )

    files = {
        "platformio_ini": (out_dir / "platformio.ini", ini),
        "pins_h": (out_dir / "include" / "pins.h", pins_header(spec)),
        "main_cpp": (out_dir / "src" / "main.cpp", main_cpp),
    }
    for path, text in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, newline="\n")  # same bytes on every OS
    return ToolResult(
        ok=True,
        artifacts={name: str(path.resolve()) for name, (path, _) in files.items()},
    )


def _available_pins(project_dir: Path) -> str:
    pins_h = project_dir / "include" / "pins.h"
    macros = (
        re.findall(r"#define (PIN_\w+)", pins_h.read_text()) if pins_h.is_file() else []
    )
    return ", ".join(macros) or "none (pins.h defines no GPIO pins)"


def _missing_main(project_dir: Path) -> ToolResult:
    return ToolResult(
        ok=False,
        errors=[
            ToolError(
                code="missing_main",
                message=f"{project_dir / 'src' / 'main.cpp'} doesn't exist",
                hint="write the project with write_firmware_project first",
            )
        ],
    )


def lint_firmware(project_dir: Path) -> ToolResult:
    main = project_dir / "src" / "main.cpp"
    if not main.is_file():
        return _missing_main(project_dir)
    text = main.read_text()
    available = _available_pins(project_dir)
    errors: list[ToolError] = []

    if not re.search(r'^\s*#\s*include\s*"pins\.h"', text, re.MULTILINE):
        errors.append(
            ToolError(
                code="missing_pins_include",
                message='src/main.cpp must #include "pins.h" and use its PIN_* macros',
                field="src/main.cpp",
                hint='add #include "pins.h" after the library includes',
            )
        )
    if "P2D_READY" not in text:
        errors.append(
            ToolError(
                code="missing_ready",
                message="src/main.cpp never prints P2D_READY; the simulator waits for it",
                field="src/main.cpp",
                hint='end setup() with Serial.println("P2D_READY");',
            )
        )

    # Blank out comments but keep newlines, so match offsets still give the right line numbers.
    code = _COMMENT.sub(lambda m: "\n" * m.group().count("\n"), text)

    def numeric(pos: int, call: str, value: str) -> ToolError:
        line = code.count("\n", 0, pos) + 1
        return ToolError(
            code="numeric_pin",
            message=(
                f"src/main.cpp:{line}: {call} uses pin number {value}; pin numbers must come "
                f"from pins.h. Available macros: {available}"
            ),
            field=f"src/main.cpp:{line}",
            hint="use the PIN_<REF>_<PIN> macro for the part pin wired there",
        )

    for m in _PIN_CALL.finditer(code):
        errors.append(numeric(m.start(), m.group(1), m.group(2)))
    for m in _WIRE_BEGIN.finditer(code):
        args = [a.strip() for a in m.group(1).split(",")]
        if (
            len(args) >= 2
        ):  # Wire.begin(sda, scl[, freq]); Wire.begin(addr) is target mode
            errors += [
                numeric(m.start(), "Wire.begin", a) for a in args[:2] if a.isdigit()
            ]

    return ToolResult(ok=not errors, errors=errors)


def parse_compile_errors(log: str, project_dir: Path) -> list[ToolError]:
    """`file:line:col: error: msg` lines, paths relative to the project where possible."""
    errors: list[ToolError] = []
    seen: set[str] = set()
    root = project_dir.resolve()
    for m in _COMPILER_ERROR.finditer(log):
        path = Path(m["file"])
        if path.is_absolute() and path.is_relative_to(root):
            path = path.relative_to(root)
        where = f"{path.as_posix()}:{m['line']}:{m['col']}"
        if (
            where + m["msg"] in seen
        ):  # the same header error repeats per translation unit
            continue
        seen.add(where + m["msg"])
        hint = None
        if _UNDECLARED_PIN.search(m["msg"]):
            hint = f"pins.h defines {_available_pins(project_dir)}; use one of these"
        errors.append(
            ToolError(
                code="compile_error",
                message=f"{where}: {m['msg']}",
                field=where,
                hint=hint,
            )
        )
    return errors


def compile_firmware(project_dir: Path) -> ToolResult:
    """log: last 40 lines of the build"""
    if not (project_dir / "src" / "main.cpp").is_file():
        return _missing_main(project_dir)
    pio = shutil.which("pio")
    if pio is None:
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="pio_missing",
                    message="PlatformIO (pio) isn't installed on the server",
                    hint="run make setup",
                )
            ],
        )
    try:
        r = subprocess.run(
            [pio, "run", "-d", str(project_dir)],
            check=False,
            capture_output=True,
            text=True,
            timeout=COMPILE_TIMEOUT_S,
        )
    except (
        OSError
    ) as e:  # pio on PATH but not runnable (broken shim, no exec permission)
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="pio_failed",
                    message=f"PlatformIO ({pio}) couldn't be started: {e}",
                    hint="reinstall it with make setup",
                )
            ],
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout or ""
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="compile_timeout",
                    message=f"the build took longer than {COMPILE_TIMEOUT_S} s and was stopped",
                )
            ],
            log=_tail(out),
        )
    full = r.stdout + r.stderr
    log = _tail(full)
    if r.returncode == 0:
        return ToolResult(ok=True, log=log)
    errors = parse_compile_errors(full, project_dir) or [
        ToolError(
            code="compile_error",
            message="the build failed without a compiler error line (linker or library "
            "problem); read the log",
        )
    ]
    return ToolResult(ok=False, errors=errors, log=log)


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-LOG_LINES:])

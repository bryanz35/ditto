"""Custom shapes: build spec.enclosure.code, model-written build123d source, into printable parts.

The code is checked (allowed imports, no file or interpreter access), saved as cad/model.py and run by
backend/cad/run_model.py in a separate process with a time and memory limit. Its docstring says what
the code must define: `parts` for a print-only project; for a device `body` around the case's BAY,
extra separately printed `parts` with where each goes (`assembled`), external parts placed on them
(`mounts`), or both (base and lid keep their names, so the layout, assembly and build guide work
unchanged). run_model checks that the assembled device holds together.
check_enclosure then checks every printed part.

Error codes: no_model, forbidden_code, model_error, bad_model_output, model_timeout, cad_build_failed,
layout_mismatch, not_assembled; warning: unmounted_parts.
"""

import ast
import json
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.contracts.artifacts import EnclosureManifest
from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec
from backend.tools.build_enclosure import enclosure_manifest, layout_error, standoffs

ROOT = Path(__file__).resolve().parents[2]
RUN_MODEL = ROOT / "backend" / "cad" / "run_model.py"
ALLOWED_IMPORTS = {"build123d", "math"}
FORBIDDEN_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "input",
    "breakpoint",
    "help",
    "exit",
    "quit",
    "Mesher",
}
FORBIDDEN_ATTRS = {
    # modules build123d re-exports (tests/unit/cad/test_custom_model.py keeps this list complete)
    *[
        "ET",
        "Lib3MF",
        "PT",
        "TopoDS",
        "brep_from_stl",
        "build_common",
        "build_constants",
        "build_enums",
        "build_line",
    ],
    *[
        "build_part",
        "build_sketch",
        "colorsys",
        "contextvars",
        "copy_module",
        "ctypes",
        "drafting",
        "exporters",
    ],
    *[
        "exporters3d",
        "ezdxf",
        "functools",
        "geometry",
        "importers",
        "inspect",
        "io",
        "itertools",
        "joints",
        "json",
    ],
    *[
        "logging",
        "math",
        "mesher",
        "np",
        "objects_curve",
        "objects_part",
        "objects_sketch",
        "operations_generic",
    ],
    *[
        "operations_part",
        "operations_sketch",
        "os",
        "pack_utils",
        "persistence",
        "re",
        "requests",
        "svgpathtools",
    ],
    *[
        "sys",
        "ta",
        "tempfile",
        "text",
        "topology",
        "trianglesolver",
        "unicodedata",
        "version",
        "warnings",
        "webbrowser",
    ],
    *["webcolors", "zoom"],
    # and other ways out
    *[
        "Path",
        "pathlib",
        "subprocess",
        "shutil",
        "socket",
        "importlib",
        "builtins",
        "gc",
        "signal",
    ],
}
"""Attribute and imported names model code may not use, even as `bd.<name>`. `math` is listed
because build123d.math is reachable that way; `import math` itself is allowed."""
TIMEOUT_S = 120
CPU_S = 90
MEMORY_BYTES = (
    4 * 2**30
)  # build123d (OCCT + OpenBLAS) doesn't start under 2 GB of address space
FILE_BYTES = 200 * 2**20
# shortcut: an AST allowlist plus rlimits is not a real sandbox; run it in a container (nsjail,
# gVisor) before hosting this for users you don't trust.


def _io_name(name: str) -> bool:
    """build123d's file readers and writers: export_stl, import_step, ExportSVG..."""
    return name.lower().startswith(("export", "import"))


def check_source(code: str) -> list[ToolError]:
    """Static check of model-written code: what it may import and which names it may touch."""
    try:
        tree = ast.parse(code, "model.py")
    except SyntaxError as e:
        return [_err("model_error", f"model.py line {e.lineno}: {e.msg}")]
    problems = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import | ast.ImportFrom):
            mods = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            names = [] if isinstance(node, ast.Import) else [a.name for a in node.names]
            bad = [m for m in mods if m.split(".")[0] not in ALLOWED_IMPORTS]
            bad += [
                n
                for n in names
                if _io_name(n) or n in FORBIDDEN_NAMES or n in FORBIDDEN_ATTRS
            ]
            if bad or getattr(node, "level", 0):
                problems.append(
                    f"line {line}: import of {bad or 'a relative module'}; only build123d and "
                    "math may be imported, without their file import/export functions"
                )
        elif isinstance(node, ast.Name) and (
            node.id in FORBIDDEN_NAMES
            or node.id
            in FORBIDDEN_ATTRS - {"math"}  # `from build123d import *` brings os in
            or node.id.startswith("__")
            or _io_name(node.id)
        ):
            problems.append(f"line {line}: `{node.id}` isn't allowed")
        elif isinstance(node, ast.Attribute) and (
            node.attr.startswith("_")
            or _io_name(node.attr)
            or node.attr in FORBIDDEN_ATTRS
        ):
            problems.append(f"line {line}: attribute `.{node.attr}` isn't allowed")
    if problems:
        message = "model.py does more than build shapes: " + "; ".join(problems[:8])
        return [
            _err(
                "forbidden_code",
                message,
                "build shapes only; code here saves the files",
            )
        ]
    return []


def build_custom_model(
    spec: ProjectSpec, layout: Layout | None, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    """layout: required for a device (spec.mcu set), None for a print-only project."""
    code = spec.enclosure.code
    device = spec.mcu is not None
    if spec.enclosure.template != "custom" or not code:
        return ToolResult(
            ok=False,
            errors=[
                _err(
                    "no_model",
                    "this print-only project has no shape yet: the enclosure agent must write "
                    "its build123d code with write_model",
                    field="enclosure.code",
                )
            ],
        )
    if errors := check_source(code):
        return ToolResult(ok=False, errors=errors)
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    job: dict = {"code": code, "out_dir": str(out_dir)}
    if device:
        if layout is None:
            raise ValueError("build_custom_model needs the layout for a device")
        if mismatch := layout_error(spec, layout, lib):
            return mismatch
        manifest = enclosure_manifest(spec, layout, lib)
        external = {}  # ref -> board size, for `mounts`
        for p in spec.parts:
            part = lib.get(p.part_id)
            if part.mounting == "external":
                external[p.ref] = [part.board_mm.l, part.board_mm.w, part.board_mm.h]
        job["box"] = {
            "cavity_mm": layout.cavity_mm,
            "wall_mm": manifest.wall_mm,
            "cutouts": [c.model_dump(mode="json") for c in manifest.cutouts],
            "standoffs": standoffs(spec, layout, lib),
            "external": external,
        }
    model_py = out_dir / "model.py"
    model_py.write_text(code)
    for old in [*out_dir.glob("*.stl"), *out_dir.glob("*.step")]:
        if not (device and old.stem in ("base", "lid")):
            old.unlink()  # a part the previous model had

    with tempfile.TemporaryDirectory() as tmp:
        job["result"] = str(Path(tmp) / "result.json")
        job_path = Path(tmp) / "job.json"
        job_path.write_text(json.dumps(job))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(RUN_MODEL), str(ROOT), str(job_path)],
                check=False,
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1"},
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                start_new_session=True,
                preexec_fn=_limits,
            )
        except subprocess.TimeoutExpired:
            return _failed(
                "model_timeout",
                f"model.py ran longer than {TIMEOUT_S} s; simplify it (fewer booleans, no loops "
                "over thousands of shapes)",
            )
        result_path = Path(job["result"])
        if not result_path.is_file():
            tail = (proc.stderr or proc.stdout or "").strip()[-1200:]
            return _failed(
                "model_error",
                f"model.py crashed the CAD process (exit {proc.returncode}, often the CPU or "
                f"memory limit): {tail}",
            )
        out = json.loads(result_path.read_text())
    if not out["ok"]:
        return _failed(out["code"], out["message"])

    prints = {n: tuple(v) for n, v in sorted(out["prints"].items())}
    warnings = []
    if device:
        manifest = EnclosureManifest.model_validate(
            manifest.model_dump()
            | {
                "prints": prints,
                "outer_mm": out["outer"],
                "assembled": out["assembled"],
                "mounts": out["mounts"],
                "build_order": out["order"],
            }
        )
        if loose := sorted(set(job["box"]["external"]) - set(manifest.mounts)):
            warnings.append(
                ToolError(
                    code="unmounted_parts",
                    message=f"not mounted on any printed part, so shown beside the device: "
                    f"{', '.join(loose)}. If a printed part holds one (a servo in an arm link, a "
                    'sensor in a bracket), place it with `mounts = {"ref": Location}`',
                    field="enclosure.code",
                    severity="warning",
                )
            )
    else:
        biggest = max(prints.values(), key=lambda s: s[0] * s[1] * s[2])
        manifest = EnclosureManifest(
            spec_rev=spec.rev,
            template="custom",
            wall_mm=spec.enclosure.wall_mm,
            cavity_mm=(0.0, 0.0, 0.0),
            outer_mm=biggest,
            cutouts=[],
            prints=prints,
        )
    path = out_dir / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return ToolResult(
        ok=True,
        errors=warnings,
        artifacts={
            **out["artifacts"],
            "model_py": str(model_py),
            "manifest": str(path),
        },
        data={"manifest": manifest.model_dump(mode="json")},
    )


def _limits() -> None:
    for limit, value in (
        (resource.RLIMIT_CPU, CPU_S),
        (resource.RLIMIT_AS, MEMORY_BYTES),
        (resource.RLIMIT_FSIZE, FILE_BYTES),
    ):
        resource.setrlimit(limit, (value, value))


def _err(
    code: str, message: str, hint: str | None = None, field: str = "enclosure.code"
) -> ToolError:
    return ToolError(code=code, message=message, hint=hint, field=field)


def _failed(code: str, message: str) -> ToolResult:
    return ToolResult(ok=False, errors=[_err(code, message)])

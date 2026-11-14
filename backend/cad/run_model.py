"""Runs model-written build123d code in its own process (started by backend/tools/custom_model.py).

    python -I run_model.py <repo root> <job.json>

job.json: {"code": str, "out_dir": str, "result": str, and for a device "box": {"cavity_mm",
"wall_mm", "cutouts", "standoffs"}}. Writes STL and STEP files to out_dir and a JSON result:
{"ok": true, "artifacts": {...}, "prints": {name: [x, y, z]}} or {"ok": false, "code": ..., "message": ...}.

The code runs with these names already defined (and anything it imports from build123d and math):
- print-only: nothing extra. It must set `parts = {"name": shape, ...}`.
- device: BAY (the closed case's outer solid, enclosure frame), CAVITY_MM (L, W, H), WALL_MM. It must
  set `body` (a shape built around BAY). Code then makes base = box base + (body - keep-out) and keeps
  the box lid, so the parts always fit, every opening stays clear and the lid still comes off.
"""

import json
import re
import sys
import traceback
from pathlib import Path

NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
MAX_PARTS = 8


def _fail(result: Path, code: str, message: str) -> None:
    result.write_text(json.dumps({"ok": False, "code": code, "message": message}))


def _model_traceback() -> str:
    """The traceback from the model's own code on, so the message points at its lines."""
    lines = traceback.format_exc().splitlines()
    start = next((i for i, line in enumerate(lines) if '"model.py"' in line), 1)
    return "\n".join(lines[:1] + lines[start:])[-1500:]


def main(root: str, job_path: str) -> None:
    sys.path.insert(0, root)
    job = json.loads(Path(job_path).read_text())
    result = Path(job["result"])
    from build123d import Shape

    from backend.cad.box_lid import box_lid_shapes, export_parts
    from backend.contracts.artifacts import CutoutRecord

    box = job.get("box")
    env: dict = {"__name__": "model"}
    if box:
        cutouts = [CutoutRecord.model_validate(c) for c in box["cutouts"]]
        shapes = box_lid_shapes(
            tuple(box["cavity_mm"]),
            box["wall_mm"],
            cutouts,
            [tuple(s) for s in box["standoffs"]],
        )
        env |= {
            "BAY": shapes["bay"],
            "CAVITY_MM": tuple(box["cavity_mm"]),
            "WALL_MM": box["wall_mm"],
        }
    try:
        exec(compile(job["code"], "model.py", "exec"), env)  # noqa: S102 (checked by custom_model)
    except Exception:  # noqa: BLE001 (any error in the model's code goes back to the model)
        return _fail(result, "model_error", _model_traceback())

    if box:
        body = env.get("body")
        if not isinstance(body, Shape):
            return _fail(
                result,
                "bad_model_output",
                "a device's model must set `body` to one build123d shape built around BAY; "
                f"got {type(body).__name__}",
            )
        try:
            prints = {
                "base": shapes["base"] + (body - shapes["keepout"]),
                "lid": shapes["lid"],
            }
        except Exception:  # noqa: BLE001
            return _fail(
                result,
                "cad_build_failed",
                f"joining body to the case failed: {traceback.format_exc()[-800:]}",
            )
    else:
        prints = env.get("parts")
        if not isinstance(prints, dict) or not prints:
            return _fail(
                result,
                "bad_model_output",
                'the model must set `parts = {"name": shape, ...}` (one entry per printed part)',
            )
        bad = [
            n
            for n, s in prints.items()
            if not (isinstance(n, str) and NAME.match(n)) or not isinstance(s, Shape)
        ]
        if bad or len(prints) > MAX_PARTS:
            return _fail(
                result,
                "bad_model_output",
                f"`parts` needs at most {MAX_PARTS} entries, each a lowercase name (letters, "
                f"digits, _) -> one build123d shape; these aren't: {bad}",
            )
    empty = [n for n, s in prints.items() if s.volume <= 0]
    if empty:
        return _fail(
            result, "bad_model_output", f"these parts have no volume: {sorted(empty)}"
        )
    try:
        artifacts = export_parts(dict(sorted(prints.items())), Path(job["out_dir"]))
    except Exception:  # noqa: BLE001
        return _fail(
            result,
            "cad_build_failed",
            f"export failed: {traceback.format_exc()[-800:]}",
        )
    sizes = {}
    for name, shape in prints.items():
        bb = shape.bounding_box()
        sizes[name] = [round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)]
    result.write_text(json.dumps({"ok": True, "artifacts": artifacts, "prints": sizes}))


if __name__ == "__main__":
    main(*sys.argv[1:3])

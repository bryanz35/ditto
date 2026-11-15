"""Runs model-written build123d code in its own process (started by backend/tools/custom_model.py).

    python -I run_model.py <repo root> <job.json>

job.json: {"code": str, "out_dir": str, "result": str, and for a device "box": {"cavity_mm",
"wall_mm", "cutouts", "standoffs", "external": {ref: [l, w, h]}}}. Writes STL and STEP files to
out_dir and a JSON result: {"ok": true, "artifacts": {...}, "prints": {name: [x, y, z]},
"outer": [x, y, z], "assembled": {name: pose}, "mounts": {ref: pose}, "order": [...]} (a pose is
{"on", "transform"}, see contracts/artifacts.py Pose; outer: every
part as exported; for a device, base and lid only, so the closed device) or {"ok": false,
"code": ..., "message": ...}.

The code runs with these names already defined (and anything it imports from build123d and math):
- print-only: nothing extra. It must set `parts = {"name": shape, ...}`.
- device: BAY (the closed case's outer solid, enclosure frame), CAVITY_MM (L, W, H), WALL_MM. It sets
  `body` (a shape built around BAY), `parts` (separately printed pieces, as for print-only, never
  named base or lid), or both. Code makes base = box base + (body - keep-out) and keeps the box lid,
  so the parts always fit, every opening stays clear and the lid still comes off. With `parts` it
  must also set `assembled = {"name": Location}` (the move from the print bed to the part's place in
  the device), and it may set `mounts = {"ref": Location}` to put an external part (its board_mm box,
  x 0..l, y 0..w, z 0..h) in or on a printed part. Code then checks the assembled device: every
  part and mounted box comes within TOUCH_MM of something that leads back to the case, and no two
  overlap by more than OVERLAP_SHARE of the smaller one.
  shortcut: the electronics always sit in one axis-aligned box bay; free placement (a tilted screen,
  parts spread through the body) needs model-proposed placements and collision checks.
"""

import itertools
import json
import math
import re
import sys
import traceback
from pathlib import Path

NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
MAX_PARTS = 8
CASE = ("base", "lid")
TOUCH_MM = 5.0
"""How close a part must come to what holds it: servo horns, screws and washers bridge small gaps."""
OVERLAP_SHARE = 0.05


class _Bad(Exception):
    """A model output the assembly check rejects: (code, message)."""


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

    parts = env.get("parts", {} if box else None)
    if not isinstance(parts, dict) or not (parts or box):
        return _fail(
            result,
            "bad_model_output",
            'the model must set `parts = {"name": shape, ...}` (one entry per printed part)',
        )
    bad = [
        n
        for n, s in parts.items()
        if not (isinstance(n, str) and NAME.match(n))
        or not isinstance(s, Shape)
        or (box and n in CASE)
    ]
    if bad or len(parts) > MAX_PARTS:
        return _fail(
            result,
            "bad_model_output",
            f"`parts` needs at most {MAX_PARTS} entries, each a lowercase name (letters, "
            f"digits, _; not base or lid on a device) -> one build123d shape; these aren't: {bad}",
        )
    prints = parts
    if box:
        body = env.get("body")
        if body is None and not parts:
            return _fail(
                result,
                "bad_model_output",
                "a device's model must set `body` (one build123d shape built around BAY), "
                '`parts = {"name": shape, ...}` (separately printed pieces), or both',
            )
        if body is not None and not isinstance(body, Shape):
            return _fail(
                result,
                "bad_model_output",
                f"`body` must be one build123d shape built around BAY; got {type(body).__name__}",
            )
        try:
            base = (
                shapes["base"]
                if body is None
                else shapes["base"] + (body - shapes["keepout"])
            )
        except Exception:  # noqa: BLE001
            return _fail(
                result,
                "cad_build_failed",
                f"joining body to the case failed: {traceback.format_exc()[-800:]}",
            )
        prints = {"base": base, "lid": shapes["lid"], **parts}
    empty = [n for n, s in prints.items() if s.volume <= 0]
    if empty:
        return _fail(
            result, "bad_model_output", f"these parts have no volume: {sorted(empty)}"
        )
    assembled, mounts, order = {}, {}, []
    if box:
        try:
            assembled, mounts, order = _assemble(prints, env, box.get("external", {}))
        except _Bad as e:
            return _fail(result, *e.args)
    try:
        artifacts = export_parts(dict(sorted(prints.items())), Path(job["out_dir"]))
    except Exception:  # noqa: BLE001
        return _fail(
            result,
            "cad_build_failed",
            f"export failed: {traceback.format_exc()[-800:]}",
        )
    sizes, whole = {}, None
    for name, shape in prints.items():
        bb = shape.bounding_box()
        sizes[name] = _size(bb)
        # a device's extra parts sit in print position, not on the case
        if not box or name in CASE:
            whole = bb if whole is None else whole.add(bb)
    out = {
        "ok": True,
        "artifacts": artifacts,
        "prints": sizes,
        "outer": _size(whole),
        "assembled": assembled,
        "mounts": mounts,
        "order": order,
    }
    result.write_text(json.dumps(out))


def _assemble(prints: dict, env: dict, external: dict) -> tuple[dict, dict, list]:
    """A device's assembled poses (`assembled`, `mounts`) and a build order, after checking that
    the assembled device holds together. Raises _Bad."""
    from build123d import Align, Box, Location

    extras = sorted(n for n in prints if n not in CASE)
    poses, held = env.get("assembled", {}), env.get("mounts", {})
    if not isinstance(poses, dict) or not isinstance(held, dict):
        raise _Bad(
            "bad_model_output", "`assembled` and `mounts` must be dicts of Locations"
        )
    if sorted(poses) != extras:
        raise _Bad(
            "bad_model_output",
            "give every entry of `parts` its place in the assembled device, and nothing else: "
            '`assembled = {"name": Pos(x, y, z) * Rot(a, b, c), ...}` moves the part from its print '
            f"position to where it sits (enclosure frame). Missing: {sorted(set(extras) - set(poses))}; "
            f"not in `parts`: {sorted(set(poses) - set(extras))}",
        )
    unknown = sorted(set(held) - set(external))
    if unknown:
        raise _Bad(
            "bad_model_output",
            f"`mounts` places external parts by ref; {unknown} aren't. External parts: "
            f"{sorted(external) or 'none'}",
        )
    bad = [n for n, v in [*poses.items(), *held.items()] if not isinstance(v, Location)]
    if bad:
        raise _Bad(
            "bad_model_output",
            f"{bad}: each value in `assembled` and `mounts` must be a Location such as "
            "Pos(x, y, z) * Rot(a, b, c)",
        )
    nodes = {n: prints[n] for n in CASE} | {n: poses[n] * prints[n] for n in extras}
    for ref, loc in held.items():
        nodes[ref] = loc * Box(*external[ref], align=(Align.MIN,) * 3)

    boxes = {n: s.bounding_box() for n, s in nodes.items()}
    dists: dict[tuple[str, str], float] = {}

    def dist(a: str, b: str) -> float:
        key = (min(a, b), max(a, b))
        if key not in dists:
            dists[key] = nodes[a].distance_to(nodes[b])
        return dists[key]

    def apart(a: str, b: str) -> float:
        """Lower bound on dist(a, b) from the bounding boxes."""
        A, B = boxes[a], boxes[b]
        return math.hypot(
            *(
                max(
                    getattr(A.min, k) - getattr(B.max, k),
                    getattr(B.min, k) - getattr(A.max, k),
                    0,
                )
                for k in "XYZ"
            )
        )

    problems = []
    touching: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in itertools.combinations(nodes, 2):
        if apart(a, b) > TOUCH_MM or dist(a, b) > TOUCH_MM:
            continue
        touching[a].add(b)
        touching[b].add(a)
        if dist(a, b) < 0.01 and {a, b} != set(CASE):
            shared = (nodes[a] & nodes[b]).volume
            if shared > OVERLAP_SHARE * min(nodes[a].volume, nodes[b].volume):
                problems.append(
                    f"{a} and {b} overlap by {shared:.0f} mm³ in the assembled device; move one "
                    "of them, or cut a pocket for the other"
                )
    # breadth first from the case: each part attaches to the one that reached it
    on, order, i = {}, list(CASE), 0
    while i < len(order):
        for m in sorted(touching[order[i]] - set(order)):
            on[m] = order[i]
            order.append(m)
        i += 1
    seen = set(order)
    for n in sorted(set(nodes) - seen):
        near = min(sorted(seen), key=lambda m: dist(n, m))
        where = "`mounts`" if n in held else "`assembled`"
        problems.append(
            f"{n} doesn't attach to the device: nothing within {TOUCH_MM:g} mm of it leads back to "
            f"the case (nearest: {near}, {dist(n, near):.1f} mm away); fix its entry in {where}"
        )
    if problems:
        raise _Bad("not_assembled", "; ".join(problems[:8]))
    return (
        {n: {"on": on[n], "transform": _matrix(poses[n])} for n in extras},
        {r: {"on": on[r], "transform": _matrix(held[r])} for r in sorted(held)},
        order[len(CASE) :],
    )


def _matrix(loc) -> list[float]:
    """A Location as a 4x4 row-major matrix (rounded, so the same code gives the same file)."""
    t = loc.wrapped.Transformation()
    rows = [[t.Value(r, c) for c in (1, 2, 3, 4)] for r in (1, 2, 3)]
    return [round(v, 6) + 0.0 for row in rows for v in row] + [0.0, 0.0, 0.0, 1.0]


def _size(bb) -> list[float]:
    return [round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)]


if __name__ == "__main__":
    main(*sys.argv[1:3])

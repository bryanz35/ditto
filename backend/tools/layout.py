"""Deterministic part layout (T11): places every inside part on the cavity floor.

Parts whose features face a wall go against that wall (left and right in columns, front and back in
rows); the rest are packed in rows with `clearance_mm` gaps. Each cavity corner keeps a square free
for the lid's screw post. Rotation is always 0, so a feature keeps the face it has in the part frame.

Error codes: unknown_part. Warnings: feature_not_reachable.
"""

import math
from pathlib import Path

from backend.contracts.parts import PartDef, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, PartInstance, Placement, ProjectSpec

CORNER_POST_MM = 6.0
"""Square screw post in each cavity corner: nothing is placed there."""
LIP_MM = 3.0
"""Depth of the lid lip that hangs into the top of the cavity."""
STANDOFF_MM = 3.0
"""Height of the standoffs under parts that have mount holes."""
WALLS = ("left", "right", "front", "back")


def _r(v: float) -> float:
    return round(v, 2) + 0.0  # + 0.0 turns -0.0 into 0.0


def footprint(p: Placement, part: PartDef) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of a placed part seen from above."""
    l, w = part.board_mm.l, part.board_mm.w
    if p.rot_deg in (90, 270):
        l, w = w, l
    return p.x_mm, p.y_mm, p.x_mm + l, p.y_mm + w


def part_wall(part: PartDef) -> str | None:
    """The wall a part goes against: the face of its first feature that isn't on top."""
    return next((f.face for f in part.features if f.face != "top"), None)


def inside_parts(spec: ProjectSpec, lib: PartLibrary) -> list[PartInstance]:
    parts = spec.instances
    return sorted(
        (p for p in parts if lib.get(p.part_id).mounting == "inside"),
        key=lambda p: p.ref,
    )


def layout_parts(spec: ProjectSpec, lib: PartLibrary) -> tuple[Layout, list[ToolError]]:
    """The layout itself, without writing files. Assumes every part id is in the library."""
    c, post = spec.enclosure.clearance_mm, CORNER_POST_MM
    groups: dict[str | None, list[tuple[str, PartDef]]] = {}
    for inst in inside_parts(spec, lib):
        part = lib.get(inst.part_id)
        groups.setdefault(part_wall(part), []).append((inst.ref, part))

    pos: dict[
        str, list[float]
    ] = {}  # ref -> [x, y]; right and back get fixed once L, W are known

    def column(items):  # stacked along y, starting past the front corner post
        y = post + c
        for ref, part in items:
            pos[ref] = [0.0, y]
            y += part.board_mm.w + c
        return max((p.board_mm.l for _, p in items), default=0.0), y

    left_w, left_end = column(groups.get("left", []))
    right_w, right_end = column(groups.get("right", []))
    x0 = max(left_w, post) + c

    def row(items):  # along x, between the left column and the right one
        x = x0
        for ref, part in items:
            pos[ref] = [x, 0.0]
            x += part.board_mm.l + c
        return max((p.board_mm.w for _, p in items), default=0.0), x

    front, back, free = (
        groups.get("front", []),
        groups.get("back", []),
        groups.get(None, []),
    )
    front_h, front_end = row(front)
    back_h, back_end = row(back)

    # Free parts: rows of roughly square overall shape, between the front and back rows.
    area = sum((p.board_mm.l + c) * (p.board_mm.w + c) for _, p in free)
    target = max(
        front_end - x0,
        back_end - x0,
        max((p.board_mm.l + c for _, p in free), default=0.0),
        math.sqrt(area),
    )
    y = front_h + c if front else c
    x, row_h, free_end = x0, 0.0, x0
    for ref, part in free:
        l, w = part.board_mm.l, part.board_mm.w
        if x > x0 and x + l + c > x0 + target:
            y, x, row_h = y + row_h + c, x0, 0.0
        pos[ref] = [x, y]
        x += l + c
        row_h = max(row_h, w)
        free_end = max(free_end, x)
    middle_end = y + row_h + c if free else (front_h + c if front else c)

    length = max(front_end, back_end, free_end) + max(right_w, post)
    width = max(middle_end + back_h, left_end + post, right_end + post, 2 * post + c)
    for ref, part in groups.get("right", []):
        pos[ref][0] = length - part.board_mm.l
    for ref, part in back:
        pos[ref][1] = width - part.board_mm.w

    placements, warnings, height = [], [], 0.0
    for wall, items in groups.items():
        for ref, part in items:
            z = STANDOFF_MM if part.mount_holes else 0.0
            height = max(height, z + part.board_mm.h)
            placements.append(
                Placement(
                    ref=ref,
                    x_mm=_r(pos[ref][0]),
                    y_mm=_r(pos[ref][1]),
                    z_mm=z,
                    against_wall=wall,
                )
            )
            warnings += [
                ToolError(
                    code="feature_not_reachable",
                    message=f"{ref}'s {f.kind} faces {f.face} but {ref} sits against the "
                    f"{wall} wall, so it gets no opening; pick a part with its "
                    f"{part_wall(part)}-facing and {f.kind} features on the same face",
                    severity="warning",
                )
                for f in part.features
                if f.face not in ("top", wall)
            ]
    layout = Layout(
        placements=sorted(placements, key=lambda p: p.ref),
        cavity_mm=(_r(length), _r(width), _r(height + c + LIP_MM)),
    )
    return layout, warnings


def compute_layout(spec: ProjectSpec, lib: PartLibrary, out_dir: Path) -> ToolResult:
    unknown = [
        ToolError(
            code="unknown_part",
            message=f"{p.ref} uses part_id {p.part_id!r}, which isn't in the parts library; "
            f"known ids: {', '.join(sorted(lib.parts))}",
            field=f"parts[{i - 1}].part_id" if i else "mcu.part_id",
        )
        for i, p in enumerate(spec.instances)
        if p.part_id not in lib
    ]
    if unknown:
        return ToolResult(ok=False, errors=unknown)
    layout, warnings = layout_parts(spec, lib)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = (out_dir / "layout.json").resolve()
    path.write_text(layout.model_dump_json(indent=2) + "\n")
    return ToolResult(
        ok=True,
        errors=warnings,
        artifacts={"layout_json": str(path)},
        data={"layout": layout.model_dump(mode="json")},
    )

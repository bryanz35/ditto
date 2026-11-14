"""box_lid template (T11): build123d geometry for the base and lid, in the enclosure frame (base.py).

The base is an open box with the cavity floor at z=0; the lid is a plate on top at z=H with a lip that
hangs into the cavity. Both are exported where they sit when closed, so the assembly preview and the
viewer can place parts straight from the layout. Imported lazily: importing build123d takes seconds.
"""

from pathlib import Path

from build123d import Align, Box, Cylinder, Pos, Shape, export_step, export_stl

from backend.contracts.artifacts import CutoutRecord
from backend.tools.layout import CORNER_POST_MM, LIP_MM

MIN = (Align.MIN, Align.MIN, Align.MIN)
BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)
SCREW_PILOT_MM = 2.2  # M2.5 self-tapping into plastic
SCREW_CLEAR_MM = 2.9
LIP_T_MM = 1.2
LIP_GAP_MM = 0.2
# Fixed, so the same spec gives the same STEP file.
STEP_TIMESTAMP = "2000-01-01T00:00:00"


def _wall_cut(c: CutoutRecord, L: float, W: float, wall: float) -> Shape:
    (u, v), (w, h) = c.center_mm, c.size_mm
    depth = wall * 3
    if c.face in ("front", "back"):
        y = -wall / 2 if c.face == "front" else W + wall / 2
        return Pos(u, y, v) * Box(w, depth, h)
    x = -wall / 2 if c.face == "left" else L + wall / 2
    return Pos(x, u, v) * Box(depth, w, h)


def box_lid(
    cavity: tuple[float, float, float],
    wall: float,
    cutouts: list[CutoutRecord],
    standoffs: list[tuple[float, float, float, float]],
    out_dir: Path,
) -> dict[str, str]:
    """standoffs: (x, y, height, hole diameter) of each part mount hole. Returns artifact paths."""
    L, W, H = cavity
    P = CORNER_POST_MM
    posts = [(x, y) for x in (P / 2, L - P / 2) for y in (P / 2, W - P / 2)]

    base = Pos(-wall, -wall, -wall) * Box(
        L + 2 * wall, W + 2 * wall, H + wall, align=MIN
    )
    base -= Box(L, W, H + 1, align=MIN)
    for x, y in posts:
        base += Pos(x - P / 2, y - P / 2, 0) * Box(P, P, H, align=MIN)
    for x, y, height, d in standoffs:
        base += Pos(x, y, 0) * Cylinder(d / 2 + 1.5, height, align=BOTTOM)
    for x, y, height, d in standoffs:
        base -= Pos(x, y, 0) * Cylinder(d * 0.4, height + 1, align=BOTTOM)
    depth = min(8.0, H)
    for x, y in posts:
        base -= Pos(x, y, H - depth) * Cylinder(
            SCREW_PILOT_MM / 2, depth + 1, align=BOTTOM
        )
    for c in cutouts:
        if c.face != "top":
            base -= _wall_cut(c, L, W, wall)

    lid = Pos(-wall, -wall, H) * Box(L + 2 * wall, W + 2 * wall, wall, align=MIN)
    # Lip strips stop short of the corner posts.
    g, t, s = LIP_GAP_MM, LIP_T_MM, P + LIP_GAP_MM
    for x, y, lx, ly in (
        (s, g, L - 2 * s, t),
        (s, W - g - t, L - 2 * s, t),
        (g, s, t, W - 2 * s),
        (L - g - t, s, t, W - 2 * s),
    ):
        lid += Pos(x, y, H - LIP_MM) * Box(lx, ly, LIP_MM, align=MIN)
    for x, y in posts:
        lid -= Pos(x, y, H - 1) * Cylinder(SCREW_CLEAR_MM / 2, wall + 2, align=BOTTOM)
    for c in cutouts:
        if c.face == "top":
            (u, v), (w, h) = c.center_mm, c.size_mm
            lid -= Pos(u, v, H) * Box(w, h, 2 * (wall + LIP_MM) + 2)

    out_dir = Path(out_dir).resolve()
    artifacts = {}
    for name, shape in (("base", base), ("lid", lid)):
        stl, step = out_dir / f"{name}.stl", out_dir / f"{name}.step"
        export_stl(shape, stl)
        export_step(shape, step, timestamp=STEP_TIMESTAMP)
        artifacts |= {f"{name}_stl": str(stl), f"{name}_step": str(step)}
    return artifacts

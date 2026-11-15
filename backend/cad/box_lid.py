"""box_lid template (T11): build123d geometry for the base and lid, in the enclosure frame (base.py).

The base is an open box with the cavity floor at z=0; the lid is a plate on top at z=H with a lip that
hangs into the cavity. Both are exported where they sit when closed, so the assembly preview and the
viewer can place parts straight from the layout. Imported lazily: importing build123d takes seconds.

box_lid_shapes() also returns the bay (the closed box's outer solid), the keep-out (cavity, the
lid's path and a tunnel out of every wall opening), which a custom body built around the bay must
leave empty, and the lid's top plate, the only part of the lid a custom model may cut
(backend/cad/run_model.py). opening_paths() and path_exits() give the space each opening needs
outside the case, which run_model keeps a custom device's extra parts out of.
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
REACH_MM = 1000.0
"""How far the keep-out reaches past the box: further than any printable part."""
CABLE_REACH_MM = 15.0
"""A cable hole needs room for the cable to bend, not a plug's straight path: a stand built
further out stays solid."""
EXIT_MM = 1.0
"""Thickness of the slabs path_exits() lays on the sides of a cable hole's path."""
TOWARD_CASE = {
    "top": (2, 0),
    "front": (1, 1),
    "back": (1, 0),
    "left": (0, 1),
    "right": (0, 0),
}
"""The side of an opening's path that touches the case: (axis, 0 for its min side or 1 for max)."""
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


def _tunnel(c: CutoutRecord, L: float, W: float) -> Shape:
    """A wall opening extended outward, so nothing built outside the wall blocks it."""
    (u, v), (w, h) = c.center_mm, c.size_mm
    reach = CABLE_REACH_MM if c.feature == "cable" else REACH_MM
    if c.face in ("front", "back"):
        y = -reach / 2 if c.face == "front" else W + reach / 2
        return Pos(u, y, v) * Box(w, reach, h)
    x = -reach / 2 if c.face == "left" else L + reach / 2
    return Pos(x, u, v) * Box(reach, w, h)


def _bay(L: float, W: float, H: float, wall: float) -> Shape:
    return Pos(-wall, -wall, -wall) * Box(
        L + 2 * wall, W + 2 * wall, H + 2 * wall, align=MIN
    )


def opening_paths(
    cavity: tuple[float, float, float], wall: float, cutouts: list[CutoutRecord]
) -> list[tuple[CutoutRecord, Shape]]:
    """Outside the closed case, the space each opening needs clear: straight up from a lid opening,
    straight out of a wall opening (a cable hole: its first CABLE_REACH_MM past the inner wall)."""
    L, W, H = cavity
    bay = _bay(L, W, H, wall)
    paths = []
    for c in cutouts:
        if c.face == "top":
            (u, v), (w, h) = c.center_mm, c.size_mm
            path = Pos(u, v, H) * Box(w, h, REACH_MM, align=BOTTOM)
        else:
            path = _tunnel(c, L, W)
        paths.append((c, path - bay))
    return paths


def path_exits(c: CutoutRecord, path: Shape) -> list[Shape]:
    """EXIT_MM slabs on every side of an opening's path but the one against the case: a cable
    leaves its hole's path through one of them."""
    bb = path.bounding_box()
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    slabs = []
    for k in range(3):
        for side in (0, 1):
            if (k, side) == TOWARD_CASE[c.face]:
                continue
            a, b = list(lo), list(hi)
            a[k], b[k] = (hi[k], hi[k] + EXIT_MM) if side else (lo[k] - EXIT_MM, lo[k])
            slabs.append(Pos(*a) * Box(*(y - x for x, y in zip(a, b)), align=MIN))
    return slabs


def box_lid_shapes(
    cavity: tuple[float, float, float],
    wall: float,
    cutouts: list[CutoutRecord],
    standoffs: list[tuple[float, float, float, float]],
) -> dict[str, Shape]:
    """base, lid, plate, bay and keepout (see the module docstring), in the enclosure frame.
    standoffs: (x, y, height, hole diameter) of each part mount hole."""
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

    plate = Pos(-wall, -wall, H) * Box(L + 2 * wall, W + 2 * wall, wall, align=MIN)
    lid = plate
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

    bay = _bay(L, W, H, wall)
    keepout = Box(L, W, REACH_MM, align=MIN)  # the cavity, open upward
    keepout += Pos(-wall, -wall, H) * Box(  # the lid and the way it lifts off
        L + 2 * wall, W + 2 * wall, REACH_MM, align=MIN
    )
    for c in cutouts:
        if c.face != "top":
            keepout += _tunnel(c, L, W)
    return {"base": base, "lid": lid, "plate": plate, "bay": bay, "keepout": keepout}


def export_parts(shapes: dict[str, Shape], out_dir: Path) -> dict[str, str]:
    """STL and STEP of each shape; returns artifact paths (<name>_stl, <name>_step)."""
    out_dir = Path(out_dir).resolve()
    artifacts = {}
    for name, shape in shapes.items():
        stl, step = out_dir / f"{name}.stl", out_dir / f"{name}.step"
        export_stl(shape, stl)
        export_step(shape, step, timestamp=STEP_TIMESTAMP)
        artifacts |= {f"{name}_stl": str(stl), f"{name}_step": str(step)}
    return artifacts


def box_lid(
    cavity: tuple[float, float, float],
    wall: float,
    cutouts: list[CutoutRecord],
    standoffs: list[tuple[float, float, float, float]],
    out_dir: Path,
) -> dict[str, str]:
    """standoffs: (x, y, height, hole diameter) of each part mount hole. Returns artifact paths."""
    shapes = box_lid_shapes(cavity, wall, cutouts, standoffs)
    return export_parts({"base": shapes["base"], "lid": shapes["lid"]}, out_dir)

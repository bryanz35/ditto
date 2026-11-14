"""Printability and fit checks (T11) on build_enclosure's STLs in out_dir.

Checks: each STL is watertight; each fits the printer's build volume (backend/parts/printers/<id>.yaml,
any axis-aligned orientation); the walls are at least spec.enclosure.wall_mm; every placement is inside
the cavity, clear of the corner screw posts and of every other part.

Error codes: unknown_printer, missing_stl, not_watertight, too_big_for_printer, wall_too_thin,
part_outside_cavity, parts_overlap.
"""

import itertools
from pathlib import Path

import trimesh
import yaml

from backend.contracts.parts import PARTS_DIR, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec
from backend.tools.layout import CORNER_POST_MM, footprint

PRINTERS_DIR = PARTS_DIR / "printers"
TOL_MM = 0.01


def _placement_errors(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary
) -> list[ToolError]:
    L, W, H = layout.cavity_mm
    P = CORNER_POST_MM
    ids = {p.ref: p.part_id for p in [spec.mcu, *spec.parts]}
    errors, boxes = [], []
    for i, p in enumerate(layout.placements):
        if ids.get(p.ref) not in lib:
            errors.append(
                ToolError(
                    code="part_outside_cavity",
                    message=f"placement {p.ref} isn't a known part of this spec; rerun the layout",
                    field=f"layout.placements[{i}]",
                )
            )
            continue
        part = lib.get(ids[p.ref])
        x0, y0, x1, y1 = footprint(p, part)
        top = p.z_mm + part.board_mm.h
        if (
            x0 < -TOL_MM
            or y0 < -TOL_MM
            or x1 > L + TOL_MM
            or y1 > W + TOL_MM
            or top > H
        ):
            errors.append(
                ToolError(
                    code="part_outside_cavity",
                    message=f"{p.ref} spans x {x0:g}..{x1:g}, y {y0:g}..{y1:g}, z up to {top:g} "
                    f"mm but the cavity is {L:g} x {W:g} x {H:g} mm; rerun the layout",
                    field=f"layout.placements[{i}]",
                )
            )
        boxes.append((p.ref, (x0, y0, x1, y1)))
    boxes += [
        (f"the corner screw post at ({x:g}, {y:g})", (x, y, x + P, y + P))
        for x in (0.0, L - P)
        for y in (0.0, W - P)
    ]
    for (ra, a), (rb, b) in itertools.combinations(boxes, 2):
        if (
            min(a[2], b[2]) - max(a[0], b[0]) > TOL_MM
            and min(a[3], b[3]) - max(a[1], b[1]) > TOL_MM
        ):
            errors.append(
                ToolError(
                    code="parts_overlap",
                    message=f"{ra} and {rb} overlap seen from above; rerun the layout",
                    field="layout",
                )
            )
    return errors


def check_enclosure(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path, printer_id: str
) -> ToolResult:
    errors = _placement_errors(spec, layout, lib)
    profile = PRINTERS_DIR / f"{printer_id}.yaml"
    volume = (
        sorted(yaml.safe_load(profile.read_text())["build_volume_mm"])
        if profile.is_file()
        else None
    )
    if volume is None:
        known = sorted(p.stem for p in PRINTERS_DIR.glob("*.yaml"))
        errors.append(
            ToolError(
                code="unknown_printer",
                message=f"no printer profile {printer_id!r}; known profiles: {', '.join(known)}",
                field="user.printer",
            )
        )
    watertight = fits = True
    for name in ("base", "lid"):
        path = Path(out_dir) / f"{name}.stl"
        if not path.is_file():
            errors.append(
                ToolError(
                    code="missing_stl",
                    message=f"{path} doesn't exist; run build_enclosure first",
                )
            )
            watertight = fits = False
            continue
        mesh = trimesh.load_mesh(path)
        if not mesh.is_watertight:
            watertight = False
            errors.append(
                ToolError(
                    code="not_watertight",
                    message=f"{name}.stl has holes or open edges, so slicers may print it wrong",
                    hint="a cutout probably grazes an edge; change clearance_mm or wall_mm",
                )
            )
        size = sorted(float(e) for e in mesh.extents)
        if volume and any(s > v for s, v in zip(size, volume)):
            fits = False
            errors.append(
                ToolError(
                    code="too_big_for_printer",
                    message=f"{name} is {' x '.join(f'{e:.1f}' for e in mesh.extents)} mm, "
                    f"too big for {printer_id}'s {' x '.join(f'{v:g}' for v in volume)} mm "
                    f"build volume in any orientation",
                    hint="use fewer or smaller parts, or a printer with a larger bed",
                )
            )
        if name == "base":
            wall = spec.enclosure.wall_mm
            thinnest = min(
                (float(mesh.extents[i]) - layout.cavity_mm[i]) / 2 for i in (0, 1)
            )
            if thinnest < wall - TOL_MM:
                errors.append(
                    ToolError(
                        code="wall_too_thin",
                        message=f"the base walls are {thinnest:.2f} mm thick but "
                        f"enclosure.wall_mm asks for {wall:g} mm; rebuild the enclosure",
                        field="enclosure.wall_mm",
                    )
                )
    return ToolResult(
        ok=not errors,
        errors=errors,
        data={"watertight": watertight, "fits_printer": fits and volume is not None},
    )

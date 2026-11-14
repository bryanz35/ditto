"""Printability and fit checks (T11) on the printed parts' STLs in out_dir.

The parts are the ones cad/manifest.json lists in `prints` (base and lid when there's no manifest).
Checks: each STL is watertight, one connected piece, and fits the printer's build volume
(backend/parts/printers/<id>.yaml, any axis-aligned orientation); a print-only part has a flat face on
the bed; the box walls are at least spec.enclosure.wall_mm; every placement is inside the cavity,
clear of the corner screw posts and of every other part (devices only: layout is None otherwise).

Error codes: unknown_printer, missing_stl, not_watertight, loose_pieces, no_flat_base,
too_big_for_printer, wall_too_thin, part_outside_cavity, parts_overlap.
"""

import itertools
from pathlib import Path

import numpy as np
import trimesh
import yaml

from backend.contracts.artifacts import EnclosureManifest
from backend.contracts.parts import PARTS_DIR, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec
from backend.tools.layout import CORNER_POST_MM, footprint

PRINTERS_DIR = PARTS_DIR / "printers"
TOL_MM = 0.01
MIN_BED_CONTACT_MM2 = 25.0


def _placement_errors(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary
) -> list[ToolError]:
    L, W, H = layout.cavity_mm
    P = CORNER_POST_MM
    ids = {p.ref: p.part_id for p in spec.instances}
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


def _bed_contact_mm2(mesh: trimesh.Trimesh) -> float:
    """Area of the downward faces that lie on the part's lowest plane."""
    z0 = mesh.bounds[0][2]
    down = mesh.face_normals[:, 2] < -0.99
    low = np.all(np.abs(mesh.vertices[mesh.faces][:, :, 2] - z0) < 0.05, axis=1)
    return float(mesh.area_faces[down & low].sum())


def _load(path: Path) -> trimesh.Trimesh:
    """The STL without the zero-area triangles OCCT writes at poles and fillet corners: trimesh
    counts those as holes, slicers ignore them."""
    mesh = trimesh.load_mesh(path)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.merge_vertices()
    return mesh


def _pieces(mesh: trimesh.Trimesh) -> int:
    """Separate solids; a sealed inner void is a negative-volume shell, not a piece."""
    return sum(
        1
        for b in mesh.split(only_watertight=False, repair=False, engine="scipy")
        if b.volume > 0
    )


def _print_names(out_dir: Path) -> list[str]:
    path = Path(out_dir) / "manifest.json"
    if path.is_file():
        prints = EnclosureManifest.model_validate_json(path.read_text()).prints
        if prints:
            return sorted(prints)
    return ["base", "lid"]


def check_enclosure(
    spec: ProjectSpec,
    layout: Layout | None,
    lib: PartLibrary,
    out_dir: Path,
    printer_id: str,
) -> ToolResult:
    errors = _placement_errors(spec, layout, lib) if layout else []
    print_only = spec.mcu is None
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
    for name in _print_names(out_dir):
        path = Path(out_dir) / f"{name}.stl"
        if not path.is_file():
            errors.append(
                ToolError(
                    code="missing_stl",
                    message=f"{path} doesn't exist; build the enclosure first",
                )
            )
            watertight = fits = False
            continue
        mesh = _load(path)
        if not mesh.is_watertight:
            watertight = False
            errors.append(
                ToolError(
                    code="not_watertight",
                    message=f"{name}.stl has holes or open edges, so slicers may print it wrong",
                    hint="a cutout probably grazes an edge; change clearance_mm or wall_mm"
                    if layout
                    else "overlap touching solids by at least 0.5 mm instead of meeting at "
                    "an edge, and avoid zero-thickness features",
                )
            )
        if (pieces := _pieces(mesh)) > 1:
            errors.append(
                ToolError(
                    code="loose_pieces",
                    message=f"{name}.stl is {pieces} separate pieces that would print loose",
                    hint="make the body overlap BAY by at least 1 mm"
                    if layout
                    else "overlap the pieces by at least 1 mm, or give each its own entry in "
                    "`parts`",
                    field="enclosure.code",
                )
            )
        if print_only and _bed_contact_mm2(mesh) < MIN_BED_CONTACT_MM2:
            errors.append(
                ToolError(
                    code="no_flat_base",
                    message=f"{name}.stl touches the print bed with less than "
                    f"{MIN_BED_CONTACT_MM2:g} mm² of flat face, so it would tip or need supports",
                    hint="rotate the part so a flat face is lowest and move it to sit on z=0",
                    field="enclosure.code",
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
                    hint="use fewer or smaller parts, or a printer with a larger bed"
                    if layout
                    else "make it smaller or split it into parts that join (each its own "
                    "entry in `parts`)",
                )
            )
        if name == "base" and layout:
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

"""Enclosure build from the box_lid template (T11).

Openings come from the layout: every top or wall feature of an inside part gets a cutout where the part
sits, and every external part gets a cable hole in the back wall. Writes base/lid STL and STEP plus
cad/manifest.json (EnclosureManifest), all in the enclosure frame (see backend/contracts/base.py).

Error codes: layout_mismatch, cad_build_failed.
"""

from pathlib import Path

from backend.contracts.artifacts import CutoutRecord, EnclosureManifest
from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec, mounting
from backend.tools.layout import LIP_MM, _r, inside_parts

CABLE_HOLE_MM = 6.0


def enclosure_manifest(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary
) -> EnclosureManifest:
    """Pure: which opening serves which part feature. Assumes the layout matches the spec."""
    L, W, H = layout.cavity_mm
    wall = spec.enclosure.wall_mm
    insts = {p.ref: p for p in spec.instances}
    cutouts = []
    for p in layout.placements:
        for f in lib.get(insts[p.ref].part_id).features:
            u, v = f.offset_mm
            if f.face == "top":
                center = (p.x_mm + u, p.y_mm + v)
            elif f.face == p.against_wall:
                along = p.x_mm if f.face in ("front", "back") else p.y_mm
                center = (along + u, p.z_mm + v)
            else:
                continue  # compute_layout already warned: the part doesn't touch that wall
            cutouts.append(
                CutoutRecord(
                    for_ref=p.ref,
                    feature=f.kind,
                    face=f.face,
                    center_mm=(_r(center[0]), _r(center[1])),
                    size_mm=f.size_mm,
                )
            )
    external = sorted(p.ref for p in spec.instances if mounting(p, lib) == "external")
    for i, ref in enumerate(external):
        cutouts.append(
            CutoutRecord(
                for_ref=ref,
                feature="cable",
                face="back",
                center_mm=(_r(L * (i + 1) / (len(external) + 1)), _r(H / 2)),
                size_mm=(CABLE_HOLE_MM, CABLE_HOLE_MM),
            )
        )
    outer_l, outer_w = _r(L + 2 * wall), _r(W + 2 * wall)
    return EnclosureManifest(
        spec_rev=spec.rev,
        template=spec.enclosure.template,
        wall_mm=wall,
        cavity_mm=layout.cavity_mm,
        outer_mm=(outer_l, outer_w, _r(H + 2 * wall)),
        cutouts=sorted(cutouts, key=lambda c: (c.for_ref, c.feature, c.face)),
        prints={
            "base": (outer_l, outer_w, _r(H + wall)),
            "lid": (outer_l, outer_w, _r(wall + LIP_MM)),
        },
        unmeasured_refs=sorted(
            p.ref
            for p in spec.instances
            if lib.get(p.part_id).dims_source != "measured"
        ),
    )


def standoffs(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary
) -> list[tuple[float, float, float, float]]:
    """(x, y, height, hole diameter) of every raised part's mount holes, enclosure frame."""
    insts = {p.ref: p for p in spec.instances}
    return [
        (p.x_mm + h.x_mm, p.y_mm + h.y_mm, p.z_mm, h.d_mm)
        for p in layout.placements
        for h in lib.get(insts[p.ref].part_id).mount_holes
        if p.z_mm > 0
    ]


def layout_error(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary
) -> ToolResult | None:
    """A failed result when the layout doesn't place exactly the spec's inside parts."""
    placed = sorted(p.ref for p in layout.placements)
    known = all(p.part_id in lib for p in spec.instances)
    expected = sorted(p.ref for p in inside_parts(spec, lib)) if known else None
    if placed == expected:
        return None
    return ToolResult(
        ok=False,
        errors=[
            ToolError(
                code="layout_mismatch",
                message=f"the layout places {placed} but the spec's inside parts are "
                f"{expected}; rerun compute_layout on this spec first",
                field="layout",
            )
        ],
    )


def build_enclosure(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    if mismatch := layout_error(spec, layout, lib):
        return mismatch
    manifest = enclosure_manifest(spec, layout, lib)
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from backend.cad.box_lid import box_lid

        artifacts = box_lid(
            layout.cavity_mm,
            manifest.wall_mm,
            manifest.cutouts,
            standoffs(spec, layout, lib),
            out_dir,
        )
    # The CAD kernel fails in many ways; report it as a ToolResult, don't crash the run.
    except Exception as e:  # noqa: BLE001
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="cad_build_failed",
                    message=f"build123d failed building the box_lid enclosure: {e!r}",
                    hint="check wall_mm, clearance_mm and the parts' feature sizes",
                )
            ],
        )
    path = out_dir / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return ToolResult(
        ok=True,
        artifacts={**artifacts, "manifest": str(path)},
        data={"manifest": manifest.model_dump(mode="json")},
    )

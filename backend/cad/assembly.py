"""Assembly preview, assembly.glb (T25): the enclosure with every inside part shown where it sits.

Loads the base and lid STLs that build_enclosure wrote into the same out_dir (they are already in the
enclosure frame, closed), raises the lid by LID_LIFT_MM for an exploded view, and adds each part as a
box of its board_mm at its Placement. The scene stays in the enclosure frame (mm, z up, see
backend/contracts/base.py), like the STLs. Nodes are named "base", "lid" and each part's ref; part
meshes carry glTF extras (three.js userData) part_id, category, dims_source and unmeasured.

Error codes: layout_mismatch, enclosure_missing.
"""

from pathlib import Path

import trimesh

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec

LID_LIFT_MM = 20.0
CATEGORY_COLORS = {
    "mcu": (30, 110, 60, 255),
    "sensor": (40, 100, 200, 255),
    "display": (25, 25, 40, 255),
    "light": (240, 200, 40, 255),
    "input": (240, 140, 30, 255),
    "output": (200, 50, 50, 255),
    "power": (120, 120, 120, 255),
}
SHELL_COLOR = (220, 220, 215, 255)


def _translate(x: float, y: float, z: float):
    return trimesh.transformations.translation_matrix((x, y, z))


def build_assembly(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    insts = {p.ref: p for p in spec.instances}
    placed = sorted(p.ref for p in layout.placements)
    known = all(p.part_id in lib for p in insts.values())
    inside = (
        sorted(r for r, p in insts.items() if lib.get(p.part_id).mounting == "inside")
        if known
        else None
    )
    if placed != inside:
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="layout_mismatch",
                    message=f"the layout places {placed} but the spec's inside parts are "
                    f"{inside}; rerun compute_layout on this spec first",
                    field="layout",
                )
            ],
        )

    out_dir = Path(out_dir).resolve()
    shells = {}
    for name in ("base", "lid"):
        path = out_dir / f"{name}.stl"
        try:
            shells[name] = trimesh.load(path, file_type="stl", force="mesh")
        # Missing or corrupt STL: either way the enclosure stage has to run first.
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                ok=False,
                errors=[
                    ToolError(
                        code="enclosure_missing",
                        message=f"can't read {path.name} in {out_dir} ({e}); run "
                        "build_enclosure into this out_dir before build_assembly",
                    )
                ],
            )

    scene = trimesh.Scene()
    scene.metadata = {"spec_rev": spec.rev}
    for name, mesh in shells.items():
        mesh.visual.face_colors = SHELL_COLOR
        mesh.metadata = {}  # drop the STL header, which would land in the glTF extras
        lift = LID_LIFT_MM if name == "lid" else 0.0
        scene.add_geometry(
            mesh, node_name=name, geom_name=name, transform=_translate(0, 0, lift)
        )
    for p in layout.placements:
        part = lib.get(insts[p.ref].part_id)
        l, w, h = part.board_mm.l, part.board_mm.w, part.board_mm.h
        if p.rot_deg in (90, 270):
            l, w = w, l
        box = trimesh.creation.box(extents=(l, w, h))
        box.visual.face_colors = CATEGORY_COLORS[part.category]
        box.metadata = {
            "part_id": part.id,
            "category": part.category,
            "dims_source": part.dims_source,
            "unmeasured": part.dims_source != "measured",
        }
        scene.add_geometry(
            box,
            node_name=p.ref,
            geom_name=p.ref,
            transform=_translate(p.x_mm + l / 2, p.y_mm + w / 2, p.z_mm + h / 2),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    glb = out_dir / "assembly.glb"
    glb.write_bytes(scene.export(file_type="glb"))
    return ToolResult(ok=True, artifacts={"assembly_glb": str(glb)})

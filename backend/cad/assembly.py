"""Assembly preview, assembly.glb (T25): the enclosure with every inside part shown where it sits.

Loads the base and lid STLs that build_enclosure wrote into the same out_dir (they are already in the
enclosure frame, closed), raises the lid by LID_LIFT_MM for an exploded view, and adds each part as a
box of its board_mm at its Placement. A custom device's extra printed parts and mounted external parts
go where cad/manifest.json's `assembled` and `mounts` put them. The scene stays in the enclosure frame
(mm, z up, see backend/contracts/base.py), like the STLs. Nodes are named "base", "lid", "print_<name>"
for each extra printed part and each part's ref; part meshes carry glTF extras (three.js userData)
part_id, category, dims_source and unmeasured (and mounted_on for a mounted part), printed parts
printed: true.

Error codes: layout_mismatch, enclosure_missing.
"""

from pathlib import Path

import numpy as np
import trimesh

from backend.contracts.artifacts import EnclosureManifest
from backend.contracts.parts import PartDef, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec, mounting

LID_LIFT_MM = 20.0
CATEGORY_COLORS = {
    "mcu": (30, 110, 60, 255),
    "sensor": (40, 100, 200, 255),
    "display": (25, 25, 40, 255),
    "light": (240, 200, 40, 255),
    "input": (240, 140, 30, 255),
    "output": (200, 50, 50, 255),
    "motor": (150, 60, 200, 255),
    "power": (120, 120, 120, 255),
}
SHELL_COLOR = (220, 220, 215, 255)


def _translate(x: float, y: float, z: float):
    return trimesh.transformations.translation_matrix((x, y, z))


def _box(part: PartDef, l: float, w: float, h: float, **extra) -> trimesh.Trimesh:
    """A part as a box of l x w x h centred on its origin, coloured and tagged for the viewer."""
    box = trimesh.creation.box(extents=(l, w, h))
    box.visual.face_colors = CATEGORY_COLORS[part.category]
    box.metadata = {
        "part_id": part.id,
        "category": part.category,
        "dims_source": part.dims_source,
        "unmeasured": part.dims_source != "measured",
        **extra,
    }
    return box


def build_assembly(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    insts = {p.ref: p for p in spec.instances}
    placed = sorted(p.ref for p in layout.placements)
    known = all(p.part_id in lib for p in insts.values())
    inside = (
        sorted(r for r, p in insts.items() if mounting(p, lib) == "inside")
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
    path = out_dir / "manifest.json"
    manifest = (
        EnclosureManifest.model_validate_json(path.read_text())
        if path.is_file()
        else None
    )
    assembled = manifest.assembled if manifest else {}
    shells = {}
    for name in ("base", "lid", *sorted(assembled)):
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
        # drop the STL header, which would land in the glTF extras
        mesh.metadata = {"printed": True} if name in assembled else {}
        if name in assembled:
            node = f"print_{name}"
            transform = np.array(assembled[name].transform).reshape(4, 4)
        else:
            node, transform = (
                name,
                _translate(0, 0, LID_LIFT_MM if name == "lid" else 0.0),
            )
        scene.add_geometry(mesh, node_name=node, geom_name=node, transform=transform)
    for p in layout.placements:
        part = lib.get(insts[p.ref].part_id)
        l, w, h = part.board_mm.l, part.board_mm.w, part.board_mm.h
        if p.rot_deg in (90, 270):
            l, w = w, l
        scene.add_geometry(
            _box(part, l, w, h),
            node_name=p.ref,
            geom_name=p.ref,
            transform=_translate(p.x_mm + l / 2, p.y_mm + w / 2, p.z_mm + h / 2),
        )
    for ref, mount in sorted((manifest.mounts if manifest else {}).items()):
        if ref not in insts:
            continue  # the spec dropped it since the enclosure was built
        part = lib.get(insts[ref].part_id)
        l, w, h = part.board_mm.l, part.board_mm.w, part.board_mm.h
        place = np.array(mount.transform).reshape(4, 4)
        scene.add_geometry(
            _box(part, l, w, h, mounted_on=mount.on),
            node_name=ref,
            geom_name=ref,
            transform=place @ _translate(l / 2, w / 2, h / 2),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    glb = out_dir / "assembly.glb"
    glb.write_bytes(scene.export(file_type="glb"))
    return ToolResult(ok=True, artifacts={"assembly_glb": str(glb)})

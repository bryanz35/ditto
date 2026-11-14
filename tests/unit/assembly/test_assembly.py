"""Scene-graph tests for build_assembly on the fixture run's layout and enclosure STLs."""

import pytest
import trimesh

from backend.cad.assembly import LID_LIFT_MM, build_assembly


def _scene(spec, layout, lib, cad_dir) -> trimesh.Scene:
    result = build_assembly(spec, layout, lib, cad_dir)
    assert result.ok, result.errors
    assert result.artifacts == {"assembly_glb": str(cad_dir / "assembly.glb")}
    return trimesh.load(cad_dir / "assembly.glb")


def _world(scene: trimesh.Scene, node: str) -> trimesh.Trimesh:
    transform, geom = scene.graph[node]
    return scene.geometry[geom].copy().apply_transform(transform)


def test_nodes_one_per_part_plus_base_and_lid(spec, layout, lib, cad_dir):
    scene = _scene(spec, layout, lib, cad_dir)
    refs = {p.ref for p in layout.placements}
    assert sorted(scene.graph.nodes_geometry) == sorted(refs | {"base", "lid"})
    base, lid = _world(scene, "base").bounds, _world(scene, "lid").bounds
    assert lid[0][2] == pytest.approx(layout.cavity_mm[2] + LID_LIFT_MM)
    assert lid[0][2] > base[1][2]


def test_parts_inside_cavity_at_layout_position(spec, layout, lib, cad_dir):
    scene = _scene(spec, layout, lib, cad_dir)
    insts = {p.ref: p for p in spec.instances}
    L, W, H = layout.cavity_mm
    for p in layout.placements:
        dims = lib.get(insts[p.ref].part_id).board_mm
        lo, hi = _world(scene, p.ref).bounds
        assert lo == pytest.approx([p.x_mm, p.y_mm, p.z_mm], abs=1e-6), p.ref
        assert hi == pytest.approx(
            [p.x_mm + dims.l, p.y_mm + dims.w, p.z_mm + dims.h], abs=1e-6
        ), p.ref
        assert (lo >= -1e-6).all() and (hi <= [L + 1e-6, W + 1e-6, H + 1e-6]).all()


def test_rotation_swaps_footprint(spec, layout, lib, cad_dir):
    placements = [
        p.model_copy(update={"rot_deg": 90}) if p.ref == "env1" else p
        for p in layout.placements
    ]
    rotated = layout.model_copy(update={"placements": placements})
    env = next(p for p in placements if p.ref == "env1")
    dims = lib.get("bme280_breakout").board_mm
    lo, hi = _world(_scene(spec, rotated, lib, cad_dir), "env1").bounds
    assert lo == pytest.approx([env.x_mm, env.y_mm, env.z_mm], abs=1e-6)
    assert hi - lo == pytest.approx([dims.w, dims.l, dims.h], abs=1e-6)


def test_unmeasured_flag_in_metadata(spec, layout, lib, cad_dir):
    scene = _scene(spec, layout, lib, cad_dir)
    insts = {p.ref: p for p in spec.instances}
    for p in layout.placements:
        part = lib.get(insts[p.ref].part_id)
        meta = scene.geometry[scene.graph[p.ref][1]].metadata
        assert meta["part_id"] == part.id
        assert meta["category"] == part.category
        assert meta["unmeasured"] is (part.dims_source != "measured")


def test_missing_enclosure_returns_error(spec, layout, lib, tmp_path):
    result = build_assembly(spec, layout, lib, tmp_path)
    assert not result.ok
    assert [e.code for e in result.errors] == ["enclosure_missing"]
    assert not (tmp_path / "assembly.glb").exists()


def test_layout_mismatch_returns_error(spec, layout, lib, cad_dir):
    short = layout.model_copy(update={"placements": layout.placements[1:]})
    result = build_assembly(spec, short, lib, cad_dir)
    assert not result.ok
    assert [e.code for e in result.errors] == ["layout_mismatch"]


def test_glb_byte_identical(spec, layout, lib, cad_dir):
    _scene(spec, layout, lib, cad_dir)
    first = (cad_dir / "assembly.glb").read_bytes()
    _scene(spec, layout, lib, cad_dir)
    assert (cad_dir / "assembly.glb").read_bytes() == first

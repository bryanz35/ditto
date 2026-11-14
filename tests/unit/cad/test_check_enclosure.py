import trimesh

from backend.contracts.spec import Layout
from backend.tools.check_enclosure import check_enclosure
from backend.tools.layout import layout_parts


def _write_box(out_dir, layout, wall=2.0, extents=None):
    L, W, H = layout.cavity_mm
    box = trimesh.creation.box(
        extents=extents or (L + 2 * wall, W + 2 * wall, H + wall)
    )
    box.export(out_dir / "base.stl")
    box.export(out_dir / "lid.stl")


def _codes(result):
    return sorted({e.code for e in result.errors})


def test_good_meshes_pass(spec, lib, tmp_path):
    layout, _ = layout_parts(spec, lib)
    _write_box(tmp_path, layout)
    result = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert result.ok, result.errors
    assert result.data == {"watertight": True, "fits_printer": True}


def test_open_mesh_is_not_watertight(spec, lib, tmp_path):
    layout, _ = layout_parts(spec, lib)
    _write_box(tmp_path, layout)
    mesh = trimesh.load_mesh(tmp_path / "lid.stl")
    mesh.update_faces(list(range(1, len(mesh.faces))))  # drop a triangle
    mesh.export(tmp_path / "lid.stl")
    result = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert _codes(result) == ["not_watertight"] and not result.data["watertight"]


def test_too_big_and_thin_walls(spec, lib, tmp_path):
    layout, _ = layout_parts(spec, lib)
    _write_box(tmp_path, layout, extents=(200, layout.cavity_mm[1] + 1, 20))
    result = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert _codes(result) == ["too_big_for_printer", "wall_too_thin"]
    assert "180" in result.errors[0].message and not result.data["fits_printer"]


def test_unknown_printer_and_missing_stl(spec, lib, tmp_path):
    layout, _ = layout_parts(spec, lib)
    result = check_enclosure(spec, layout, lib, tmp_path, "nope")
    assert _codes(result) == ["missing_stl", "unknown_printer"]
    assert (
        "generic"
        in next(e for e in result.errors if e.code == "unknown_printer").message
    )


def test_overlapping_and_outside_placements(spec, lib, tmp_path):
    layout, _ = layout_parts(spec, lib)
    _write_box(tmp_path, layout)
    moved = [
        p.model_copy(update={"x_mm": 0.0, "y_mm": 0.0}) if p.ref == "oled1" else p
        for p in layout.placements
    ]
    moved[0] = moved[0].model_copy(update={"x_mm": 500.0})
    bad = Layout(placements=moved, cavity_mm=layout.cavity_mm)
    result = check_enclosure(spec, bad, lib, tmp_path, "generic")
    assert _codes(result) == ["part_outside_cavity", "parts_overlap"]
    assert any("oled1" in e.message and "esp32" in e.message for e in result.errors)

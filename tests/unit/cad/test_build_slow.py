"""Full CAD builds with build123d (make test-slow)."""

import pytest
import trimesh

from backend.contracts.spec import Layout
from backend.tools.build_enclosure import build_enclosure
from backend.tools.check_enclosure import check_enclosure
from backend.tools.layout import compute_layout
from tests.unit.cad.conftest import big_display_case, four_walls_case

pytestmark = pytest.mark.slow


def _build(spec, lib, out_dir):
    layout = Layout.model_validate(compute_layout(spec, lib, out_dir).data["layout"])
    result = build_enclosure(spec, layout, lib, out_dir)
    assert result.ok, result.errors
    return layout, result


def test_plant_monitor_builds_watertight_and_fits_generic(spec, lib, tmp_path):
    layout, result = _build(spec, lib, tmp_path)
    assert sorted(result.artifacts) == [
        "base_step",
        "base_stl",
        "lid_step",
        "lid_stl",
        "manifest",
    ]
    assert all(str(tmp_path) in p for p in result.artifacts.values())
    check = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert check.ok, check.errors
    assert check.data == {"watertight": True, "fits_printer": True}


def test_build_manifest_byte_identical(spec, lib, tmp_path):
    for d in "ab":
        _build(spec, lib, tmp_path / d)
    for name in ("manifest.json", "layout.json", "base.step", "lid.step"):
        a, b = (tmp_path / d / name for d in "ab")
        assert a.read_bytes() == b.read_bytes(), name


@pytest.mark.parametrize("case", [big_display_case, four_walls_case])
def test_variants_build_and_pass_checks(case, spec, lib, tmp_path):
    lib, spec = case(lib, spec)
    layout, _ = _build(spec, lib, tmp_path)
    check = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert check.ok, check.errors


def test_cutouts_open_the_walls(spec, lib, tmp_path):
    """Each wall cutout leaves its four corners as vertices on the wall's outer face."""
    _, result = _build(spec, lib, tmp_path)
    verts = {
        tuple(round(float(c), 2) for c in v)
        for v in trimesh.load_mesh(result.artifacts["base_stl"]).vertices
    }
    manifest = result.data["manifest"]
    L, W, _ = manifest["cavity_mm"]
    wall = manifest["wall_mm"]
    walls = {
        "left": (0, -wall),
        "right": (0, L + wall),
        "front": (1, -wall),
        "back": (1, W + wall),
    }
    checked = 0
    for c in manifest["cutouts"]:
        if c["face"] not in walls:
            continue
        axis, plane = walls[c["face"]]
        (u, v), (w, h) = c["center_mm"], c["size_mm"]
        for du in (-w / 2, w / 2):
            for dv in (-h / 2, h / 2):
                point = [0.0, 0.0, round(v + dv, 2)]
                point[axis], point[1 - axis] = round(plane, 2), round(u + du, 2)
                assert tuple(point) in verts, (c, point)
        checked += 1
    assert checked == 2  # the esp32 USB port and the soil probe cable

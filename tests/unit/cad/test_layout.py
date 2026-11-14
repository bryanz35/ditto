import itertools

import pytest

from backend.contracts.spec import Layout
from backend.tools.layout import CORNER_POST_MM, compute_layout, footprint, part_wall
from tests.unit.cad.conftest import GOLDEN, big_display_case, four_walls_case


def _layout(spec, lib, out_dir) -> Layout:
    result = compute_layout(spec, lib, out_dir)
    assert result.ok, result.errors
    return Layout.model_validate(result.data["layout"])


def _cases(lib, spec):
    return {
        "plant_monitor": (lib, spec),
        "four_walls": four_walls_case(lib, spec),
        "big_display": big_display_case(lib, spec),
    }


def test_plant_monitor_matches_golden(spec, lib, tmp_path):
    result = compute_layout(spec, lib, tmp_path)
    golden = GOLDEN / "plant_monitor_layout.json"
    assert (tmp_path / "layout.json").read_text() == golden.read_text()
    assert result.artifacts == {
        "layout_json": str((tmp_path / "layout.json").resolve())
    }


def test_layout_byte_identical(spec, lib, tmp_path):
    compute_layout(spec, lib, tmp_path / "a")
    compute_layout(spec, lib, tmp_path / "b")
    a, b = (tmp_path / d / "layout.json" for d in "ab")
    assert a.read_bytes() == b.read_bytes()


@pytest.mark.parametrize("case", ["plant_monitor", "four_walls", "big_display"])
def test_parts_inside_cavity_without_overlaps(case, spec, lib, tmp_path):
    lib, spec = _cases(lib, spec)[case]
    layout = _layout(spec, lib, tmp_path)
    L, W, H = layout.cavity_mm
    refs = {p.ref: p.part_id for p in spec.instances}
    posts = [
        (x, y, x + CORNER_POST_MM, y + CORNER_POST_MM)
        for x in (0, L - CORNER_POST_MM)
        for y in (0, W - CORNER_POST_MM)
    ]
    boxes = []
    for p in layout.placements:
        part = lib.get(refs[p.ref])
        x0, y0, x1, y1 = footprint(p, part)
        assert 0 <= x0 and 0 <= y0 and x1 <= L and y1 <= W, p.ref
        assert p.z_mm + part.board_mm.h <= H, p.ref
        boxes.append((p.ref, (x0, y0, x1, y1)))
    boxes += [(f"post{i}", b) for i, b in enumerate(posts)]
    for (ra, a), (rb, b) in itertools.combinations(boxes, 2):
        apart = a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
        assert apart, (ra, rb)


@pytest.mark.parametrize("case", ["plant_monitor", "four_walls"])
def test_wall_facing_features_touch_their_wall(case, spec, lib, tmp_path):
    lib, spec = _cases(lib, spec)[case]
    layout = _layout(spec, lib, tmp_path)
    L, W, _ = layout.cavity_mm
    refs = {p.ref: p.part_id for p in spec.instances}
    walls = set()
    for p in layout.placements:
        part = lib.get(refs[p.ref])
        assert p.against_wall == part_wall(part)
        x0, y0, x1, y1 = footprint(p, part)
        touch = {"left": x0 == 0, "front": y0 == 0, "right": x1 == L, "back": y1 == W}
        if p.against_wall:
            walls.add(p.against_wall)
            assert touch[p.against_wall], p.ref
    if case == "four_walls":
        assert walls == {"left", "right", "front", "back"}


def test_external_parts_get_no_placement(spec, lib, tmp_path):
    refs = [p.ref for p in _layout(spec, lib, tmp_path).placements]
    assert refs == ["buzzer1", "env1", "esp32", "oled1"]  # soil1 is external


def test_larger_display_grows_cavity(spec, lib, tmp_path):
    small = _layout(spec, lib, tmp_path / "small")
    big = _layout(*reversed(big_display_case(lib, spec)), tmp_path / "big")
    assert all(b >= s for b, s in zip(big.cavity_mm, small.cavity_mm))
    assert big.cavity_mm != small.cavity_mm


def test_unknown_part_is_an_error(spec, lib, tmp_path):
    parts = [spec.parts[0].model_copy(update={"part_id": "nope"}), *spec.parts[1:]]
    result = compute_layout(spec.model_copy(update={"parts": parts}), lib, tmp_path)
    assert not result.ok
    assert [(e.code, e.field) for e in result.errors] == [
        ("unknown_part", "parts[0].part_id")
    ]
    assert (
        "nope" in result.errors[0].message and not (tmp_path / "layout.json").exists()
    )


def test_feature_on_another_wall_warns(spec, lib, tmp_path):
    lib, spec = four_walls_case(lib, spec)
    part = lib.get("t_left0")
    two = part.model_copy(
        update={
            "features": [
                *part.features,
                part.features[0].model_copy(update={"face": "front"}),
            ]
        }
    )
    lib.parts["t_left0"] = two
    result = compute_layout(spec, lib, tmp_path)
    assert result.ok
    assert [e.code for e in result.errors] == ["feature_not_reachable"]
    assert result.errors[0].severity == "warning"

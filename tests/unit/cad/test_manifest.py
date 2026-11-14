from backend.contracts.spec import Layout
from backend.tools.build_enclosure import build_enclosure, enclosure_manifest
from backend.tools.layout import layout_parts
from tests.unit.cad.conftest import big_display_case, four_walls_case


def _manifest(spec, lib):
    layout, _ = layout_parts(spec, lib)
    return layout, enclosure_manifest(spec, layout, lib)


def test_manifest_byte_identical(spec, lib):
    a = _manifest(spec, lib)[1].model_dump_json(indent=2)
    b = _manifest(spec, lib)[1].model_dump_json(indent=2)
    assert a == b


def test_plant_monitor_cutouts(spec, lib):
    layout, m = _manifest(spec, lib)
    got = {(c.for_ref, c.feature, c.face) for c in m.cutouts}
    assert got == {
        ("buzzer1", "sound", "top"),
        ("env1", "vent", "top"),
        ("esp32", "usb", "left"),
        ("oled1", "display_window", "top"),
        ("soil1", "cable", "back"),
    }
    oled = next(p for p in layout.placements if p.ref == "oled1")
    window = next(c for c in m.cutouts if c.for_ref == "oled1")
    assert window.center_mm == (oled.x_mm + 14.0, oled.y_mm + 12.5)
    assert m.spec_rev == spec.rev and m.unmeasured_refs == sorted(
        ["buzzer1", "env1", "esp32", "oled1", "soil1"]
    )
    L, W, H = m.cavity_mm
    assert m.outer_mm == (L + 4, W + 4, H + 4)


def test_every_wall_feature_has_a_cutout_on_its_wall(spec, lib):
    lib, spec = four_walls_case(lib, spec)
    _, m = _manifest(spec, lib)
    for wall in ("left", "right", "front", "back"):
        assert any(c.face == wall and c.feature == "button" for c in m.cutouts), wall


def test_larger_display_moves_window_cutout(spec, lib):
    small = _manifest(spec, lib)[1]
    big_lib, big_spec = big_display_case(lib, spec)
    big = _manifest(big_spec, big_lib)[1]
    assert all(b >= s for b, s in zip(big.cavity_mm, small.cavity_mm))
    assert big.cavity_mm != small.cavity_mm
    win = {
        name: next(c for c in m.cutouts if c.feature == "display_window")
        for name, m in (("small", small), ("big", big))
    }
    assert win["big"].center_mm != win["small"].center_mm
    assert win["big"].size_mm == (30.0, 15.0)


def test_layout_for_another_spec_is_rejected(spec, lib, tmp_path):
    layout = Layout(placements=[], cavity_mm=(10, 10, 10))
    result = build_enclosure(spec, layout, lib, tmp_path)
    assert not result.ok and result.errors[0].code == "layout_mismatch"
    assert not list(tmp_path.iterdir())

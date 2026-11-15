import types
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.contracts.spec import EnclosureSpec, ProjectSpec
from backend.tools import custom_model
from backend.tools.check_enclosure import check_enclosure
from backend.tools.custom_model import FORBIDDEN_ATTRS, build_custom_model, check_source

ROOT = Path(__file__).resolve().parents[3]
BOOK = ProjectSpec.model_validate_json(
    (ROOT / "fixtures" / "specs" / "book_holder.json").read_text()
)


def with_code(code: str) -> ProjectSpec:
    enclosure = EnclosureSpec(template="custom", code=code)
    return BOOK.model_copy(update={"enclosure": enclosure})


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from build123d import *\nos.system('ls')",
        "import build123d as bd\nbd.os.system('ls')",
        "from build123d import export_stl",
        "import build123d\nbuild123d.exporters3d",
        "x = (1).__class__.__subclasses__()",
        "open('/etc/passwd')",
        "from . import secrets",
        "__builtins__",
    ],
)
def test_check_source_rejects_anything_but_shapes(code):
    errors = check_source(code)
    assert [e.code for e in errors] == ["forbidden_code"], code


def test_check_source_accepts_the_fixture_and_reports_syntax_errors():
    assert check_source(BOOK.enclosure.code) == []
    assert check_source("parts = {")[0].code == "model_error"


def test_forbidden_attrs_cover_every_module_build123d_exposes():
    import build123d

    modules = {
        n
        for n in dir(build123d)
        if isinstance(getattr(build123d, n), types.ModuleType) and not n.startswith("_")
    }
    assert modules <= FORBIDDEN_ATTRS, sorted(modules - FORBIDDEN_ATTRS)


def test_custom_template_needs_code_and_box_lid_takes_none():
    with pytest.raises(ValidationError):
        EnclosureSpec(template="custom")
    with pytest.raises(ValidationError):
        EnclosureSpec(code="parts = {}")


def test_box_lid_print_only_spec_has_no_model(tmp_path):
    spec = BOOK.model_copy(update={"enclosure": EnclosureSpec()})
    result = build_custom_model(spec, None, None, tmp_path)
    assert [e.code for e in result.errors] == ["no_model"]


@pytest.mark.slow
def test_book_holder_builds_and_passes_the_print_checks(tmp_path, lib):
    result = build_custom_model(BOOK, None, lib, tmp_path)
    assert result.ok, result.errors
    assert set(result.artifacts) == {
        "holder_stl",
        "holder_step",
        "model_py",
        "manifest",
    }
    assert result.data["manifest"]["prints"]["holder"][0] == pytest.approx(148)
    checked = check_enclosure(BOOK, None, lib, tmp_path, "generic")
    assert checked.ok, checked.errors


@pytest.mark.slow
def test_same_code_same_files(tmp_path, lib):
    a, b = tmp_path / "a", tmp_path / "b"
    build_custom_model(BOOK, None, lib, a)
    build_custom_model(BOOK, None, lib, b)
    for name in ("holder.stl", "holder.step", "manifest.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


@pytest.mark.slow
def test_errors_point_at_the_models_line(tmp_path, lib):
    code = "from build123d import *\n\nparts = {'a': Box(1, 1)}\n"
    result = build_custom_model(with_code(code), None, lib, tmp_path)
    assert result.errors[0].code == "model_error"
    assert 'model.py", line 3' in result.errors[0].message


@pytest.mark.slow
def test_wrong_output_is_explained(tmp_path, lib):
    (tmp_path / "arm.stl").write_text("the saved model's part")
    result = build_custom_model(with_code("x = 1"), None, lib, tmp_path)
    assert result.errors[0].code == "bad_model_output"
    assert "parts" in result.errors[0].message
    # a failed draft leaves the saved model's files alone
    assert (tmp_path / "arm.stl").exists()
    assert not (tmp_path / "model.py").exists()


@pytest.mark.slow
def test_endless_model_times_out(tmp_path, lib, monkeypatch):
    monkeypatch.setattr(custom_model, "TIMEOUT_S", 8)
    result = build_custom_model(with_code("while True:\n    pass"), None, lib, tmp_path)
    assert result.errors[0].code == "model_timeout"


@pytest.mark.slow
def test_loose_pieces_and_a_round_bottom_fail_the_checks(tmp_path, lib):
    code = (
        "from build123d import *\n"
        "parts = {'two': Box(10, 10, 10, align=(Align.MIN,) * 3)"
        " + Pos(20, 0, 0) * Box(10, 10, 10, align=(Align.MIN,) * 3),"
        " 'ball': Pos(0, 0, 10) * Sphere(10),"
        " 'hollow': Pos(0, 0, 15) * (Box(30, 30, 30) - Sphere(12))}\n"
    )
    spec = with_code(code)
    assert build_custom_model(spec, None, lib, tmp_path).ok
    errors = check_enclosure(spec, None, lib, tmp_path, "generic").errors
    # the sphere is watertight once OCCT's zero-area pole triangles are dropped; a sealed void
    # isn't a loose piece
    assert sorted((e.code, e.message.split(".stl")[0]) for e in errors) == [
        ("loose_pieces", "two"),
        ("no_flat_base", "ball"),
    ]


PLANT = ProjectSpec.model_validate_json(
    (ROOT / "fixtures" / "specs" / "plant_monitor.json").read_text()
)


def device_with(code: str) -> ProjectSpec:
    return PLANT.model_copy(
        update={"enclosure": EnclosureSpec(template="custom", code=code)}
    )


@pytest.mark.slow
def test_device_body_keeps_cavity_openings_and_lid_path_clear(tmp_path, lib):
    from build123d import import_step

    from backend.tools.layout import layout_parts

    spec = device_with(
        (ROOT / "fixtures" / "cad" / "plant_monitor_stand.py").read_text()
    )
    layout, _ = layout_parts(spec, lib)
    result = build_custom_model(spec, layout, lib, tmp_path)
    assert result.ok, result.errors
    manifest = result.data["manifest"]
    assert set(manifest["prints"]) == {"base", "lid"}
    assert (
        manifest["outer_mm"][0] > layout.cavity_mm[0] + 40
    )  # the foot, not just the box
    checked = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert checked.ok, checked.errors

    base = import_step(tmp_path / "base.step")
    inside = lambda points: [base.is_inside(p) for p in points]
    L, W, H = layout.cavity_mm
    w = spec.enclosure.wall_mm
    usb = next(c for c in manifest["cutouts"] if c["feature"] == "usb")
    cable = next(c for c in manifest["cutouts"] if c["feature"] == "cable")
    assert (usb["face"], cable["face"]) == ("left", "back")
    clear = [
        (L / 2, W / 2, H / 2),  # the cavity
        (L / 2, W / 2, H + w + 5),  # above the lid
        (-w - 4, *usb["center_mm"]),  # through the wing, in front of the USB port
        (
            cable["center_mm"][0],
            W + w + 2,
            cable["center_mm"][1],
        ),  # through the backrest
    ]
    solid = [
        (-w - 4, W - 3, 2.0),
        (L / 2, W + w + 2, H + 20),
    ]  # wing and backrest elsewhere
    assert inside(clear) == [False] * len(clear)
    assert inside(solid) == [True] * len(solid)


@pytest.mark.slow
def test_cable_hole_clears_room_for_the_cable_not_a_slot_through_the_stand(
    tmp_path, lib
):
    from build123d import import_step

    from backend.tools.layout import layout_parts

    stand = (  # 40 mm of stand behind the back wall, up to the cable hole's centre (z H/2)
        "from build123d import *\nL, W, H = CAVITY_MM\nw = WALL_MM\n"
        "body = Pos(-w, W + w - 1, -w) * Box(L + 2 * w, 40, {top} + w, "
        "align=(Align.MIN,) * 3)"
    )
    spec = device_with(stand.format(top="H / 2"))
    layout, _ = layout_parts(spec, lib)
    result = build_custom_model(spec, layout, lib, tmp_path)
    assert result.ok, result.errors
    cable = next(
        c for c in result.data["manifest"]["cutouts"] if c["feature"] == "cable"
    )
    (u, v), W, w = cable["center_mm"], layout.cavity_mm[1], spec.enclosure.wall_mm
    base = import_step(tmp_path / "base.step")
    assert not base.is_inside((u, W + w + 5, v - 1))  # room behind the hole
    assert base.is_inside((u, W + w + 30, v - 1))  # the stand further back stays solid

    # As tall as the case, the stand closes the hole's room in on every side: a dead end.
    error = build_custom_model(
        device_with(stand.format(top="H")), layout, lib, tmp_path
    )
    assert [e.code for e in error.errors] == ["not_assembled"]
    assert "soil1's cable opening in the back wall" in error.errors[0].message
    assert "walled in on every side by base" in error.errors[0].message


@pytest.mark.slow
def test_device_body_that_misses_the_bay_is_loose(tmp_path, lib):
    from backend.tools.layout import layout_parts

    spec = device_with(
        "from build123d import *\nbody = Pos(140, 0, 0) * Box(10, 10, 10)"
    )
    layout, _ = layout_parts(spec, lib)
    assert build_custom_model(spec, layout, lib, tmp_path).ok
    codes = [
        e.code for e in check_enclosure(spec, layout, lib, tmp_path, "generic").errors
    ]
    assert codes == ["loose_pieces"]


# A plain case with a knob on the lid and a clip behind it that holds the soil probe.
CLIP_AND_KNOB = """from build123d import *
L, W, H = CAVITY_MM
PROBE_L, PROBE_W, PROBE_H = EXTERNAL_MM["soil1"]
MIN = (Align.MIN,) * 3
knob = Cylinder(8, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
parts = {"knob": knob, "clip": Pos(50, 0, 0) * Box(30, 10, 12, align=MIN)}
assembled = {
    "knob": Pos(L / 2, W / 2, H + WALL_MM),
    "clip": Pos(10, W + WALL_MM, -WALL_MM) * Pos(-50, 0, 0),  # against the back wall
}
mounts = {"soil1": Pos(0, W + WALL_MM + 6, 10)}  # on the clip, 6 mm clear of the wall
"""


@pytest.mark.slow
def test_device_parts_and_mounts_are_assembled_in_build_order(tmp_path, lib):
    import trimesh

    from backend.cad.assembly import build_assembly
    from backend.tools.layout import layout_parts

    spec = device_with(CLIP_AND_KNOB)
    layout, _ = layout_parts(spec, lib)
    result = build_custom_model(spec, layout, lib, tmp_path)
    assert result.ok, result.errors
    assert result.errors == []  # the only external part is mounted: no warning
    manifest = result.data["manifest"]
    assert set(manifest["prints"]) == {"base", "lid", "knob", "clip"}
    w = spec.enclosure.wall_mm
    L, W, _ = layout.cavity_mm
    assert manifest["outer_mm"][0] == pytest.approx(L + 2 * w)  # the case only
    assert manifest["build_order"] == ["clip", "knob", "soil1"]
    assert manifest["assembled"]["clip"]["on"] == "base"
    assert manifest["mounts"]["soil1"]["on"] == "clip"
    checked = check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert checked.ok, checked.errors

    assert build_assembly(spec, layout, lib, tmp_path).ok
    scene = trimesh.load(tmp_path / "assembly.glb")
    clip = scene.geometry["print_clip"].copy()
    clip.apply_transform(scene.graph.get("print_clip")[0])
    assert clip.bounds[0] == pytest.approx([10, W + w, -w])
    probe = scene.graph.get("soil1")[0][:3, 3]  # the box's centre
    assert probe == pytest.approx([49, W + w + 6 + 11.5, 13.5])


@pytest.mark.slow
@pytest.mark.parametrize(
    ("change", "code", "says"),
    [
        (("assembled = {",), "bad_model_output", "`assembled` isn't set"),
        (
            ('"knob": Pos(L / 2, W / 2, H + WALL_MM),', ""),
            "bad_model_output",
            "`assembled` has no entry for ['knob']",
        ),
        (
            ('    "clip": Pos(10,', '    "dial": Pos(0, 0, 0),\n    "clip": Pos(10,'),
            "bad_model_output",
            "entries for ['dial'], which aren't in `parts`",
        ),
        (
            ('"knob": Pos(L / 2', '"knob": Pos(L / 2 + 300'),
            "not_assembled",
            "knob doesn't attach to the device",
        ),
        (
            ("+ 6, 10)}", "+ 6, 10), 'env1': Pos(0, 0, 0)}"),
            "bad_model_output",
            "['env1'] aren't",
        ),
        (
            ("Pos(0, W + WALL_MM + 6, 10)", "Pos(-2, -2, -2)"),
            "not_assembled",
            "in the assembled device, within x ",
        ),
        (
            ('"knob": Pos(L / 2, W / 2,', '"knob": Pos(69.3, 29.5,'),  # on the screen
            "not_assembled",
            "knob blocks oled1's display_window opening in the lid",
        ),
    ],
)
def test_assembly_problems_are_explained(tmp_path, lib, change, code, says):
    from backend.tools.layout import layout_parts

    model = CLIP_AND_KNOB
    if len(change) == 1:  # drop `assembled`
        model = model[: model.index(change[0])] + model[model.index("mounts") :]
    else:
        model = model.replace(*change)
    spec = device_with(model)
    layout, _ = layout_parts(spec, lib)
    error = build_custom_model(spec, layout, lib, tmp_path).errors[0]
    assert error.code == code
    assert says in error.message, error.message


@pytest.mark.slow
def test_lid_cut_goes_through_the_plate_and_leaves_the_lip(tmp_path, lib):
    from build123d import import_step

    from backend.cad.box_lid import LIP_GAP_MM, LIP_T_MM
    from backend.tools.layout import LIP_MM, layout_parts

    y = LIP_GAP_MM + LIP_T_MM / 2  # over the front lip strip
    spec = device_with(
        "from build123d import *\nL, W, H = CAVITY_MM\n"
        f"lid_cut = Pos(L / 2, {y}, H - 20) * Cylinder(3, 60, align=(Align.CENTER,) * 2 + (Align.MIN,))"
    )
    layout, _ = layout_parts(spec, lib)
    assert build_custom_model(spec, layout, lib, tmp_path).ok
    L, _, H = layout.cavity_mm
    w = spec.enclosure.wall_mm
    lid = import_step(tmp_path / "lid.step")
    assert not lid.is_inside((L / 2, y, H + w / 2))  # the hole in the plate
    assert lid.is_inside((L / 2 + 6, y, H + w / 2))  # plate beside it
    assert lid.is_inside((L / 2, y, H - LIP_MM / 2))  # the lip under it is whole


@pytest.mark.slow
def test_a_part_placed_into_the_board_fails_with_the_boards_ref(tmp_path, lib):
    from backend.tools.layout import footprint, layout_parts

    spec = device_with(CLIP_AND_KNOB)
    layout, _ = layout_parts(spec, lib)
    board = next(p for p in layout.placements if p.ref == "esp32")
    x0, y0, x1, y1 = footprint(board, lib.get(spec.mcu.part_id))
    into = f'"knob": Pos({(x0 + x1) / 2}, {(y0 + y1) / 2}, {board.z_mm}),'
    spec = device_with(
        CLIP_AND_KNOB.replace('"knob": Pos(L / 2, W / 2, H + WALL_MM),', into)
    )
    error = build_custom_model(spec, layout, lib, tmp_path).errors[0]
    assert error.code == "not_assembled"
    assert "knob overlaps esp32 inside the case" in error.message, error.message

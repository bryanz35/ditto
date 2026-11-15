from backend.contracts.spec import ProjectSpec
from backend.runtime.deps import ORDER, changed_fields, stages_to_rerun


def test_parts_change_reruns_every_stage():
    assert stages_to_rerun({"parts"}) == ORDER
    assert len(ORDER) == 8


def test_enclosure_change_reruns_only_the_cad_stages():
    assert stages_to_rerun({"enclosure"}) == ["layout", "enclosure", "assembly"]


CAD = ["layout", "enclosure", "assembly"]
RERUNS = {  # every ProjectSpec field -> the stages an edit of it reruns
    "rev": [],
    "title": [],
    "prompt": [],
    "requirements": [],
    "assumptions": [],
    "user": [
        "enclosure",
        "assembly",
        "bom",
    ],  # printer (check_enclosure), owned and budget
    "mcu": ORDER,
    "parts": ORDER,
    "connections": ["validate", "firmware", "wiring", "simulate"],
    "firmware": [
        "validate",
        "firmware",
        "simulate",
    ],  # needs_wifi: validate's adc2_wifi check
    "enclosure": CAD,
    "custom_parts": ORDER,  # read wherever parts are
}


def test_each_spec_field_reruns_the_stages_that_read_it():
    assert set(RERUNS) == set(ProjectSpec.model_fields), "add the new field to RERUNS"
    for field, stages in RERUNS.items():
        assert stages_to_rerun({field}) == stages, field


def test_changed_fields():
    old = {"rev": 1, "enclosure": {"wall_mm": 2.0}, "title": "a"}
    new = {"rev": 2, "enclosure": {"wall_mm": 3.0}, "title": "a"}
    assert changed_fields(old, new) == {"rev", "enclosure"}


def test_a_custom_part_look_reruns_nothing():
    part = {"id": "x_pot", "name": "pot"}
    old = {"rev": 1, "custom_parts": [part]}  # saved before the field existed
    assert changed_fields(
        old, {"rev": 2, "custom_parts": [{**part, "look": "pot_rotary"}]}
    ) == {"rev"}
    assert changed_fields(
        old, {"rev": 2, "custom_parts": [{**part, "name": "knob"}]}
    ) == {"rev", "custom_parts"}

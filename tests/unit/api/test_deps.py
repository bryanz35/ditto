from backend.runtime.deps import ORDER, changed_fields, stages_to_rerun


def test_parts_change_reruns_every_stage():
    assert stages_to_rerun({"parts"}) == ORDER
    assert len(ORDER) == 8


def test_enclosure_change_reruns_only_the_cad_stages():
    assert stages_to_rerun({"enclosure"}) == ["layout", "enclosure", "assembly"]


def test_firmware_and_user_changes():
    assert stages_to_rerun({"firmware"}) == ["firmware", "simulate"]
    assert stages_to_rerun({"user"}) == ["bom"]
    assert stages_to_rerun({"title"}) == []


def test_changed_fields():
    old = {"rev": 1, "enclosure": {"wall_mm": 2.0}, "title": "a"}
    new = {"rev": 2, "enclosure": {"wall_mm": 3.0}, "title": "a"}
    assert changed_fields(old, new) == {"rev", "enclosure"}

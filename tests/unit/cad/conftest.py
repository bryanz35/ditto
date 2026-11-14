from pathlib import Path

import pytest

from backend.contracts.parts import Feature, PartLibrary, load_library
from backend.contracts.spec import PartInstance, ProjectSpec

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture
def lib() -> PartLibrary:
    return load_library()


@pytest.fixture
def spec() -> ProjectSpec:
    return ProjectSpec.model_validate_json(
        (ROOT / "fixtures" / "specs" / "plant_monitor.json").read_text()
    )


def big_display_case(lib: PartLibrary, spec: ProjectSpec):
    """The plant monitor with its 0.96" OLED swapped for a 1.3" one (in memory: the YAMLs are T18's)."""
    small = lib.get("ssd1306_096_i2c")
    big = small.model_copy(
        update={
            "id": "sh1106_13_i2c",
            "board_mm": small.board_mm.model_copy(update={"l": 35.4, "w": 33.5}),
            "features": [
                Feature(
                    kind="display_window",
                    face="top",
                    offset_mm=(17.7, 15.0),
                    size_mm=(30.0, 15.0),
                )
            ],
        }
    )
    big_lib = PartLibrary({**lib.parts, big.id: big})
    parts = [
        p.model_copy(update={"part_id": big.id}) if p.ref == "oled1" else p
        for p in spec.parts
    ]
    return big_lib, spec.model_copy(update={"parts": parts})


def four_walls_case(lib: PartLibrary, spec: ProjectSpec):
    """Extra parts whose features face each wall, two of them on the left wall with the mcu."""
    buzzer = lib.get("buzzer_passive")
    extra = {}
    for wall, n in (("left", 1), ("right", 2), ("front", 2), ("back", 1)):
        for i in range(n):
            pid = f"t_{wall}{i}"
            extra[pid] = buzzer.model_copy(
                update={
                    "id": pid,
                    "features": [
                        Feature(
                            kind="button",
                            face=wall,
                            offset_mm=(5.0, 4.0),
                            size_mm=(6.0, 6.0),
                        )
                    ],
                }
            )
    new_lib = PartLibrary({**lib.parts, **extra})
    insts = [
        PartInstance(ref=pid.replace("_", ""), part_id=pid, role="test", reason="test")
        for pid in extra
    ]
    return new_lib, spec.model_copy(update={"parts": [*spec.parts, *insts]})

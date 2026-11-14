"""T23: every library snippet, alone on the esp32_devkitc, lints and compiles."""

import re
import shutil
from pathlib import Path

import pytest

from backend.contracts.parts import BoardDef, PartDef, load_library
from backend.contracts.spec import Connection, PartInstance, ProjectSpec
from backend.tools.firmware import (
    compile_firmware,
    lint_firmware,
    write_firmware_project,
)

ROOT = Path(__file__).resolve().parents[3]
PARTS_DIR = ROOT / "backend/parts"
BASE = ProjectSpec.model_validate_json(
    (ROOT / "fixtures/specs/plant_monitor.json").read_text()
)
LIB = load_library()
NOT_SIGNALS = {"power", "gnd", "config"}  # wired to rails, never to a GPIO
# General-purpose devkitc GPIOs: no reserved, strapping or input-only pins.
FREE_GPIOS = [32, 33, 25, 26, 27, 4, 16, 17, 18, 19, 21, 22, 23]
PARTS = sorted((p for p in LIB.parts.values() if p.snippet), key=lambda p: p.id)
needs_pio = pytest.mark.skipif(
    shutil.which("pio") is None, reason="PlatformIO not installed (run make setup)"
)


def signal_pins(part: PartDef) -> list[str]:
    return [p.name for p in part.pins if p.type not in NOT_SIGNALS]


def snippet_project(part: PartDef, out_dir: Path) -> tuple[str, Path]:
    """Write a project with the board and this part; returns the snippet text and the project dir."""
    assert part.snippet
    text = (PARTS_DIR / part.snippet).read_text()
    pins = "|".join(map(re.escape, signal_pins(part)))
    refs = set(re.findall(rf"\bPIN_([A-Z0-9]+)_(?:{pins})\b", text))
    assert len(refs) == 1, (
        f"{part.snippet} should use one ref in its PIN_* macros, found {refs}"
    )
    ref = refs.pop().lower()
    assert len(signal_pins(part)) <= len(FREE_GPIOS)
    spec = BASE.model_copy(
        update={
            "parts": [
                PartInstance(ref=ref, part_id=part.id, role="snippet", reason="T23")
            ],
            "connections": [
                Connection(part_ref=ref, part_pin=pin, mcu_pin=f"GPIO{n}", bus="gpio")
                for pin, n in zip(signal_pins(part), FREE_GPIOS)
            ],
        }
    )
    result = write_firmware_project(spec, LIB, text, out_dir)
    assert result.ok, result.errors
    return text, out_dir


@pytest.mark.parametrize("part", PARTS, ids=lambda p: p.id)
def test_snippet_lints(part, tmp_path):
    _, project = snippet_project(part, tmp_path)
    result = lint_firmware(project)
    assert result.ok, result.errors


@pytest.mark.parametrize("part", PARTS, ids=lambda p: p.id)
def test_snippet_macros_match_part_pins(part, tmp_path):
    text, project = snippet_project(part, tmp_path)
    defined = set(
        re.findall(r"#define (PIN_\w+)", (project / "include/pins.h").read_text())
    )
    used = set(re.findall(r"\bPIN_[A-Z0-9]+_\w+", text))
    assert used <= defined, (
        f"{part.snippet} uses pins {part.id} doesn't have: {used - defined}"
    )


def test_every_wired_part_has_a_snippet():
    missing = [
        p.id
        for p in LIB.parts.values()
        if not isinstance(p, BoardDef) and signal_pins(p) and not p.snippet
    ]
    assert not missing


@pytest.mark.slow
@needs_pio
@pytest.mark.parametrize("part", PARTS, ids=lambda p: p.id)
def test_snippet_compiles(part, tmp_path):
    _, project = snippet_project(part, tmp_path)
    result = compile_firmware(project)
    assert result.ok, (result.errors, result.log)

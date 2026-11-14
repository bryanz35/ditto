import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.contracts.parts import PartLibrary, load_library
from backend.contracts.spec import ProjectSpec
from backend.tools import firmware, simulation
from backend.tools.simulation import build_simulation, run_simulation

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def lib() -> PartLibrary:
    return load_library()


@pytest.fixture
def spec() -> ProjectSpec:
    return ProjectSpec.model_validate_json(
        (ROOT / "fixtures" / "specs" / "plant_monitor.json").read_text()
    )


@pytest.fixture
def sim_dir(spec, lib, tmp_path) -> Path:
    """A built sim/ next to a firmware/ project with (fake) compiled firmware."""
    build = tmp_path / "firmware" / ".pio" / "build" / "esp32dev"
    build.mkdir(parents=True)
    (build / "firmware.bin").write_bytes(b"bin")
    (build / "firmware.elf").write_bytes(b"elf")
    assert build_simulation(spec, lib, tmp_path / "firmware", tmp_path / "sim").ok
    return tmp_path / "sim"


def test_plant_monitor_diagram_has_wokwi_parts_and_one_wire_per_connection(
    spec, lib, tmp_path
):
    result = build_simulation(spec, lib, tmp_path / "firmware", tmp_path / "sim")

    assert result.ok
    diagram = json.loads(Path(result.artifacts["diagram_json"]).read_text())
    parts = {p["id"]: p for p in diagram["parts"]}
    assert parts["esp32"]["type"] == "board-esp32-devkit-c-v4"
    with_model = {p.ref for p in spec.parts if lib.get(p.part_id).wokwi_type}
    assert set(parts) == {"esp32"} | with_model == {"esp32", "oled1", "buzzer1"}
    assert parts["oled1"]["attrs"] == {"i2cAddress": "0x3c"}
    assert sorted(e.message.split()[0] for e in result.errors) == ["env1", "soil1"]
    assert all(e.severity == "warning" for e in result.errors)

    wires = [c for c in diagram["connections"] if "$serialMonitor" not in c[1]]
    expected = [c for c in spec.connections if c.part_ref in with_model]
    assert len(wires) == len(expected) == 6
    assert [(a, b) for a, b, _, _ in wires] == [
        ("oled1:VCC", "esp32:3V3"),
        ("oled1:GND", "esp32:GND.1"),
        ("oled1:SCL", "esp32:22"),
        ("oled1:SDA", "esp32:21"),
        ("buzzer1:2", "esp32:25"),
        ("buzzer1:1", "esp32:GND.1"),
    ]


def test_wokwi_toml_points_at_platformio_output_and_output_is_deterministic(
    spec, lib, tmp_path
):
    first = build_simulation(spec, lib, tmp_path / "firmware", tmp_path / "sim")
    toml = Path(first.artifacts["wokwi_toml"]).read_text()
    assert 'firmware = "../firmware/.pio/build/esp32dev/firmware.bin"' in toml
    assert 'elf = "../firmware/.pio/build/esp32dev/firmware.elf"' in toml

    second = build_simulation(spec, lib, tmp_path / "firmware", tmp_path / "again")
    for name in ("diagram_json", "wokwi_toml"):
        assert (
            Path(first.artifacts[name]).read_bytes()
            == Path(second.artifacts[name]).read_bytes()
        )


def test_no_token_is_skipped_without_calling_the_cli(sim_dir, monkeypatch):
    monkeypatch.delenv("WOKWI_CLI_TOKEN", raising=False)
    monkeypatch.setattr(simulation.subprocess, "run", pytest.fail)

    result = run_simulation(sim_dir, 15_000)

    assert result.skipped and not result.ok
    assert "WOKWI_CLI_TOKEN" in result.errors[0].message


def _fake_cli(monkeypatch, returncode: int, serial: str) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        Path(cmd[cmd.index("--serial-log-file") + 1]).write_text(serial)
        if returncode == 0:
            Path(cmd[cmd.index("--screenshot-file") + 1]).write_bytes(b"png")
        return subprocess.CompletedProcess(cmd, returncode, "", "")

    monkeypatch.setenv("WOKWI_CLI_TOKEN", "wok_test")
    monkeypatch.setattr(simulation.shutil, "which", lambda _: "/bin/wokwi-cli")
    monkeypatch.setattr(simulation.subprocess, "run", run)
    return calls


def test_ready_run_returns_serial_log_and_screenshot(sim_dir, monkeypatch):
    calls = _fake_cli(monkeypatch, 0, "boot\nP2D_READY\n")

    result = run_simulation(sim_dir, 15_000)

    assert result.ok, result.errors
    assert set(result.artifacts) == {"serial_log", "screenshot"}
    cmd = calls[0]
    assert cmd[1] == str(sim_dir.resolve())
    for flag, value in [
        ("--timeout", "15000"),
        ("--expect-text", "P2D_READY"),
        ("--screenshot-part", "oled1"),
        ("--screenshot-time", "15000"),
    ]:
        assert cmd[cmd.index(flag) + 1] == value


def test_timeout_reports_the_serial_tail(sim_dir, monkeypatch):
    _fake_cli(monkeypatch, 42, "boot\nGuru Meditation Error\n")

    result = run_simulation(sim_dir, 15_000)

    assert not result.ok and not result.skipped
    assert result.errors[0].code == "sim_timeout"
    assert "Guru Meditation Error" in result.errors[0].message
    assert set(result.artifacts) == {"serial_log"}


def test_missing_firmware_is_an_error(sim_dir, monkeypatch):
    _fake_cli(monkeypatch, 0, "")
    (
        sim_dir.parent / "firmware" / ".pio" / "build" / "esp32dev" / "firmware.bin"
    ).unlink()

    result = run_simulation(sim_dir, 15_000)

    assert result.errors[0].code == "firmware_missing"


@pytest.mark.slow
@pytest.mark.live
def test_plant_monitor_reaches_ready_in_wokwi(spec, lib, tmp_path):
    if not (
        shutil.which("pio")
        and shutil.which("wokwi-cli")
        and os.environ.get("WOKWI_CLI_TOKEN")
    ):
        pytest.skip("needs pio, wokwi-cli and WOKWI_CLI_TOKEN")
    main_cpp = (ROOT / "fixtures" / "firmware" / "plant_monitor_main.cpp").read_text()
    project = tmp_path / "firmware"
    assert firmware.write_firmware_project(spec, lib, main_cpp, project).ok
    compiled = firmware.compile_firmware(project)
    assert compiled.ok, compiled.log
    assert build_simulation(spec, lib, project, tmp_path / "sim").ok

    result = run_simulation(tmp_path / "sim", 15_000)

    assert result.ok, result.errors
    assert "P2D_READY" in Path(result.artifacts["serial_log"]).read_text()
    assert Path(result.artifacts["screenshot"]).stat().st_size > 0

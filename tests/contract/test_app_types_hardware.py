from backend.app.main import app
from backend.contracts.export_types import OUT, schema_text
from backend.contracts.hardware import HARDWARE_FILE, load_hardware


def test_app_mounts_the_event_stream():
    assert app.url_path_for("run_events", run_id="x") == "/runs/x/events"


def test_typescript_contracts_are_up_to_date():
    assert (OUT / "schema.json").read_text() == schema_text(), "run `make types`"
    assert (OUT / "index.ts").is_file()


def test_unknown_hardware_means_mode_v_with_simulation(tmp_path):
    path = tmp_path / "HARDWARE.md"
    path.write_text(
        "HAS_PARTS=unknown\nMODE=unknown   # P | E | V\nSIMULATE=auto\nPRINTER_MODEL=\n"
    )
    hw = load_hardware(path)
    assert (hw.mode, hw.simulate, hw.has_parts, hw.printer_model) == (
        "V",
        True,
        None,
        "generic",
    )


def test_mode_p_turns_simulation_off_unless_forced(tmp_path):
    path = tmp_path / "HARDWARE.md"
    path.write_text(
        "HAS_PARTS=yes\nHAS_PRINTER=yes\nPRINTER_MODEL=bambu_p1s\nMODE=P\nSIMULATE=auto\n"
    )
    assert load_hardware(path).simulate is False
    path.write_text("MODE=P\nSIMULATE=on\n")
    assert load_hardware(path).simulate is True


def test_the_real_hardware_file_parses():
    load_hardware(HARDWARE_FILE)

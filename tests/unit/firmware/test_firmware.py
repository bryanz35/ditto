import shutil
from pathlib import Path

import pytest

from backend.contracts.parts import load_library
from backend.contracts.spec import ProjectSpec
from backend.tools.firmware import (
    compile_firmware,
    lint_firmware,
    parse_compile_errors,
    pins_header,
    write_firmware_project,
)

ROOT = Path(__file__).resolve().parents[3]
SPEC = ProjectSpec.model_validate_json(
    (ROOT / "fixtures/specs/plant_monitor.json").read_text()
)
GOLDEN = (ROOT / "fixtures/firmware/plant_monitor_main.cpp").read_text()
FIXTURE_FW = ROOT / "fixtures/runs/plant_monitor/firmware"
LIB = load_library()
needs_pio = pytest.mark.skipif(
    shutil.which("pio") is None, reason="PlatformIO not installed (run make setup)"
)


def project(tmp_path: Path, main_cpp: str = GOLDEN) -> Path:
    result = write_firmware_project(SPEC, LIB, main_cpp, tmp_path)
    assert result.ok, result.errors
    return tmp_path


def test_pins_header_matches_fixture_run():
    assert pins_header(SPEC) == (FIXTURE_FW / "include/pins.h").read_text()


def test_project_matches_fixture_run_and_is_deterministic(tmp_path):
    result = write_firmware_project(SPEC, LIB, GOLDEN, tmp_path / "a")
    assert set(result.artifacts) == {"platformio_ini", "pins_h", "main_cpp"}
    assert Path(result.artifacts["main_cpp"]).read_text() == GOLDEN
    assert (tmp_path / "a/platformio.ini").read_text() == (
        FIXTURE_FW / "platformio.ini"
    ).read_text()
    write_firmware_project(SPEC, LIB, GOLDEN, tmp_path / "b")
    for name in ("platformio.ini", "include/pins.h", "src/main.cpp"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()


def test_ini_without_lib_deps(tmp_path):
    spec = SPEC.model_copy(
        update={"parts": [p for p in SPEC.parts if p.ref == "buzzer1"]}
    )
    write_firmware_project(spec, LIB, GOLDEN, tmp_path)
    ini = (tmp_path / "platformio.ini").read_text()
    assert "board = esp32dev" in ini and "lib_deps" not in ini


KEYBOARD = """#include <Arduino.h>
#include "pins.h"
#include "USB.h"
#include "USBHIDKeyboard.h"

USBHIDKeyboard Keyboard;

void setup() {
  Serial.begin(115200);
  Keyboard.begin();
  USB.begin();
  Serial.println("P2D_READY");
}

void loop() {}
"""
XIAO = SPEC.model_copy(
    update={
        "mcu": SPEC.mcu.model_copy(update={"part_id": "xiao_esp32s3_sense"}),
        "parts": [],
        "connections": [],
    }
)


def test_native_usb_sketch_gets_deep_lib_scan_and_otg_mode(tmp_path):
    write_firmware_project(XIAO, LIB, KEYBOARD, tmp_path / "usb")
    ini = (tmp_path / "usb/platformio.ini").read_text()
    assert "lib_ldf_mode = deep\n" in ini
    assert "build_flags = -DARDUINO_USB_MODE=0" in ini
    write_firmware_project(XIAO, LIB, GOLDEN, tmp_path / "plain")
    assert "lib_ldf_mode" not in (tmp_path / "plain/platformio.ini").read_text()


@pytest.mark.slow
@needs_pio
def test_native_usb_keyboard_compiles(tmp_path):
    write_firmware_project(XIAO, LIB, KEYBOARD, tmp_path)
    result = compile_firmware(tmp_path)
    assert result.ok, result.errors


def test_unknown_part_is_an_error_not_an_exception(tmp_path):
    bad = SPEC.parts[0].model_copy(update={"part_id": "flux_capacitor"})
    result = write_firmware_project(
        SPEC.model_copy(update={"parts": [bad]}), LIB, GOLDEN, tmp_path
    )
    assert not result.ok
    assert result.errors[0].code == "unknown_part"
    assert result.errors[0].field == "parts[0].part_id"


def test_lint_accepts_golden(tmp_path):
    result = lint_firmware(project(tmp_path))
    assert result.ok, result.errors


def test_lint_rejects_numeric_pin_and_accepts_macro(tmp_path):
    bad = GOLDEN.replace(
        "pinMode(PIN_BUZZER1_SIG, OUTPUT);",
        "pinMode(PIN_BUZZER1_SIG, OUTPUT);\n  digitalWrite(4, HIGH);",
    )
    result = lint_firmware(project(tmp_path, bad))
    assert not result.ok
    [err] = result.errors
    assert err.code == "numeric_pin"
    assert (
        err.field
        == f"src/main.cpp:{bad.splitlines().index('  digitalWrite(4, HIGH);') + 1}"
    )
    assert "PIN_BUZZER1_SIG" in err.message  # lists the macros to use instead

    good = bad.replace("digitalWrite(4, HIGH)", "digitalWrite(PIN_BUZZER1_SIG, HIGH)")
    assert lint_firmware(project(tmp_path, good)).ok


@pytest.mark.parametrize(
    "line",
    [
        "Wire.begin(21, 22);",
        "Wire.begin(PIN_ENV1_SDA, 22);",
        "ledcAttach(25, 2000, 8);",
        "tone(25, 2000);",
        "int v = analogRead (34);",
    ],
)
def test_lint_rejects_other_numeric_pins(tmp_path, line):
    result = lint_firmware(
        project(tmp_path, GOLDEN.replace("analogReadResolution(12);", line))
    )
    assert result.errors and {e.code for e in result.errors} == {"numeric_pin"}


def test_lint_ignores_comments_and_wire_target_mode(tmp_path):
    text = GOLDEN.replace(
        "analogReadResolution(12);",
        "// digitalWrite(4, HIGH);\n  /* pinMode(5,\n OUTPUT); */\n  Wire1.begin(0x08);",
    )
    assert lint_firmware(project(tmp_path, text)).ok


def test_lint_requires_pins_include_and_ready(tmp_path):
    text = GOLDEN.replace('#include "pins.h"\n', "").replace('"P2D_READY"', '"ready"')
    result = lint_firmware(project(tmp_path, text))
    assert {e.code for e in result.errors} == {"missing_pins_include", "missing_ready"}


def test_missing_main(tmp_path):
    assert lint_firmware(tmp_path).errors[0].code == "missing_main"
    assert compile_firmware(tmp_path).errors[0].code == "missing_main"


def test_parse_compile_errors(tmp_path):
    log = f"""Compiling .pio/build/esp32dev/src/main.cpp.o
src/main.cpp:26:3: error: expected ',' or ';' before 'undefinedThing'
{tmp_path}/src/main.cpp:5:10: fatal error: Nope.h: No such file or directory
src/main.cpp:26:3: error: expected ',' or ';' before 'undefinedThing'
src/main.cpp:30:1: warning: unused variable 'x'
*** [.pio/build/esp32dev/src/main.cpp.o] Error 1
"""
    errors = parse_compile_errors(log, tmp_path)
    assert [(e.field, e.message) for e in errors] == [
        (
            "src/main.cpp:26:3",
            "src/main.cpp:26:3: expected ',' or ';' before 'undefinedThing'",
        ),
        ("src/main.cpp:5:10", "src/main.cpp:5:10: Nope.h: No such file or directory"),
    ]


def test_parse_compile_errors_windows_drive_path(tmp_path):
    log = r"C:\Users\me\.pio\libdeps\Foo\Foo.h:3:1: error: 'x' does not name a type"
    [err] = parse_compile_errors(log, tmp_path)
    assert err.field and err.field.endswith("Foo.h:3:1")
    assert err.message.endswith("Foo.h:3:1: 'x' does not name a type")


def test_undeclared_pin_macro_hint_lists_pins_h(tmp_path):
    project(tmp_path)
    log = (
        "src/main.cpp:12:11: error: 'PIN_BZ1_POSITIVE' was not declared in this scope\n"
        "src/main.cpp:13:3: error: 'foo' was not declared in this scope\n"
    )
    pin_err, other = parse_compile_errors(log, tmp_path)
    assert "PIN_BUZZER1_SIG" in (pin_err.hint or "")
    assert "PIN_SOIL1_AOUT" in (pin_err.hint or "")
    assert other.hint is None


def test_pio_that_cannot_start_is_an_error_not_an_exception(tmp_path, monkeypatch):
    import backend.tools.firmware as fw

    def boom(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(fw.shutil, "which", lambda _: "/usr/bin/pio")
    monkeypatch.setattr(fw.subprocess, "run", boom)
    result = compile_firmware(project(tmp_path))
    assert not result.ok and result.errors[0].code == "pio_failed"


@pytest.mark.slow
@needs_pio
def test_golden_plant_monitor_compiles(tmp_path):
    result = compile_firmware(project(tmp_path))
    assert result.ok, (result.errors, result.log)
    assert "SUCCESS" in result.log


@pytest.mark.slow
@needs_pio
def test_syntax_error_gives_line_numbers(tmp_path):
    lines = GOLDEN.splitlines()
    n = lines.index("  int soil = analogRead(PIN_SOIL1_AOUT);")
    lines[n] = lines[n].removesuffix(";")  # missing semicolon
    result = compile_firmware(project(tmp_path, "\n".join(lines) + "\n"))
    assert not result.ok
    assert result.errors and all(e.code == "compile_error" for e in result.errors)
    # gcc reports a missing ';' on the line itself or at the start of the next one
    fields = [e.field or "" for e in result.errors]
    assert any(
        f.startswith((f"src/main.cpp:{n + 1}:", f"src/main.cpp:{n + 2}:"))
        for f in fields
    )
    assert result.log and len(result.log.splitlines()) <= 40

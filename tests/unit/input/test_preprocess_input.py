import subprocess
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from backend.tools import preprocess_input as mod
from backend.tools.preprocess_input import MAX_EDGE, OPENAI_URL, preprocess_input


def test_images_are_upright_capped_and_flattened(tmp_path):
    photo = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° to display
    Image.new("RGB", (4000, 1000), "red").save(photo, exif=exif)
    sketch = tmp_path / "sketch.png"
    Image.new("RGBA", (200, 100), (0, 0, 0, 0)).save(sketch)

    result = preprocess_input([photo, sketch], tmp_path / "out")

    assert result.ok and not result.errors
    out_photo, out_sketch = map(Path, result.data["images"])
    assert out_photo.name == "00_photo.jpg" and out_photo.is_absolute()
    with Image.open(out_photo) as img:
        assert img.size == (392, MAX_EDGE)
    with Image.open(out_sketch) as img:
        assert img.mode == "RGB" and img.getpixel((10, 10)) == (255, 255, 255)
    assert sorted(result.artifacts.values()) == sorted(result.data["images"])
    assert result.data["transcript"] is None


def test_no_inputs_is_skipped(tmp_path):
    result = preprocess_input([], tmp_path)
    assert result.skipped and not result.ok


def test_bad_files_are_warnings_unless_nothing_is_usable(tmp_path):
    good = tmp_path / "good.png"
    Image.new("RGB", (10, 10)).save(good)
    notes = tmp_path / "notes.txt"
    notes.write_text("hi")
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")

    result = preprocess_input([good, notes, broken], tmp_path / "out")
    assert result.ok and len(result.data["images"]) == 1
    assert [(e.code, e.severity) for e in result.errors] == [
        ("unsupported_file", "warning"),
        ("unreadable_image", "warning"),
    ]

    result = preprocess_input([notes], tmp_path / "out")
    assert not result.ok and result.errors[0].severity == "error"


def test_transcription_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("P2D_TRANSCRIBE", raising=False)
    text, error = mod._transcribe(tmp_path / "a.wav")
    assert text is None and error.code == "no_transcriber"


@respx.mock
def test_transcription_openai(tmp_path, monkeypatch):
    monkeypatch.setenv("P2D_TRANSCRIBE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text="hi\n"))
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    assert mod._transcribe(wav) == ("hi", None)
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"

    route.mock(return_value=httpx.Response(429))
    text, error = mod._transcribe(wav)
    assert text is None and error.code == "transcription_failed"


def test_transcription_whisper(tmp_path, monkeypatch):
    monkeypatch.setenv("P2D_TRANSCRIBE", "whisper")
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(cmd):
        Path(cmd[cmd.index("--output_dir") + 1], "a.txt").write_text(" said this \n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(mod, "_run", fake_run)
    assert mod._transcribe(tmp_path / "a.wav") == ("said this", None)


def _make_video(path: Path, audio: bool) -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
    cmd += ["-i", "testsrc=duration=10:size=2000x500:rate=5"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=duration=10", "-shortest"]
    subprocess.run([*cmd, str(path)], check=True)
    return path


@pytest.mark.slow
def test_video_gives_keyframes_and_transcript(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        mod, "_transcribe", lambda wav: calls.append(wav) or ("mocked", None)
    )
    talking = _make_video(tmp_path / "talking.mp4", audio=True)
    silent = _make_video(tmp_path / "silent.mp4", audio=False)

    result = preprocess_input([talking], tmp_path / "out")
    assert result.ok and not result.errors, result.errors
    frames = result.data["images"]
    assert 1 <= len(frames) <= 8
    for frame in frames:
        with Image.open(frame) as img:
            assert max(img.size) <= MAX_EDGE
    assert result.data["transcript"] == "mocked"
    assert Path(result.artifacts["transcript"]).read_text() == "mocked"
    assert calls[0].is_file()

    result = preprocess_input([silent], tmp_path / "out")
    assert result.ok and 1 <= len(result.data["images"]) <= 8
    assert "transcript" in result.data and result.data["transcript"] is None
    assert len(calls) == 1

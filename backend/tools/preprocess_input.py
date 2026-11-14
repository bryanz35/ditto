"""Image and video preprocessing (T17).

Images are turned upright (EXIF), flattened onto white and capped to a 1568 px long edge (bigger
images only cost more tokens; the model API downscales them anyway). A video becomes up to 8
keyframes spread over its length (ffmpeg) plus a transcript of its audio track.

Transcription is chosen by env P2D_TRANSCRIBE: "whisper" (local openai-whisper CLI), "openai"
(speech-to-text API, needs OPENAI_API_KEY) or unset/"off". P2D_TRANSCRIBE_MODEL overrides the
model (defaults: "base" for whisper, "whisper-1" for openai).

Outputs go to out_dir, which may also hold the uploads, so every output name starts with the
input's index ("00_sketch.jpg", "01_demo_frames/03.jpg"), never overwriting an upload.
data: images (absolute paths, in input order), transcript (str | None).

Problems with single files are warnings, so one bad upload doesn't hide the others; ok is false
(and they become errors) only when no input produced anything.

Error codes:
- skipped: no input files
- unsupported_file: not an image or video type we read
- unreadable_image: Pillow can't open the file
- ffmpeg_missing: ffmpeg or ffprobe isn't on PATH
- ffmpeg_failed: ffprobe or ffmpeg failed on a video
- no_transcriber: the video has audio but transcription is off
- transcription_failed: the transcriber is misconfigured or failed
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.contracts.results import ToolError, ToolResult

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
MAX_EDGE = 1568
MAX_FRAMES = 8
OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"


def preprocess_input(paths: list[Path], out_dir: Path) -> ToolResult:
    if not paths:
        return ToolResult(
            ok=False,
            errors=[ToolError(code="skipped", message="No uploads to preprocess.")],
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir.resolve()
    images: list[Path] = []
    transcripts: list[str] = []
    warnings: list[ToolError] = []
    for i, path in enumerate(map(Path, paths)):
        prefix = f"{i:02d}_{path.stem}"
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            dest = out_dir / f"{prefix}.jpg"
            try:
                _normalise(path, dest)
                images.append(dest)
            except (OSError, UnidentifiedImageError) as e:
                warnings.append(
                    _warn("unreadable_image", f"Couldn't read {path.name}: {e}")
                )
        elif suffix in VIDEO_SUFFIXES:
            frames, transcript, errors = _video(path, out_dir, prefix)
            images += frames
            transcripts += [transcript] if transcript else []
            warnings += errors
        else:
            warnings.append(
                _warn(
                    "unsupported_file",
                    f"{path.name} isn't a supported upload; send an image "
                    f"({', '.join(sorted(IMAGE_SUFFIXES))}) or a video "
                    f"({', '.join(sorted(VIDEO_SUFFIXES))}).",
                )
            )

    artifacts = {p.relative_to(out_dir).as_posix(): str(p) for p in images}
    transcript = "\n\n".join(transcripts) or None
    if transcript:
        (out_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        artifacts["transcript"] = str(out_dir / "transcript.txt")
    ok = bool(images or transcript)
    if not ok:
        warnings = [e.model_copy(update={"severity": "error"}) for e in warnings]
    return ToolResult(
        ok=ok,
        errors=warnings,
        artifacts=artifacts,
        data={"images": [str(p) for p in images], "transcript": transcript},
    )


def _normalise(src: Path, dest: Path) -> None:
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        rgba = img.convert("RGBA")
    flat = Image.new("RGB", rgba.size, "white")
    flat.paste(rgba, mask=rgba)  # transparent sketches would turn black as plain RGB
    flat.save(dest, "JPEG", quality=85)


def _video(
    src: Path, out_dir: Path, prefix: str
) -> tuple[list[Path], str | None, list[ToolError]]:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        msg = f"Can't read the video {src.name}: ffmpeg/ffprobe isn't installed on the server."
        return [], None, [_warn("ffmpeg_missing", msg)]
    probe = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type"]
        + ["-of", "json", str(src)]
    )
    try:
        info = json.loads(probe.stdout)
        duration = float(info["format"]["duration"])
    except (ValueError, KeyError):
        return [], None, [_ffmpeg_failed(src, probe)]

    frames_dir = out_dir / f"{prefix}_frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir()
    fit = f"scale={MAX_EDGE}:{MAX_EDGE}:force_original_aspect_ratio=decrease"
    run = _run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
        + ["-vf", f"fps={MAX_FRAMES / max(duration, 1):.4f},{fit}"]
        + ["-frames:v", str(MAX_FRAMES), "-q:v", "3", str(frames_dir / "%02d.jpg")]
    )
    frames = sorted(frames_dir.glob("*.jpg"))
    errors = [] if run.returncode == 0 else [_ffmpeg_failed(src, run)]

    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        return frames, None, errors
    wav = out_dir / f"{prefix}.wav"
    run = _run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
        + ["-vn", "-ac", "1", "-ar", "16000", str(wav)]
    )
    if run.returncode:
        return frames, None, [*errors, _ffmpeg_failed(src, run)]
    transcript, error = _transcribe(wav)
    return frames, transcript, [*errors, *([error] if error else [])]


def _transcribe(audio: Path) -> tuple[str | None, ToolError | None]:
    """Returns (transcript, None) or (None, warning)."""
    backend = os.environ.get("P2D_TRANSCRIBE", "off").strip().lower()
    model = os.environ.get("P2D_TRANSCRIBE_MODEL")
    try:
        if backend == "whisper":
            if not shutil.which("whisper"):
                msg = "P2D_TRANSCRIBE=whisper but the whisper CLI isn't installed (pip install openai-whisper)."
                return None, _warn("transcription_failed", msg)
            run = _run(
                ["whisper", str(audio), "--model", model or "base"]
                + ["--output_format", "txt", "--output_dir", str(audio.parent)]
            )
            if run.returncode:
                msg = f"whisper failed on {audio.name}: {run.stderr.strip()[-300:]}"
                return None, _warn("transcription_failed", msg)
            return audio.with_suffix(".txt").read_text(encoding="utf-8").strip(), None
        if backend == "openai":
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                msg = "P2D_TRANSCRIBE=openai but OPENAI_API_KEY is empty."
                return None, _warn("transcription_failed", msg)
            with audio.open("rb") as f:
                response = httpx.post(
                    OPENAI_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    data={"model": model or "whisper-1", "response_format": "text"},
                    files={"file": (audio.name, f, "audio/wav")},
                    timeout=120,
                )
            response.raise_for_status()
            return response.text.strip(), None
    except (httpx.HTTPError, OSError) as e:
        return None, _warn(
            "transcription_failed", f"{backend} transcription failed: {e}"
        )
    msg = (
        f"The video has an audio track but transcription is off (P2D_TRANSCRIBE={backend!r}); "
        "set it to whisper or openai to include what was said."
    )
    return None, _warn("no_transcriber", msg)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, 1, "", f"{cmd[0]} timed out after 300 s"
        )


def _ffmpeg_failed(src: Path, run: subprocess.CompletedProcess[str]) -> ToolError:
    msg = f"ffmpeg couldn't read the video {src.name}: {run.stderr.strip()[-300:]}"
    return _warn("ffmpeg_failed", msg)


def _warn(code: str, message: str) -> ToolError:
    return ToolError(code=code, message=message, severity="warning")

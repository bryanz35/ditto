# T17: pillow as a direct dependency; transcription env vars

**What** (T00-owned files):
1. `pyproject.toml`: add `pillow>=13` to `dependencies`.
2. `.env.example`: add
   ```
   # Video transcription (T17): whisper (local CLI) | openai | off (default)
   P2D_TRANSCRIBE=
   # Optional model override (defaults: base for whisper, whisper-1 for openai)
   P2D_TRANSCRIBE_MODEL=
   OPENAI_API_KEY=
   ```

**Why:** `backend/tools/preprocess_input.py` imports Pillow, which today is only installed transitively
(build123d -> threejs-materials). A version bump upstream could drop it. The env vars select the
transcriber; without them transcription is off and the tool returns a `no_transcriber` warning.

**Who it affects:** nobody else; no contract change. T17 works as-is with the current files.

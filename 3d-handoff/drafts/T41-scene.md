# T41: scene files for the 3D build viewer (scene contracts, `scene` stage, part header data)

<!-- Draft. File it as handoff/contract-requests/T41-scene.md once T41 exists on the board, then
     `python3 scripts/board.py request --file handoff/contract-requests/T41-scene.md --summary "scene contracts, scene stage, part header fields"`. -->

What: five additive changes. No existing field, file or model changes shape; `cad/layout.json`
(`spec.Layout`) and `wiring.json` (`artifacts.Wiring`) and their consumers stay as they are.

**1. New `backend/contracts/scene.py`**: the models from `3d-handoff/handoff/reference/scene_contracts.py`,
rebuilt on `Model` (unknown fields are errors, attribute docstrings reach the TS types), with these
differences:

| Handoff | Contract | Why |
| --- | --- | --- |
| `Layout` | `SceneLayout` | `spec.Layout` exists |
| `Wiring` | `SceneWiring` | `artifacts.Wiring` exists |
| `Dims` | `SceneDims` | `parts.Dims` exists |
| `Enclosure` | `SceneEnclosure` | reads clearly next to `EnclosureSpec` |
| `rev: int` | `spec_rev: int` | every other artifact uses `spec_rev` |
| `ViewerPart.features: list[dict]` | `list[Feature]` (`parts.Feature`) | typed, same data as the YAML |
| `GET /parts/library.json` | `SceneLayout.parts: dict[str, ViewerPart]` (only the parts this run uses) | no new router; a run keeps the part data it was built with, so replays and old runs don't change when the library does |

Unchanged from the handoff: the ref patterns (`base`, `lid`, `<ref>`, `<ref>.s<k>`, `lid.s<k>`,
`w.<ref>.<pin>`, `usb`), the action types, the step ids (`print`, `place:<ref>`, `screw:<ref>`,
`mount:<ref>`, `mount:all`, `wire:<ref>`, `wire:all`, `flash`, `lid`), and every other field.
The MCU ref is `spec.mcu.ref` (e.g. `esp32`), never the literal `mcu`.

The module docstring defines the **web frame** exactly as the handoff does (mm, Y-up, origin at the
centre of the base's bottom face, +z toward the viewer) and states its relation to the enclosure frame
in `base.py`, which the handoff got wrong (the enclosure origin is the front-left corner of the cavity
floor, not the case centre):

```
web = (x - L/2,  z + wall,  W/2 - y)      # (x, y, z) enclosure frame; (L, W, _) = cavity_mm; wall = spec.enclosure.wall_mm
```

and the **part frame** for header and look coordinates: the same frame as `mount_holes` (base.py's part
frame: front-left-bottom corner of the bounding box, pin headers included).

**2. Optional fields on `PartDef`** (`backend/contracts/parts.py`), all defaulted so every YAML still loads:

```python
class Header(Model):
    id: str
    """"J2", "H1": as printed on the board, or invented when it isn't."""
    origin_mm: tuple[float, float]
    """(x, y) of pin index 0 in the part frame, like mount_holes."""
    pitch_mm: tuple[float, float]
    """(dx, dy) step to the next pin, e.g. (2.54, 0)."""
    side: Literal["top", "bottom"]
    """Which way the pins point."""
    pin_len_mm: float = 6.0
    pins: list[str | None]
    """Pin names in physical order, each one of the part's `pins`. None marks a physical pin nobody
    may wire (EN on the DevKitC). A name may repeat (the DevKitC has three GND pins)."""

class LookShape(Model): ...   # as in the handoff, coordinates in the part frame

# new PartDef fields
short_name: str | None = None
"""Kid-friendly noun for step text ("screen", "beeper"); None uses `name`."""
pcb_z_mm: float = 0.0
"""Height of the PCB's bottom face above the part-frame origin: board_mm.h includes the headers
below the PCB (about 8.5 mm on most breakouts), the viewer needs to know where the PCB starts."""
pcb_t_mm: float = 1.6
"""PCB thickness."""
pcb_color: str | None = None
headers: list[Header] = []
look: list[LookShape] = []
```

New `PartDef` validator: when `headers` is non-empty, every non-None header entry is one of `pins`,
and every name in `pins` appears on a header at least once.

Not added: `sound_port`. The existing `sound` feature kind (with `size_mm`) gives the lid its holes.

**3. `Stage` gains `"scene"`**, between `"wiring"` and `"simulate"` (`backend/contracts/events.py`).
That is all the SSE change there is:

- "scene ready" = the `scene` stage's `passed` event; its `artifacts` carry `scene_layout_json`,
  `scene_wiring_json` and `instructions_json` (paths `scene/layout.json`, `scene/wiring.json`,
  `scene/instructions.json`), served by the existing `GET /runs/{id}/files/{path}`.
- "scene stale" = the existing `stale` status on stage `scene`, emitted by the engine on edits.
- No `type` field and no new event kinds (the handoff's `{"type": "scene"}` envelope doesn't exist here).

**4. `ToolBox` gains `build_scene`** (`backend/contracts/tools.py`):

```python
class BuildScene(Protocol):  # T41. artifacts: scene_layout_json, scene_wiring_json, instructions_json
    def __call__(self, spec: ProjectSpec, layout: Layout, manifest: EnclosureManifest,
                 lib: PartLibrary, printer: str, out_dir: Path) -> ToolResult: ...
```

Error codes it may return (in its module docstring): `pin_conflict` (field `connections`; the message
names the free pins that would work and, for 3V3 shortages, whether the part accepts 5V), `no_headers`
(a wired part has no `headers` yet), `layout_mismatch`.

**5. `invariants.check_scene(layout: SceneLayout, wiring: SceneWiring, instructions: Instructions,
spec: ProjectSpec) -> list[str]`**: the handoff's `check_instructions` (every ref exists; each board,
screw, wire, the lid and the cable installed exactly once per level; upload after all wiring; lid
last; no MCU header pin used twice; all three files at the spec's rev). `cross_checks` reports it as
code `scene_mismatch`.

Also with the contract: `SceneLayout`, `SceneWiring`, `Instructions` added to `export_types.MODELS`;
`CONTRACT_VERSION` 5 -> 6; the handoff's `fixtures/timer/*.json` converted to the renamed models under
`fixtures/scene/timer/` as **shape fixtures** for the frontend (their numbers come from invented part
data, so they are not goldens); `tests/contract/` loads them.

Why: the 3D build viewer (`3d-handoff/handoff/3D_INSTRUCTIONS.md`) needs every object's world position,
the physical header pin each wire goes on, and ordered steps for each level. Nothing in the contracts
carries header positions, where the PCB sits inside `board_mm.h`, kid-friendly names or step plans;
`PartDef` forbids unknown fields, so the library can't hold them; `Stage` has no slot for a stage that
writes them; `ToolBox` has no tool for the engine to call. One new stage instead of the handoff's changes
to `layout` and `wiring` keeps today's files and consumers untouched, and a scene failure (for example a
`pin_conflict`) doesn't skip `simulate`.

Affects:
- I (T01/T20): the contract changes above; a `not_implemented` stub of `build_scene` in
  `backend/tools/toolbox.py` and a fake in `backend/tools/fakes.py` that copies
  `fixtures/scene/timer/` (so `P2D_RUNNER=fake` shows a scene before T41 lands); stub files
  `backend/tools/scene.py` and `tests/unit/scene/`; `make types`; header data in the plant-monitor
  part YAMLs it owns (`esp32_devkitc`, `ssd1306_096_i2c`, `buzzer_passive`, `bme280_breakout`), or a
  grant to T41 for those new fields only; the ownership-map rows in the T41 card.
- T41 (B-cad): implements `build_scene`, wires the stage.
- B-validate (T21's `cross_checks.py`): maps `check_scene` to `scene_mismatch`. One line; T41 can
  do it with a grant.
- B-web: `'scene'` in `STAGES` (`state.ts`, `state.test.ts`), a "Build steps are complete" row in
  `CROSS_CHECKS` (`panels.tsx`), and the viewer reads `scene/*.json` and `layout.parts` instead of
  `/parts/library.json`. `guide.ts` can later render `instructions.json` (step ids change from
  `place-<ref>` to `place:<ref>`, which resets progress saved in the browser).
- Q: `tests/integration/` expectations that enumerate stages.
- Nobody else: `cad/layout.json`, `wiring.json`, `assembly.glb` and the BOM are unchanged.

Decisions needed (my recommendation first):
1. **Demo device for the scene goldens.** The plant monitor needs 3V3 three times, GND four times,
   and GPIO21 and GPIO22 twice each; the DevKitC has one 3V3, three GND and one of each GPIO, so its scene
   fails with `pin_conflict` (correctly: two female jumpers can't share a male pin).
   (a) Add `fixtures/specs/timer.json` (ESP32 + OLED + buzzer: one 3V3, two GND, fits) as the
   scene golden and the showcase candidate (T31); the plant monitor shows the scene stage red
   with an actionable message until a hub exists. (b) Put the handoff's breadboard hub (task 8) in T41,
   about +1.5 h.
2. **DevKitC mounting.** It has no holes. Recommend leaving `mount_holes: []`: the scene gets no
   screws for it and the step says how it's held (cradle or hot glue), rather than inventing holes.
   Its male headers point down, so female jumpers go underneath: the board needs about 10.5 mm under
   the pin tips (2.5 housing + 8 wire bend), which layout.py's header-clearance rule will require.
3. **Library data on the parts endpoint** (`SceneLayout.parts` vs `GET /parts/library.json`).
   Recommend `SceneLayout.parts`; the endpoint can come later if a page needs the whole library.

Workaround until decided: T41 keeps the scene models and the header data for the three timer parts
local to `backend/tools/scene.py` (`shortcut:` comment), tests `build_scene` by calling it directly,
and doesn't wire the stage until the contract lands.

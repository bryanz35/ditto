# Backend handoff: 3D build instructions (LEGO-style viewer)

> **For Claude Code.** Read this whole file first, then `CLAUDE.md` and `handoff/BUILD_PLAN.md`.
> Where those files disagree with this one on **paths or ownership, they win**: keep the intent and
> adapt the paths. Make a short plan, then do the tasks in section 5 in order. Each task has a
> "done when" line. Don't change existing spec fields (the schema is frozen); only add optional fields.

## 1. What changed and why

Ditto is pivoting toward beginners and young learners. After a run, the user sees a 3D model of
their device (hovering explodes it into parts), then builds it step by step like a LEGO manual: each
step plays a short 3D animation (print the case, drop a board onto its posts, drive the screws,
push on jumper wires, plug in USB and upload, close the lid). Skill level (beginner / intermediate /
expert) changes how many steps there are and how they're worded.

The frontend owns how things *look and move*. The backend owns **what goes where and in what order**.
That extends the rule already in `PROJECT_PLAN.md` ("the agent decides, code verifies"):

- **Code computes every coordinate and the step order.** These are deterministic functions of the
  spec + parts library + `layout.py` output.
- **The LLM writes words only:** part reasons (already in the spec) and, optionally, a friendlier
  rewrite of each step's text. It never outputs coordinates, refs or step order.

A working browser prototype of the viewer exists. Your job is to make the backend emit the three
JSON files it consumes.

## 2. What's in this handoff folder

| Path | What it is |
| --- | --- |
| `reference/instruction_spike.html` | The working viewer prototype (open it in Chrome; it loads three.js from a CDN). The JS functions `headerPins`, `pickPin`, `planSteps`, `textFor` are the logic you're porting. |
| `reference/scene_contracts.py` | **The contract.** Pydantic models for every file the viewer reads. Copy to `backend/contracts/scene.py`. |
| `reference/scene_reference.py` | A self-contained Python port of the spike logic that produces the files below. Run `python scene_reference.py out/` to see it work. Port its functions into the real stages. |
| `fixtures/timer/*.json` | Output of the reference for the spike's demo device (ESP32 + OLED + buzzer). **The frontend is building against these right now.** Your output must have the same shape. |

## 3. The contract

| File | Written by stage | Contains | Served at (suggested) |
| --- | --- | --- | --- |
| `layout.json` | `layout` | Case geometry, every object's home position, board transforms, explode offsets, print-bed layout | `GET /api/runs/{run_id}/layout.json` |
| `wiring.json` | `wiring` | The **physical** header pin each wire uses, pin tip positions, wire colors | `GET /api/runs/{run_id}/wiring.json` |
| `instructions.json` | `instructions` (**new**) | Ordered steps for all three skill levels. Steps hold refs only, never coordinates | `GET /api/runs/{run_id}/instructions.json` |
| `library.json` | static | The viewer-facing fields of each library part (to draw boards procedurally) | `GET /api/parts/library.json` |

All three run files carry the same `rev` (the spec revision they were built from).

**Refs** are the shared vocabulary between the files. Use exactly these patterns:

| Ref | Object |
| --- | --- |
| `base`, `lid` | Printed case parts |
| `<part_ref>` (e.g. `mcu`, `oled1`) | A placed board, same ref as the spec's `PartInstance.ref` |
| `<part_ref>.s<k>` (e.g. `mcu.s1`), `lid.s<k>` | Screw k of that board or of the lid, 1-based, in `mount_holes` order |
| `w.<part_ref>.<part_pin>` (e.g. `w.oled1.SDA`) | One jumper wire, one per spec `Connection` |
| `usb` | The USB cable |

**Action types** (the animation vocabulary): `print`, `place`, `screw`, `wire`, `plug`, `flash`, plus
`highlight` as a generic fallback (the viewer pulses the targets). Don't invent new types without
telling the frontend.

### SSE

Match the existing event envelope in the codebase. Add:

- `scene`: emitted once **all three** files exist for a rev.
  `{"type": "scene", "run_id": "...", "rev": 7, "layout": "<url>", "wiring": "<url>", "instructions": "<url>", "library": "<url>"}`
- `stale`: emitted when a spec patch starts rerunning any of `layout`, `wiring` or `instructions`.
  `{"type": "stale", "run_id": "...", "rev_pending": 8, "stages": ["layout", "wiring", "instructions"]}`.
  The viewer greys out until the next `scene`.

All three skill levels are precomputed in `instructions.json`, so the skill toggle in the UI needs no
backend call.

## 4. Coordinate frames (read carefully: most bugs will be here)

**Web frame** (everything in the JSON): millimetres, **Y-up**, origin = centre of the case's bottom
face. `+x` right, `+y` up, `+z` toward the viewer ("front").

**CAD frame** (build123d / `layout.py`): millimetres, **Z-up**, same origin (`box_lid` already uses
`Align.MIN` on z, centred on x and y).

Convert in **exactly one function**, e.g. `backend/tools/frame.py`:

```python
TO_WEB = np.array([[1, 0, 0, 0],
                   [0, 0, 1, 0],
                   [0,-1, 0, 0],
                   [0, 0, 0, 1]], float)          # (x, y, z)_cad -> (x, z, -y)_web
```

So the CAD front wall (`-y`, as in `cutout()` in `box_lid.py`) becomes web `+z`, facing the camera.

**Part-local frame** `(u, v, h)`: the library's own 2D offsets (`mount_holes`, `features`, and the
new `headers`) with `h` up from the PCB's bottom face. Use whatever origin the YAML already uses
(the board's corner, per `PROJECT_PLAN.md`). Each placed board gets:

```python
local_to_world = TO_WEB @ T(cx, cy, floor + standoff) @ Rz(rot_deg) @ T(-l/2, -w/2, 0)
# serialise COLUMN-MAJOR: m.flatten(order="F")   <- three.js Matrix4.fromArray expects this
```

The viewer builds each board in its local frame and applies that matrix, so it never flips axes itself.

**Sanity check (make it a unit test).** In `fixtures/timer`, the ESP32's corner sits at CAD
`(-45.5, -14, 7)`. Header J2 pin 0 (3V3) is at local `(50.36, 1.3)`, with its tip at
`h = 1.6 + 6`. That gives CAD `(4.86, -12.7, 14.6)`, which is web **`(4.86, 14.6, 12.7)`**.
Your code must reproduce that number.

**Meshes are optional.** The viewer builds the box-and-lid case procedurally from the `enclosure`
block, so you don't need to ship meshes for the demo. If you later add GLBs (for free-form extras),
put their URLs in `enclosure.meshes`. build123d's `export_gltf` already rotates Z-up to Y-up. glTF
is defined in metres, so **verify the scale with a 10 mm test cube** before relying on it. If it
comes out 0.01 instead of 10, multiply by 1000. `assembly.glb` is no longer needed by the viewer:
deprioritise it.

## 5. Tasks (in order)

Times are rough guesses. Tasks 1–6 are the demo. Do 7 and 8 only if time allows.

### Task 1: Contracts and fixtures in the repo (≈30 min, unblocks the frontend)
- Copy `scene_contracts.py` to `backend/contracts/scene.py`. Copy `fixtures/timer/` to
  `tests/fixtures/scene/timer/`.
- Add a test that loads each fixture through its model (`Layout`, `Wiring`, `Instructions`, `ViewerPart`).
- Add `skill_level: Literal["beginner","intermediate","expert"] = "beginner"` to `UserContext` (optional
  field, so the freeze still holds). Pass it into the parts-and-pins prompt: beginners get no soldering,
  plug-in modules, at most about 4 modules, and kid-friendly `reason` text.
- **Done when** the fixtures validate in CI and `UserContext` round-trips with and without the new field.

### Task 2: Parts library additions (≈1 h, mostly measuring)
For every part used by the demo devices (showcase device, plant monitor, makerspace device), add:

```yaml
short_name: screen            # kid-friendly noun used in step text
pcb_color: "#1f4e9c"          # optional, for the procedural model
headers:
  - id: H1
    origin: [9.84, 26.1]      # (u, v) of pin index 0, same origin as mount_holes
    pitch: [2.54, 0]          # step to the next pin
    side: bottom              # which way the pins point: top | bottom
    pin_len_mm: 6
    pins: [GND, VCC, SCL, SDA]
look:                         # optional cosmetic shapes, see LookShape in the contract
  - {shape: screen, at: [13.65, 13.4], size: [22, 11, 0]}
```

- MCU header pin names **must equal the strings the spec uses** for `mcu_pin` (`GPIO21`, `3V3`, `GND`),
  and must list the flash pins too so they're physically present.
- Measure header positions with calipers like `board_mm`. Mark the part `provisional: true` until measured.
- `features` gains `sound_port` (buzzers/speakers) so the lid gets holes. `display_window` already exists.
- Serve `GET /api/parts/library.json` as `{part_id: ViewerPart}`.
- **Done when** a validator asserts that every header pin name is in the part's `pins` list and vice
  versa, for every library part.

### Task 3: Write `layout.json` from the layout stage (≈1.5 h)
Port `build_layout()` from the reference, fed by the real `layout.py` placements.
- One `SceneObject` per board (with `local_to_world`), per screw, plus `base`, `lid` and `usb`.
- Cutouts come from `usb` features, lid openings from `display_window` and `sound_port` features,
  standoffs from `mount_holes` plus standoff heights.
- **Explode offsets** (deterministic rule, from the reference):
  - Boards rise `28 + 6*i` mm in mount order.
  - A board sitting under a lid window slides sideways out of the case footprint, 8 mm clear of the
    wall and 22 mm up, so the exploded lid doesn't hide it.
  - Screws take their parent's offset plus 18 mm up.
  - The lid goes 35 mm above the tallest exploded board inside the case; its screws go 22 mm above that.
  - The USB cable moves 34 mm along its axis.
- `print_layout`: base at the origin, lid beside it on the bed (from `UserContext.printer`).
- **New layout rules** (the spike hit both):
  1. **Top-facing displays sit just under the lid.** Set the standoff so the display surface is
     ≤ 3 mm below the lid's underside. Otherwise the window shows wires instead of the screen.
  2. **Header clearance.** For `side: top`, require
     `board_top + pin_len + 2.5 (connector housing) + 8 (wire bend) ≤ floor + inner_h`.
     For `side: bottom`, require `standoff ≥ pin_len + 2.5 + 8`. Include this headroom when computing
     cavity height.
- **Feed `layout.json` (or the same in-memory object) to `box_lid.py` too.** Then the CAD and the
  viewer can't disagree.
- **Done when** the timer fixture reproduces from real code (positions within 0.01 mm), and the
  frame unit test from section 4 passes.

### Task 4: Pin allocation in the wiring stage, writing `wiring.json` (≈1 h)
Port `header_pins()` and `build_wiring()`.
- The spec says `mcu_pin: "GND"`, but a builder pushes a wire onto **one specific header pin**.
  Allocate the nearest unused pin with that name. Two wires can never share one pin.
- If no free pin is left, raise `PinConflict`, which becomes
  `request_change(field="connections", reason=..., options=[...])`. Good options: another pin with the
  same function, 5V instead of 3V3 for parts whose `supply_voltage` allows it, or a breadboard hub (task 8).
- Wire colors: GND black, 3V3/5V red, SCL yellow, SDA blue, everything else green/orange/purple/white.
- Update the dependency map, since the wiring stage now needs world positions:

```python
DEPENDS_ON["wiring"] = {"mcu", "parts", "connections", "layout"}               # CHANGED
DEPENDS_ON["instructions"] = {"layout", "wiring", "enclosure", "user"}          # NEW
ORDER = ["validate", "layout", "enclosure", "assembly", "firmware", "wiring",
         "instructions", "simulate", "bom"]
```

- **Done when** the timer fixture reproduces, and a test with two parts both needing `3V3` on a
  DevKitC raises `PinConflict`.

### Task 5: The `instructions` stage (≈1 h)
Port `plan_steps()`, `needs()`, `step_text()` and `check_instructions()`.
- The order is fixed by code: print, then mount (MCU first, then shortest parts first), then wire
  (one step per part), then plug & upload, then lid.
- Granularity by skill: **beginner** splits place and screw into separate steps; **intermediate**
  merges them per part; **expert** does one mount step and one wire step. All three go in one file.
  On the timer fixture that's 11, 8 and 5 steps.
- `step_text()` templates are the **fallback text and must always exist**.
- Add `check_instructions()` to `cross_checks` and show it in the checks panel as
  "Instructions complete". It verifies that:
  - every ref exists;
  - every board, screw, wire, the lid and the cable is installed exactly once per skill level;
  - upload comes after all wiring;
  - the lid is last;
  - no MCU pin is used twice.
- **Done when** the timer fixture reproduces and the check passes on all demo devices.

### Task 6: API, SSE and replay (≈45 min)
- Add the endpoints in section 3, plus the `scene` and `stale` events.
- `P2D_RUNNER=replay:<dir>` must serve all four files and emit `scene` like a live run.
  **The judging demo will run from replay.**
- Commit golden outputs for each demo device to `tests/fixtures/scene/<device>/` and tell Caden.
  The frontend swaps them in as mocks.
- **Done when** `curl` returns all four files for a replayed run and the frontend viewer loads them.

### Task 7 (optional): LLM text polish
- One call per skill level. Input: the steps (`id`, `kind`, `title`, template `text`, part names and
  reasons). Output: `{"texts": {"<step id>": "<text>"}}`, nothing else.
- Reject the output and keep the template if:
  - the step ids differ;
  - the length is over 50 words (beginner), 25 (intermediate) or 12 (expert);
  - it contains any number that isn't in the template (this catches made-up quantities and pins).
- Cache by `(rev, skill)`. When text changes, bump `text_rev` and re-emit `scene`.

### Task 8 (optional, but needed if the plant monitor stays the reference): breadboard hub for shared nets
As far as we know (verify against Espressif's DevKitC V4 pinout), the DevKitC has **one 3V3 pin,
one 5V pin and three GND pins**. The plant monitor has four modules, so it can't be wired with
jumpers alone: the allocator will (correctly) raise `PinConflict`. Fix it by adding a
`mini_breadboard` library part (kind hub). When a net has more than one member, wire MCU pin →
breadboard row, then each part → that row (`kind: "jumper_mf"`, pin `dir: 1`, holes as `PinWorld`).
Alternatively, choose demo devices that pass the allocator without a hub.

## 6. Other physical issues found while building the prototype
- **The DevKitC has no mounting holes** (as far as we know). The fixture invents four. Decide between
  a printed clip/cradle and a board with holes, and update the library honestly.
- **Header direction matters.** A screen whose pins point up collides with the lid; pointing down
  needs taller posts. Encode `side` per header; the clearance rule in task 3 catches the rest.
- **Two female jumpers can't share a male pin**, even where `validate_pins` allows shared I2C lines.
  Electrical validity ≠ buildable.

## 7. Don'ts
- Don't let the model emit coordinates, refs, step order or pin choices.
- Don't add axis flips anywhere except `frame.py`.
- Don't block the demo on GLB meshes or `assembly.glb`.
- Don't hide a failing instructions check. Show it red like the others.
- Don't rename refs or action types without telling the frontend: those strings are the contract.

## 8. How the frontend uses each field (so you know what breaks it)
| Field | Viewer behaviour |
| --- | --- |
| `objects[].position` / `local_to_world` | Home pose. Animations add offsets on top |
| `objects[].explode` | Target offset when the user hovers the overview model |
| `objects[].axis` | Screws spin and travel along it; the cable slides in along it |
| `wiring.pins[].position`, `dir` | Wire endpoints; the connector housing goes on the side `dir` points to |
| `steps[].actions` | Played in order; each target animates one after another |
| `steps[].focus` | The camera frames these refs |
| `steps[].needs` | The "You need" box |
| `steps[].text` | Shown verbatim |
| `rev` mismatch between files | Viewer waits; shows the stale state |

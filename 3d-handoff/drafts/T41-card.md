# T41 task card (draft)

<!-- Draft for the Integrator. Four pieces, each for the file named in its heading. The contract
     request it relies on is drafted next to this file (T41-scene.md). -->

## 1. `handoff/BUILD_PLAN.md`: task table row

```
| T41 | 3D build scene | 4 | T11, T14 | B-cad | R | B-web | Unit (frame, pins, steps, check); integration on the timer golden | 5–6 h |
```

## 2. `handoff/BUILD_PLAN.md`: card

### T41 · 3D build scene

- **Agent:** B-cad · **Wave:** 4 · **Depends on:** T11, T14 · contract request `T41-scene`
- **Owns:** `backend/tools/scene.py`, `tests/unit/scene/`, `fixtures/runs/timer/` (the recorded timer run and its scene goldens, a
  grant like T12's `fixtures/firmware/`);
  shared with earlier tasks: `backend/tools/layout.py` and `backend/tools/build_enclosure.py`
  (after T11), `backend/runtime/deps.py` and `backend/runtime/stages.py` (after T14, T22, T39). With
  a grant: the contract's new fields (`short_name`, `pcb_z_mm`, `pcb_t_mm`, `pcb_color`, `headers`,
  `look`) in `esp32_devkitc.yaml`, `ssd1306_096_i2c.yaml` and `buzzer_passive.yaml`, and the
  `scene_mismatch` line in `backend/tools/cross_checks.py`.
- **Read first:** `3d-handoff/handoff/3D_INSTRUCTIONS.md` sections 3, 4 and 5 for intent and the
  explode rules; `backend/contracts/base.py` and `scene.py` for the frames, which differ from section 4
  (the enclosure origin is the cavity's front-left floor corner, `board_mm.h` includes the headers).
  `reference/scene_reference.py` is a port guide, not a spec: it hard-codes the `mcu` ref, the
  timer's parts, invented mount holes and a centred origin.
- **Why:** the 3D viewer shows the device exploding into parts and plays each build step as an
  animation. Code computes every position, pin and step; the model writes no coordinates.
- **Build:**
  - `build_scene(spec, layout, manifest, lib, printer, out_dir)` writes `scene/layout.json`,
    `scene/wiring.json` and `scene/instructions.json`. Pure and deterministic like the other tools.
  - **One frame function** in `scene.py`: enclosure frame (x, y, z) to web (x - L/2, z + wall, W/2 - y).
    Board transform `local_to_world = to_web @ T(x_mm, y_mm, z_mm)` (rotation is always 0), serialised
    column-major. No other code flips axes.
  - **Geometry from the CAD inputs, not recomputed:** cutouts and lid openings from
    `manifest.cutouts`; standoffs from a `standoffs(spec, layout, lib)` helper factored out of
    `build_enclosure` and used by both; lid screws from the `CORNER_POST_MM` posts; lid and floor
    thickness `wall_mm`, lid lip `LIP_MM`. This way the CAD and the viewer can't disagree.
  - **Explode offsets** as in the handoff (boards rise `28 + 6*i` in mount order, a board under a lid
    window slides out sideways, screws +18 over their parent, the lid 35 over the tallest exploded board,
    its screws +22, the cable 34 along its axis). `print_layout` from the printer profile's bed.
  - **Physical pin allocation:** each `Connection` gets the nearest free MCU header pin with that
    name; none free gives `pin_conflict` (field `connections`), and the message lists what would work
    (another pin of the same function, 5V when the part's `supply_voltage` allows it). Wire colours
    as in the handoff.
  - **Steps** for all three levels in one file, ordered by code: print, mount (MCU first, then
    shortest parts first), one wire step per wired part, plug and upload, lid. Beginner splits place
    and screw, intermediate merges them per part, expert has one mount and one wire step. Never emit a
    step with no targets (no screw step for a part without mount holes). Parts with `mounting:
    external` get a place step that feeds their cable through its hole (the handoff has none).
    Template text never names one device ("25:00" is the timer's). Upload text matches `guide.ts`
    (PlatformIO or the Arduino IDE): the app has no Upload button.
  - **layout.py rules:** a top-facing `display_window` part sits with its top at most 3 mm under
    the lid (compute the cavity height first, then raise the display); headers that get wires need
    `2.5 + 8` mm free past the pin tips (above `z_mm + board_mm.h` for `top`, below `z_mm + pcb_z_mm`
    for `bottom`); both count towards the cavity height.
  - **Stage:** `DEPENDS_ON["scene"] = {"layout", "enclosure", "mcu", "parts", "connections"}` placed
    after `wiring` (user changes reach it through `enclosure`); in `stages.py`, skip with a message
    when layout or enclosure didn't pass, otherwise call `tb.build_scene` with
    `cad/layout.json`, `cad/manifest.json` and the printer used by `check_enclosure`.
  - **Header data** for the timer's three parts from datasheets, `provisional: true` as today.
  - **Goldens:** record one live run of the timer prompt (one paid run) into `fixtures/runs/timer/`,
    scene files included; tell B-web.
- **Out of scope (follow-ups):** LLM rewrites of step text (handoff task 7), the breadboard hub
  (handoff task 8, unless the Integrator picks option (b) of the request's decision 1), GLB meshes
  for the case. `assembly.glb` stays as it is.
- **Acceptance:**
  - [ ] Frame test: enclosure `(0, 0, -wall)` maps to web `(-L/2, 0, W/2)` and the cavity floor's
        centre to `(0, wall, 0)`; a board's header pin through `local_to_world` lands where
        `to_web` puts the same point computed by hand.
  - [ ] Every standoff and cutout in `scene/layout.json` equals the CAD's (`standoffs()` and
        `manifest.cutouts` through `to_web`), within 0.01 mm.
  - [ ] Two parts both needing `3V3` on a DevKitC give `pin_conflict` on `connections`, with a message
        that names the alternatives.
  - [ ] The timer spec gives files that validate against the scene contracts, pass `check_scene` for
        all three levels, and have the same refs and action types as `fixtures/scene/timer/`.
  - [ ] `check_scene` fails on hand-broken copies: the lid not last, a wire missing, a screw twice.
  - [ ] Same spec twice gives byte-identical files.
  - [ ] An edit that changes `connections` reruns `scene` (`stages_to_rerun` test); an edit to
        `firmware` doesn't.
  - [ ] `P2D_RUNNER=replay:fixtures/runs/timer make dev`: `curl` returns all three files from
        `/runs/{id}/files/scene/...` and the `scene` stage passes.
- **Tests:** `tests/unit/scene/` (frame, allocator, steps, explode, check); a test in
  `tests/unit/api/test_deps.py` for the new dependency row; the replay smoke run by hand.
- **Consumer sign-off (B-web):** the viewer loads the timer goldens from a replayed run and
  greys out on the `scene` stage's `stale` event.

## 3. `handoff/tasks.json`

Add to `tasks` (before `T35`, which stays last):

```json
{
  "id": "T41",
  "title": "3D build scene",
  "kind": "builder",
  "agent": "B-cad",
  "person": "B",
  "slug": "scene",
  "deps": ["T11", "T14"],
  "consumers": ["B-web"],
  "soft": [],
  "slow": false,
  "branch": "feat/T41-scene"
}
```

and append `"T41"` to `agents["B-cad"]`.

## 4. `CLAUDE.md`: ownership map rows

```
| `backend/tools/scene.py`, `fixtures/runs/timer/` | T41 | 3D build scene; recorded timer run |
```

and extend the existing rows: `backend/tools/layout.py`, `backend/tools/build_enclosure.py` →
"T11, then T41"; `backend/runtime/` → "T14, then T22, T39, T41" (T41: `deps.py`, `stages.py` only).

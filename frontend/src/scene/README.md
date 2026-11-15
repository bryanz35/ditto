# 3D scene (`scene/`)

The device in the overview and the build guide, ported from the 3D instruction spike.

- `parts.ts`: one procedural model per library part (`LOOKS`, keyed by part id). A custom part borrows
  one of `GENERIC` (preview them all at `/parts.html`): the spec's `look` (PartDef.look, which the
  parts agent sets), else one its name suggests (`NAMED` regexes: "pot" → `pot_rotary`, ...), else
  its category's fallback. Boards and displays never borrow. Adding a look: a `PartLook` value in
  `backend/contracts/parts.py`, `make types`, the `GENERIC` entry (tsc fails until it exists) and
  the list in `backend/agent/prompts/parts.md`. Header pins sit on the edge facing the board; a board's USB faces its
  nearest wall. `LIBRARY` copies the bits of `backend/parts/library/*.yaml` the view needs (category,
  size, pin order, external): add a row when you add a library part.
- `device.ts`: builds the scene from what the app already loads: `assembly.glb` (case, lid, one box per
  inside part, named by ref), the spec (part ids, outside parts) and `wiring.json` (one jumper per row).
  `setOverview(exploded)` / `setBuild(steps, index)` pick what is shown; `update(dt)` animates:
  - Overview: lid see-through, wires in; hovering or "Exploded" pulls the parts apart.
  - Print: the base grows under the nozzle. Place: the part drops in under an arrow. Wiring: that
    part's wires go on one by one. Code: the USB plug goes in, the board uploads, screens light.
    Close: the lid drops on and its screws turn. Each step loops.
- `Viewer3D.tsx` mounts it (react-three-fiber) and keeps the old STL view for runs with no assembly.

Debugging: `npm run dev`, open `/viewer.html` (the plant_monitor fixture) or `/viewer.html?run=<id>`
(a real run through the API) and click through the steps. In dev builds `window.__device` is the scene.

- `route.ts`: each wire's path. Straight up off the pin, across, down onto the other pin, taking the
  lowest clear way: round a tall part when it can, over it (under the lid) when it can't. The parts at
  a wire's own ends don't count near their pins (a low pin on a tall part). An outside part's wires
  leave through its cable hole (cad/manifest.json) and go up over whatever lies between. Every
  candidate is checked against the part boxes and the printed shells (case, lid, a custom device's
  prints, through a BVH). `device.wireClips()` lists what each wire still hits (all `[]` normally);
  dev builds log `[wires] ... clips ...` for the rest.

Known shortcuts: pins are drawn pointing up so the wires read clearly (a DevKitC's point down);
wires don't avoid each other beyond a small spread; outside parts lie behind the case, not at their
cable hole; the shell check follows a wire's centreline, not its full radius; on a custom body the
cable's real way from the hole to a part (inside the body, along an arm) isn't known, so those wires
can still clip it (dev builds say which); the explode offsets are a simple rule (board lowest, the rest
stacked and spread).

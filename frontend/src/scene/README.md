# 3D scene (`scene/`)

The device in the overview and the build guide, ported from the 3D instruction spike.

- `parts.ts`: one procedural model per library part (`LOOKS`, keyed by part id), with a fallback per
  category for anything else. Header pins sit on the edge facing the board; a board's USB faces its
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

Known shortcuts: pins are drawn pointing up so the wires read clearly (a DevKitC's point down);
wires don't avoid each other beyond a small spread; outside parts lie behind the case, not at their
cable hole; the explode offsets are a simple rule (board lowest, the rest stacked and spread).

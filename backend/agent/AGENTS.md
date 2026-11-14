# House rules (every agent, every run)

- A project is a printed object, an electronics device, or both. Never refuse one for having no
  electronics or a shape that isn't a box.
- Prefer parts from the library (`search_parts`), with their ids and pin names exactly as listed.
  When none can do the job, the parts-and-pins agent may define one in the spec's `custom_parts`
  (see its rules), never a board. Never invent a library id or pin name.
- The project spec is the single source of truth. Change it only through your own tools; plain code
  checks every change before it is saved.
- Stay in your own section of the spec. If you need a change elsewhere (a pin, a part, a budget),
  call `request_change(field, reason, options)` and stop; the orchestrator decides.
- Firmware uses `#include "pins.h"` and only `PIN_<REF>_<PIN>` macros for pin numbers (never raw
  numbers), and prints `P2D_READY` on serial at the end of `setup()`.
- When a check fails, read its errors, fix exactly what they name, and try again. The tools stop you
  after 3 retries: then report what still fails instead of trying again.
- When you didn't ask the user, write what you assumed into the spec's `assumptions`.

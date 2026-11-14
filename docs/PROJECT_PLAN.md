# Project plan: Prompt-to-Device (technical reference for agents)

This is the repo copy of the team's project plan doc, kept for Claude Code agents, which can't open the
original. It holds the technical design. **Where this file and `handoff/BUILD_PLAN.md` or `CLAUDE.md`
disagree on file paths or ownership, those two files win.** Paths below already follow the build plan.

## What we're building

A Lovable-style web app that turns a text prompt, a sketch or a short video into a buildable device: a
parts list with real prices, a wiring plan, compiled firmware and a 3D-printable enclosure, with every
step checked by code. At the demo the team shows an AI-powered device that the tool designed during the
hackathon. Pitch line: "AI that builds physical AI."

Target users: students and makers at a campus makerspace or engineering club; solo founders who need a
prototype before hiring an engineer; people who need a custom assistive device that isn't sold anywhere.

Demo success criteria:

- Three example prompts run end to end, each in a few minutes.
- Every run shows passing checks: spec valid, firmware compiles, enclosure printable, BOM within budget.
- One device designed by the tool runs firmware it wrote and calls an AI model: printed and assembled
  if we have parts and a printer, on a breadboard if we only have parts, in the Wokwi simulator if we
  have neither (see "Hardware availability").
- A live change ("add a buzzer") updates firmware, wiring, BOM and enclosure together.

Features that exist because a judge scores them: inventory and budget memory (reuse owned parts, price
only what's missing, remember rejected choices); explain mode (each part and pin carries a one-line
reason); a checks panel visible on every run; one assistive-device example prompt.

## Scope

| In scope | Out of scope |
| --- | --- |
| ESP32 boards plus breakout modules, wired with jumpers or perfboard | Custom PCB fabrication (stretch: tscircuit preview, render only) |
| A curated library of 25–40 parts with verified pinouts | Choosing from every part on the market |
| Template enclosure (box and lid), free-form CAD code for small extras | Moving mechanisms, multi-part assemblies, injection molding |
| Arduino-framework firmware built with PlatformIO | ESP-IDF, RTOS work, over-the-air updates |
| BOM with cached and live prices | Placing orders |
| Input as text, image or sketch, and video (keyframes plus transcript) | True video-to-CAD |
| Inventory and budget memory, explain mode | User accounts and teams |

Example devices:

1. **Showcase device: to be decided (physical build).** Placeholder. Must use only library parts, call an
   AI model through our backend (for the Physical AI track), and be printed and working by hour 28.
2. **Plant monitor (example prompt):** ESP32 DevKit, capacitive soil-moisture sensor, BME280, OLED,
   buzzer alert. The reference case for every fixture and test.
3. **The makerspace's request (example prompt):** chosen after the team's interview.

## Hardware availability

It isn't yet confirmed that we'll have electronics parts or a 3D printer at the event. The tool itself
(prompt → verified design files) needs neither; hardware affects only the showcase demo. The humans
record what's available in `handoff/HARDWARE.md` by hour 2, which sets the mode:

- **P** (parts + printer): print and assemble the showcase device.
- **E** (parts, no printer): showcase device on a breadboard; the enclosure is shown as a 3D assembly
  preview and exported print-ready.
- **V** (no parts): showcase firmware runs in the Wokwi simulator, beside the 3D assembly preview.

Two features exist so every mode has a convincing demo: an **assembly preview** (`assembly.glb`: the
enclosure, an exploded lid, and every part placed where the layout puts it) and **simulation** (a Wokwi
`diagram.json` generated from the spec, run with `wokwi-cli` until the firmware prints `P2D_READY`).
Wokwi needs an API token (`WOKWI_CLI_TOKEN`) and internet access: firmware is uploaded to its servers
for the run. Choose the showcase device from parts Wokwi supports, so a late change of mode never forces
a new device. Full fallback table: section 0 of `handoff/BUILD_PLAN.md`.

## Architecture

One orchestrator agent plans the build and hands each domain to a specialist sub-agent. Every sub-agent
reads and writes the same project spec, and plain-code tools check each result before the UI shows it.

```
 Web app ──SSE── API server ◄── showcase device (requests via relay)
                     │
 Memory ◄──► Orchestrator (deepagents) ◄──► Project spec (spec.json)
                     │
   ┌─────────────┬───┴─────────┬──────────────┐
 Parts+pins   Firmware     Enclosure     BOM pricing (tool)
   │  ▲          │  ▲          │  ▲          │  ▲
   ▼  │ retry    ▼  │          ▼  │          ▼  │
 validate_spec  PlatformIO   CAD build     Budget check     ← plain-code checks,
 pins/voltage   compile      watertight,   total vs budget     failures go back to the
 /I2C                        fits bed                           sub-agent (max 3 retries)
```

| Component | Technology | Job |
| --- | --- | --- |
| Web app | Vite, React, TypeScript; @react-three/fiber; server-sent events (SSE) | Chat, upload, tabs for 3D, wiring, BOM, code and checks |
| API server | FastAPI | Runs agent sessions, streams events, serves files |
| Orchestrator | LangChain deepagents | Plans, delegates, retries failed checks, patches the spec on edits |
| Parts and pins sub-agent | deepagents sub-agent | Picks library parts, assigns pins, writes a reason for each |
| Firmware sub-agent | deepagents sub-agent | Writes Arduino `main.cpp` (pins come from generated `pins.h`) |
| Enclosure sub-agent | deepagents sub-agent | Sets enclosure parameters and extras; geometry comes from the template |
| Check tools | Pydantic, PlatformIO, build123d, trimesh | Validate, compile, build and check |
| Pricing | Nexar GraphQL API with a JSON cache | Unit prices and stock per BOM line |
| Input preprocessing | ffmpeg, Whisper | Video → keyframes + transcript |
| Memory | SQLite | Inventory, budget, rejected choices |
| Device relay | FastAPI router | Calls the AI model for the showcase device so the API key never sits on the device |

**How a run flows**

1. The orchestrator reads the prompt, images and inventory. It asks at most two clarifying questions;
   otherwise it states assumptions and continues.
2. The parts and pins sub-agent drafts the spec; `validate_spec` checks it (up to 3 retries).
3. Firmware and enclosure sub-agents run in parallel on the validated spec, each with its check and retry loop.
4. `price_bom` prices the parts list, subtracting owned parts.
5. The UI receives each stage's result as an event and fills its tab.

### Keeping the sub-tasks aligned

Sub-agents never coordinate directly. Every value that crosses domains is computed from the spec by code,
so a part swap reaches the CAD and the firmware automatically; the orchestrator steps in only when a
change can't be satisfied.

1. **Geometry comes from the parts library, not from the enclosure agent.** A deterministic layout step
   (`backend/tools/layout.py`) places each module's footprint (`board_mm`, `mount_holes`, `features`) on
   the base plate. Modules with a USB port, lens or display go against the wall their feature faces; the
   rest are packed in rows with `clearance_mm` gaps. Standoffs, cutouts and cavity size are computed from
   those placements. Swap a 0.96" OLED for a 1.3" one and the window, standoffs and box size change on
   the next run without the model touching them.
2. **Each stage declares what it reads.** After any spec patch, code compares old and new spec and reruns
   only stages whose inputs changed, in dependency order.
3. **Every output records the spec revision it was built from.** The spec has a `rev` counter; the UI
   marks artifacts from an older rev as out of date until the rerun finishes.
4. **Cross-domain checks run after every rerun.** `pins.h` matches `connections`; every wall-facing part
   feature has a cutout; every module fits the cavity; every BOM line maps to a part.
5. **Conflicts go up, not sideways.** A sub-agent that can't satisfy the spec calls
   `request_change(field, reason, options)` instead of editing another stage's section. The orchestrator
   picks an option or asks the user, then patches the spec, which restarts step 2.

| Spec change | Stages that rerun |
| --- | --- |
| Part added, removed or swapped | validate, layout, enclosure, assembly, firmware, wiring, simulate, BOM |
| Pin reassigned | validate, firmware, wiring, simulate |
| Enclosure parameter (wall, clearance) | layout, enclosure, assembly |
| Firmware behavior | firmware, simulate |
| Budget or owned parts | BOM (and part choice if over budget) |

```python
# backend/runtime/deps.py
DEPENDS_ON = {            # stage -> spec fields or stages it reads
    "validate":  {"mcu", "parts", "connections"},
    "layout":    {"mcu", "parts", "enclosure"},
    "enclosure": {"layout", "enclosure"},
    "assembly":  {"layout", "enclosure"},
    "firmware":  {"mcu", "parts", "connections", "firmware"},
    "wiring":    {"mcu", "parts", "connections"},
    "simulate":  {"firmware", "wiring"},        # skipped when the mode doesn't need it
    "bom":       {"mcu", "parts", "user"},
}
ORDER = ["validate", "layout", "enclosure", "assembly", "firmware", "wiring", "simulate", "bom"]  # topological

def changed_fields(old: dict, new: dict) -> set[str]:
    return {k for k in new if old.get(k) != new.get(k)}

def stages_to_rerun(changed: set[str]) -> list[str]:
    dirty = set(changed)
    for stage in ORDER:
        if DEPENDS_ON[stage] & dirty:
            dirty.add(stage)          # later stages that read this stage rerun too
    return [s for s in ORDER if s in dirty]

# stages_to_rerun({"parts"})     -> all eight stages
# stages_to_rerun({"enclosure"}) -> ["layout", "enclosure", "assembly"]
```

## Using deepagents

Deep Agents (`pip install deepagents`) is LangChain's "agent harness" built on LangGraph. Its core loop
is an ordinary tool-calling loop; what it adds is built-in planning, a virtual filesystem, sub-agents,
memory, human-in-the-loop and context management. The sponsor's workshop
(`langchain-samples/hack-princeton-intro-to-deep-agents`) builds an agent with `create_deep_agent()` and
serves it with `langgraph dev`. Check the installed version's docs before coding: APIs have changed
between versions (planning became opt-in in v0.7).

How we use each feature, and what we deliberately keep in our own code:

| Feature | What it is | Our use |
| --- | --- | --- |
| Sub-agents (`task` tool) | The orchestrator delegates to a named sub-agent, which works in its own isolated context and returns one report | Three specialists: parts-and-pins, firmware, enclosure. Each sees only its tools. Firmware and enclosure run in parallel (async sub-agents if supported) |
| Planning (`write_todos`) | A to-do list the agent writes and updates; it doesn't execute anything but keeps long tasks on track | Enabled; every update is streamed to the UI as a `plan` event, so judges see the agent's live plan |
| Virtual filesystem (`ls`, `read_file`, `write_file`, `edit_file`, …) with pluggable backends | A workspace for notes and intermediate results | **Scratchpad only** (in-memory backend). Real artifacts are written only by our validated tools |
| Human-in-the-loop (`interrupt_on` + a checkpointer) | Pause before a tool call for approval, edits or answers | Clarifying questions (max two) and approving an over-budget BOM, shown as `question` events |
| Checkpointer / threads | Durable conversation state per thread | `thread_id = run_id`, so edits continue the same conversation |
| Memory (`AGENTS.md` via `memory`) | Instructions always loaded, which the agent can update | House rules: library parts only, `PIN_*` macros, `P2D_READY`, `request_change` |
| Per-sub-agent `model` | Different models for different sub-agents | Stronger model for parts-and-pins; faster one elsewhere |

What stays in plain code, not in the agent: every check, the 3-retry limit, the stage dependency map
and reruns, layout and geometry, pin numbers (`pins.h`), and pricing. The agent decides; code verifies.

## Project spec schema

The spec is the single source of truth. The agent fills it through structured output; plain code
computes the BOM, check results, module layout and enclosure dimensions (from the library), never the
model. After the freeze, change it only by adding optional fields. T01 adds `rev`, `Placement` and
`Layout` (see `handoff/BUILD_PLAN.md`).

```python
# Sketch of backend/contracts/spec.py. The code is authoritative (it adds rev, Placement, Layout).
from typing import Literal
from pydantic import BaseModel, Field

class UserContext(BaseModel):
    budget_usd: float | None = None
    owned: dict[str, int] = {}              # part id -> quantity, from the inventory memory
    printer: str | None = None              # e.g. "bambu-p1s"
    rejected: list[str] = []                # "no buzzers", "smaller case"

class PartInstance(BaseModel):
    ref: str                                # "oled1", unique in this spec
    part_id: str                            # key into the parts library
    qty: int = 1
    role: str                               # "shows soil moisture"
    reason: str                             # explain mode: why this part
    i2c_address: str | None = None          # I2C parts: which of the part's addresses this one uses

class Connection(BaseModel):
    part_ref: str                           # "oled1"
    part_pin: str                           # "SDA"
    mcu_pin: str                            # "GPIO5", "3V3", "GND"
    bus: Literal["i2c", "spi", "i2s", "uart", "gpio", "analog", "power"]
    reason: str = ""

class EnclosureSpec(BaseModel):             # openings come from the parts' library features
    template: Literal["box_lid"] = "box_lid"
    wall_mm: float = Field(2.0, ge=1.2, le=4.0)
    clearance_mm: float = 1.0
    extras: list[str] = []                  # free-form CAD requests, e.g. "belt clip"

class FirmwareSpec(BaseModel):
    framework: Literal["arduino"] = "arduino"
    behaviors: list[str]                    # "every 10 min, read soil moisture and show it"
    needs_wifi: bool = False

class ProjectSpec(BaseModel):
    title: str
    prompt: str
    requirements: list[str]                 # restated, testable requirements
    assumptions: list[str] = []             # stated when we didn't ask
    user: UserContext = UserContext()
    mcu: PartInstance
    parts: list[PartInstance]
    connections: list[Connection]
    firmware: FirmwareSpec
    enclosure: EnclosureSpec = EnclosureSpec()
```

## Parts library

The agent chooses only from a hand-checked library of 25–40 parts, which stops it inventing pinouts. One
YAML file per part, checked against its datasheet and measured with calipers.

| Field | Used by | Notes |
| --- | --- | --- |
| `id`, `name`, `category` | Parts agent, UI | Stable key referenced by the spec |
| `pins` (name, type, voltage) | Pin validator, wiring | Types: power, gnd, i2c_sda, i2c_scl, gpio_in, gpio_out, analog, i2s_* |
| `logic_voltage`, `supply_voltage`, `max_current_ma` | Validator | 5 V parts on 3.3 V logic; current budget |
| `i2c_addresses` | Validator | Two parts on one address |
| `board_mm`, `mount_holes`, `dims_source` | Layout, enclosure | `measured` (calipers), `datasheet` or `listing`; `provisional: true` until measured |
| `wokwi_type` (boards: `wokwi_board`) | Simulation | Wokwi part name; empty if Wokwi doesn't have the part |
| `features` (usb, lens, display window, button cap) with offsets | Cutouts | Relative to the board's corner |
| `pio_lib_deps`, `snippet` | Firmware agent | Library names plus a known-good example using `PIN_*` macros |
| `mpn`, `vendor_url`, `manual_price_usd` | Pricing | Generic modules have no MPN: manual price and link |
| `owned_alternatives` | Inventory memory | Parts that can stand in |
| `source` | Reviewers | Datasheet or vendor URL for every pin, voltage and address |
| Boards only: `reserved_pins`, `input_only_pins`, `strapping_pins`, `adc2_pins`, `pio_board` | Validator, firmware | Board facts live here, never in code |

```yaml
# backend/parts/library/ssd1306_096_i2c.yaml
id: ssd1306_096_i2c
name: 0.96" OLED, 128x64, I2C (SSD1306)
category: display
logic_voltage: 3.3
supply_voltage: [3.3, 5.0]
i2c_addresses: ["0x3C", "0x3D"]   # set by a jumper on most modules
pins:
  - {name: GND, type: gnd}
  - {name: VCC, type: power}
  - {name: SCL, type: i2c_scl}
  - {name: SDA, type: i2c_sda}
board_mm: {l: TODO, w: TODO, h: TODO}
provisional: true
dims_source: datasheet
wokwi_type: TODO           # Wokwi's part name, if it has one
mount_holes: [TODO]
features:
  - {kind: display_window, face: top, offset_mm: [TODO, TODO], size_mm: [TODO, TODO]}
pio_lib_deps: ["adafruit/Adafruit SSD1306", "adafruit/Adafruit GFX Library"]
snippet: snippets/ssd1306_hello.cpp
mpn: null
vendor_url: TODO
manual_price_usd: TODO
source: TODO
```

Starter list:

| Category | Parts |
| --- | --- |
| Microcontrollers | ESP32-DevKitC, Seeed XIAO ESP32S3 Sense (camera) |
| Sensors | BME280, capacitive soil moisture, HC-SR04 ultrasonic, PIR motion, DS18B20, INMP441 I2S microphone |
| Displays and light | SSD1306 OLED, WS2812B LED ring or strip |
| Input | Tactile button, arcade button, KY-040 rotary encoder |
| Output | Passive buzzer, vibration motor module, SG90 servo, MAX98357A I2S amplifier + speaker, relay module |
| Power | USB-C power only |

Pricing: `scripts/prefetch_prices.py` queries Nexar by MPN before the event and writes
`backend/parts/prices.json` with a timestamp. Live lookups refresh the cache and fall back to it on any
error (the free tier allows about 1,000 queries a month). Don't scrape Octopart's website: its data pages
are blocked by bot protection.

## Verification

Nothing the model produces reaches the UI until plain code has checked it. Failures go back to the
sub-agent with up to 3 retries; if it still fails, the UI shows a red check rather than hiding it.

| Check | Tool | Catches |
| --- | --- | --- |
| Spec shape | `ProjectSpec.model_validate` | Missing fields, unknown part IDs, bad enum values |
| Pin conflicts | `validate_spec` | Two signals on one GPIO, unconnected part pins |
| Board pin rules | Board YAML | On the classic ESP32: GPIO6–11 (wired to flash), outputs on input-only GPIO34–39, strapping pins, analog reads on ADC2 pins while Wi-Fi is on |
| Electrical | `validate_spec` | 5 V logic on a 3.3 V pin, duplicate I2C addresses, current over budget |
| Firmware compiles | `pio run` | Syntax errors, missing libraries, wrong board |
| Firmware matches spec | Generated `pins.h`; lint forbids numeric pin literals | Code that disagrees with the wiring |
| Enclosure builds | build123d exports STEP and STL | Broken CAD code, failed booleans |
| Enclosure printable | trimesh watertight; fits the printer's build volume | Open meshes, oversize parts |
| Fit | Placements inside the cavity with clearance | Board hits a wall or the lid |
| BOM | Prices present; total vs budget | Missing prices, over budget |
| Cross-domain | `cross_checks` | pins ↔ connections, cutouts ↔ features, BOM ↔ parts, stale artifacts |
| Simulation | Wokwi `diagram.json` + `wokwi-cli`, waits for `P2D_READY` | Firmware that compiles but never boots; required when we have no hardware |

```python
# Core of the pin check (T10 builds the full version in backend/tools/validate_spec.py)
from collections import defaultdict

def validate_pins(spec, lib) -> list[str]:
    errors = []
    board = lib.get(spec.mcu.part_id)
    used = defaultdict(list)
    for c in spec.connections:
        if c.bus == "power":
            continue
        used[c.mcu_pin].append(f"{c.part_ref}.{c.part_pin}")
        if c.mcu_pin in board.reserved_pins:
            errors.append(f"{c.mcu_pin} is reserved on {board.name}; pick another pin")
        if c.mcu_pin in board.input_only_pins and lib.pin_type(c) == "gpio_out":
            errors.append(f"{c.mcu_pin} is input-only but drives {c.part_ref}.{c.part_pin}")
    for pin, users in used.items():
        shared_bus = all(u.split(".")[1] in ("SDA", "SCL") for u in users)  # I2C may share
        if len(users) > 1 and not shared_bus:
            errors.append(f"{pin} is used by {', '.join(users)}")
    for p in spec.parts:
        wired = {c.part_pin for c in spec.connections if c.part_ref == p.ref}
        missing = {pin.name for pin in lib.get(p.part_id).pins} - wired
        if missing:
            errors.append(f"{p.ref} has unconnected pins: {sorted(missing)}")
    return errors
```

## Starter code

**Orchestrator** (check the installed deepagents version first: argument names have changed between
versions). Tools are passed in from a `ToolBox` so tests can use fakes.

```python
# backend/agent/orchestrator.py (sketch)
from deepagents import create_deep_agent

def build_agent(tools, model: str, prompts):
    parts_agent = {
        "name": "parts-and-pins",
        "description": "Chooses parts from the library and assigns pins. Use first.",
        "system_prompt": prompts["parts"],
        "tools": [tools.search_parts, tools.write_spec, tools.validate_spec, tools.request_change],
    }
    firmware_agent = {
        "name": "firmware",
        "description": "Writes Arduino firmware for a validated spec and compiles it.",
        "system_prompt": prompts["firmware"],
        "tools": [tools.write_firmware, tools.request_change],   # wraps write_firmware_project + lint + compile
    }
    enclosure_agent = {
        "name": "enclosure",
        "description": "Builds and checks a printable enclosure for a validated spec.",
        "system_prompt": prompts["enclosure"],
        "tools": [tools.build_enclosure, tools.check_enclosure, tools.request_change],
    }
    return create_deep_agent(
        model=model,                                   # from P2D_MODEL
        tools=[tools.validate_spec, tools.price_bom],
        system_prompt=prompts["orchestrator"],
        subagents=[parts_agent, firmware_agent, enclosure_agent],
    )
```

**Enclosure template** (build123d)

```python
# backend/cad/templates/box_lid.py (starting point for T11)
from build123d import Box, Cylinder, Pos, Align, export_step, export_stl

BASE = (Align.CENTER, Align.CENTER, Align.MIN)

def cutout(face, u, v, w, h, L, W, wall):
    """A box that cuts a w x h opening in one wall; u, v = centre offsets in mm."""
    if face == "front":  return Pos(u, -(W / 2 + wall / 2), wall + v) * Box(w, wall * 3, h)
    if face == "back":   return Pos(u,  (W / 2 + wall / 2), wall + v) * Box(w, wall * 3, h)
    if face == "left":   return Pos(-(L / 2 + wall / 2), u, wall + v) * Box(wall * 3, w, h)
    if face == "right":  return Pos( (L / 2 + wall / 2), u, wall + v) * Box(wall * 3, w, h)
    raise ValueError(face)  # top-face openings are cut in the lid

def box_lid(L, W, H, wall=2.0, holes=(), cutouts=(), out="runs/tmp/enclosure"):
    shell = Box(L + 2 * wall, W + 2 * wall, H + wall, align=BASE)
    shell -= Pos(0, 0, wall) * Box(L, W, H + 1, align=BASE)
    for x, y in holes:                               # standoffs for M2.5 screws
        shell += Pos(x, y, wall) * Cylinder(2.5, 5, align=BASE)
        shell -= Pos(x, y, wall) * Cylinder(1.1, 5, align=BASE)
    for c in cutouts:
        shell -= cutout(c["face"], c["u"], c["v"], c["w"], c["h"], L, W, wall)
    lid = Box(L + 2 * wall, W + 2 * wall, wall, align=BASE)   # TODO: lip + screw holes
    export_step(shell, f"{out}_base.step"); export_stl(shell, f"{out}_base.stl")
    export_step(lid, f"{out}_lid.step");    export_stl(lid, f"{out}_lid.stl")
    return shell, lid
```

**Firmware helpers**

```python
# backend/tools/firmware.py (starting point for T12)
import subprocess

def pins_header(spec) -> str:
    lines = ["#pragma once", "// generated from spec.json: do not edit"]
    for c in sorted(spec.connections, key=lambda c: (c.part_ref, c.part_pin)):
        if c.mcu_pin.startswith("GPIO"):
            name = f"PIN_{c.part_ref}_{c.part_pin}".upper()
            lines.append(f"#define {name} {c.mcu_pin.removeprefix('GPIO')}")
    return "\n".join(lines) + "\n"

def run_pio(project_dir: str) -> tuple[bool, str]:
    r = subprocess.run(["pio", "run", "-d", project_dir],
                       capture_output=True, text=True, timeout=600)
    log = (r.stdout + r.stderr).splitlines()[-40:]
    return r.returncode == 0, "\n".join(log)
```

```ini
; firmware_templates/platformio.ini.j2
[env:{{ env_name }}]
platform = espressif32
board = {{ pio_board }}          ; e.g. esp32dev, seeed_xiao_esp32s3
framework = arduino
monitor_speed = 115200
lib_deps = {{ lib_deps | join("\n    ") }}
```

**Video input**

```bash
ffmpeg -i input.mp4 -vf "fps=1/2,scale=768:-1" -frames:v 8 frames/%02d.jpg
whisper input.mp4 --model base --output_format txt   # or a speech-to-text API
```

Keyframes and transcript go to the orchestrator as images plus text, the same path a sketch takes.

## Risks the build should design for

| Risk | Fallback built into the code |
| --- | --- |
| Model output fails validation repeatedly | Retry limit enforced in code; one worked example in the prompt; template defaults for the failing field |
| Agent too slow for a live demo | Firmware and enclosure in parallel; faster model for parts; `P2D_RUNNER=replay:<dir>` serves a cached run |
| PlatformIO toolchain download fails at the venue | Toolchains pre-installed during setup |
| Nexar rate limit or outage | `prices.json` cache; manual prices |
| Venue Wi-Fi drops | Cached runs served locally |

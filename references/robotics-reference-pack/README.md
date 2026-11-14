---
pack: robotics-reference-pack
version: 1.0
built: 2026-11-14
audience: AI agents (and humans) planning CAD, wiring and software for robots similar to these five builds
---

# Robotics reference pack

Five built robots, documented as structured reference designs. Each project file gives the architecture, bill of materials, power design, suggested pin map, CAD notes, software structure, lessons learned, open items and a verification checklist. A shared component library holds datasheet-derived specs and links for every part.

## Projects at a glance

| File | Robot | Compute pattern | Main / secondary compute | Drive / actuation | Key sensing | Power |
|---|---|---|---|---|---|---|
| `projects/01_three_pod_coaxial_swerve.md` | 3-pod coaxial swerve | SBC + real-time MCU | Raspberry Pi 4B / Pico RP2040 | 6x Pololu 37D, 3x MDD10A | ISM330DHCX IMU, 6x GP2Y0E03 via TCA9548A, 3x REV Through Bore V2, 3x Hall encoders | 3S LiPo 3000 mAh, 3x LM2596 (5 V Pi, 5 V servo, 3.3 V) |
| `projects/02_ftc_decode_robot.md` | FTC robot (2025-26 DECODE) | Vendor ecosystem | REV Control Hub / Expansion Hub / goBILDA Pinpoint | Mecanum, 7x Yellow Jacket, 4 servos; turret, sorter, string-driven actuator | 4x color sensors, 2x 4-bar dead wheels, 7 motor encoders | 12 V NiMH FTC battery |
| `projects/03_4dof_vr_teleop_arm.md` | 4-DOF arm, VR teleop | MCU + edge device | ESP32 / Android app + Meta Quest 3 | NEMA 17 cycloidal shoulder, 4x 25 kg servos (differential wrist, claw, camera) | AS5047P | not recorded (recommendations given) |
| `projects/04_stepper_differential_drive.md` | Open-loop diff drive | Single SBC | Raspberry Pi 4B | 2x NEMA 17, 2x TMC2209, idler | none | 12 V NiMH 10S **or** 8x AA (conflict flagged), 5 V buck |
| `projects/05_tripod_narrow_competition_vehicle.md` | Tripod narrow vehicle | Single 5 V MCU | Arduino UNO R3 | Pololu 37D + BTS7960, servo 4-bar steering | AS5047P sprung odometry wheel, motor encoder | 8x AA direct |

The arm is designed to mount on the swerve: the swerve's dedicated 5 V servo is the arm's base-yaw joint.

## How an agent should use this pack
1. Read `00_design_patterns.md` (compute patterns, power rules, logic levels, I2C addressing, CAD conventions, workflow).
2. Open the project closest to the new robot.
3. Fill `templates/project_spec_template.yaml` for the new design.
4. Pull parts and specs from `components/components.json` (machine-readable) or `components/component_library.md` (readable).
5. Follow the chosen project's verification checklist.

Single-context agents can load `ALL_IN_ONE.md`, which concatenates everything.

## What is fact vs. suggestion
- **Recorded by the builder**: compute choices, parts, roles, design rationale and lessons (e.g., two 5 V bucks so the Pi never browns out; two flywheel motors to limit speed fluctuations; motor sync in code for straight-line driving).
- **From datasheets** (checked 2026-11-14): numbers in `components.json`, with links.
- **Suggested by the pack**: pin maps, port allocations, protocols, software layouts and power recommendations. These are labeled "suggested" or "recommended" and are consistent with the datasheets, but are not the as-built wiring.
- **Flagged**: each project has an "Open items" list of facts not recorded (gear ratios, dimensions, servo models, link transports), and integration risks are called out where found (Pololu encoder voltage into a 3.3 V Pico, LM2596 headroom for the Pi 4B, UNO regulator powering a servo, power-source conflict on the diff drive).

## Datasheets
Datasheet PDFs are not bundled: the build environment could not download them. `datasheets/datasheet_index.md` lists every link, and

```
python3 datasheets/fetch_datasheets.py
```

downloads them into `datasheets/<component_id>/` on any machine with internet access (standard-library Python only).

## Layout
```
README.md                     this file
00_design_patterns.md         cross-project rules and formulas
projects/                     one reference design per robot
components/components.json    machine-readable part library (source of truth)
components/component_library.md  generated readable version
datasheets/datasheet_index.md every datasheet link
datasheets/fetch_datasheets.py   downloader
templates/project_spec_template.yaml
tools/build_docs.py           regenerates generated files
ALL_IN_ONE.md                 single-file bundle
```

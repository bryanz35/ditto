---
doc: design_patterns
purpose: Cross-project rules, formulas and checklists distilled from the five reference builds
read_before: any project file when planning a new robot
---

# Cross-project design patterns

These patterns recur across the five builds in `projects/`. Use them as defaults when planning a similar robot, and deviate only with a stated reason.

## 1. Compute architecture patterns

| Pattern | Used in | When to choose it | Split of responsibilities |
|---|---|---|---|
| **SBC + real-time MCU** | 3-pod swerve (Pi 4B + Pico) | Wireless/SSH, heavy compute or vision **and** tight control loops/many encoders | SBC: networking, UI, kinematics, odometry fusion, logging, high-level planning. MCU: PID loops (≥500 Hz), encoder decoding, sensor polling, local safety stops, watchdog. |
| **Single SBC, open loop** | Differential drive (Pi 4B) | Steppers with no feedback, low speed, compute-light | SBC does everything; motion timing must be offloaded (DMA waveforms or driver-side velocity mode) because Linux jitters. |
| **Single MCU + wireless edge device** | 4-DOF arm (ESP32 + Android + Quest 3) | Human-in-the-loop teleoperation; heavy math on a phone/headset | Edge device: tracking, IK, video. MCU: actuator timing, encoder reads, joint limits, link-loss failsafe. |
| **Single 5 V MCU** | Tripod vehicle (Arduino UNO) | Simple, few actuators, battery voltage within the board's Vin range | MCU does sensing, control and actuation; keep loops simple and fixed-rate. |
| **Vendor ecosystem controller** | FTC robot (REV Control Hub + Expansion Hub + Pinpoint) | Competition rules require it, or speed of development beats flexibility | Hub runs the SDK; coprocessors (Pinpoint) offload high-rate sensing. |

Rule of thumb: if a loop needs < 2 ms jitter, it does not belong on Linux.

## 2. Power architecture patterns

1. **Separate rails per noisy load.** The swerve uses one 5 V buck for the Pi and a second 5 V buck for the servo so servo current spikes never brown out the Pi. Apply the same rule to any SBC + servo/motor system.
2. **Motors run straight from the battery** through the driver; logic gets regulated rails.
3. **Budget at stall, not at running current.** Sum stall currents of everything that can stall at once; size the fuse, battery C-rating, wire gauge and drivers to that.
4. **Bulk capacitance** (470-2200 µF, rated ≥1.5x battery voltage) at each motor driver input and at servo buses.
5. **Common ground** between every rail and every logic device; star the grounds at the battery/distribution point for high-current returns.
6. **Fuse + switch** directly after the battery.
7. **Low-voltage cutoff** for LiPo packs: monitor pack voltage with an ADC divider and stop motors at ~3.3 V/cell under load.

### Power budget worksheet (copy into every new project)

| Rail | Loads | Typical A | Peak/stall A | Source | Source rating | Margin |
|---|---|---|---|---|---|---|
| VBAT | motor drivers | | | battery | C x Ah | ≥1.5x peak |
| 5 V (SBC) | SBC + USB | | | buck #1 | | ≥1.3x |
| 5-6 V (servo) | servos | | | buck/BEC #2 | | ≥ (stall x n x 0.5) |
| 3.3 V | sensors | | | buck #3 or MCU LDO | | |

## 3. Logic-level compatibility table

| Device | Logic | Notes |
|---|---|---|
| Raspberry Pi 4B GPIO | 3.3 V | not 5 V tolerant |
| Raspberry Pi Pico / RP2040 | 3.3 V | not 5 V tolerant |
| ESP32 | 3.3 V | not 5 V tolerant; GPIO34-39 input only |
| Arduino UNO R3 | 5 V | 3.3 V outputs usually read as HIGH, but check thresholds |
| REV Hub I2C | 3.3 V | 5 V sensors need a level shifter |
| Pololu 37D encoder | = encoder Vcc (3.5-20 V) | **trap for 3.3 V MCUs** |
| goBILDA Yellow Jacket encoder | 3.3-5 V | follow supply |
| AS5047P | = VDD (3.3 V or 5 V mode) | |
| GP2Y0E03 I2C | = VIN(IO) | |
| MDD10A inputs | 3.3 V or 5 V | |
| TMC2209 | VIO 3.3-5 V | |

## 4. I2C address planning

1. List every device and its address before wiring.
2. Duplicates: (a) put them on separate buses (REV hubs have 4 buses each), (b) use a TCA9548A mux (swerve: 6x GP2Y0E03 at 0x40), (c) use an address-select pin, (d) last resort, permanent address programming (GP2Y0E03 E-Fuse).
3. Keep bus length short (< 30 cm at 400 kHz without buffers), twist SDA/SCL with GND, and confirm pull-ups exist exactly once per bus segment (2.2-4.7 kΩ to the bus voltage).

| Address (7-bit) | Device |
|---|---|
| 0x28/0x29 | BNO055 (REV hub internal IMU) |
| 0x31 | goBILDA Pinpoint |
| 0x40 | GP2Y0E03 (all units) |
| 0x52 | REV Color Sensor V3, REV 2m Distance Sensor |
| 0x6A/0x6B | ISM330DHCX |
| 0x70-0x77 | TCA9548A |

## 5. Sensing patterns

- **Absolute + incremental pairing.** Swerve pods use an absolute encoder (REV Through Bore) on the steering axis so the pod angle is known at power-up, plus a Hall quadrature encoder on the drive motor for velocity. Use absolute sensing on anything that must home without moving.
- **Dead-wheel odometry.** Un-driven, spring-loaded tracking wheels (FTC 4-bar pods; tripod's custom sprung wheel with AS5047P) avoid wheel-slip errors of driven wheels. Keep them spring-loaded, on the ground plane, and mounted rigidly in the direction of travel.
- **IMU fusion.** Heading from integrated gyro Z (bias-calibrated at rest) + translation from wheel or dead-wheel encoders is the default 2D localization. The Pinpoint does this in hardware at 1500 Hz.
- **Reactive safety sensors.** Short-range distance sensors (swerve's 6x GP2Y0E03) should be evaluated on the MCU in the control loop so a stop does not depend on Wi-Fi or Linux.

## 6. Actuator and driver selection

| Need | Default choice from these builds | Why |
|---|---|---|
| Brushed DC with encoder, ≤ 12 V, ≤ 5.5 A stall | Pololu 37D + Cytron MDD10A (dual 10 A) | Driver headroom ~2x stall-free continuous, 3.3 V logic |
| Single high-current brushed motor on 5 V MCU | BTS7960 module | 43 A limit, cheap; IC obsolete, consider BTN8982-based modules |
| Open-loop precise position/velocity | NEMA 17 + TMC2209 | quiet, 256 µsteps, UART config, VACTUAL velocity mode |
| High-torque joint without backlash | NEMA 17 + printed cycloidal reducer + AS5047P on output | low backlash, back-drivable-ish, open loop with encoder check |
| Light positional joints | 25 kg-cm digital servos on a dedicated 6 V rail | simple, self-contained |
| FTC | goBILDA Yellow Jacket + REV hubs | legal, documented, plug-and-play |

## 7. Software patterns

- **Fixed-rate loops**: MCU PID 500-1000 Hz; kinematics/odometry 100-200 Hz; telemetry 10-50 Hz.
- **Command link SBC→MCU**: framed binary packets (start byte, length, msg id, payload, CRC-16) over UART/USB-CDC; MCU watchdog stops motors if no valid packet for 100-250 ms.
- **State machines** for mechanisms (sorter, intake, shooter spin-up) rather than nested if/else.
- **Units**: SI internally (m, rad, s); convert at the edges.
- **Calibration constants** in one config file (wheel diameters, offsets, encoder zero offsets, PID gains), never hard-coded in logic.
- **Bring-up order**: power rails with no loads → logic boards → each sensor alone → each motor alone at low duty → closed loops one at a time → integration.

## 8. CAD conventions for agents

- Units mm; model every purchased part from vendor STEP files when available (Pololu, goBILDA, REV and Raspberry Pi publish them).
- 3D-printing clearances (FDM, 0.4 mm nozzle): 0.2-0.3 mm per side sliding fit, 0.1 mm press fit, holes undersized ~0.1-0.2 mm for heat-set inserts per insert vendor.
- Keep the center of gravity low and inside the support polygon (critical for 3-wheel layouts: tripod, diff-drive, 3-pod swerve).
- Reserve cable channels and connector clearance in the first CAD pass; route high-current wires away from I2C/encoder wires.
- Give every encoder a concentric, rigid mount; magnetic encoders need a magnet pocket on the shaft axis and a defined air gap.

## 9. Agent workflow for a new, similar project

1. Fill `templates/project_spec_template.yaml`.
2. Pick the closest reference build in `projects/` and the compute pattern from §1.
3. Select parts from `components/components.json`; add new parts in the same schema.
4. Do the power budget (§2) and logic-level check (§3) before drawing wiring.
5. Write the pin map table and wiring list (connector, wire gauge, from → to).
6. CAD: drivetrain/mechanism skeleton → motor and sensor placement → electronics tray → cable routing.
7. Software: skeleton modules from the reference build's software section; implement bring-up tests first.
8. Run the verification checklist at the end of the chosen project file.

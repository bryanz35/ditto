# Component library

Generated from `components.json` by `tools/build_docs.py`. Edit the JSON, then rebuild.

## Usage matrix

| Component | 3-pod swerve | FTC DECODE robot | 4-DOF VR arm | Stepper diff drive | Tripod vehicle |
|---|---|---|---|---|---|
| Raspberry Pi 4 Model B | x |  |  | x |  |
| Raspberry Pi Pico (RP2040) | x |  |  |  |  |
| ESP32 (e.g., ESP32-WROOM-32E dev board) |  |  | x |  |  |
| Arduino UNO R3 (A000066) |  |  |  |  | x |
| REV Control Hub (REV-31-1595) |  | x |  |  |  |
| REV Expansion Hub (REV-31-1153) |  | x |  |  |  |
| goBILDA Pinpoint Odometry Computer (3110-0002-0001; V2 is 3110-0002-0002) |  | x |  |  |  |
| goBILDA 4-Bar Odometry Pod, 32 mm wheel (3110-0001-0002) |  | x |  |  |  |
| goBILDA 5203 Series Yellow Jacket planetary gear motor |  | x |  |  |  |
| REV Color Sensor V3 (REV-31-1557) - assumed model |  | x |  |  |  |
| ST ISM330DHCX 6-axis IMU | x |  |  |  |  |
| Sharp GP2Y0E03 IR distance sensor | x |  |  |  |  |
| TI TCA9548A 8-channel I2C switch/mux | x |  |  |  |  |
| REV Through Bore Encoder V2 | x |  |  |  |  |
| ams OSRAM AS5047P 14-bit magnetic rotary encoder |  |  | x |  | x |
| Pololu 37D metal gearmotor, 12 V, 64 CPR encoder (helical pinion) | x |  |  |  | x |
| Cytron MDD10A dual-channel 10 A motor driver | x |  |  |  |  |
| BTS7960 43 A H-bridge module (IBT-2 style, 2x Infineon BTS7960B) |  |  |  |  | x |
| Trinamic/ADI TMC2209 stepper driver (StepStick-style module) |  |  |  | x |  |
| NEMA 17 bipolar stepper (17HS4401-class reference) |  |  | x | x |  |
| 25 kg-cm digital servo (DS3225-class reference) |  |  | x |  |  |
| LM2596 adjustable buck converter module | x |  |  |  |  |
| 3S LiPo 3000 mAh | x |  |  |  |  |
| FTC-legal 12 V NiMH robot battery (e.g., REV-31-1302) |  | x |  |  |  |

## Raspberry Pi 4 Model B

- **id:** `rpi4b`  
- **category:** compute/SBC  
- **manufacturer:** Raspberry Pi Ltd  
- **used in:** 3-pod swerve, Stepper diff drive

| Spec | Value |
|---|---|
| soc | BCM2711 quad Cortex-A72 64-bit @1.5 GHz |
| power input | 5 V via USB-C or GPIO header, 3 A minimum (2.5 A ok if USB peripherals < 500 mA) |
| gpio logic | 3.3 V, NOT 5 V tolerant |
| gpio count | 28 BCM GPIO on 40-pin header |
| wireless | 2.4/5 GHz 802.11ac, Bluetooth 5.0 |
| board size mm | 85 x 56 |
| mounting holes | 4x M2.5 on 58 x 49 mm rectangle |
| operating temp C | 0-50 |

**Interfaces:** UART (GPIO14 TX / GPIO15 RX); I2C1 (GPIO2 SDA / GPIO3 SCL); SPI0; HW PWM (GPIO12/13/18/19); USB; Wi-Fi/SSH

**Gotchas:**
- Powering via GPIO 5 V pins bypasses the USB-C input protection; use a regulated, low-ripple 5.1 V supply that can hold 3 A.
- Linux is not real-time: step-pulse generation or tight PID loops on the Pi will jitter. Offload to an MCU or use DMA-timed waveforms (pigpio) or driver-side motion (TMC2209 VACTUAL).
- Under-voltage (lightning bolt / throttled flag) causes CPU throttling and SD-card corruption; check `vcgencmd get_throttled` during bring-up.

**Datasheets:**
- [Product brief](https://pip-assets.raspberrypi.com/categories/545-raspberry-pi-4-model-b/documents/RP-008344-DS-2-raspberry-pi-4-product-brief.pdf)
- [Datasheet (GPIO electrical, alt functions)](https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-datasheet.pdf) *(link pattern not verified)*

## Raspberry Pi Pico (RP2040)

- **id:** `pico_rp2040`  
- **category:** compute/MCU  
- **manufacturer:** Raspberry Pi Ltd  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| cpu | Dual Cortex-M0+ up to 133 MHz |
| memory | 264 kB SRAM, 2 MB QSPI flash |
| gpio | 26 user GPIO (GP0-GP22, GP26-GP28), 3 of which are ADC |
| logic | 3.3 V, NOT 5 V tolerant |
| pwm | 8 slices x 2 channels |
| pio | 2 PIO blocks x 4 state machines (use for quadrature decode and pulse-width capture) |
| power input | VSYS 1.8-5.5 V (on-board buck-boost to 3.3 V); VBUS 5 V from USB |
| board size mm | 51 x 21 |
| mounting holes | 4x 2.1 mm on 47.0 x 11.4 mm |

**Interfaces:** 2x UART; 2x I2C; 2x SPI; USB 1.1 device (CDC serial); PIO; ADC

**Gotchas:**
- Any sensor output that swings to 5 V (e.g., Pololu 37D Hall encoder powered at 5 V) must be level-shifted or divided before reaching a GPIO.
- Use PIO quadrature decoding (pico-examples/pio/quadrature_encoder) instead of GPIO interrupts for >1 encoder at high count rates.

**Datasheets:**
- [Pico datasheet](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf)
- [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)
- [Hardware design with RP2040](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)

## ESP32 (e.g., ESP32-WROOM-32E dev board)

- **id:** `esp32`  
- **category:** compute/MCU  
- **manufacturer:** Espressif  
- **used in:** 4-DOF VR arm

| Spec | Value |
|---|---|
| cpu | Xtensa dual-core LX6 up to 240 MHz |
| wireless | Wi-Fi 802.11 b/g/n + Bluetooth (Classic + BLE) |
| logic | 3.3 V, NOT 5 V tolerant |
| pwm | LED PWM (LEDC) up to 16 channels + MCPWM (motor PWM) peripheral |
| input only pins | GPIO34-39 (no pull-ups, input only) |
| strapping pins | GPIO0, 2, 5, 12 (MTDI), 15 (MTDO) - avoid for outputs that are pulled at boot |

**Interfaces:** Wi-Fi (UDP/WebSocket); BLE; SPI (VSPI: 18 SCK, 19 MISO, 23 MOSI, 5 CS by convention); I2C; UART; LEDC/MCPWM; RMT

**Gotchas:**
- GPIO12 high at boot selects 1.8 V flash on many modules -> boot failure; never pull it up.
- ADC2 pins are unusable while Wi-Fi is active.
- Wi-Fi TX bursts draw ~250-350 mA peaks; give the 3.3 V rail bulk capacitance and do not share it with servos.

**Datasheets:**
- [ESP32 series datasheet](https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf)
- [ESP32-WROOM-32E/32UE module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)

## Arduino UNO R3 (A000066)

- **id:** `arduino_uno_r3`  
- **category:** compute/MCU  
- **manufacturer:** Arduino  
- **used in:** Tripod vehicle

| Spec | Value |
|---|---|
| mcu | ATmega328P @16 MHz, 2 kB SRAM, 32 kB flash, 1 kB EEPROM |
| logic | 5 V |
| vin recommended | 7-12 V (limits 6-20 V); above 12 V the linear regulator may overheat |
| io | 14 digital (6 PWM: D3, D5, D6, D9, D10, D11), 6 analog |
| external interrupts | Only D2 (INT0) and D3 (INT1); others need pin-change interrupts |
| io current | 20 mA per pin recommended |
| 3v3 pin | 50 mA max |
| board size mm | 68.6 x 53.4 |

**Interfaces:** SPI (D10 SS, D11 MOSI, D12 MISO, D13 SCK); I2C (A4 SDA, A5 SCL); UART (D0/D1, shared with USB)

**Gotchas:**
- Servo library uses Timer1 and disables analogWrite() on D9 and D10.
- The on-board 5 V linear regulator dissipates (Vin - 5) x I; at 12 V in, a few hundred mA of servo current will overheat it. Power servos from a separate 5-6 V buck.
- Only two hardware interrupt pins: plan encoder wiring before assigning pins.

**Datasheets:**
- [UNO R3 datasheet](https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf) *(link pattern not verified)*
- [UNO R3 schematic](https://content.arduino.cc/assets/UNO-TH_Rev3e_sch.pdf)
- [Board outline DXF (CAD)](http://arduino.cc/documents/ArduinoUno.dxf)

## REV Control Hub (REV-31-1595)

- **id:** `rev_control_hub`  
- **category:** compute/FTC controller  
- **manufacturer:** REV Robotics  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| motor ports | 4 (JST VH 2-pin) with 4 quadrature encoder ports (JST PH 4-pin) |
| servo ports | 6 (0.1 in header), 500-2500 us extended range; ports share power in pairs (0-1, 2-3, 4-5) |
| servo plus 5v budget | 5 A total shared across all servo ports and +5 V aux ports |
| digital io | 8 |
| analog in | 4 |
| i2c | 4 independent buses, 3.3 V, 100/400 kHz, 500 mA total supply |
| battery | 12 V NiMH FTC battery via XT30; second XT30 port daisy-chains an Expansion Hub |
| hw encoder ports | Encoder ports 0 and 3 are hardware-decoded (best for high-speed motors such as flywheels) |

**Interfaces:** RS485 to Expansion Hub; USB-A (webcams); Wi-Fi to Driver Hub; HDMI

**Gotchas:**
- Internal IMU lives on I2C bus 0; put add-on I2C devices on buses 1-3.
- High-current servos: use ports 0, 2, 4 (one per power pair) or add a Servo Power Module.
- Absolute (pulse) outputs of encoders like the REV Through Bore are not supported on hub encoder ports - quadrature only.

**Datasheets:**
- [Control system overview / Control Hub specs](https://docs.revrobotics.com/duo-control/control-system-overview)
- [FTC Control Hub ports](https://ftc-docs.firstinspires.org/control_hard_compon/rc_components/hub/ports/ch-ports.html)

## REV Expansion Hub (REV-31-1153)

- **id:** `rev_expansion_hub`  
- **category:** compute/FTC I/O expander  
- **manufacturer:** REV Robotics  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| motor ports | 4 + 4 encoder ports |
| servo ports | 6, 500-2500 us, power shared in pairs |
| aux 5v | 2 ports, 5 V / 2 A (shares 5 A budget with servos) |
| i2c | 4 independent buses, 3.3 V |
| digital io | 8 |
| analog in | 4 |
| size mm | 143 x 103 x 29.5, mounting holes on 16 mm spacing |

**Interfaces:** RS485 to Control Hub

**Gotchas:**
- Address the hub as 'Expansion Hub 2' in the robot configuration; bulk-read both hubs each loop.

**Datasheets:**
- [Expansion Hub getting started / specs](https://www.revrobotics.com/content/docs/REV-31-1153-GS.pdf)

## goBILDA Pinpoint Odometry Computer (3110-0002-0001; V2 is 3110-0002-0002)

- **id:** `gobilda_pinpoint`  
- **category:** sensor/odometry coprocessor  
- **manufacturer:** goBILDA  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| function | Fuses 2 dead-wheel quadrature encoders with an internal IMU |
| update rate | 1500 Hz algorithm loop |
| supply | 3.3-5 V, 80 mA |
| i2c address | 0x31, tested to 400 kHz |
| max encoder rate | 256,000 events/s |
| connector | 4-pos JST PH |
| max rotation | 2000 RPM (IMU) |

**Interfaces:** I2C to Control Hub (not bus 0); 2x quadrature encoder inputs

**Gotchas:**
- Robot must be stationary during resetPosAndIMU()/recalibrateIMU() (~0.25 s).
- Set encoder resolution (goBILDA_4_BAR_POD) and X/Y pod offsets in mm relative to the tracking point; sign convention: left of center is positive for X pod offset.

**Datasheets:**
- [User guide (specs + I2C register map)](https://servocity.com/content/user_manuals/3110-0002-0001%20User%20Guide.pdf)
- [Product page](https://gobilda.com/pinpoint-odometry-computer-imu-sensor-fusion-for-2-wheel-odometry)

## goBILDA 4-Bar Odometry Pod, 32 mm wheel (3110-0001-0002)

- **id:** `gobilda_4bar_pod`  
- **category:** sensor/dead wheel  
- **manufacturer:** goBILDA  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| wheel | 32 mm omni, 50A durometer rollers |
| encoder | 2000 counts per revolution |
| resolution | 2000 / (pi x 32) = 19.894 ticks/mm |
| mounting | fits inside 43 x 43 mm profiles (e.g., goBILDA 1120 U-channel), M4 hardware |
| weight g | 84 |
| connector | 4-pos JST PH |

**Interfaces:** Quadrature to Pinpoint

**Gotchas:**
- Spring preload is factory-tuned; do not add extra downforce.

**Datasheets:**
- [Product page](https://gobilda.com/4-bar-odometry-pod-32mm-wheel)

## goBILDA 5203 Series Yellow Jacket planetary gear motor

- **id:** `gobilda_yellow_jacket_5203`  
- **category:** actuator/brushed DC gearmotor  
- **manufacturer:** goBILDA  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| motor | RS-555 brushed, 12 V nominal |
| no load current | 0.25 A @12 V |
| stall current | 9.2 A @12 V (all ratios) |
| encoder | Hall quadrature, 3.3-5 V, 28 counts per motor revolution x gear ratio at output |
| example ratios | 1:1 6000 RPM (28 CPR); 3.7:1 1620 RPM (103.8 CPR); 5.2:1 1150 RPM; 13.7:1 435 RPM (383.6 CPR); 19.2:1 312 RPM; 26.9:1 223 RPM |
| shaft | 8 mm REX, 24 mm length |
| mounting | 4x M4 x 10 mm deep on 16 mm square goBILDA pattern |
| connectors | 3.5 mm bullet (motor), 4-pos JST XH (encoder) |

**Interfaces:** Hub motor port (JST VH adapter); Hub encoder port

**Gotchas:**
- Flywheels: choose 1:1 or 3.7:1 and put their encoders on hardware-decoded ports 0/3.

**Datasheets:**
- [Example product page with full specs (99.5:1)](https://www.gobilda.com/5203-series-yellow-jacket-planetary-gear-motor-99-5-1-ratio-24mm-length-8mm-rex-shaft-60-rpm-3-3-5v-encoder/)
- [Example product page (3.7:1)](https://gobilda.com/5203-series-yellow-jacket-planetary-gear-motor-3-7-1-ratio-1620-rpm-3-3-5v-encoder)

## REV Color Sensor V3 (REV-31-1557) - assumed model

- **id:** `rev_color_sensor_v3`  
- **category:** sensor/color + proximity  
- **manufacturer:** REV Robotics (Broadcom APDS-9151 inside)  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| i2c address | 0x52 (fixed) |
| supply | 3.3 V max |
| channels | R, G, B, IR/alpha + proximity |
| proximity range | 1-10 cm |
| i2c speed | 100 or 400 kHz |
| led | built-in white LED, switchable |

**Interfaces:** I2C (JST PH 4-pin)

**Gotchas:**
- Fixed address: one sensor per I2C bus (or add an I2C mux). Shares 0x52 with the REV 2m Distance Sensor.
- Color values differ between V2 and V3; recalibrate thresholds per sensor under match lighting.

**Datasheets:**
- [REV Color Sensor V3 datasheet](https://www.revrobotics.com/content/docs/REV-31-1557-DS.pdf)
- [APDS-9151 datasheet](https://docs.broadcom.com/doc/APDS-9151-DS)

## ST ISM330DHCX 6-axis IMU

- **id:** `ism330dhcx`  
- **category:** sensor/IMU  
- **manufacturer:** STMicroelectronics  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| accel fs | +/-2/4/8/16 g |
| gyro fs | +/-125/250/500/1000/2000/4000 dps |
| supply | 1.71-3.6 V |
| interfaces | I2C / SPI (3- or 4-wire) |
| i2c address | 0x6A (SDO/SA0 low) or 0x6B (high) |
| extras | FIFO, machine-learning core, finite state machine, sensor hub |
| temp range C | -40 to +105 |
| package | LGA-14L 2.5 x 3.0 x 0.83 mm (use a breakout, e.g., Adafruit/SparkFun) |

**Interfaces:** I2C; SPI; INT1/INT2 data-ready

**Gotchas:**
- Mount near the chassis center of rotation, rigidly, away from motor magnets; vibration-isolate if wheels are hard.
- Run gyro bias calibration at startup while stationary; integrate gyro Z for heading and fuse with wheel odometry.

**Datasheets:**
- [Datasheet DS13012](https://www.st.com/resource/en/datasheet/ism330dhcx.pdf)
- [Product page (app notes)](https://www.st.com/en/mems-and-sensors/ism330dhcx.html)

## Sharp GP2Y0E03 IR distance sensor

- **id:** `gp2y0e03`  
- **category:** sensor/distance  
- **manufacturer:** Sharp / Socle Technology  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| range | 4-50 cm |
| supply | 2.7-5.5 V, 36 mA |
| outputs | I2C + analog (Vout(A)) |
| i2c address | 0x80 8-bit = 0x40 7-bit (changeable only by one-time E-Fuse programming) |
| distance register | 0x5E (2 bytes), shift register 0x35 |
| pins | VDD, Vout(A), GND, VIN(IO), GPIO1, SCL, SDA |
| temp range C | -10 to +60 |

**Interfaces:** I2C; Analog

**Gotchas:**
- All units share one address -> use a TCA9548A mux (as built) or E-Fuse reprogramming (permanent, risky).
- VIN(IO) sets the I2C logic level; tie to 3.3 V on a 3.3 V bus.
- GPIO1 controls active/standby; tie high (to VIN(IO)) for always-on.
- IR sensors struggle on black/very shiny surfaces and in sunlight.

**Datasheets:**
- [Datasheet](https://global.sharp/products/device/lineup/data/pdf/datasheet/gp2y0e03_e.pdf)
- [Application note (registers, E-Fuse)](https://www.makerguides.com/wp-content/uploads/2024/10/GP2Y0E03-application-notes.pdf)

## TI TCA9548A 8-channel I2C switch/mux

- **id:** `tca9548a`  
- **category:** interface/I2C mux  
- **manufacturer:** Texas Instruments  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| channels | 8 |
| supply | 1.65-5.5 V |
| i2c address | 0x70-0x77 via A0-A2 |
| bus speed | 100 / 400 kHz |
| control | single 8-bit register, one bit per channel; any combination may be enabled |
| reset | active-low RESET to recover a stuck downstream bus |
| voltage translation | yes - pass gates limited by VCC |

**Interfaces:** I2C

**Gotchas:**
- Downstream channels need their own pull-ups if the breakout lacks them.
- Select exactly one channel when talking to identical-address devices.

**Datasheets:**
- [Datasheet SCPS207](https://www.ti.com/lit/ds/symlink/tca9548a.pdf) *(link pattern not verified)*
- [Product page](https://www.ti.com/product/TCA9548A)

## REV Through Bore Encoder V2

- **id:** `rev_through_bore_v2`  
- **category:** sensor/absolute + incremental encoder  
- **manufacturer:** REV Robotics  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| outputs | ABI quadrature + absolute pulse-width (duty cycle) |
| accuracy | up to +/-0.5 deg (V2) |
| absolute pulse v1 reference | period 1025 us (975.6 Hz), 1 us = 0 deg, 1024 us = 360 deg, 10-bit |
| bore | 1/2 in hex default; inserts for 3/8 in hex, 5 mm hex, 1/4 in round |
| mounting | holes on 0.5 in pitch |
| zero | factory-calibrated to case notch (do not disassemble) |
| connector | JST-PH 6-pin |

**Interfaces:** Quadrature A/B/Index; Absolute PWM (ABS, white wire)

**Gotchas:**
- SKU naming is inconsistent across REV pages (REV-11-1271 vs REV-11-3174); confirm which unit you have and read its spec page for supply/logic levels.
- Power from 3.3 V when connecting directly to a 3.3 V MCU unless the spec page confirms 3.3 V logic at 5 V supply.
- Read the absolute channel with PIO/timer capture; it updates ~1 kHz, adequate for a steering loop.

**Datasheets:**
- [V2 documentation](https://docs.revrobotics.com/rev-crossover-products/sensors/tbe)
- [V1 datasheet (pulse timing reference)](https://www.revrobotics.com/content/docs/REV-11-1271-DS.pdf)
- [V2 product page](https://www.revrobotics.com/rev-11-3174/)

## ams OSRAM AS5047P 14-bit magnetic rotary encoder

- **id:** `as5047p`  
- **category:** sensor/absolute magnetic encoder  
- **manufacturer:** ams OSRAM  
- **used in:** 4-DOF VR arm, Tripod vehicle

| Spec | Value |
|---|---|
| resolution | 14-bit absolute (16384 counts/rev) over SPI |
| incremental | ABI up to 12-bit decimal/binary (programmable; e.g., 4000 steps = 1000 pulses/rev) |
| max speed | 28,000 rpm |
| supply | 5 V mode: VDD 4.5-5.5 V (internal LDO, 1 uF on VDD3V3); 3.3 V mode: VDD and VDD3V3 tied, 3.0-3.6 V |
| supply current | ~15 mA |
| spi | mode 1 (CPOL=0, CPHA=1), 16-bit frames with even parity; angle register 0x3FFF |
| other outputs | UVW commutation, PWM |
| package | TSSOP-14 (use a breakout board) |

**Interfaces:** SPI; ABI quadrature; PWM

**Gotchas:**
- Needs a diametrically magnetized magnet (typ. 6 mm x 2.5 mm) centered on the axis; air gap ~0.5-3 mm per datasheet. Design a magnet pocket in CAD concentric with the shaft.
- Logic levels follow VDD: at 5 V supply outputs are 5 V (fine for UNO, not for ESP32).

**Datasheets:**
- [Datasheet](https://www.infineon.com/row/public/documents/24/49/infineon-as5047p-datasheet-en.pdf)
- [Fact sheet](https://look.ams-osram.com/m/96c6ce98dbc085b4/original/AS5047P_FS000140_1-00.pdf)

## Pololu 37D metal gearmotor, 12 V, 64 CPR encoder (helical pinion)

- **id:** `pololu_37d`  
- **category:** actuator/brushed DC gearmotor  
- **manufacturer:** Pololu  
- **used in:** 3-pod swerve, Tripod vehicle

| Spec | Value |
|---|---|
| rated voltage | 12 V (24 V versions exist) |
| stall current | 5.5 A @12 V (12 V versions) |
| no load current | 0.2 A @12 V |
| example ratios | 10:1 1000 RPM 4.9 kg-cm; 30:1 330 RPM 14 kg-cm; 131:1, 150:1 for steering |
| encoder | 64 counts per motor-shaft revolution (both edges of A and B); output CPR = 64 x gear ratio |
| encoder supply | 3.5-20 V, 10 mA max; A/B outputs swing 0 V to Vcc |
| wires | red/black motor, green GND, blue Vcc, yellow A, white B |
| shaft | 6 mm D, 16 mm long |
| body | 37 mm diameter; do not screw >3 mm into gearbox face holes |

**Interfaces:** Motor driver H-bridge; Quadrature encoder

**Gotchas:**
- Encoder minimum Vcc is 3.5 V and outputs swing to Vcc: on a 3.3 V MCU either power at 5 V and divide/level-shift A/B, or accept out-of-spec 3.3 V operation.
- Do not stall at rated voltage for extended periods (Pololu FAQ: no).
- Budget stall current, not running current, for fuses, wiring and driver selection.

**Datasheets:**
- [37D gearmotor datasheet (performance curves)](https://www.pololu.com/file/0J1706/pololu-37d-metal-gearmotors.pdf)
- [Dimension diagram (CAD)](https://www.pololu.com/file/0J1069/37d-metal-gearmotors-dimension-diagram.pdf)
- [Example product page (30:1)](https://www.pololu.com/product-info-merged/4752)

## Cytron MDD10A dual-channel 10 A motor driver

- **id:** `cytron_mdd10a`  
- **category:** driver/brushed DC  
- **manufacturer:** Cytron  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| channels | 2 |
| motor voltage | 5-30 V (Rev 2.0; Rev 1.0 is 5-25 V) |
| current | 10 A continuous per channel, 30 A peak (<10 s) |
| logic | 3.3 V and 5 V compatible |
| control | PWM + DIR per channel (sign-magnitude) or locked-antiphase |
| pwm freq | up to 20 kHz |
| size mm | 84.5 x 62 |
| test buttons | on-board per channel |

**Interfaces:** PWM1/DIR1/PWM2/DIR2/GND header

**Gotchas:**
- No reverse-polarity protection: key the battery connector.
- Use 18-20 kHz PWM to stay above audible range.

**Datasheets:**
- [Product page (download 'MDD10A User's Manual')](https://www.cytron.io/p-10amp-5v-30v-dc-motor-driver-2-channels) *(link pattern not verified)*

## BTS7960 43 A H-bridge module (IBT-2 style, 2x Infineon BTS7960B)

- **id:** `bts7960`  
- **category:** driver/brushed DC  
- **manufacturer:** Infineon (IC, now obsolete); modules are generic  
- **used in:** Tripod vehicle

| Spec | Value |
|---|---|
| supply | 5.5-27.5 V |
| current limit | 43 A typical (switched-mode current limitation) |
| path resistance | ~16 mOhm typ (7 mOhm high side + 9 mOhm low side) |
| pwm | up to 25 kHz |
| module pins | RPWM, LPWM, R_EN, L_EN, R_IS, L_IS, VCC (5 V logic), GND |
| protection | overtemperature, overcurrent, under/overvoltage |

**Interfaces:** 2x PWM + 2x enable + 2x current sense

**Gotchas:**
- IC is obsolete; successor family is BTN8982 / BTN9970. Module quality varies.
- Never drive RPWM and LPWM high together.

**Datasheets:**
- [BTS7960 datasheet](https://www.infineon.com/dgdl/Infineon-BTS7960-DS-v01_01-en.pdf)

## Trinamic/ADI TMC2209 stepper driver (StepStick-style module)

- **id:** `tmc2209`  
- **category:** driver/stepper  
- **manufacturer:** Analog Devices (Trinamic)  
- **used in:** Stepper diff drive

| Spec | Value |
|---|---|
| motor supply | 4.75-29 V |
| current | 2 A RMS / 2.8 A peak per coil (IC rating; modules realistically ~1.2-1.4 A RMS without active cooling) |
| microstepping | 8/16/32/64 by pins; up to 256 native via UART; MicroPlyer interpolation to 256 |
| modes | StealthChop2 (quiet), SpreadCycle (high-speed torque), StallGuard4, CoolStep |
| uart | single-wire UART on PDN_UART; 4 addresses via MS1/MS2 to share one bus |
| internal pulse generator | VACTUAL register runs the motor at a set velocity without STEP pulses |
| logic | VIO 3.3-5 V |

**Interfaces:** STEP/DIR/EN; UART

**Gotchas:**
- Set current (VREF or IRUN via UART) below the motor's rated phase current and heatsink the module.
- Never disconnect a motor while the driver is powered.
- Pi UART TX connects to PDN_UART through a 1 kOhm resistor; RX ties directly (single-wire half duplex).

**Datasheets:**
- [TMC2209 datasheet rev 1.08](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.08.pdf) *(link pattern not verified)*
- [Product page](https://www.analog.com/en/products/tmc2209.html)

## NEMA 17 bipolar stepper (17HS4401-class reference)

- **id:** `nema17`  
- **category:** actuator/stepper  
- **manufacturer:** various (exact model not specified by user)  
- **used in:** 4-DOF VR arm, Stepper diff drive

| Spec | Value |
|---|---|
| step angle | 1.8 deg (200 full steps/rev) |
| rated current | ~1.7 A/phase |
| phase resistance | ~1.5 Ohm |
| inductance | ~2.8 mH |
| holding torque | ~40-43 N-cm |
| frame | 42.3 mm square, 40 mm body length |
| mounting | 4x M3 on 31 mm square, 22 mm pilot boss, 5 mm shaft |

**Interfaces:** 4-wire bipolar (A+, A-, B+, B-)

**Gotchas:**
- Torque falls with speed; size with the pull-out torque curve, not holding torque.
- Wire colors vary by vendor: identify coil pairs with a multimeter (~1.5 Ohm across a pair).

**Datasheets:**
- [Reference NEMA 17 (Pololu #2267)](https://www.pololu.com/product/2267)
- [NEMA 17 common dimensions (RepRap wiki)](https://reprap.org/wiki/NEMA_17)

## 25 kg-cm digital servo (DS3225-class reference)

- **id:** `servo_25kg`  
- **category:** actuator/hobby servo  
- **manufacturer:** various (exact model not specified by user)  
- **used in:** 4-DOF VR arm

| Spec | Value |
|---|---|
| voltage | 4.8-6.8 V (non-HV versions) |
| stall torque | ~21-25 kg-cm at 5-6.8 V (varies by variant) |
| stall current | ~1.9-2.9 A (budget 3 A each) |
| pulse range | 500-2500 us, 50-333 Hz |
| rotation | 180 deg or 270 deg variants |
| size mm | 40 x 20 x 40.5, ~60-67 g, 25T spline |

**Interfaces:** PWM signal, 3-wire

**Gotchas:**
- Never power from an MCU 5 V pin. Budget stall x count x 0.5 minimum, with headroom for transients; add 1000+ uF bulk capacitance at the servo bus.
- Check whether yours is 180 or 270 deg before computing pulse-to-angle mapping.

**Datasheets:**
- [DS3225 spec sheet](https://bzbuas.com/wp-content/uploads/2023/02/DS3225.pdf)

## LM2596 adjustable buck converter module

- **id:** `lm2596_adj`  
- **category:** power/DC-DC buck  
- **manufacturer:** Texas Instruments (IC); modules are generic  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| input | 4.5-40 V |
| output | 1.2-37 V adjustable, 3 A rated |
| frequency | 150 kHz |
| efficiency | ~80% at 12 V in, 5 V / 3 A out (LM2596-5.0 typical) |
| protection | thermal shutdown, current limit |
| dropout note | fixed 5 V version needs Vin >= 7 V for regulation spec |

**Interfaces:** IN+/IN-/OUT+/OUT-; trim pot

**Gotchas:**
- Generic modules frequently carry counterfeit ICs and small inductors; derate to ~2 A continuous without a heatsink.
- A Pi 4B wants 3 A: an LM2596 module is at its limit. Prefer a 5 A buck for the Pi rail.
- Set output with a meter under load before connecting electronics; lock the pot with a dab of glue.

**Datasheets:**
- [LM2596 datasheet SNVS124](https://www.ti.com/lit/ds/symlink/lm2596.pdf) *(link pattern not verified)*
- [Product page](https://www.ti.com/product/LM2596)

## 3S LiPo 3000 mAh

- **id:** `lipo_3s_3000`  
- **category:** power/battery  
- **manufacturer:** various  
- **used in:** 3-pod swerve

| Spec | Value |
|---|---|
| voltage | 11.1 V nominal, 12.6 V full, 9.9 V (3.3 V/cell) practical cutoff |
| capacity | 3.0 Ah, ~33 Wh |
| discharge | check C rating; 25C x 3 Ah = 75 A burst |

**Interfaces:** XT60 typical; balance lead

**Gotchas:**
- Add a main fuse and a switch; add a low-voltage alarm or firmware cutoff using an ADC voltage divider.

## FTC-legal 12 V NiMH robot battery (e.g., REV-31-1302)

- **id:** `ftc_12v_nimh`  
- **category:** power/battery  
- **manufacturer:** REV Robotics / others  
- **used in:** FTC DECODE robot

| Spec | Value |
|---|---|
| voltage | 12 V nominal NiMH |
| fuse | 20 A ATM fuse inline |
| connector | XT30 via labeled power switch |

**Interfaces:** XT30

**Gotchas:**
- Follow the current season's competition manual for legal batteries, switches and wiring.

**Datasheets:**
- [FTC robot wiring diagram example (B2)](https://ftc-docs.firstinspires.org/_downloads/4b186ff4e86995d4783883bf72a90474/B2.pdf)

# Datasheet index

Every link in the pack, grouped by component. To download them all locally run:

```
python3 datasheets/fetch_datasheets.py
```

Files land in `datasheets/<component_id>/`. Links marked *unverified* follow the vendor's usual URL pattern but were not confirmed when the pack was built; if one fails, search the vendor site for the part number.

| Component | Document | Link | Status |
|---|---|---|---|
| `rpi4b` | Product brief | https://pip-assets.raspberrypi.com/categories/545-raspberry-pi-4-model-b/documents/RP-008344-DS-2-raspberry-pi-4-product-brief.pdf | verified |
| `rpi4b` | Datasheet (GPIO electrical, alt functions) | https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-datasheet.pdf | unverified |
| `pico_rp2040` | Pico datasheet | https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf | verified |
| `pico_rp2040` | RP2040 datasheet | https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf | verified |
| `pico_rp2040` | Hardware design with RP2040 | https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf | verified |
| `esp32` | ESP32 series datasheet | https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf | verified |
| `esp32` | ESP32-WROOM-32E/32UE module datasheet | https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf | verified |
| `arduino_uno_r3` | UNO R3 datasheet | https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf | unverified |
| `arduino_uno_r3` | UNO R3 schematic | https://content.arduino.cc/assets/UNO-TH_Rev3e_sch.pdf | verified |
| `arduino_uno_r3` | Board outline DXF (CAD) | http://arduino.cc/documents/ArduinoUno.dxf | verified |
| `rev_control_hub` | Control system overview / Control Hub specs | https://docs.revrobotics.com/duo-control/control-system-overview | verified |
| `rev_control_hub` | FTC Control Hub ports | https://ftc-docs.firstinspires.org/control_hard_compon/rc_components/hub/ports/ch-ports.html | verified |
| `rev_expansion_hub` | Expansion Hub getting started / specs | https://www.revrobotics.com/content/docs/REV-31-1153-GS.pdf | verified |
| `gobilda_pinpoint` | User guide (specs + I2C register map) | https://servocity.com/content/user_manuals/3110-0002-0001%20User%20Guide.pdf | verified |
| `gobilda_pinpoint` | Product page | https://gobilda.com/pinpoint-odometry-computer-imu-sensor-fusion-for-2-wheel-odometry | verified |
| `gobilda_4bar_pod` | Product page | https://gobilda.com/4-bar-odometry-pod-32mm-wheel | verified |
| `gobilda_yellow_jacket_5203` | Example product page with full specs (99.5:1) | https://www.gobilda.com/5203-series-yellow-jacket-planetary-gear-motor-99-5-1-ratio-24mm-length-8mm-rex-shaft-60-rpm-3-3-5v-encoder/ | verified |
| `gobilda_yellow_jacket_5203` | Example product page (3.7:1) | https://gobilda.com/5203-series-yellow-jacket-planetary-gear-motor-3-7-1-ratio-1620-rpm-3-3-5v-encoder | verified |
| `rev_color_sensor_v3` | REV Color Sensor V3 datasheet | https://www.revrobotics.com/content/docs/REV-31-1557-DS.pdf | verified |
| `rev_color_sensor_v3` | APDS-9151 datasheet | https://docs.broadcom.com/doc/APDS-9151-DS | verified |
| `ism330dhcx` | Datasheet DS13012 | https://www.st.com/resource/en/datasheet/ism330dhcx.pdf | verified |
| `ism330dhcx` | Product page (app notes) | https://www.st.com/en/mems-and-sensors/ism330dhcx.html | verified |
| `gp2y0e03` | Datasheet | https://global.sharp/products/device/lineup/data/pdf/datasheet/gp2y0e03_e.pdf | verified |
| `gp2y0e03` | Application note (registers, E-Fuse) | https://www.makerguides.com/wp-content/uploads/2024/10/GP2Y0E03-application-notes.pdf | verified |
| `tca9548a` | Datasheet SCPS207 | https://www.ti.com/lit/ds/symlink/tca9548a.pdf | unverified |
| `tca9548a` | Product page | https://www.ti.com/product/TCA9548A | verified |
| `rev_through_bore_v2` | V2 documentation | https://docs.revrobotics.com/rev-crossover-products/sensors/tbe | verified |
| `rev_through_bore_v2` | V1 datasheet (pulse timing reference) | https://www.revrobotics.com/content/docs/REV-11-1271-DS.pdf | verified |
| `rev_through_bore_v2` | V2 product page | https://www.revrobotics.com/rev-11-3174/ | verified |
| `as5047p` | Datasheet | https://www.infineon.com/row/public/documents/24/49/infineon-as5047p-datasheet-en.pdf | verified |
| `as5047p` | Fact sheet | https://look.ams-osram.com/m/96c6ce98dbc085b4/original/AS5047P_FS000140_1-00.pdf | verified |
| `pololu_37d` | 37D gearmotor datasheet (performance curves) | https://www.pololu.com/file/0J1706/pololu-37d-metal-gearmotors.pdf | verified |
| `pololu_37d` | Dimension diagram (CAD) | https://www.pololu.com/file/0J1069/37d-metal-gearmotors-dimension-diagram.pdf | verified |
| `pololu_37d` | Example product page (30:1) | https://www.pololu.com/product-info-merged/4752 | verified |
| `cytron_mdd10a` | Product page (download 'MDD10A User's Manual') | https://www.cytron.io/p-10amp-5v-30v-dc-motor-driver-2-channels | unverified |
| `bts7960` | BTS7960 datasheet | https://www.infineon.com/dgdl/Infineon-BTS7960-DS-v01_01-en.pdf | verified |
| `tmc2209` | TMC2209 datasheet rev 1.08 | https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.08.pdf | unverified |
| `tmc2209` | Product page | https://www.analog.com/en/products/tmc2209.html | verified |
| `nema17` | Reference NEMA 17 (Pololu #2267) | https://www.pololu.com/product/2267 | verified |
| `nema17` | NEMA 17 common dimensions (RepRap wiki) | https://reprap.org/wiki/NEMA_17 | verified |
| `servo_25kg` | DS3225 spec sheet | https://bzbuas.com/wp-content/uploads/2023/02/DS3225.pdf | verified |
| `lm2596_adj` | LM2596 datasheet SNVS124 | https://www.ti.com/lit/ds/symlink/lm2596.pdf | unverified |
| `lm2596_adj` | Product page | https://www.ti.com/product/LM2596 | verified |
| `ftc_12v_nimh` | FTC robot wiring diagram example (B2) | https://ftc-docs.firstinspires.org/_downloads/4b186ff4e86995d4783883bf72a90474/B2.pdf | verified |

## Other references

- [FTC 2025-2026 DECODE Competition Manual (archived season of the FTC robot)](https://ftc-resources.firstinspires.org/ftc/game/manual)
- [FTC current game and season materials](https://ftc-resources.firstinspires.org/ftc/game)
- [Pico quadrature encoder PIO example](https://github.com/raspberrypi/pico-examples/tree/master/pio/quadrature_encoder)
- [goBILDA Pinpoint FTC driver](https://github.com/goBILDA-Official/FtcRobotController-Add-Pinpoint)

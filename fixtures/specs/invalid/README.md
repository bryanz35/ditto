# Invalid specs

Each file is `fixtures/specs/plant_monitor.json` with one change, and must fail `validate_spec` with
exactly the error code in its file name (T10's acceptance test). All of them are valid `ProjectSpec`
shapes; only the hardware is wrong.

| File | Change |
| --- | --- |
| `pin_conflict.json` | `buzzer1.SIG` on GPIO21, which the I2C bus (`env1.SDA`, `oled1.SDA`) already uses |
| `reserved_pin.json` | `buzzer1.SIG` on GPIO6 (SPI flash) |
| `input_only_output.json` | `buzzer1.SIG` (a `gpio_out` pin) on input-only GPIO35 |
| `voltage_mismatch.json` | `env1.VCC` on the 5V pin; the GY-BME280 3.3 V module accepts only 3.3 V |
| `unconnected_pin.json` | `soil1.AOUT` not wired |
| `unknown_part.json` | `buzzer1` uses part id `buzzer_active`, which isn't in the library |
| `i2c_address_conflict.json` | three BME280s on one bus; the module has only two addresses (0x76, 0x77) |

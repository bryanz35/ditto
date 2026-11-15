import { Box3, Vector2, Vector3 } from 'three'
import { expect, it } from 'vitest'
import { buildPart, GENERIC, lookFor, lookOf } from './parts'

it('scales the servo look to a custom motor its own size', () => {
  // an MG996R defined as a custom part: no look of its own, so it borrows the servo's by name
  const size = new Vector3(40.7, 19.7, 42.9)
  const { root } = buildPart('x_mg996r', 'motor', size, new Vector2(0, 1), ['GND', 'VCC', 'PWM'])
  const drawn = new Box3().setFromObject(root).getSize(new Vector3())
  // x is left out: the horn hangs past the body, as on a real servo
  expect(Math.abs(drawn.y - size.y)).toBeLessThan(1)
  expect(Math.abs(drawn.z - size.z)).toBeLessThan(1)
})

it.each([
  // custom parts from real runs
  ['x_pot_10k', '10k linear rotary potentiometer (panel mount)', 'pot_rotary'],
  ['x_slide_pot_throttle', 'Slide potentiometer 10k linear, 45 mm travel, breakout style', 'pot_slide'],
  ['x_joystick_thumb_2axis', '2-axis analog thumb joystick module with push button (KY-023 style)', 'joystick'],
  ['x_mg996r', 'MG996R metal-gear servo (TowerPro), powered from external 6 V rail', 'servo'],
  ['x_psu_5v_3a', '5-6 V 3 A DC wall supply with barrel jack (servo rail)', 'barrel_jack'],
  ['x_cap_2200uf', '2200 uF 10 V electrolytic capacitor (servo rail bulk cap)', 'capacitor'],
  // specific before general, and near misses
  ['x_drv', 'DRV8833 dual motor driver', 'driver_small'],
  ['x_motor', 'Yellow TT gear motor 1:48', 'tt_gearmotor'],
  ['x_motor', '130 DC motor', 'dc_motor'],
  ['x_led', 'Red 5 mm LED', 'led_5mm'],
  ['x_btn', 'Big red button', 'button_tactile_6mm'],
  ['x_btn', '24 mm arcade button', 'button_arcade_30mm'],
  ['x_buzz', 'Active piezo buzzer 5 V', 'buzzer_passive'],
  ['x_soil', 'Capacitive soil moisture sensor', null],
  ['x_strip', 'WS2812 LED strip, 30 LEDs', null],
  ['x_fet', 'MOSFET switch module', null],
  ['x_fan', '40 mm cooling fan', null],
])('%s "%s" borrows %s', (id, name, look) => {
  expect(lookFor(id, name)).toBe(look)
})

it("takes a custom part's look over its name, except on boards and displays", () => {
  expect(lookOf('x_pot', 'input', { name: 'Rotary pot', look: 'joystick' })).toBe(GENERIC.joystick)
  expect(lookOf('x_pot', 'input', { name: 'Rotary pot', look: null })).toBe(GENERIC.pot_rotary)
  expect(lookOf('x_xiao', 'mcu', { name: 'XIAO RP2040', look: 'led_5mm' })).not.toBe(GENERIC.led_5mm)
})

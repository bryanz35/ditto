import { Box3, Vector2, Vector3 } from 'three'
import { expect, it } from 'vitest'
import { buildPart } from './parts'

it('scales the servo look to a custom motor its own size', () => {
  // an MG996R defined as a custom part: no look of its own, so it gets the motor category's
  const size = new Vector3(40.7, 19.7, 42.9)
  const { root } = buildPart('x_mg996r', 'motor', size, new Vector2(0, 1), ['GND', 'VCC', 'PWM'])
  const drawn = new Box3().setFromObject(root).getSize(new Vector3())
  // x is left out: the horn hangs past the body, as on a real servo
  expect(Math.abs(drawn.y - size.y)).toBeLessThan(1)
  expect(Math.abs(drawn.z - size.z)).toBeLessThan(1)
})

// Dev-only preview of the generic part looks (`npm run dev`, then /parts.html): one view per look,
// drag to orbit. Not part of the app build (vite only builds index.html).
import { OrbitControls, PerspectiveCamera, View } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { StrictMode, useMemo, useRef, useState, type RefObject } from 'react'
import { createRoot } from 'react-dom/client'
import { Vector2, Vector3 } from 'three'
import '../index.css'
import { buildPart, GENERIC, type Category, type PartLook } from '../scene/parts'

type Item = [id: string, label: string, matches: string, cat: Category, mm: [number, number, number], pins: string[]]
const ITEMS: Item[] = [
  ['pot_rotary', 'Rotary pot', 'pot, potentiometer, trimmer', 'input', [17, 17, 25], ['1', '2', '3']],
  ['pot_slide', 'Slide pot', 'slide pot, fader', 'input', [60, 12, 15], ['VCC', 'OUT', 'GND']],
  ['joystick', 'Joystick', 'joystick, thumbstick, ky-023', 'input', [34, 26, 32], ['GND', '5V', 'VRX', 'VRY', 'SW']],
  ['switch_rocker', 'Switch', 'switch, rocker, toggle', 'input', [21, 15, 16], ['1', '2']],
  ['servo', 'Servo (existing look)', 'servo', 'motor', [40.7, 19.7, 42.9], ['GND', 'VCC', 'PWM']],
  ['dc_motor', 'DC motor', 'dc motor, 130 motor', 'motor', [38, 20, 20], ['+', '-']],
  ['tt_gearmotor', 'TT gearmotor', 'tt motor, gearmotor', 'motor', [64, 22.5, 19], ['+', '-']],
  ['n20_gearmotor', 'N20 gearmotor', 'n20, micro gear', 'motor', [34, 12, 10], ['+', '-']],
  ['driver_l298n', 'L298N driver', 'l298n', 'output', [43, 43, 27], ['ENA', 'IN1', 'IN2', 'IN3', 'IN4', 'ENB']],
  ['driver_small', 'Small motor driver', 'drv8833, tb6612, a4988', 'output', [21, 19, 10], ['AIN1', 'AIN2', 'BIN1', 'BIN2', 'VCC', 'GND']],
  ['driver_uln2003', 'ULN2003 board', 'uln2003', 'output', [35, 32, 15], ['IN1', 'IN2', 'IN3', 'IN4', 'VCC', 'GND']],
  ['capacitor', 'Electrolytic cap', 'capacitor, uF', 'power', [13, 13, 25], ['+', '-']],
  ['barrel_jack', 'Barrel jack / PSU', 'barrel, dc jack, psu, supply', 'power', [30, 20, 15], ['VIN', 'GND']],
  ['buck_module', 'Buck / boost module', 'buck, boost, lm2596', 'power', [43, 21, 14], ['IN+', 'IN-', 'OUT+', 'OUT-']],
  ['battery_holder', 'Battery holder', 'battery, 18650, aa', 'power', [58, 31, 16], ['+', '-']],
  ['led_5mm', 'LED', 'led', 'light', [6, 6, 9], ['A', 'K']],
  ['ldr_module', 'LDR module', 'ldr, photoresistor', 'sensor', [32, 14, 10], ['VCC', 'GND', 'DO', 'AO']],
  ['x_widget', 'Fallback (no name matches)', 'anything else', 'output', [25, 18, 8], ['SIG', 'VCC', 'GND']],
]

export function Cell({ item, on }: { item: Item; on: boolean }) {
  const [id, label, matches, cat, mm, pins] = item
  const model = useMemo(() => {
    const look = id in GENERIC ? (id as PartLook) : null
    return buildPart(id, cat, new Vector3(...mm), new Vector2(0, 1), pins, { name: '', look })
  }, [id, cat, mm, pins])
  model.setPower(on ? 'on' : 'off')
  const d = Math.max(...mm) * 2.6
  return (
    <figure style={{ margin: 0, background: 'var(--color-surface-panel)', borderRadius: 8, overflow: 'hidden' }}>
      <View style={{ height: 240 }}>
        <PerspectiveCamera makeDefault fov={30} up={[0, 0, 1]} position={new Vector3(0.55, -0.85, 0.6).multiplyScalar(d)} />
        <OrbitControls makeDefault />
        <ambientLight intensity={0.7} />
        <directionalLight position={[100, -100, 200]} intensity={1.5} />
        <directionalLight position={[-120, 90, 80]} intensity={0.5} />
        <primitive object={model.root} />
      </View>
      <figcaption style={{ padding: '8px 12px 12px', color: 'var(--color-text-primary)', font: '13px system-ui' }}>
        <b style={{ color: 'var(--color-text-bright)' }}>{label}</b> <code style={{ opacity: 0.6 }}>{id}</code>
        <div style={{ color: 'var(--color-text-secondary)' }}>
          {matches} · {mm.join(' × ')} mm
        </div>
      </figcaption>
    </figure>
  )
}

export function Preview() {
  const ref = useRef<HTMLElement>(null)
  const [on, setOn] = useState(false)
  return (
    <main ref={ref} style={{ padding: 16, minHeight: '100vh', background: 'var(--color-surface-base)' }}>
      <button type="button" className="btn" onClick={() => setOn((x) => !x)} style={{ marginBottom: 12 }}>
        {on ? 'Power off' : 'Power on (LEDs)'}
      </button>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {ITEMS.map((item) => (
          <Cell key={item[0]} item={item} on={on} />
        ))}
      </div>
      <Canvas
        eventSource={ref as RefObject<HTMLElement>}
        style={{ position: 'fixed', inset: 0, pointerEvents: 'none' }}
      >
        <View.Port />
      </Canvas>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
)

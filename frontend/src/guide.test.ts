import { beforeEach, describe, expect, it } from 'vitest'
import bomJson from '../../fixtures/runs/plant_monitor/bom.json'
import layoutJson from '../../fixtures/runs/plant_monitor/cad/layout.json'
import enclosureJson from '../../fixtures/runs/plant_monitor/cad/manifest.json'
import runManifest from '../../fixtures/runs/plant_monitor/manifest.json'
import specJson from '../../fixtures/runs/plant_monitor/spec.json'
import wiringJson from '../../fixtures/runs/plant_monitor/wiring.json'
import type { Bom, EnclosureManifest, Layout, ProjectSpec, Wiring } from './contracts'
import { buildSteps, loadProgress, partNoun, saveProgress, WIRE_COLOURS, wireId } from './guide'

const artifacts = runManifest.artifacts as Record<string, { path: string }>
const urlOf = (name: string) => (artifacts[name] ? `/api/runs/r1/files/${artifacts[name].path}?v=1` : null)
const wiring = wiringJson as Wiring
const input = {
  spec: specJson as unknown as ProjectSpec, // the fixture leaves out fields that have defaults (user.level, user.name)
  layout: layoutJson as Layout,
  wiring,
  bom: bomJson as Bom,
  enclosure: enclosureJson as EnclosureManifest,
  urlOf,
}
const steps = buildSteps(input)

describe('buildSteps on the plant monitor', () => {
  it('prints, places every part, wires every part, uploads and closes', () => {
    expect(steps.map((s) => s.id)).toEqual([
      'print',
      'place-esp32',
      'place-env1',
      'place-oled1',
      'place-buzzer1',
      'place-soil1', // external: no placement, a cable hole in the back wall
      'wire-env1',
      'wire-oled1',
      'wire-soil1',
      'wire-buzzer1',
      'code',
      'close',
    ])
    expect(steps.find((s) => s.id === 'place-soil1')!.body).toContain('hole in the back wall')
    expect(steps.find((s) => s.id === 'place-esp32')!.body).toContain('USB port up with the opening in the left wall')
    expect(steps.find((s) => s.id === 'place-oled1')!.label).toBe('Place screen')
  })

  it('has wiring steps that match wiring.json row for row', () => {
    expect(steps.filter((s) => s.kind === 'Wiring').flatMap((s) => s.wires)).toEqual(wiring.rows)
    for (const s of steps.filter((s) => s.kind === 'Wiring')) {
      expect(s.needs[0].qty).toBe(`${s.wires.length}×`)
    }
  })

  it('colours each wire by its pin type', () => {
    const screen = steps.find((s) => s.id === 'wire-oled1')!.wires
    expect(screen.map((w) => WIRE_COLOURS[w.pin_type])).toEqual(['red', 'black', 'yellow', 'blue'])
  })

  it('links the files each step needs', () => {
    expect(steps[0].files.map((f) => f.name)).toEqual(['base.stl', 'lid.stl'])
    expect(steps.find((s) => s.id === 'code')!.files.map((f) => f.name)).toEqual(['main.cpp', 'pins.h', 'platformio.ini'])
  })

  it('marks a part the user owns', () => {
    const bom = { ...input.bom, lines: input.bom.lines.map((l) => (l.part_id === 'ssd1306_096_i2c' ? { ...l, owned_qty: 1 } : l)) }
    const owned = buildSteps({ ...input, bom }).find((s) => s.id === 'place-oled1')!
    expect(owned.needs[0].have).toBe(true)
  })
})

it('names parts plainly', () => {
  expect(partNoun('Passive buzzer module (KY-006)')).toBe('beeper')
  expect(partNoun('BME280 temperature, humidity and pressure module')).toBe('BME280 temperature')
})

describe('progress', () => {
  beforeEach(() => localStorage.clear())

  it('round-trips per run and drops ids the guide no longer has', () => {
    saveProgress('r1', { at: 'wire-oled1', done: ['print', 'place-gone'], wires: ['oled1.VCC', 'gone1.SIG'] })
    expect(loadProgress('r1', steps)).toEqual({ at: 'wire-oled1', done: ['print'], wires: ['oled1.VCC'] })
    expect(loadProgress('r2', steps)).toEqual({ at: null, done: [], wires: [] })
    expect(wireId(wiring.rows[0])).toBe('env1.VCC')
  })
})

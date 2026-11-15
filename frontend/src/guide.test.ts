import { beforeEach, describe, expect, it } from 'vitest'
import bomJson from '../../fixtures/runs/plant_monitor/bom.json'
import layoutJson from '../../fixtures/runs/plant_monitor/cad/layout.json'
import enclosureJson from '../../fixtures/runs/plant_monitor/cad/manifest.json'
import runManifest from '../../fixtures/runs/plant_monitor/manifest.json'
import specJson from '../../fixtures/runs/plant_monitor/spec.json'
import wiringJson from '../../fixtures/runs/plant_monitor/wiring.json'
import type { Bom, EnclosureManifest, Layout, ProjectSpec, Wiring } from './contracts'
import { buildSteps, loadProgress, partNoun, saveProgress, WIRE_COLOURS, wireId } from './guide'
import { printsOf } from './ui'

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
    const board = steps.find((s) => s.id === 'place-esp32')!.body
    expect(board).toContain('against the left wall and against the front wall')
    expect(board).toContain('USB port up with the opening in the left wall')
    expect(steps.find((s) => s.id === 'place-oled1')!.body).toContain('56 mm from the left wall')
    expect(steps.find((s) => s.id === 'place-oled1')!.label).toBe('Place screen')
    expect(steps.find((s) => s.id === 'wire-oled1')!.tip!.note).toMatch(/^3V3, GND, GPIO22 and GPIO21 are shared/)
    expect(steps[0].tip!.tone).toBe('warning') // every plant-monitor part has datasheet sizes only
  })

  it('has wiring steps that match wiring.json row for row', () => {
    expect(steps.filter((s) => s.kind === 'Wiring').flatMap((s) => s.wires)).toEqual(wiring.rows)
    for (const s of steps.filter((s) => s.kind === 'Wiring')) {
      expect(s.needs[0].qty).toBe(`${s.wires.length}×`)
    }
  })

  it("lists a custom device's extra printed parts with the case", () => {
    const enclosure = { ...input.enclosure, prints: { ...input.enclosure.prints, knob: [20, 20, 12] } } as EnclosureManifest
    const files = (name: string) => `/f/${name}.x?v=1`
    const print = buildSteps({ ...input, enclosure, urlOf: files })[0]
    expect(print.files.map((f) => f.url)).toEqual(['/f/base_stl.x?v=1', '/f/lid_stl.x?v=1', '/f/knob_stl.x?v=1'])
    expect(print.body).toContain('the case, then the knob')
  })

  it('fits printed parts and mounts parts on them in build order, each after what it attaches to', () => {
    const at = { transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }
    const enclosure = {
      ...input.enclosure,
      prints: { base: [80, 60, 40], lid: [80, 60, 5], probe_clip: [30, 20, 10] },
      assembled: { probe_clip: { on: 'base', ...at } },
      mounts: { soil1: { on: 'probe_clip', ...at } },
      build_order: ['probe_clip', 'soil1'],
    } as EnclosureManifest
    const built = buildSteps({ ...input, enclosure })
    expect(built.map((s) => s.id).slice(4, 7)).toEqual(['place-buzzer1', 'assemble-probe_clip', 'place-soil1'])
    const fit = built.find((s) => s.id === 'assemble-probe_clip')!
    expect([fit.kind, fit.title, fit.ref]).toEqual(['Assemble', 'Fit the probe clip', 'probe_clip'])
    expect(fit.body).toContain('onto the case')
    const mount = built.find((s) => s.id === 'place-soil1')!
    expect(mount.title).toBe('Mount the soil sensor')
    expect(mount.body).toContain('in the probe clip')
    expect(mount.body).toContain('hole in the back wall')
  })

  it("gives the viewer a device's extra parts but never its base and lid", () => {
    const prints = { base: [80, 60, 40], lid: [80, 60, 5], knob: [20, 20, 12] } as EnclosureManifest['prints']
    const files = (name: string) => `/f/${name}`
    expect(printsOf(input.spec, { ...input.enclosure, prints }, files)).toEqual([{ url: '/f/knob_stl', width: 20 }])
    expect(printsOf(input.spec, input.enclosure, files)).toEqual([]) // an old manifest without prints
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

describe('buildSteps on a print-only project', () => {
  const book = { ...input.spec, mcu: null, firmware: null, parts: [], connections: [] }
  const enclosure = {
    ...input.enclosure,
    template: 'custom',
    cutouts: [],
    prints: { holder: [148, 82.6, 157.8], peg: [10, 10, 20] },
  } as EnclosureManifest
  const prints = (name: string) => (name.endsWith('_stl') || name.endsWith('_step') ? `/f/${name}.x?v=1` : null)
  const steps = buildSteps({ ...input, spec: book, enclosure, urlOf: prints })

  it('has one print step per printed part and nothing to wire', () => {
    expect(steps.map((s) => s.id)).toEqual(['print-holder', 'print-peg'])
    expect(steps[0].body).toContain('148 × 83 × 158 mm')
    expect(steps[0].files.map((f) => f.detail)).toEqual(['3D print file', 'CAD file (to edit)'])
    expect(steps.every((s) => s.wires.length === 0 && s.kind === 'Print')).toBe(true)
  })
})

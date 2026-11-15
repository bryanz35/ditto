// The build guide (Figma 25:735, 28:900): steps derived from the run's files, never written by the model.
import type { Bom, EnclosureManifest, Layout, ProjectSpec, Wiring, WiringRow } from './contracts'
import type { IconName } from './Icon'
import type { UrlOf } from './panels'

export type StepKind = 'Print' | 'Place' | 'Assemble' | 'Wiring' | 'Code' | 'Close'

export interface Need {
  qty: string
  what: string
  /** Already in My parts (BomLine.owned_qty covers it). */
  have?: boolean
}

export interface StepFile {
  name: string
  detail: string
  url: string
  icon: IconName
}

export interface Step {
  id: string
  kind: StepKind
  /** Short name for the tracker tile. */
  label: string
  title: string
  body: string
  /** Part shown in the 3D view, if the step is about one, and its plain name ("screen"). */
  ref: string | null
  noun: string | null
  /** The board's short name, for "screen VCC → ESP32 3V3". */
  board: string
  wires: WiringRow[]
  needs: Need[]
  files: StepFile[]
  tip: { tone: 'tip' | 'warning'; note: string } | null
}

// Wire colour by pin type (Figma wire/* variables; only power, ground, SCL and SDA are in the file).
export const WIRE_COLOURS: Record<WiringRow['pin_type'], string> = {
  power: 'red',
  gnd: 'black',
  i2c_scl: 'yellow',
  i2c_sda: 'blue',
  analog: 'green',
  gpio: 'orange',
  gpio_in: 'orange',
  gpio_out: 'orange',
  spi_sck: 'purple',
  spi_mosi: 'purple',
  spi_miso: 'purple',
  spi_cs: 'purple',
  uart_tx: 'white',
  uart_rx: 'white',
  i2s_bclk: 'teal',
  i2s_ws: 'teal',
  i2s_din: 'teal',
  i2s_dout: 'teal',
  config: 'grey',
}

const NOUNS: [RegExp, string][] = [
  [/oled|lcd|display|screen|tft/i, 'screen'],
  [/buzzer|speaker/i, 'beeper'],
  [/soil/i, 'soil sensor'],
]

/** Plain name for a part: "screen", "beeper", else its library name up to the first comma or bracket. */
export const partNoun = (name: string) =>
  NOUNS.find(([re]) => re.test(name))?.[1] ?? name.split(/[,(]/)[0].trim()

const FEATURE: Record<string, string> = {
  usb: 'USB port',
  display_window: 'screen',
  lens: 'lens',
  button: 'button',
  led: 'light',
  sound: 'sound hole',
  vent: 'sensor',
  cable: 'cable',
}
/** "a, b and c" */
const and = (items: string[]) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items.at(-1)}` : (items[0] ?? ''))
// within the layout's clearance of a wall counts as against it
const from = (mm: number, wall: string) => (mm < 2 ? `against the ${wall} wall` : `${Math.round(mm)} mm from the ${wall} wall`)
const where = (face: string) => (face === 'top' ? 'the lid' : `the ${face} wall`)
/** A printed part's name as words: "upper_arm" -> "upper arm". */
const words = (name: string) => name.replaceAll('_', ' ')

export function buildSteps({
  spec,
  layout,
  wiring,
  bom,
  enclosure,
  urlOf,
}: {
  spec: ProjectSpec
  layout: Layout
  wiring: Wiring
  bom: Bom | null
  enclosure: EnclosureManifest | null
  urlOf: UrlOf
}): Step[] {
  const board = spec.mcu
  if (!board) return enclosure ? printSteps({ enclosure, urlOf }) : []
  const line = (ref: string) => bom?.lines.find((l) => l.refs.includes(ref))
  const name = (ref: string) =>
    line(ref)?.name ?? wiring.rows.find((r) => r.part_ref === ref)?.part_name ?? [board, ...spec.parts].find((p) => p.ref === ref)?.part_id ?? ref
  const have = (ref: string) => {
    const l = line(ref)
    return !!l && l.owned_qty >= l.qty
  }
  const noun = (ref: string) => (ref === board.ref ? 'board' : partNoun(name(ref)))
  // "ESP32" in "screen VCC → ESP32 3V3"
  const mcu = name(board.ref).split(/[\s-]/)[0] || 'board'
  const cutouts = enclosure?.cutouts ?? []
  const file = (artifact: string, detail: string, icon: IconName): StepFile[] => {
    const url = urlOf(artifact)
    return url ? [{ name: url.split('?')[0].split('/').pop()!, detail, url, icon }] : []
  }
  const step = (s: Partial<Step> & Pick<Step, 'id' | 'kind' | 'label' | 'title' | 'body'>): Step => ({
    ref: null,
    noun: s.ref ? noun(s.ref) : null,
    board: mcu,
    wires: [],
    needs: [],
    files: [],
    tip: null,
    ...s,
  })

  const steps: Step[] = []
  const unmeasured = enclosure?.unmeasured_refs ?? []
  const size = enclosure && ` Closed, the case is ${enclosure.outer_mm.map((v) => Math.round(v)).join(' × ')} mm.`
  // A custom device's model can add pieces printed apart from the case (a knob, a stand).
  const extras = Object.keys(enclosure?.prints ?? {})
    .filter((n) => n !== 'base' && n !== 'lid')
    .sort()
  steps.push(
    step({
      id: 'print',
      kind: 'Print',
      label: 'Print case',
      title: extras.length ? 'Print the case and parts' : 'Print the case',
      body: `Send ${extras.length ? `every file (the case, then the ${and(extras.map(words))})` : 'both files'} to your 3D printer. Start this first and do the next steps while it prints.${size ?? ''}`,
      files: ['base', 'lid', ...extras].flatMap((n) => file(`${n}_stl`, '3D print file', 'box')),
      needs: [
        { qty: '1×', what: '3D printer' },
        { qty: '', what: 'PLA filament (any colour)' },
      ],
      tip:
        unmeasured.length > 0
          ? {
              tone: 'warning',
              note: `Sizes for the ${and(unmeasured.map(noun))} come from datasheets, not calipers: check your parts against the case before you print.`,
            }
          : { tone: 'tip', note: 'Print the base with its open side facing up. No supports needed.' },
    }),
  )

  // Parts inside the case: the board first, then the spec's order.
  const order = [board, ...spec.parts].map((p) => p.ref)
  const placed = [...layout.placements].sort((a, b) => order.indexOf(a.ref) - order.indexOf(b.ref))
  for (const p of placed) {
    const n = noun(p.ref)
    const lineUp = cutouts
      .filter((c) => c.for_ref === p.ref)
      .map((c) => ` Line its ${FEATURE[c.feature]} up with the opening in ${where(c.face)}.`)
      .join('')
    steps.push(
      step({
        id: `place-${p.ref}`,
        kind: 'Place',
        label: `Place ${n}`,
        title: `Place the ${n}`,
        body:
          `Set it in its spot, ${from(p.x_mm, 'left')} and ${from(p.y_mm, 'front')}.${lineUp}` +
          ' If there are posts under it, screw it down; if not, a dab of hot glue holds it.',
        ref: p.ref,
        needs: [{ qty: '1×', what: name(p.ref), have: have(p.ref) }],
        tip: { tone: 'warning', note: 'Turn screws until snug, then stop. Too tight can crack the plastic posts.' },
      }),
    )
  }
  // A custom device's extra printed parts and the parts mounted on them, in build order: each after
  // what it attaches to.
  const assembled = enclosure?.assembled ?? {}
  const mounts = enclosure?.mounts ?? {}
  const onto = (on: string) =>
    on === 'base' ? 'case' : on === 'lid' ? 'lid' : assembled[on] ? words(on) : noun(on)
  for (const id of enclosure?.build_order ?? []) {
    if (assembled[id]) {
      steps.push(
        step({
          id: `assemble-${id}`,
          kind: 'Assemble',
          label: `Fit ${words(id)}`,
          title: `Fit the ${words(id)}`,
          body: `Fit it onto the ${onto(assembled[id].on)} as the picture shows, with the screws or pegs its holes are made for.`,
          ref: id,
          noun: words(id),
        }),
      )
    } else if (mounts[id]) {
      const n = noun(id)
      const hole = cutouts.find((c) => c.for_ref === id && c.feature === 'cable')
      steps.push(
        step({
          id: `place-${id}`,
          kind: 'Place',
          label: `Mount ${n}`,
          title: `Mount the ${n}`,
          body:
            `Fit it in the ${onto(mounts[id].on)} as the picture shows and screw it in.` +
            (hole ? ` Run its cable to the hole in ${where(hole.face)} and through it, so its pins end up inside.` : ''),
          ref: id,
          needs: [{ qty: '1×', what: name(id), have: have(id) }],
        }),
      )
    }
  }
  // Other parts that sit outside (mounting: external) have no placement, only a cable hole.
  for (const p of spec.parts.filter((p) => !layout.placements.some((q) => q.ref === p.ref) && !mounts[p.ref])) {
    const n = noun(p.ref)
    const hole = cutouts.find((c) => c.for_ref === p.ref && c.feature === 'cable')
    steps.push(
      step({
        id: `place-${p.ref}`,
        kind: 'Place',
        label: `Place ${n}`,
        title: `Feed the ${n} cable in`,
        body: `The ${n} sits outside the case.${hole ? ` Pass its cable through the hole in ${where(hole.face)} from the outside, so its pins end up inside.` : ''}`,
        ref: p.ref,
        needs: [{ qty: '1×', what: name(p.ref), have: have(p.ref) }],
      }),
    )
  }

  // One wiring step per part, in wiring.json's order.
  const refs = [...new Set(wiring.rows.map((r) => r.part_ref))]
  for (const ref of refs) {
    const n = noun(ref)
    const wires = wiring.rows.filter((r) => r.part_ref === ref)
    const shared = [...new Set(wires.map((w) => w.mcu_pin))].filter((pin) =>
      wiring.rows.some((r) => r.mcu_pin === pin && r.part_ref !== ref),
    )
    steps.push(
      step({
        id: `wire-${ref}`,
        kind: 'Wiring',
        label: `Wire ${n}`,
        title: `Connect the ${n}`,
        body: 'Push each wire onto its pin until it clicks into place. Match the colours below: each colour has one job, so you can check your work at a glance.',
        ref,
        wires,
        needs: [{ qty: `${wires.length}×`, what: 'Jumper wires' }],
        tip:
          shared.length > 0
            ? {
                tone: 'tip',
                note: `${and(shared)} ${shared.length > 1 ? 'are' : 'is'} shared with other parts: use a breadboard or a splitter so every wire reaches the same pin.`,
              }
            : { tone: 'tip', note: 'Pull gently on each wire after you push it on. If it slides off, it was not all the way on.' },
      }),
    )
  }

  const usb = cutouts.find((c) => c.for_ref === board.ref && c.feature === 'usb')
  steps.push(
    step({
      id: 'code',
      kind: 'Code',
      label: 'Upload code',
      title: 'Upload the code',
      body:
        `Plug the USB cable into the ${mcu}${usb ? ` through the hole in ${where(usb.face)}` : ''}, then open the files in ` +
        'PlatformIO (or the Arduino IDE) and upload. Open the serial monitor at 115200 baud: the board prints P2D_READY when it has started.',
      ref: board.ref,
      files: [
        ...file('main_cpp', 'Arduino code', 'file-code'),
        ...file('pins_h', 'Pin map', 'file-code'),
        ...file('platformio_ini', 'PlatformIO project', 'file-code'),
      ],
      needs: [
        { qty: '1×', what: 'USB cable' },
        { qty: '1×', what: 'Computer with PlatformIO or the Arduino IDE' },
      ],
      tip: {
        tone: 'tip',
        note: /esp32/i.test(board.part_id)
          ? `Nothing happening? Hold the BOOT button on the ${mcu} while the upload starts.`
          : `Nothing happening? Check the ${mcu} and its port are selected, and try another USB cable: some only charge.`,
      },
    }),
  )

  const top = cutouts.filter((c) => c.face === 'top').map((c) => FEATURE[c.feature])
  steps.push(
    step({
      id: 'close',
      kind: 'Close',
      label: 'Close lid',
      title: 'Close the lid',
      body:
        'Tuck the wires in so none sit over an opening, then press the lid on and screw it into the four corner posts.' +
        (top.length ? ` Check the ${and([...new Set(top)])} line${top.length > 1 ? '' : 's'} up with the openings in the lid.` : ''),
      // box_lid.py: M2.5 self-tapping screws into 8 mm pilot holes through a 2 mm lid
      needs: [{ qty: '4×', what: 'M2.5 × 10 mm self-tapping screws' }],
      tip: { tone: 'warning', note: 'Turn until snug, then stop. Too tight can crack the plastic posts.' },
    }),
  )
  return steps
}

/** A print-only project's guide: one step per printed part (cad/manifest.json's prints). */
export function printSteps({ enclosure, urlOf }: { enclosure: EnclosureManifest; urlOf: UrlOf }): Step[] {
  const names = Object.keys(enclosure.prints).sort()
  return names.map((name) => {
    const files = [`${name}_stl`, `${name}_step`].flatMap((artifact) => {
      const url = urlOf(artifact)
      const detail = artifact.endsWith('_stl') ? '3D print file' : 'CAD file (to edit)'
      return url ? [{ name: url.split('?')[0].split('/').pop()!, detail, url, icon: 'box' as IconName }] : []
    })
    const size = enclosure.prints[name].map((v) => Math.round(v)).join(' × ')
    return {
      id: `print-${name}`,
      kind: 'Print',
      label: names.length > 1 ? `Print ${name}` : 'Print',
      title: `Print the ${name}`,
      body: `Send ${name}.stl to your 3D printer as it is: it is already the right way up, flat side down. It is ${size} mm.`,
      ref: null,
      noun: null,
      board: '',
      wires: [],
      needs: [
        { qty: '1×', what: '3D printer' },
        { qty: '', what: 'PLA filament (any colour)' },
      ],
      files,
      tip: { tone: 'tip', note: 'Let the bed cool before you lift the part off: it comes away more easily and stays flat.' },
    } satisfies Step
  })
}

/** The step as plain text for Ask Ditto, with what the card shows: body, wires (with colours), tip. */
export const stepText = (s: Step, index: number, total: number) =>
  [
    `Step ${index + 1} of ${total}: ${s.title} (${s.kind})`,
    s.body,
    ...s.wires.map((w) => `${s.noun} ${w.part_pin} → ${s.board} ${w.mcu_pin} (${WIRE_COLOURS[w.pin_type]} wire)`),
    s.tip && `Tip: ${s.tip.note}`,
  ]
    .filter(Boolean)
    .join('\n')

export interface Progress {
  /** Id of the step on screen. */
  at: string | null
  done: string[]
  /** Ticked wires, as "<part_ref>.<part_pin>". */
  wires: string[]
}

export const wireId = (w: WiringRow) => `${w.part_ref}.${w.part_pin}`
const key = (runId: string) => `ditto.build.${runId}`

/** Progress kept in this browser, per run; ids the current guide no longer has are dropped (the spec changed). */
export function loadProgress(runId: string, steps: Step[]): Progress {
  let saved: Partial<Progress> = {}
  try {
    saved = JSON.parse(localStorage.getItem(key(runId)) ?? '{}') as Partial<Progress>
  } catch {
    // private window or storage switched off: start over
  }
  const ids = steps.map((s) => s.id)
  const wires = steps.flatMap((s) => s.wires.map(wireId))
  return {
    at: saved.at && ids.includes(saved.at) ? saved.at : null,
    done: (saved.done ?? []).filter((id) => ids.includes(id)),
    wires: (saved.wires ?? []).filter((id) => wires.includes(id)),
  }
}

export function saveProgress(runId: string, progress: Progress) {
  try {
    localStorage.setItem(key(runId), JSON.stringify(progress))
  } catch {
    // storage off: progress lives until the tab closes
  }
}

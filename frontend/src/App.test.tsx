import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import runJsonl from '../../fixtures/events/plant_monitor.jsonl?raw'
import editJsonl from '../../fixtures/events/plant_monitor_edit.jsonl?raw'
import App from './App'

// jsdom has no WebGL: stand in for the canvas, show what it was given and let a test click a part.
vi.mock('./Viewer3D', () => ({
  default: ({
    base,
    lid,
    assembly,
    selected,
    onSelect,
  }: {
    base: string | null
    lid: string | null
    assembly: string | null
    selected: { ref: string; label: string } | null
    onSelect?: (ref: string) => void
  }) => (
    <div data-testid="viewer">
      {base} {lid} {assembly} {selected && `label:${selected.ref}`}
      <button type="button" onClick={() => onSelect?.('oled1')}>
        click oled1
      </button>
    </div>
  ),
}))

// The fixture run directory, served the way GET /runs/{id}/files/{path} would.
const RUN_FILES = import.meta.glob<string>('../../fixtures/runs/plant_monitor/**/*.{json,cpp,h,ini,log}', {
  query: '?raw',
  import: 'default',
  eager: true,
})
/** Run files a test serves instead of the fixture's, by path in the run directory. */
let fileOverrides: Record<string, string> = {}
const fileBody = (url: string) => {
  const path = url.match(/\/files\/([^?]+)/)?.[1] ?? ''
  return fileOverrides[path] ?? RUN_FILES[`../../fixtures/runs/plant_monitor/${path}`]
}

class FakeEventSource {
  static CONNECTING = 0
  static CLOSED = 2
  static instances: FakeEventSource[] = []
  onmessage: ((m: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onopen: (() => void) | null = null
  readyState = FakeEventSource.CONNECTING
  closed = false
  url: string
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
  emit(lines: string[]) {
    act(() => lines.forEach((data) => this.onmessage?.({ data })))
  }
  /** The connection dropped; readyState says whether EventSource will reconnect. */
  fail(readyState: number) {
    act(() => {
      this.readyState = readyState
      this.onerror?.()
    })
  }
}

/** What GET /runs returns; null: the API has no run list (404). */
let serverRuns: Record<string, unknown>[] | null = null
let editStatus = 202
let putStatus = 200
/** What GET /memory returns; null: the memory API isn't there (404). */
let memory: Record<string, unknown> | null = null

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/api/runs' && init?.method === 'POST') {
    return { ok: true, json: async () => ({ run_id: 'r1' }) }
  }
  if (url.endsWith('/edit')) {
    return { ok: editStatus < 300, status: editStatus, text: async () => '{"detail":"The run is still working"}' }
  }
  if (url === '/api/runs') {
    return serverRuns ? { ok: true, json: async () => serverRuns } : { ok: false, status: 404, text: async () => 'not found' }
  }
  if (url.endsWith('/cancel')) return { ok: true, status: 202, text: async () => '{}' }
  if (url.endsWith('/answer')) return { ok: true, status: 200, text: async () => '{"ok":true}' }
  if (url === '/api/memory' && init?.method === 'PUT') {
    if (putStatus >= 300) return { ok: false, status: putStatus, text: async () => '{"detail":"unknown part id: nope"}' }
    const sent = JSON.parse(init.body as string)
    memory = { ...sent, owned: Object.fromEntries(Object.entries(sent.owned).filter(([, qty]) => Number(qty) > 0)) }
    return { ok: true, json: async () => memory }
  }
  if (url === '/api/memory') {
    return memory ? { ok: true, json: async () => memory } : { ok: false, status: 404, text: async () => 'not found' }
  }
  const body = fileBody(url)
  return body === undefined
    ? { ok: false, status: 404, text: async () => 'not found' }
    : { ok: true, text: async () => body }
})

const toLines = (jsonl: string) => jsonl.split('\n').filter((l) => l.trim())
const lines = toLines(runJsonl)
const editLines = toLines(editJsonl)
/** The fixture run with the events of one stage changed. */
const withStage = (stage: string, change: (e: Record<string, unknown>) => Record<string, unknown>) =>
  lines.map((l) => {
    const e = JSON.parse(l) as Record<string, unknown>
    return e.stage === stage ? JSON.stringify(change(e)) : l
  })
const openRun = () => {
  history.replaceState(null, '', '/?run=plant_monitor')
  render(<App />)
  return openStream()
}
const lastCall = (url: string, method?: string) =>
  fetchMock.mock.calls.filter(([u, init]) => u === url && (!method || init?.method === method)).at(-1)
const openStream = () => FakeEventSource.instances.at(-1)!
const checks = () => screen.getByLabelText('Checks')
const stage = (name: string) => checks().querySelector(`[data-stage="${name}"]`) as HTMLElement
/** The status pill in the overview's top bar opens the Details drawer. */
const openDetails = () => fireEvent.click(screen.getByRole('button', { name: /Plan ready|Updating/ }))
const tab = (name: string) => fireEvent.click(screen.getByRole('tab', { name }))
const PLANT_MEMORY = { budget_usd: 30, owned: { bme280_breakout: 1 }, printer: null, rejected: [] }

beforeEach(() => {
  FakeEventSource.instances = []
  fetchMock.mockClear()
  editStatus = 202
  putStatus = 200
  memory = null
  fileOverrides = {}
  serverRuns = null
  localStorage.clear()
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  history.replaceState(null, '', '/')
})

describe('Start', () => {
  it('resumes the run named in the URL after a refresh', () => {
    history.replaceState(null, '', '/?run=abc')
    render(<App />)
    expect(openStream().url).toBe('/api/runs/abc/events')
  })

  it('starts a run with the saved parts, keeps its id in the URL and lists it under Recent', async () => {
    memory = PLANT_MEMORY
    render(<App />)
    await screen.findByText('1 part in your kit')
    expect(FakeEventSource.instances).toHaveLength(0)
    fireEvent.change(screen.getByLabelText('Describe what you want to make'), { target: { value: 'plant monitor' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Plan it' })))
    const [, init] = lastCall('/api/runs', 'POST')!
    const body = init!.body as FormData
    expect(body.get('prompt')).toBe('plant monitor')
    expect(JSON.parse(body.get('user_context') as string)).toEqual({ ...PLANT_MEMORY, level: 'beginner' })
    expect(location.search).toBe('?run=r1')
    expect(openStream().url).toBe('/api/runs/r1/events')

    cleanup() // a reload: the project is still listed
    history.replaceState(null, '', '/')
    render(<App />)
    const row = within(screen.getByRole('navigation', { name: 'Projects' })).getByRole('button', { name: /plant monitor/ })
    expect(row.textContent).toMatch(/Planning…/)
  })

  it('sends the chosen skill level with the run and shows the saved name (T37)', async () => {
    memory = { ...PLANT_MEMORY, level: 'intermediate', name: 'Ada Lovelace' }
    render(<App />)
    const account = await screen.findByText('Ada Lovelace')
    expect(account.closest('.account')!.querySelector('.avatar')!.textContent).toBe('AL')
    const level = screen.getByRole('group', { name: 'Skill level' })
    expect(level.title).toBe('') // connected: no "Not connected yet (T37)"
    fireEvent.click(within(level).getByRole('button', { name: 'Expert' }))
    fireEvent.change(screen.getByLabelText('Describe what you want to make'), { target: { value: 'door chime' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Plan it' })))
    const user = JSON.parse((lastCall('/api/runs', 'POST')![1]!.body as FormData).get('user_context') as string)
    expect(user).toMatchObject({ level: 'expert', name: 'Ada Lovelace', owned: { bme280_breakout: 1 } })
  })

  it('sends the level even without the memory API', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('Describe what you want to make'), { target: { value: 'lamp' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Plan it' })))
    const user = JSON.parse((lastCall('/api/runs', 'POST')![1]!.body as FormData).get('user_context') as string)
    expect(user).toEqual({ level: 'beginner' })
    screen.getByText('Your kit')
  })

  it("lists the server's runs under Recent, next to the ones started here (T39)", async () => {
    serverRuns = [{ run_id: 'elsewhere', title: 'Night light', stage: 'done', status: 'passed', ts: Date.now() / 1000, spec_rev: 1 }]
    render(<App />)
    const row = await within(screen.getByRole('navigation', { name: 'Projects' })).findByRole('button', { name: /Night light/ })
    expect(row.textContent).toMatch(/Plan ready/)
    fireEvent.click(row)
    expect(openStream().url).toBe('/api/runs/elsewhere/events')
  })

  it('sends with Enter, while Shift+Enter starts a new line', async () => {
    render(<App />)
    const box = screen.getByLabelText('Describe what you want to make')
    fireEvent.change(box, { target: { value: 'night light' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(lastCall('/api/runs', 'POST')).toBeUndefined()
    await act(async () => fireEvent.keyDown(box, { key: 'Enter' }))
    expect((lastCall('/api/runs', 'POST')![1]!.body as FormData).get('prompt')).toBe('night light')
  })
})

describe('Planning', () => {
  it('shows Ditto at work: its plan, what it is doing and the prompt', async () => {
    const stream = openRun()
    stream.emit(lines.slice(0, 1))
    expect(screen.getByLabelText('Plan').textContent).toContain('Choose parts and pins')
    screen.getByText(/Dittoing · \d+:\d\d/)
    stream.emit(lines.slice(1, 2))
    screen.getByText('Ditto has a question for you')
    stream.emit(lines.slice(2, 6)) // validate failed, retrying
    screen.getByText('Fixing a problem with the wiring…')
    stream.emit(lines.slice(6, 8)) // the spec is saved; parts and pins chosen
    await screen.findByText('Picking parts for your plant monitor…')
    await screen.findByText(/A plant monitor for my desk/) // the prompt, from the spec
    expect(screen.getByRole('heading', { level: 2, name: 'Recent' })).toBeTruthy()
  })

  it('answers a question with one of its options', async () => {
    const stream = openRun()
    stream.emit(lines.slice(0, 2))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Battery' })))
    const [, init] = lastCall('/api/runs/plant_monitor/answer')!
    expect(JSON.parse(init!.body as string)).toEqual({ question_id: 'q1', answer: 'Battery' })
    screen.getByText('You answered: Battery')
    stream.emit(lines.slice(2, 3)) // the agent moved on
    expect(screen.queryByText(/USB power or from a battery/)).toBeNull()
  })

  it('answers a question in free text from the composer', async () => {
    openRun().emit(lines.slice(0, 2))
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'a USB power bank' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Answer' })))
    const [, init] = lastCall('/api/runs/plant_monitor/answer')!
    expect(JSON.parse(init!.body as string)).toEqual({ question_id: 'q1', answer: 'a USB power bank' })
  })

  it('lists attempts only when one failed (sub-agents also run stages to check their work)', () => {
    const pass = (seq: number) => JSON.stringify({ ...JSON.parse(lines[6]), seq, message: `check ${seq}` }) // validate passed
    openRun().emit([...lines.slice(0, 3), pass(4), pass(5)])
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(stage('validate').textContent).toContain('check 5')
    expect(stage('validate').textContent).not.toMatch(/attempt/)
  })

  it('shows the running attempt of a retried stage', () => {
    openRun().emit(lines.slice(0, 6))
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(stage('validate').textContent).toMatch(/running.*attempt 2: Checking the revised spec/)
  })

  it('stops the run with Stop (T39)', async () => {
    const stream = openRun()
    stream.emit(lines.slice(0, 1))
    const stop = screen.getByRole('button', { name: 'Stop' })
    expect(stop.getAttribute('data-placeholder')).toBeNull()
    await act(async () => fireEvent.click(stop))
    expect(lastCall('/api/runs/plant_monitor/cancel', 'POST')).toBeDefined()
    expect(screen.queryByRole('alert')).toBeNull()
  })
  it('keeps a run that ended without a spec in the chat, with Ditto\'s reply, and takes a message', async () => {
    const event = (seq: number, stage: string, status: string, message: string, data = {}) =>
      JSON.stringify({ ...JSON.parse(lines[0]), seq, stage, status, message, artifacts: {}, errors: [], data })
    const stream = openRun()
    stream.emit([
      lines[0],
      event(90, 'plan', 'running', "There's no joystick part: should I use four buttons?", { chat: 'agent' }),
      event(91, 'done', 'failed', 'Waiting for your reply'),
    ])
    screen.getByText(/should I use four buttons/)
    expect(screen.queryByRole('button', { name: /Plan ready/ })).toBeNull() // still in the chat
    fireEvent.change(screen.getByRole('textbox', { name: 'Message Ditto' }), { target: { value: 'yes, buttons' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
    expect(JSON.parse(lastCall('/api/runs/plant_monitor/edit')![1]!.body as string)).toEqual({ instruction: 'yes, buttons' })
    stream.emit([event(92, 'plan', 'queued', 'yes, buttons', { chat: 'user' })])
    screen.getByText('yes, buttons', { selector: '.user-msg p' })
  })
})

describe('Overview', () => {
  it('shows the conversation about the design: follow-ups and Ditto\'s replies', () => {
    const chat = (seq: number, who: string, message: string) =>
      JSON.stringify({ ...JSON.parse(lines[0]), seq, message, data: { chat: who } })
    const last = JSON.parse(lines.at(-1)!).seq as number
    openRun().emit([...lines, chat(last + 1, 'user', 'make the walls 3 mm'), chat(last + 2, 'agent', 'Walls are **3 mm** now.')])
    const log = screen.getByRole('list', { name: 'Conversation' })
    expect([...log.querySelectorAll('li')].map((li) => [li.className, li.textContent])).toEqual([
      ['from-user', 'make the walls 3 mm'],
      ['from-agent', 'Walls are 3 mm now.'],
    ])
    within(log).getByText('3 mm', { selector: 'strong' }) // Ditto's replies are markdown
    // folds to its tab so it doesn't cover the model
    fireEvent.click(screen.getByRole('button', { name: /Conversation/ }))
    expect(screen.queryByRole('list', { name: 'Conversation' })).toBeNull()
  })

  it('opens once the plan is done, with the parts from the BOM and their roles from the spec', async () => {
    openRun().emit(lines)
    screen.getByRole('button', { name: 'Plan ready · all checks passed' })
    const parts = screen.getByRole('region', { name: 'Parts list' })
    await within(parts).findByText('5 items')
    await within(parts).findByText('shows the readings · 1×')
    within(parts).getByText(/^\$25\.00 to buy/)
    within(parts).getByText('$25.00') // the total

    // the part's reason and wiring when its row opens
    fireEvent.click(within(parts).getByRole('button', { name: /OLED/ }))
    within(parts).getByText('Small and cheap; shares the I2C bus with the BME280')
    within(parts).getByText('4 wires (I2C)')
    within(parts).getByText('3V3 from the board')

    fireEvent.click(within(parts).getByRole('button', { name: /^Buy$/ }))
    const store = within(screen.getByRole('region', { name: 'Where to buy' })).getByRole('link', { name: /protosupplies\.com/ })
    expect(store.getAttribute('href')).toBe('https://protosupplies.com/product/oled-0-96-128x64-i2c-blue-display/')
  })

  it('lists every store offer cheapest first, and Buy all gives the cheapest store per part to buy (T38)', async () => {
    const bom = JSON.parse(RUN_FILES['../../fixtures/runs/plant_monitor/bom.json'])
    const oled = bom.lines.find((l: { part_id: string }) => l.part_id === 'ssd1306_096_i2c')
    oled.offers = [
      { seller: 'LCSC', url: 'https://lcsc.example/oled', unit_price_usd: 3.1, in_stock: true },
      { seller: 'DigiKey', url: 'https://digikey.example/oled', unit_price_usd: 4.2, in_stock: false },
      { seller: 'Mouser', url: null, unit_price_usd: 4.5, in_stock: null },
    ]
    bom.lines.find((l: { part_id: string }) => l.part_id === 'bme280_breakout').owned_qty = 1
    fileOverrides = { 'bom.json': JSON.stringify(bom) }
    openRun().emit(lines)
    const parts = screen.getByRole('region', { name: 'Parts list' })
    await within(parts).findByText('5 items')

    fireEvent.click(within(parts).getByRole('button', { name: /OLED/ }))
    fireEvent.click(within(parts).getByRole('button', { name: /^Buy$/ }))
    const where = screen.getByRole('region', { name: 'Where to buy' })
    within(where).getByText('3 stores found')
    expect(within(where).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'LLCSCIn stock$3.10',
      'DDigiKeyOut of stock$4.20',
      'MMouserOpens the store page$4.50',
    ])
    expect(within(where).getByRole('link', { name: /LCSC/ }).getAttribute('href')).toBe('https://lcsc.example/oled')
    expect(within(where).queryByRole('link', { name: /Mouser/ })).toBeNull() // no url: nothing to open
    expect(where.querySelector('[data-placeholder]')).toBeNull()

    fireEvent.click(within(parts).getByRole('button', { name: /Buy all/ }))
    const all = screen.getByRole('region', { name: 'Buy all' })
    within(all).getByText('4 parts to buy') // the BME280 is owned
    expect(within(all).getByRole('link', { name: /OLED.*LCSC/ }).getAttribute('href')).toBe('https://lcsc.example/oled')
    expect(within(all).queryByText(/BME280/)).toBeNull()
  })

  it('switches between the exploded assembly and the closed case, and finds a clicked part in the list', async () => {
    openRun().emit(lines)
    const viewer = await screen.findByTestId('viewer')
    expect(viewer.textContent).toContain('/api/runs/plant_monitor/files/cad/assembly.glb')
    fireEvent.click(screen.getByRole('button', { name: 'click oled1' }))
    const row = screen.getByRole('button', { name: /OLED/ }).closest('li')!
    expect(row.getAttribute('aria-expanded')).toBe('true')
    expect(viewer.textContent).toContain('label:oled1')
    fireEvent.click(screen.getByRole('button', { name: 'Assembled' }))
    expect(screen.getByTestId('viewer').textContent).not.toContain('assembly.glb')
    expect(screen.getByTestId('viewer').textContent).toContain('/api/runs/plant_monitor/files/cad/lid.stl')
  })

  it('shows only the case when there is no assembly preview', async () => {
    openRun().emit(withStage('assembly', (e) => ({ ...e, status: 'skipped', artifacts: {} })))
    expect((await screen.findByTestId('viewer')).textContent).toContain('cad/base.stl')
    expect(screen.queryByRole('button', { name: 'Exploded' })).toBeNull()
  })

  it('adds a part to My parts with "I have one"', async () => {
    memory = PLANT_MEMORY
    openRun().emit(lines)
    fireEvent.click(await screen.findByRole('button', { name: /OLED/ }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'I have one' })))
    const [, init] = lastCall('/api/memory', 'PUT')!
    expect(JSON.parse(init!.body as string).owned).toEqual({ bme280_breakout: 1, ssd1306_096_i2c: 1 })
    screen.getByRole('button', { name: 'Added to My parts' })
  })

  it('sends a quick reply or a typed change only when idle, and shows a refusal', async () => {
    const stream = openRun()
    stream.emit(lines)
    const chip = () => screen.getByRole('button', { name: 'Make it simpler' }) as HTMLButtonElement
    expect(chip().disabled).toBe(false)

    editStatus = 409
    await act(async () => fireEvent.click(chip()))
    expect(screen.getByRole('alert').textContent).toMatch(/409.*still working/)

    editStatus = 202
    fireEvent.change(screen.getByLabelText('Change the design'), { target: { value: 'add a buzzer' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
    const [, init] = lastCall('/api/runs/plant_monitor/edit')!
    expect(JSON.parse(init!.body as string)).toEqual({ instruction: 'add a buzzer' })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(chip().disabled).toBe(true) // until the edit's events arrive and finish
    stream.emit(editLines.slice(0, 1))
    expect(chip().disabled).toBe(true)
    screen.getByRole('button', { name: /^Updating/ })
    stream.emit(editLines.slice(1))
    expect(chip().disabled).toBe(false)
  })

  it('answers a question from the text box, never with a quick reply', async () => {
    const stream = openRun()
    stream.emit(lines)
    const question = { id: 'q2', text: 'This goes over budget by $4. Go ahead?', options: ['Yes', 'No'], timeout_s: 60 }
    stream.emit([JSON.stringify({ ...JSON.parse(lines[22]), seq: 28, status: 'waiting', message: 'Question for you', artifacts: {}, data: { question } })])
    expect((screen.getByRole('button', { name: 'Make it simpler' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'yes, go ahead' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
    const [, init] = lastCall('/api/runs/plant_monitor/answer')!
    expect(JSON.parse(init!.body as string)).toEqual({ question_id: 'q2', answer: 'yes, go ahead' })
    expect(lastCall('/api/runs/plant_monitor/edit')).toBeUndefined()
  })

  it('marks the 3D view stale during an edit until the case is rebuilt', () => {
    const stream = openRun()
    stream.emit(lines)
    expect(screen.queryByText(/Out of date/)).toBeNull()
    stream.emit(editLines.slice(0, 5)) // through "assembly stale"
    screen.getByText(/Out of date/)
    stream.emit(editLines.slice(5))
    expect(screen.queryByText(/Out of date/)).toBeNull()
  })

  it('shows a failed rerun as failed while its files stay out of date', () => {
    const stream = openRun()
    stream.emit(lines)
    stream.emit(editLines.slice(0, 5)) // layout, enclosure and assembly marked stale
    openDetails()
    const enclosure = () => stage('enclosure').querySelector('.badge')!.textContent
    expect(enclosure()).toBe('stale')
    const event = (seq: number, status: string, extra = {}) =>
      JSON.stringify({ ...JSON.parse(editLines[7]), seq, status, message: `enclosure ${status}`, artifacts: {}, ...extra })
    stream.emit([
      event(33, 'running'),
      event(34, 'failed', {
        errors: [{ code: 'not_watertight', message: 'base.stl has open edges', field: null, hint: null, severity: 'error' }],
      }),
    ])
    expect(enclosure()).toBe('failed')
    screen.getByText(/base\.stl has open edges/)
    screen.getByText(/Out of date/) // the 3D view still shows the rev 2 case
  })
})

describe('Build guide', () => {
  const card = () => screen.getByRole('region', { name: /^Step \d+$/ })
  const startBuilding = async () => {
    openRun().emit(lines)
    fireEvent.click(screen.getByRole('button', { name: /Start building/ }))
    return within(await screen.findByRole('region', { name: /^Step \d+$/ }))
  }

  it('walks the steps from the run files and keeps the progress in this browser', async () => {
    const step = await startBuilding()
    step.getByRole('heading', { name: 'Print the case' })
    expect(step.getByRole('link', { name: 'Download base.stl' }).getAttribute('href')).toMatch(/files\/cad\/base\.stl\?/)
    step.getByRole('link', { name: 'Download lid.stl' })
    const tracker = screen.getByRole('navigation', { name: 'Steps' })
    expect(within(tracker).getAllByRole('listitem')).toHaveLength(12)

    // jump to the screen's wiring, tick a wire, finish the step
    fireEvent.click(within(tracker).getByRole('button', { name: /Wire screen/ }))
    within(card()).getByRole('heading', { name: 'Connect the screen' })
    within(card()).getByText('Wires · 0 of 4 connected')
    const vcc = within(card()).getByRole('checkbox', { name: /screen VCC.*ESP32 3V3.*red/ })
    fireEvent.click(vcc)
    expect(vcc.getAttribute('aria-checked')).toBe('true')
    within(card()).getByText('Wires · 1 of 4 connected')
    fireEvent.click(within(card()).getByRole('button', { name: 'Done, next step' }))
    within(card()).getByRole('heading', { name: 'Connect the soil sensor' })
    screen.getByText('Building · 1 of 12 steps done')
    screen.getByText('1 of 12 done')

    // a reload comes back to the same step with the same ticks
    cleanup()
    const resumed = await startBuilding()
    resumed.getByRole('heading', { name: 'Connect the soil sensor' })
    fireEvent.click(within(card()).getByRole('button', { name: 'Back' }))
    expect(within(card()).getByRole('checkbox', { name: /screen VCC/ }).getAttribute('aria-checked')).toBe('true')

    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    screen.getByRole('region', { name: 'Parts list' })
  })
})

describe('Details drawer', () => {
  it('keeps every check and file from the old tabs', async () => {
    openRun().emit(lines)
    openDetails()

    expect(stage('validate').textContent).toMatch(/attempt 1: failed/)
    expect(stage('validate').textContent).toMatch(/pin_conflict/)
    expect(stage('validate').textContent).toMatch(/attempt 2: passed/)
    expect(stage('done').textContent).toMatch(/passed/)
    const crossChecks = checks().querySelectorAll('[data-check]')
    expect([...crossChecks].map((row) => row.querySelector('.badge')?.textContent)).toEqual(Array(7).fill('passed'))

    tab('Wiring')
    const wiring = await screen.findByRole('table')
    expect(within(wiring).getAllByRole('row')).toHaveLength(14) // header + 13 rows
    expect(wiring.textContent).toContain('3V3')

    tab('BOM')
    await screen.findByText(/vs budget \$30\.00/)

    tab('Code')
    expect((await screen.findByLabelText('src/main.cpp')).textContent).toContain('P2D_READY')
    expect((await screen.findByLabelText('include/pins.h')).textContent).toContain('PIN_')
    expect((await screen.findByLabelText('platformio.ini')).textContent).toContain('platform')

    tab('Simulation')
    expect((await screen.findByLabelText('Serial log')).textContent).toContain('P2D_READY')
    expect(screen.getByRole('img', { name: 'Simulator screenshot' }).getAttribute('src')).toContain(
      '/api/runs/plant_monitor/files/sim/screenshot.png',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Close details' }))
    expect(screen.queryByRole('complementary', { name: 'Details' })).toBeNull()
  })

  it('hides the simulation tab when simulate was skipped', () => {
    openRun().emit(withStage('simulate', (e) => ({ ...e, status: 'skipped', message: 'No WOKWI_CLI_TOKEN', artifacts: {} })))
    openDetails()
    screen.getByRole('tab', { name: 'BOM' })
    expect(screen.queryByRole('tab', { name: 'Simulation' })).toBeNull()
  })

  it('shows one row per cross-check and fails the one that found a problem', () => {
    const problem = (code: string, message: string) => ({ code, message, field: null, hint: null, severity: 'error' })
    openRun().emit(
      withStage('checks', (e) =>
        e.status === 'passed'
          ? {
              ...e,
              status: 'failed',
              message: '2 problems',
              errors: [problem('stale_artifact', 'bom.json is at rev 1, spec is rev 2'), problem('new_check', 'a check the UI has no row for')],
            }
          : e,
      ),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Plan ready · some checks need a look' }))
    const row = stage('checks')
    expect(row.querySelector('[data-check="stale_artifact"]')!.textContent).toMatch(/failed.*bom\.json is at rev 1/)
    expect(row.querySelector('[data-check="pins_mismatch"]')!.textContent).toMatch(/passed/)
    expect(row.textContent).toContain('a check the UI has no row for')
  })
})

describe('My parts', () => {
  it('saves the inventory and budget, and shows a refusal', async () => {
    memory = PLANT_MEMORY
    render(<App />)
    await screen.findByText('1 part in your kit')
    fireEvent.click(screen.getByRole('button', { name: /My parts/ }))
    within(screen.getByRole('list', { name: 'Owned parts' })).getByText('bme280_breakout')
    fireEvent.change(screen.getByLabelText('Part id'), { target: { value: 'ssd1306_096_i2c' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.change(screen.getByLabelText('Budget (USD)'), { target: { value: '20' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Save' })))
    const [, init] = lastCall('/api/memory', 'PUT')!
    expect(JSON.parse(init!.body as string)).toEqual({
      ...PLANT_MEMORY,
      budget_usd: 20,
      owned: { bme280_breakout: 1, ssd1306_096_i2c: 1 },
    })
    screen.getByText(/Saved/)
    screen.getByText('2 parts in your kit')

    // a removed part is gone once saved, as the API drops it
    fireEvent.click(screen.getByRole('button', { name: 'Remove bme280_breakout' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Save' })))
    expect(screen.queryByText('bme280_breakout', { selector: '.inventory code' })).toBeNull()
    screen.getByText('1 part in your kit')

    putStatus = 422
    fireEvent.change(screen.getByLabelText('Part id'), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Save' })))
    expect(screen.getByRole('alert').textContent).toMatch(/422.*unknown part id/)
  })
})

describe('Connection', () => {
  it('says when the stream is down and reopens it on Retry', () => {
    const first = openRun()
    first.emit(lines.slice(0, 5))
    first.fail(FakeEventSource.CONNECTING)
    screen.getByText(/Reconnecting/)
    first.fail(FakeEventSource.CLOSED)
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(first.closed).toBe(true)
    expect(openStream()).not.toBe(first)
    expect(screen.queryByText(/Lost the connection/)).toBeNull()
    openStream().emit(lines) // starts again at seq 1: the events already shown are dropped
    openDetails()
    expect(stage('done').textContent).toMatch(/passed/)
    openStream().fail(FakeEventSource.CONNECTING) // the server ends the stream at done
    expect(screen.queryByText(/Reconnecting/)).toBeNull()
  })
})

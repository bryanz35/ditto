import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import runJsonl from '../../fixtures/events/plant_monitor.jsonl?raw'
import editJsonl from '../../fixtures/events/plant_monitor_edit.jsonl?raw'
import App from './App'

// jsdom has no WebGL: stand in for the canvas and show what it was given.
vi.mock('./Viewer3D', () => ({
  default: ({ base, lid, assembly }: { base: string | null; lid: string | null; assembly: string | null }) => (
    <div data-testid="viewer">
      {base} {lid} {assembly}
    </div>
  ),
}))

// The fixture run directory, served the way GET /runs/{id}/files/{path} would.
const RUN_FILES = import.meta.glob<string>('../../fixtures/runs/plant_monitor/**/*.{json,cpp,h,ini,log}', {
  query: '?raw',
  import: 'default',
  eager: true,
})
const fileBody = (url: string) =>
  RUN_FILES[`../../fixtures/runs/plant_monitor/${url.match(/\/files\/([^?]+)/)?.[1]}`]

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

let editStatus = 202

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/api/runs' && init?.method === 'POST') {
    return { ok: true, json: async () => ({ run_id: 'r1' }) }
  }
  if (url.endsWith('/edit')) {
    return { ok: editStatus < 300, status: editStatus, text: async () => '{"detail":"The run is still working"}' }
  }
  if (url.endsWith('/answer')) return { ok: true, status: 200, text: async () => '{"ok":true}' }
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
const lastCall = (url: string) => fetchMock.mock.calls.filter(([u]) => u === url).at(-1)
const openStream = () => FakeEventSource.instances.at(-1)!

beforeEach(() => {
  FakeEventSource.instances = []
  fetchMock.mockClear()
  editStatus = 202
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  history.replaceState(null, '', '/')
})

describe('App', () => {
  it('resumes the run named in the URL after a refresh', () => {
    history.replaceState(null, '', '/?run=abc')
    render(<App />)
    expect(openStream().url).toBe('/api/runs/abc/events')
  })

  it('starts a run and keeps its id in the URL', async () => {
    render(<App />)
    expect(FakeEventSource.instances).toHaveLength(0)
    fireEvent.change(screen.getByLabelText('Describe the device'), { target: { value: 'plant monitor' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Build it' })))
    const [url, init] = fetchMock.mock.calls.find(([u]) => u === '/api/runs')!
    expect(url).toBe('/api/runs')
    expect((init!.body as FormData).get('prompt')).toBe('plant monitor')
    expect(location.search).toBe('?run=r1')
    expect(openStream().url).toBe('/api/runs/r1/events')
  })

  it('fills every tab and the checks panel from the fixture run', async () => {
    history.replaceState(null, '', '/?run=plant_monitor')
    render(<App />)
    openStream().emit(lines)

    // checks panel, on every tab: the failed-then-retried validate stage
    const validate = screen.getByLabelText('Checks').querySelector('[data-stage="validate"]') as HTMLElement
    expect(validate.textContent).toMatch(/attempt 1: failed/)
    expect(validate.textContent).toMatch(/pin_conflict/)
    expect(validate.textContent).toMatch(/attempt 2: passed/)
    const done = screen.getByLabelText('Checks').querySelector('[data-stage="done"]') as HTMLElement
    expect(done.textContent).toMatch(/passed/)
    const crossChecks = screen.getByLabelText('Checks').querySelectorAll('[data-check]')
    expect([...crossChecks].map((row) => row.querySelector('.badge')?.textContent)).toEqual(Array(7).fill('passed'))

    const viewer = await screen.findByTestId('viewer')
    expect(viewer.textContent).toContain('/api/runs/plant_monitor/files/cad/base.stl')
    expect(viewer.textContent).toContain('/api/runs/plant_monitor/files/cad/lid.stl')

    fireEvent.click(screen.getByRole('tab', { name: 'Wiring' }))
    const wiring = await screen.findByRole('table')
    expect(within(wiring).getAllByRole('row')).toHaveLength(14) // header + 13 rows
    expect(wiring.textContent).toContain('3V3')

    fireEvent.click(screen.getByRole('tab', { name: 'BOM' }))
    await screen.findByText(/vs budget \$30\.00/)
    screen.getByText('$25.00')

    fireEvent.click(screen.getByRole('tab', { name: 'Code' }))
    expect((await screen.findByLabelText('src/main.cpp')).textContent).toContain('P2D_READY')
    expect((await screen.findByLabelText('include/pins.h')).textContent).toContain('PIN_')
    expect((await screen.findByLabelText('platformio.ini')).textContent).toContain('platform')

    screen.getByLabelText('Checks') // still there on the last tab
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

  it('answers a question in free text', async () => {
    openRun().emit(lines.slice(0, 2))
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'a USB power bank' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Answer' })))
    const [, init] = lastCall('/api/runs/plant_monitor/answer')!
    expect(JSON.parse(init!.body as string)).toEqual({ question_id: 'q1', answer: 'a USB power bank' })
  })

  it('sends an edit only once the run is done, and shows a refusal', async () => {
    const stream = openRun()
    stream.emit(lines.slice(0, 20))
    fireEvent.change(screen.getByLabelText('Change the design'), { target: { value: 'add a buzzer' } })
    const button = () => screen.getByRole('button', { name: /Apply change|Working/ }) as HTMLButtonElement
    expect(button().disabled).toBe(true)
    stream.emit(lines.slice(20))
    expect(button().disabled).toBe(false)

    editStatus = 409
    await act(async () => fireEvent.click(button()))
    expect(screen.getByRole('alert').textContent).toMatch(/409.*still working/)

    editStatus = 202
    await act(async () => fireEvent.click(button()))
    const [, init] = lastCall('/api/runs/plant_monitor/edit')!
    expect(JSON.parse(init!.body as string)).toEqual({ instruction: 'add a buzzer' })
    expect(screen.queryByRole('alert')).toBeNull()
    fireEvent.change(screen.getByLabelText('Change the design'), { target: { value: 'make the walls 3 mm' } })
    expect(button().disabled).toBe(true) // until the edit's events arrive and finish
    stream.emit(editLines.slice(0, 1))
    expect(button().disabled).toBe(true)
    stream.emit(editLines.slice(1))
    expect(button().disabled).toBe(false)
  })

  it('marks the 3D view stale during an edit until the enclosure is rebuilt', () => {
    const stream = openRun()
    stream.emit(lines)
    expect(screen.queryByText(/Out of date/)).toBeNull()
    stream.emit(editLines.slice(0, 4)) // through "enclosure stale"
    screen.getByText(/Out of date/)
    stream.emit(editLines.slice(4))
    expect(screen.queryByText(/Out of date/)).toBeNull()
  })

  it('offers the assembly view once assembly.glb exists', async () => {
    const stream = openRun()
    stream.emit(lines.slice(0, 13)) // enclosure passed, assembly not built yet
    expect((await screen.findByTestId('viewer')).textContent).toContain('cad/base.stl')
    expect(screen.queryByRole('button', { name: 'Assembly' })).toBeNull()
    stream.emit(lines.slice(13, 15))
    expect(screen.getByTestId('viewer').textContent).not.toContain('assembly.glb')
    fireEvent.click(screen.getByRole('button', { name: 'Assembly' }))
    expect(screen.getByTestId('viewer').textContent).toContain('/api/runs/plant_monitor/files/cad/assembly.glb')
    fireEvent.click(screen.getByRole('button', { name: 'Enclosure' }))
    expect(screen.getByTestId('viewer').textContent).not.toContain('assembly.glb')
  })

  it('shows the serial log and screenshot when the simulate stage ran', async () => {
    openRun().emit(lines)
    fireEvent.click(screen.getByRole('tab', { name: 'Simulation' }))
    expect((await screen.findByLabelText('Serial log')).textContent).toContain('P2D_READY')
    expect(screen.getByRole('img', { name: 'Simulator screenshot' }).getAttribute('src')).toContain(
      '/api/runs/plant_monitor/files/sim/screenshot.png',
    )
  })

  it('hides the simulation tab when simulate was skipped', () => {
    openRun().emit(withStage('simulate', (e) => ({ ...e, status: 'skipped', message: 'No WOKWI_CLI_TOKEN', artifacts: {} })))
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
    const checks = screen.getByLabelText('Checks').querySelector('[data-stage="checks"]') as HTMLElement
    expect(checks.querySelector('[data-check="stale_artifact"]')!.textContent).toMatch(/failed.*bom\.json is at rev 1/)
    expect(checks.querySelector('[data-check="pins_mismatch"]')!.textContent).toMatch(/passed/)
    expect(checks.textContent).toContain('a check the UI has no row for')
  })

  it('shows the running attempt of a retried stage', () => {
    openRun().emit(lines.slice(0, 6))
    const validate = screen.getByLabelText('Checks').querySelector('[data-stage="validate"]') as HTMLElement
    expect(validate.textContent).toMatch(/running.*attempt 2: Checking the revised spec/)
  })

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
    expect(screen.getByLabelText('Checks').querySelector('[data-stage="done"]')!.textContent).toMatch(/passed/)
    openStream().fail(FakeEventSource.CONNECTING) // the server ends the stream at done
    expect(screen.queryByText(/Reconnecting/)).toBeNull()
  })
})

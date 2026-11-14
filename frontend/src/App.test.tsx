import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import runJsonl from '../../fixtures/events/plant_monitor.jsonl?raw'
import App from './App'

// jsdom has no WebGL: stand in for the canvas and show what it was given.
vi.mock('./Viewer3D', () => ({
  default: ({ base, lid }: { base: string | null; lid: string | null }) => (
    <div data-testid="viewer">
      {base} {lid}
    </div>
  ),
}))

// The fixture run directory, served the way GET /runs/{id}/files/{path} would.
const RUN_FILES = import.meta.glob<string>('../../fixtures/runs/plant_monitor/**/*.{json,cpp,h,ini}', {
  query: '?raw',
  import: 'default',
  eager: true,
})
const fileBody = (url: string) =>
  RUN_FILES[`../../fixtures/runs/plant_monitor/${url.match(/\/files\/([^?]+)/)?.[1]}`]

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((m: { data: string }) => void) | null = null
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
}

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/api/runs' && init?.method === 'POST') {
    return { ok: true, json: async () => ({ run_id: 'r1' }) }
  }
  const body = fileBody(url)
  return body === undefined
    ? { ok: false, status: 404, text: async () => 'not found' }
    : { ok: true, text: async () => body }
})

const lines = runJsonl.split('\n').filter((l) => l.trim())
const openStream = () => FakeEventSource.instances.at(-1)!

beforeEach(() => {
  FakeEventSource.instances = []
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
})

// Build guide: one step card at a time over the 3D view, a step tracker below (Figma 25:735, 28:900).
import confetti from 'canvas-confetti'
import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import Markdown from 'react-markdown'
import { askBuild, useJson, useSend } from './api'
import type { Bom, ChatTurn, EnclosureManifest, Layout, ProjectSpec, Wiring } from './contracts'
import { buildSteps, loadProgress, printSteps, saveProgress, stepText, WIRE_COLOURS, wireId, type Progress, type Step } from './guide'
import { Icon } from './Icon'
import type { UrlOf } from './panels'
import { printsOf, soon, type Print } from './ui'

const Viewer3D = lazy(() => import('./Viewer3D'))

export function Build({
  runId,
  title,
  spec,
  urlOf,
  onBack,
  onExit,
}: {
  runId: string
  title: string
  spec: ProjectSpec | null
  urlOf: UrlOf
  onBack: () => void
  onExit: () => void
}) {
  const layout = useJson<Layout>(urlOf('layout_json'))
  const wiring = useJson<Wiring>(urlOf('wiring_json'))
  const bom = useJson<Bom>(urlOf('bom_json'))
  const enclosure = useJson<EnclosureManifest>(urlOf('manifest'))
  const printOnly = spec !== null && !spec.mcu
  const prints = printsOf(spec, enclosure, urlOf)
  const steps = printOnly
    ? enclosure && printSteps({ enclosure, urlOf })
    : spec && layout && wiring
      ? buildSteps({ spec, layout, wiring, bom, enclosure, urlOf })
      : null
  const needed = printOnly ? ['spec', 'manifest'] : ['spec', 'layout_json', 'wiring_json']
  const missing = needed.filter((name) => !urlOf(name))

  const topbar = (status: string) => (
    <header className="topbar">
      <span className="logo" />
      <b>Ditto</b>
      <span className="slash">/</span>
      <span className="project">{title}</span>
      <span className="pill">
        <Icon name="hammer" />
        {status}
      </span>
      <span className="spacer" />
      <button type="button" className="btn" onClick={onExit}>
        <Icon name="log-out" />
        Exit
      </button>
    </header>
  )

  if (!steps) {
    return (
      <main className="overview build">
        {topbar('Building')}
        <p className="empty center">
          {missing.length > 0
            ? printOnly
              ? 'The build guide needs the 3D model, and this run has none yet.'
              : 'The build guide needs the case layout and the wiring, and this run has none yet.'
            : 'Loading the build guide…'}
        </p>
        <nav className="tracker" aria-label="Steps">
          <button type="button" className="btn secondary" onClick={onBack}>
            <Icon name="arrow-left" />
            Overview
          </button>
        </nav>
      </main>
    )
  }
  return <Guide key={steps.map((s) => s.id).join()} {...{ runId, steps, prints, spec, wiring, enclosure, urlOf, topbar, onBack }} />
}

function Guide({
  runId,
  steps,
  prints,
  spec,
  wiring,
  enclosure,
  urlOf,
  topbar,
  onBack,
}: {
  runId: string
  steps: Step[]
  /** A print-only project's parts, shown instead of the case; a device's extras, beside it. */
  prints: Print[]
  spec: ProjectSpec | null
  wiring: Wiring | null
  enclosure: EnclosureManifest | null
  urlOf: UrlOf
  topbar: (status: string) => ReactNode
  onBack: () => void
}) {
  const [progress, setProgress] = useState<Progress>(() => loadProgress(runId, steps))
  useEffect(() => saveProgress(runId, progress), [runId, progress])
  const index = Math.max(0, steps.findIndex((s) => s.id === progress.at))
  const step = steps[index]
  const done = progress.done.length
  const go = (i: number) => setProgress((p) => ({ ...p, at: steps[i].id }))
  const finish = () => {
    if (index === steps.length - 1) confetti({ particleCount: 150, spread: 100, origin: { y: 0.6 }, disableForReducedMotion: true })
    setProgress((p) => ({
      ...p,
      done: p.done.includes(step.id) ? p.done : [...p.done, step.id],
      at: steps[Math.min(index + 1, steps.length - 1)].id,
    }))
  }
  const tick = (id: string) =>
    setProgress((p) => ({ ...p, wires: p.wires.includes(id) ? p.wires.filter((w) => w !== id) : [...p.wires, id] }))

  // the device as it is during this step, playing the step's animation (scene/device.ts)
  const assembly = urlOf('assembly_glb')

  return (
    <main className="overview build">
      <div className="viewport">
        {urlOf('base_stl') || prints.length ? (
          <Suspense fallback={<p className="empty center">Loading the 3D view…</p>}>
            <Viewer3D
              base={spec && !spec.mcu ? null : urlOf('base_stl')}
              lid={step.kind === 'Close' ? urlOf('lid_stl') : null}
              prints={prints}
              assembly={assembly}
              spec={spec}
              wiring={wiring}
              manifest={enclosure}
              build={{ steps, index }}
              leftInset={392}
              selected={assembly && step.ref && step.kind !== 'Code' ? { ref: step.ref, label: step.noun ?? step.ref } : null}
            />
          </Suspense>
        ) : (
          <p className="empty center">No case yet.</p>
        )}
        <p className="viewport-hint mono">Drag to turn · Scroll to zoom</p>
      </div>
      {topbar(done === steps.length ? `Built · all ${steps.length} steps done` : `Building · ${done} of ${steps.length} steps done`)}

      <section className="step-card" aria-label={`Step ${index + 1}`}>
        <header className="step-header">
          <span className="top">
            <span className="number">{index + 1}</span>
            <span className="total">/ {steps.length}</span>
            <span className="spacer" />
            <span className="tag">{step.kind}</span>
          </span>
          <h2>{step.title}</h2>
        </header>
        <p>{step.body}</p>
        {step.wires.length > 0 && (
          <div className="group">
            <h3 className="caps">
              Wires · {step.wires.filter((w) => progress.wires.includes(wireId(w))).length} of {step.wires.length} connected
            </h3>
            {step.wires.map((w) => {
              const id = wireId(w)
              const on = progress.wires.includes(id)
              const colour = WIRE_COLOURS[w.pin_type]
              return (
                <button key={id} type="button" role="checkbox" aria-checked={on} className="wire" title={w.reason || undefined} onClick={() => tick(id)}>
                  <Icon name={on ? 'check' : 'square'} className="box" />
                  <span className="swatch" data-colour={colour} style={{ background: `var(--color-wire-${colour})` }} />
                  <span>
                    {step.noun} {w.part_pin}
                  </span>
                  <Icon name="arrow-right" className="arrow" />
                  <span>
                    {step.board} {w.mcu_pin}
                  </span>
                  <span className="spacer" />
                  <span className="mono">{colour}</span>
                </button>
              )
            })}
          </div>
        )}
        {step.kind === 'Code' && (
          // shortcut: no browser flashing yet (needs a compiled .bin and a Web Serial flasher); upload from PlatformIO
          <button type="button" className="btn primary tall wide" {...soon(null)}>
            <Icon name="arrow-up" />
            Upload to the board
          </button>
        )}
        {step.files.length > 0 && (
          <div className="group">
            <h3 className="caps">Files for this step</h3>
            {step.files.map((f) => (
              <div key={f.name} className="file-item">
                <span className="tile">
                  <Icon name={f.icon} />
                </span>
                <span className="text">
                  <span className="name">{f.name}</span>
                  <span className="detail">{f.detail}</span>
                </span>
                <a className="btn secondary" href={f.url} download={f.name} aria-label={`Download ${f.name}`}>
                  <Icon name="download" />
                  Download
                </a>
              </div>
            ))}
            {step.kind === 'Code' && urlOf('main_cpp') && <CopyCode url={urlOf('main_cpp')!} />}
          </div>
        )}
        {step.tip && (
          <p className={`callout ${step.tip.tone}`}>
            <Icon name={step.tip.tone === 'warning' ? 'triangle-alert' : 'lightbulb'} />
            {step.tip.note}
          </p>
        )}
        {step.needs.length > 0 && (
          <div className="needs">
            <h3 className="caps">You need</h3>
            {step.needs.map((n) => (
              <p key={n.what}>
                <b>{n.qty}</b>
                <span className="what">{n.what}</span>
                {n.have && (
                  <span className="have">
                    <Icon name="check" />
                    you have it
                  </span>
                )}
              </p>
            ))}
          </div>
        )}
        <nav className="step-nav">
          {index > 0 && (
            <button type="button" className="btn secondary" onClick={() => go(index - 1)}>
              <Icon name="arrow-left" />
              Back
            </button>
          )}
          <span className="spacer" />
          <button type="button" className="btn primary" onClick={finish}>
            <Icon name="check" />
            {index === steps.length - 1 ? 'Done' : step.kind === 'Code' ? 'It works! Next step' : 'Done, next step'}
          </button>
        </nav>
      </section>
      <AskDitto runId={runId} step={stepText(step, index, steps.length)} />

      <nav className="tracker" aria-label="Steps">
        <button type="button" className="btn secondary" onClick={onBack}>
          <Icon name="arrow-left" />
          Overview
        </button>
        <ol>
          {steps.map((s, i) => (
            <li key={s.id}>
              <button type="button" className="step-tile" aria-current={i === index ? 'step' : undefined} onClick={() => go(i)}>
                <span className="mono">
                  {progress.done.includes(s.id) && <Icon name="check" />}
                  {i + 1}
                </span>
                <span className="label">{s.label}</span>
              </button>
            </li>
          ))}
        </ol>
        <span className="progress">
          {done} of {steps.length} done
          <span className="track">
            <span style={{ width: `${(100 * done) / steps.length}%` }} />
          </span>
        </span>
      </nav>
    </main>
  )
}

/** Ditto in the corner and its speech-bubble chat: questions about the build, answered from the run's files. */
function AskDitto({ runId, step }: { runId: string; step: string }) {
  const [open, setOpen] = useState(false)
  // kept while the panel is closed and across steps; gone on reload (shortcut: not saved)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [text, setText] = useState('')
  const { sending, error, send } = useSend()
  const log = useRef<HTMLOListElement>(null)
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight
  }, [turns.length, sending, open])
  const submit = async () => {
    const question = text.trim()
    if (!question || sending) return
    const history = turns
    setTurns([...history, { role: 'user', text: question }])
    setText('')
    const ok = await send(async () => {
      const answer = await askBuild(runId, { question, step, history })
      setTurns([...history, { role: 'user', text: question }, { role: 'ditto', text: answer }])
    })
    if (!ok) {
      setTurns(history)
      setText(question)
    }
  }
  return (
    <>
      {open && <span className="bubble-open" aria-hidden="true" />}
      {open && (
        <section className="ask-panel" aria-label="Ask Ditto">
          <header>
            <span className="caps">Ask Ditto</span>
            <span className="spacer" />
            <button type="button" className="icon-btn sm" aria-label="Close the chat" onClick={() => setOpen(false)}>
              <Icon name="x" />
            </button>
          </header>
          <ol ref={log} className="chat-log" aria-label="Conversation">
            {turns.length === 0 && <li className="from-agent">Stuck on this step? Ask me anything about the build.</li>}
            {turns.map((t, i) =>
              t.role === 'user' ? (
                <li key={i} className="from-user">
                  {t.text}
                </li>
              ) : (
                <li key={i} className="from-agent">
                  <Markdown>{t.text}</Markdown>
                </li>
              ),
            )}
            {sending && (
              <li className="working" role="status">
                <span className="sprite" aria-hidden="true" />
                <span className="status-text">Thinking…</span>
              </li>
            )}
          </ol>
          <form
            className="input-row"
            onSubmit={(e) => {
              e.preventDefault()
              void submit()
            }}
          >
            <span className="compact">
              <input aria-label="Ask about the build" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about this step…" />
              <button type="submit" className="icon-btn send" aria-label="Send" disabled={sending || !text.trim()}>
                <Icon name="arrow-up" />
              </button>
            </span>
          </form>
          {error && <p role="alert">{error}</p>}
        </section>
      )}
      <button
        type="button"
        className="ditto-button"
        aria-label={open ? 'Close Ask Ditto' : 'Ask Ditto'}
        aria-expanded={open}
        title="Ask Ditto"
        onClick={() => setOpen(!open)}
      />
    </>
  )
}

function CopyCode({ url }: { url: string }) {
  const { sending, error, send } = useSend()
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`Loading the code failed (${res.status})`)
    await navigator.clipboard.writeText(await res.text())
  }
  return (
    <>
      <span className="file-actions">
        <button type="button" className="btn" disabled={sending} onClick={async () => setCopied(await send(copy))}>
          <Icon name={copied ? 'check' : 'copy'} />
          {copied ? 'Copied' : 'Copy code'}
        </button>
      </span>
      {error && <p role="alert">{error}</p>}
    </>
  )
}

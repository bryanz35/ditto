// Build guide: one step card at a time over the 3D view, a step tracker below (Figma 25:735, 28:900).
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { useJson, useSend } from './api'
import type { Bom, EnclosureManifest, Layout, ProjectSpec, Wiring } from './contracts'
import { buildSteps, loadProgress, saveProgress, WIRE_COLOURS, wireId, type Progress, type Step } from './guide'
import { Icon } from './Icon'
import type { UrlOf } from './panels'
import { soon } from './ui'

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
  const steps = spec && layout && wiring ? buildSteps({ spec, layout, wiring, bom, enclosure, urlOf }) : null
  const missing = ['spec', 'layout_json', 'wiring_json'].filter((name) => !urlOf(name))

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
          {missing.length > 0 ? 'The build guide needs the case layout and the wiring, and this run has none yet.' : 'Loading the build guide…'}
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
  return <Guide key={steps.map((s) => s.id).join()} {...{ runId, steps, urlOf, topbar, onBack }} />
}

function Guide({
  runId,
  steps,
  urlOf,
  topbar,
  onBack,
}: {
  runId: string
  steps: Step[]
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
  const finish = () =>
    setProgress((p) => ({
      ...p,
      done: p.done.includes(step.id) ? p.done : [...p.done, step.id],
      at: steps[Math.min(index + 1, steps.length - 1)].id,
    }))
  const tick = (id: string) =>
    setProgress((p) => ({ ...p, wires: p.wires.includes(id) ? p.wires.filter((w) => w !== id) : [...p.wires, id] }))

  // place and wire steps show the parts in place, the last step the closed box, the rest the bare case
  const assembly = step.ref && step.kind !== 'Code' ? urlOf('assembly_glb') : null

  return (
    <main className="overview build">
      <div className="viewport">
        {urlOf('base_stl') ? (
          <Suspense fallback={<p className="empty center">Loading the 3D view…</p>}>
            <Viewer3D
              base={urlOf('base_stl')}
              lid={step.kind === 'Close' ? urlOf('lid_stl') : null}
              assembly={assembly}
              selected={assembly && step.ref ? { ref: step.ref, label: step.noun ?? step.ref } : null}
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

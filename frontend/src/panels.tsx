import { useState, type FormEvent, type ReactNode } from 'react'
import { useText } from './api'
import type { Bom, ToolError, Wiring } from './contracts'
import { STAGES, type RunState, type Status } from './state'

/** Resolves an artifact name to its file URL (null until a stage has produced it). */
export type UrlOf = (name: string) => string | null

const Badge = ({ status }: { status: Status | 'stale' }) => (
  <span className={`badge ${status}`}>{status}</span>
)

export function ChatPanel({
  state,
  onStart,
}: {
  state: RunState
  onStart: (prompt: string, files: File[]) => Promise<void>
}) {
  const [prompt, setPrompt] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      await onStart(prompt, files)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  return (
    <aside className="chat">
      <h1>Prompt-to-Device</h1>
      <ol className="log">
        {state.log.map((e) => (
          <li key={e.seq}>
            <Badge status={e.status} /> <b>{e.stage}</b> {e.message}
          </li>
        ))}
      </ol>
      {state.question && (
        <div className="question" role="status">
          <p>{state.question.text}</p>
          {state.question.options.length > 0 && <p>Options: {state.question.options.join(' · ')}</p>}
        </div>
      )}
      {state.todos.length > 0 && (
        <ul className="todos" aria-label="Plan">
          {state.todos.map((t) => (
            <li key={t.content} className={t.status}>
              {t.status === 'completed' ? '✓' : t.status === 'in_progress' ? '…' : '○'} {t.content}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={submit}>
        <label htmlFor="prompt">Describe the device</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="A plant monitor that beeps when the soil is dry"
          rows={4}
        />
        <label htmlFor="files">Sketch or video (optional)</label>
        <input
          id="files"
          type="file"
          accept="image/*,video/*"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <button type="submit" disabled={sending || !prompt.trim()}>
          {sending ? 'Starting…' : 'Build it'}
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </aside>
  )
}

export function ChecksPanel({ state }: { state: RunState }) {
  return (
    <section className="checks" aria-label="Checks">
      <h2>Checks {state.specRev > 0 && <small>spec rev {state.specRev}</small>}</h2>
      <ul>
        {STAGES.map((stage) => {
          const s = state.stages[stage]
          return (
            <li key={stage} data-stage={stage}>
              <b>{stage}</b> <Badge status={state.stale.includes(stage) ? 'stale' : (s?.status ?? 'queued')} />{' '}
              {s?.message}
              {s && s.attempts.length > 1 && (
                <ol className="attempts">
                  {s.attempts.map((a, i) => (
                    <li key={i}>
                      attempt {a.attempt ?? i + 1}: <Badge status={a.status} /> {a.message}
                      <Errors errors={a.errors} />
                    </li>
                  ))}
                </ol>
              )}
              {s && s.attempts.length <= 1 && <Errors errors={s.errors} />}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Errors({ errors }: { errors: ToolError[] }) {
  if (errors.length === 0) return null
  return (
    <ul className="errors">
      {errors.map((e, i) => (
        <li key={i} className={e.severity}>
          <code>{e.code}</code> {e.message}
          {e.field && <> (field <code>{e.field}</code>)</>}
          {e.hint && <div className="hint">Hint: {e.hint}</div>}
        </li>
      ))}
    </ul>
  )
}

/** Fetches one artifact and renders it, or says why it can't yet. */
function ArtifactView({
  url,
  stale,
  children,
}: {
  url: string | null
  stale: boolean
  children: (text: string) => ReactNode
}) {
  const { text, error } = useText(url)
  if (!url) return <p className="empty">Not built yet.</p>
  if (error) return <p role="alert">Couldn't load it: {error}</p>
  if (text === null) return <p className="empty">Loading…</p>
  return (
    <>
      {stale && <p className="stale-note"><Badge status="stale" /> Out of date: the spec changed since this was made.</p>}
      {children(text)}
    </>
  )
}

export function WiringTab({ url, stale }: { url: string | null; stale: boolean }) {
  return (
    <ArtifactView url={url} stale={stale}>
      {(text) => (
        <table>
          <thead>
            <tr><th>Part</th><th>Part pin</th><th>MCU pin</th><th>Bus</th><th>Type</th><th>Why</th></tr>
          </thead>
          <tbody>
            {(JSON.parse(text) as Wiring).rows.map((r) => (
              <tr key={`${r.part_ref}.${r.part_pin}`}>
                <td title={r.part_name}>{r.part_ref}</td>
                <td>{r.part_pin}</td>
                <td>{r.mcu_pin}</td>
                <td>{r.bus}</td>
                <td>{r.pin_type}</td>
                <td>{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </ArtifactView>
  )
}

const usd = (v: number | null) => (v === null ? '—' : `$${v.toFixed(2)}`)

export function BomTab({ url, stale }: { url: string | null; stale: boolean }) {
  return (
    <ArtifactView url={url} stale={stale}>
      {(text) => {
        const bom = JSON.parse(text) as Bom
        return (
          <table>
            <thead>
              <tr><th>Part</th><th>Refs</th><th>Qty</th><th>Unit</th><th>Line total</th><th>Price from</th></tr>
            </thead>
            <tbody>
              {bom.lines.map((l) => (
                <tr key={l.part_id}>
                  <td>
                    {l.vendor_url ? <a href={l.vendor_url} target="_blank" rel="noreferrer">{l.name}</a> : l.name}
                    {l.owned_qty > 0 && <span className="badge owned">owned {l.owned_qty}</span>}
                  </td>
                  <td>{l.refs.join(', ')}</td>
                  <td>{l.qty}</td>
                  <td>{usd(l.unit_price_usd)}</td>
                  <td>{usd(l.line_total_usd)}</td>
                  <td>{l.price_source}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className={bom.over_budget ? 'over' : ''}>
                <td colSpan={4}>
                  Total{bom.budget_usd !== null && <> vs budget {usd(bom.budget_usd)}</>}
                  {bom.over_budget && <span className="badge failed">over budget</span>}
                </td>
                <td colSpan={2}>{usd(bom.total_usd)}</td>
              </tr>
            </tfoot>
          </table>
        )
      }}
    </ArtifactView>
  )
}

const CODE_FILES = [
  ['main_cpp', 'src/main.cpp'],
  ['pins_h', 'include/pins.h'],
  ['platformio_ini', 'platformio.ini'],
] as const

export function CodeTab({ urlOf, staleOf }: { urlOf: UrlOf; staleOf: (name: string) => boolean }) {
  return (
    <>
      {CODE_FILES.map(([name, label]) => (
        <section key={name} className="code">
          <h3>{label}</h3>
          <ArtifactView url={urlOf(name)} stale={staleOf(name)}>
            {(text) => <pre aria-label={label}>{text}</pre>}
          </ArtifactView>
        </section>
      ))}
    </>
  )
}

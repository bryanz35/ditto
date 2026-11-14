import { useState, type FormEvent, type ReactNode } from 'react'
import { useText } from './api'
import type { Bom, Question, ToolError, Wiring } from './contracts'
import { STAGES, type RunState, type StageState, type Status } from './state'

/** Resolves an artifact name to its file URL (null until a stage has produced it). */
export type UrlOf = (name: string) => string | null

const Badge = ({ status }: { status: Status | 'stale' }) => (
  <span className={`badge ${status}`}>{status}</span>
)

/** Runs one request at a time and keeps its error for the form to show. */
function useSend() {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const send = async (request: () => Promise<void>): Promise<boolean> => {
    setSending(true)
    setError(null)
    try {
      await request()
      return true
    } catch (err) {
      setError((err as Error).message)
      return false
    } finally {
      setSending(false)
    }
  }
  return { sending, error, send }
}

export function ChatPanel({
  state,
  onStart,
  onEdit,
  onAnswer,
}: {
  state: RunState
  onStart: (prompt: string, files: File[]) => Promise<void>
  /** null until there is a run to change */
  onEdit: ((instruction: string) => Promise<void>) | null
  onAnswer: (questionId: string, answer: string) => Promise<void>
}) {
  const [prompt, setPrompt] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const { sending, error, send } = useSend()

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(() => onStart(prompt, files))
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
        <QuestionBox key={state.question.id} question={state.question} onAnswer={onAnswer} />
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
      {onEdit && <EditForm state={state} onEdit={onEdit} />}
    </aside>
  )
}

function QuestionBox({
  question,
  onAnswer,
}: {
  question: Question
  onAnswer: (questionId: string, answer: string) => Promise<void>
}) {
  const [text, setText] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const { sending, error, send } = useSend()
  const answer = async (value: string) => {
    if (await send(() => onAnswer(question.id, value))) setSent(value)
  }
  return (
    <div className="question" role="status">
      <p>{question.text}</p>
      {sent !== null ? (
        <p className="empty">You answered: {sent}</p>
      ) : (
        <>
          {question.options.map((option) => (
            <button key={option} type="button" disabled={sending} onClick={() => void answer(option)}>
              {option}
            </button>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void answer(text)
            }}
          >
            <input aria-label="Your answer" value={text} onChange={(e) => setText(e.target.value)} />
            <button type="submit" disabled={sending || !text.trim()}>
              Answer
            </button>
          </form>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

/** "add a buzzer": only while the run is idle (the API answers 409 while it works). */
function EditForm({ state, onEdit }: { state: RunState; onEdit: (instruction: string) => Promise<void> }) {
  const [instruction, setInstruction] = useState('')
  // lastSeq when the edit was accepted: stay disabled until its first event arrives
  const [sentAt, setSentAt] = useState<number | null>(null)
  const { sending, error, send } = useSend()
  const idle = state.done && sentAt !== state.lastSeq
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (await send(() => onEdit(instruction))) {
      setSentAt(state.lastSeq)
      setInstruction('')
    }
  }
  return (
    <form onSubmit={submit}>
      <label htmlFor="edit">Change the design</label>
      <textarea
        id="edit"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        placeholder="add a buzzer"
        rows={2}
      />
      <button type="submit" disabled={sending || !idle || !instruction.trim()}>
        {idle ? 'Apply change' : 'Working…'}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
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
            <li key={stage} data-stage={stage} data-status={s?.status ?? 'queued'}>
              <b>{stage}</b> <Badge status={s?.status ?? 'queued'} />{' '}
              {s?.status === 'running' && s.attempt !== null && s.attempt > 1 && <>attempt {s.attempt}: </>}
              {s?.message}
              {stage === 'checks' && (s?.status === 'passed' || s?.status === 'failed') ? (
                <CrossChecks errors={s.errors} />
              ) : s && s.attempts.length > 1 && s.attempts.some((a) => a.status === 'failed') ? (
                <ol className="attempts">
                  {s.attempts.map((a, i) => (
                    <li key={i}>
                      attempt {a.attempt ?? i + 1}: <Badge status={a.status} /> {a.message}
                      <Errors errors={a.errors} />
                    </li>
                  ))}
                </ol>
              ) : (
                s && <Errors errors={s.errors} />
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// One row per error code of backend/tools/cross_checks.py; codes not listed here still show below.
const CROSS_CHECKS = [
  ['pins_mismatch', 'pins.h matches the connections'],
  ['wiring_mismatch', 'wiring table matches the connections'],
  ['layout_mismatch', 'every part fits in the cavity'],
  ['cutout_mismatch', 'every part feature has a cutout'],
  ['bom_mismatch', 'BOM matches the parts'],
  ['stale_artifact', 'every file is at the current spec rev'],
  ['missing_artifact', 'every listed file exists'],
] as const

function CrossChecks({ errors }: { errors: ToolError[] }) {
  const listed: string[] = CROSS_CHECKS.map(([code]) => code)
  return (
    <>
      <ul className="cross-checks">
        {CROSS_CHECKS.map(([code, label]) => {
          const found = errors.filter((e) => e.code === code)
          return (
            <li key={code} data-check={code}>
              <Badge status={found.length > 0 ? 'failed' : 'passed'} /> {label}
              <Errors errors={found} />
            </li>
          )
        })}
      </ul>
      <Errors errors={errors.filter((e) => !listed.includes(e.code))} />
    </>
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

export function SimulationTab({
  stage,
  urlOf,
  staleOf,
}: {
  stage: StageState
  urlOf: UrlOf
  staleOf: (name: string) => boolean
}) {
  const screenshot = urlOf('screenshot')
  return (
    <>
      <p>
        <Badge status={stage.status} /> {stage.message}
      </p>
      <Errors errors={stage.errors} />
      {screenshot && <img className="sim-shot" src={screenshot} alt="Simulator screenshot" />}
      <section className="code">
        <h3>Serial log</h3>
        <ArtifactView url={urlOf('serial_log')} stale={staleOf('serial_log')}>
          {(text) => <pre aria-label="Serial log">{text}</pre>}
        </ArtifactView>
      </section>
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

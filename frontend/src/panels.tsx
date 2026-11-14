import { useState, type ReactNode } from 'react'
import { useText, type Reply } from './api'
import type { Bom, ToolError, Wiring } from './contracts'
import { Icon } from './Icon'
import { STAGES, type RunState, type StageState, type Status } from './state'
import { usd } from './ui'

/** Resolves an artifact name to its file URL (null until a stage has produced it). */
export type UrlOf = (name: string) => string | null

export const Badge = ({ status }: { status: Status | 'stale' }) => (
  <span className={`badge ${status}`}>{status}</span>
)

/** The open question, with its options as buttons; free-text answers go through the composer. */
export function QuestionCard({ reply }: { reply: Reply }) {
  const { question, answer } = reply
  if (!question) return null
  return (
    <div className="question" role="status">
      <p>{question.text}</p>
      {answer !== null ? (
        <p className="hint">You answered: {answer}</p>
      ) : (
        <div className="options">
          {question.options.map((option) => (
            <button
              key={option}
              type="button"
              className="btn secondary"
              disabled={!reply.ready}
              onClick={() => void reply.send(option)}
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const TABS = ['Checks', 'Wiring', 'BOM', 'Code', 'Simulation'] as const
type Tab = (typeof TABS)[number]

/** Everything the checks found and every generated file, in a side drawer. */
export function Details({
  state,
  urlOf,
  staleOf,
  onClose,
}: {
  state: RunState
  urlOf: UrlOf
  staleOf: (name: string) => boolean
  onClose: () => void
}) {
  const [tab, setTab] = useState<Tab>('Checks')
  const sim = state.stages.simulate
  const tabs = TABS.filter((t) => t !== 'Simulation' || (sim && sim.status !== 'skipped'))
  return (
    <aside className="drawer" aria-label="Details">
      <header>
        <nav role="tablist">
          {tabs.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <button type="button" className="icon-btn" aria-label="Close details" onClick={onClose}>
          <Icon name="x" />
        </button>
      </header>
      <div role="tabpanel" className="drawer-body">
        {tab === 'Checks' && <ChecksPanel state={state} />}
        {tab === 'Wiring' && <WiringTab url={urlOf('wiring_json')} stale={staleOf('wiring_json')} />}
        {tab === 'BOM' && <BomTab url={urlOf('bom_json')} stale={staleOf('bom_json')} />}
        {tab === 'Code' && <CodeTab urlOf={urlOf} staleOf={staleOf} />}
        {tab === 'Simulation' && sim && <SimulationTab stage={sim} urlOf={urlOf} staleOf={staleOf} />}
      </div>
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

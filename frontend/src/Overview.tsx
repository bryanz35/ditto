// Project · Overview: the 3D model, the parts list and the follow-up dock (Figma 17:310, 19:527).
import { lazy, Suspense, useState } from 'react'
import { useJson, useSend, type Reply } from './api'
import type { Bom, BomLine, ProjectSpec, Wiring } from './contracts'
import { Icon, Segmented } from './Icon'
import { Badge, QuestionCard, type UrlOf } from './panels'
import { statusLine, type RunState } from './state'
import { partIcon, soon, usd } from './ui'

// three.js is big; load it only when the overview first renders.
const Viewer3D = lazy(() => import('./Viewer3D'))

const VIEWS = ['Assembled', 'Exploded'] as const
type View = (typeof VIEWS)[number]

const QUICK_REPLIES = [
  ['sprout', 'Make it simpler'],
  ['arrow-up', 'Make it more advanced'],
  ['search', 'Something is missing'],
  ['image', 'Not what I pictured'],
] as const

export function Overview({
  state,
  title,
  spec,
  urlOf,
  staleOf,
  reply,
  onOwn,
  onDetails,
  onBuild,
  onExit,
}: {
  state: RunState
  title: string
  spec: ProjectSpec | null
  urlOf: UrlOf
  staleOf: (name: string) => boolean
  reply: Reply
  /** Adds one of the part to My parts. */
  onOwn: (partId: string) => Promise<void>
  onDetails: () => void
  onBuild: () => void
  onExit: () => void
}) {
  const bom = useJson<Bom>(urlOf('bom_json'))
  const wiring = useJson<Wiring>(urlOf('wiring_json'))
  const assembly = urlOf('assembly_glb')
  const [view, setView] = useState<View>('Exploded')
  const [reset, setReset] = useState(0)
  const [open, setOpen] = useState<string | null>(null) // part_id of the expanded row
  const [buying, setBuying] = useState<BomLine | null>(null)
  const exploded = assembly !== null && view === 'Exploded'
  const shown = exploded ? 'assembly_glb' : 'base_stl'
  const openLine = bom?.lines.find((l) => l.part_id === open) ?? null

  const checks = state.stages.checks
  const [pillIcon, pill] = !state.done
    ? (['loader', `Updating · ${statusLine(state, spec?.title ?? null)}`] as const)
    : checks?.status === 'passed'
      ? (['check', 'Plan ready · all checks passed'] as const)
      : (['x', 'Plan ready · some checks need a look'] as const)

  return (
    <main className="overview">
      <div className="viewport">
        {urlOf('base_stl') ? (
          <Suspense fallback={<p className="empty center">Loading the 3D view…</p>}>
            <Viewer3D
              key={reset}
              base={urlOf('base_stl')}
              lid={urlOf('lid_stl')}
              assembly={exploded ? assembly : null}
              selected={exploded && openLine ? { ref: openLine.refs[0], label: openLine.name } : null}
              onSelect={(ref) => setOpen(bom?.lines.find((l) => l.refs.includes(ref))?.part_id ?? null)}
            />
          </Suspense>
        ) : (
          <p className="empty center">No case yet.</p>
        )}
        <div className="view-toolbar">
          {assembly && <Segmented label="3D view" options={VIEWS} value={view} onChange={setView} />}
          {assembly && <span className="vdivider" />}
          <button type="button" className="icon-btn sm" aria-label="Reset view" onClick={() => setReset((n) => n + 1)}>
            <Icon name="rotate-ccw" />
          </button>
        </div>
        <p className="viewport-hint mono">
          Drag to turn · Scroll to zoom{exploded && ' · Click a part to find it in the list'}
        </p>
        {staleOf(shown) && (
          <p className="stale-note viewport-stale">
            <Badge status="stale" /> Out of date: the spec changed since this was built.
          </p>
        )}
      </div>

      <header className="topbar">
        <span className="logo" />
        <b>Ditto</b>
        <span className="slash">/</span>
        <span className="project">{title}</span>
        <button type="button" className="pill" onClick={onDetails} title="Open the checks and files">
          <Icon name={pillIcon} className={pillIcon} />
          {pill}
        </button>
        <span className="spacer" />
        <button type="button" className="btn" onClick={onExit}>
          <Icon name="log-out" />
          Exit
        </button>
      </header>

      <div className="dock-scrim" />
      <PartsCard
        bom={bom}
        spec={spec}
        wiring={wiring}
        stale={staleOf('bom_json')}
        open={open}
        onOpen={(id) => setOpen(open === id ? null : id)}
        onBuy={setBuying}
        onOwn={onOwn}
      />
      {buying && <BuyPanel line={buying} onClose={() => setBuying(null)} />}
      <Dock reply={reply} onBuild={onBuild} />
    </main>
  )
}

function PartsCard({
  bom,
  spec,
  wiring,
  stale,
  open,
  onOpen,
  onBuy,
  onOwn,
}: {
  bom: Bom | null
  spec: ProjectSpec | null
  wiring: Wiring | null
  stale: boolean
  open: string | null
  onOpen: (partId: string) => void
  onBuy: (line: BomLine) => void
  onOwn: (partId: string) => Promise<void>
}) {
  const owned = bom?.lines.filter((l) => l.owned_qty > 0).length ?? 0
  return (
    <section className="parts-card" aria-label="Parts list">
      <header>
        <h2>Parts list</h2>
        <span className="mono">{bom ? `${bom.lines.length} items` : ''}</span>
      </header>
      <p className="summary">
        {bom ? (
          <>
            {usd(bom.total_usd)} to buy{owned > 0 && ` · you already have ${owned} part${owned > 1 ? 's' : ''}`}
            {bom.over_budget && <Badge status="failed" />}
          </>
        ) : (
          'No parts list yet.'
        )}
      </p>
      {stale && (
        <p className="stale-note summary">
          <Badge status="stale" /> Out of date: the spec changed since this was priced.
        </p>
      )}
      <ul className="parts">
        {bom?.lines.map((line) => {
          const parts = [spec?.mcu, ...(spec?.parts ?? [])].filter((p) => p && line.refs.includes(p.ref))
          const rows = wiring?.rows.filter((r) => line.refs.includes(r.part_ref)) ?? []
          return (
            <PartRow
              key={line.part_id}
              line={line}
              role={parts[0]?.role ?? null}
              reason={parts[0]?.reason ?? null}
              rows={rows}
              open={open === line.part_id}
              onOpen={() => onOpen(line.part_id)}
              onBuy={() => onBuy(line)}
              onOwn={() => onOwn(line.part_id)}
            />
          )
        })}
      </ul>
      <footer>
        <span className="total">
          <span className="label">Total to buy</span>
          <b>{bom ? usd(bom.total_usd) : '—'}</b>
        </span>
        <span className="spacer" />
        {/* shortcut: one store per part until T38 returns several offers */}
        <button type="button" className="btn secondary" {...soon('T38')}>
          <Icon name="shopping-cart" />
          Buy all
        </button>
      </footer>
    </section>
  )
}

function PartRow({
  line,
  role,
  reason,
  rows,
  open,
  onOpen,
  onBuy,
  onOwn,
}: {
  line: BomLine
  role: string | null
  reason: string | null
  rows: Wiring['rows']
  open: boolean
  onOpen: () => void
  onBuy: () => void
  onOwn: () => Promise<void>
}) {
  const { sending, error, send } = useSend()
  const [saved, setSaved] = useState(false)
  const power = rows.find((r) => r.pin_type === 'power')
  const buses = [...new Set(rows.map((r) => r.bus).filter((b) => b !== 'power'))]
  return (
    <li className="part-row" aria-expanded={open}>
      <button type="button" className="head" onClick={onOpen}>
        <span className="tile">
          <Icon name={partIcon(`${line.part_id} ${line.name}`)} />
        </span>
        <span className="text">
          <span className="name" title={line.name}>
            {line.name}
          </span>
          <span className="detail">
            {role ?? line.refs.join(', ')} · {line.qty}×
          </span>
        </span>
        {line.owned_qty >= line.qty ? (
          <span className="have">You have it</span>
        ) : (
          <span className="price">{usd(line.line_total_usd)}</span>
        )}
        <Icon name={open ? 'chevron-down' : 'chevron-right'} className="chevron" />
      </button>
      {open && (
        <div className="details">
          {reason && <p>{reason}</p>}
          <dl>
            {power && (
              <>
                <dt>Power</dt>
                <dd>{power.mcu_pin} from the board</dd>
              </>
            )}
            {rows.length > 0 && (
              <>
                <dt>Connects with</dt>
                <dd>
                  {rows.length} wires{buses.length > 0 && ` (${buses.join(', ').toUpperCase()})`}
                </dd>
              </>
            )}
            {line.owned_qty > 0 && (
              <>
                <dt>You have</dt>
                <dd>{line.owned_qty}</dd>
              </>
            )}
          </dl>
          <div className="actions">
            <button type="button" className="btn primary" onClick={onBuy}>
              <Icon name="shopping-cart" />
              Buy
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={sending || saved}
              onClick={async () => setSaved(await send(onOwn))}
            >
              <Icon name="check" />
              {saved ? 'Added to My parts' : 'I have one'}
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
        </div>
      )}
    </li>
  )
}

const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function BuyPanel({ line, onClose }: { line: BomLine; onClose: () => void }) {
  const store = line.vendor_url ? hostOf(line.vendor_url) : null
  return (
    <section className="buy-panel" aria-label="Where to buy">
      <header>
        <span className="title">
          <h2>Where to buy</h2>
          <span className="detail">{line.name}</span>
        </span>
        <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
          <Icon name="x" />
        </button>
      </header>
      <p className="search-status">
        {store ? '1 store found' : 'No store link yet'}
        <span className="spacer" />
        <span className="mono">{line.price_source} price</span>
      </p>
      <ul className="stores">
        {store && line.vendor_url && (
          <li>
            <a className="store" href={line.vendor_url} target="_blank" rel="noreferrer">
              <span className="logo-tile">{store[0].toUpperCase()}</span>
              <span className="text">
                <span className="name">{store}</span>
                <span className="detail">Opens the store page</span>
              </span>
              <span className="price">{usd(line.unit_price_usd)}</span>
              <Icon name="external-link" />
            </a>
          </li>
        )}
        {/* shortcut: skeleton rows stand in for more stores until T38 returns several offers */}
        {[0, 1].map((i) => (
          <li key={i} className="store skeleton" {...soon('T38')}>
            <span className="logo-tile" />
            <span className="text">
              <span className="bar" />
              <span className="bar long" />
            </span>
            <span className="bar short" />
          </li>
        ))}
      </ul>
      <p className="footnote">
        More stores: not connected yet (T38). Opens the store in a new tab; Ditto never buys anything for you.
      </p>
    </section>
  )
}

function Dock({ reply, onBuild }: { reply: Reply; onBuild: () => void }) {
  const [text, setText] = useState('')
  const submit = async (value: string) => {
    if (value.trim() && reply.ready && (await reply.send(value))) setText('')
  }
  return (
    <div className="overview-dock">
      <QuestionCard reply={reply} />
      <div className="chips">
        {QUICK_REPLIES.map(([icon, label]) => (
          // a chip is an edit, never an answer to the open question
          <button
            key={label}
            type="button"
            className="chip"
            disabled={!reply.ready || reply.question !== null}
            onClick={() => void submit(label)}
          >
            <Icon name={icon} />
            {label}
          </button>
        ))}
      </div>
      <form
        className="input-row"
        onSubmit={(e) => {
          e.preventDefault()
          void submit(text)
        }}
      >
        <span className="compact">
          <input
            aria-label={reply.question ? 'Your answer' : 'Change the design'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask a question, or tell Ditto what to change…"
          />
          {/* shortcut: an edit carries text only (EditRequest has no files) */}
          <button type="button" className="icon-btn" aria-label="Add image" {...soon(null)}>
            <Icon name="image-plus" />
          </button>
          <button type="submit" className="icon-btn send" aria-label="Send" disabled={!reply.ready || !text.trim()}>
            <Icon name="arrow-up" />
          </button>
        </span>
        <button type="button" className="btn primary tall" onClick={onBuild}>
          <Icon name="hammer" />
          Start building
        </button>
      </form>
      {reply.error && <p role="alert">{reply.error}</p>}
    </div>
  )
}

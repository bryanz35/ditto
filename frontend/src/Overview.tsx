// Project · Overview: the 3D model, the parts list and the follow-up dock (Figma 17:310, 19:527).
import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import Markdown from 'react-markdown'
import { useJson, useSend, type Reply } from './api'
import type { Bom, BomLine, BomOffer, EnclosureManifest, Event, ProjectSpec, Wiring } from './contracts'
import { Icon, Segmented } from './Icon'
import { Badge, QuestionCard, type UrlOf } from './panels'
import { chatTurns, statusLine, turnUsage, type RunState } from './state'
import { partIcon, printsOf, soon, usd } from './ui'

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
  const manifest = useJson<EnclosureManifest>(urlOf('manifest'))
  const prints = printsOf(spec, manifest, urlOf)
  const printOnly = spec !== null && !spec.mcu
  const assembly = urlOf('assembly_glb')
  const [view, setView] = useState<View>('Assembled')
  const [reset, setReset] = useState(0)
  const [open, setOpen] = useState<string | null>(null) // part_id of the expanded row
  const [partsShown, setPartsShown] = useState(true)
  const [chatShown, setChatShown] = useState(true)
  const turns = chatTurns(state)
  // from Send until Ditto answers: a reply, a question, or the end of the run
  const working = reply.pending !== null || (!state.done && !state.question && turns.at(-1)?.data.chat === 'user')
  // one part's stores, or 'all': the cheapest store for every part still to buy
  const [buying, setBuying] = useState<BomLine | 'all' | null>(null)
  const exploded = assembly !== null && view === 'Exploded'
  const shown = assembly ? 'assembly_glb' : printOnly ? 'manifest' : 'base_stl'
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
        {urlOf('base_stl') || prints.length ? (
          <Suspense fallback={<p className="empty center">Loading the 3D view…</p>}>
            <Viewer3D
              key={reset}
              base={printOnly ? null : urlOf('base_stl')}
              lid={printOnly ? null : urlOf('lid_stl')}
              prints={prints}
              assembly={assembly}
              spec={spec}
              wiring={wiring}
              exploded={exploded}
              selected={assembly && openLine ? { ref: openLine.refs[0], label: openLine.name } : null}
              leftInset={392}
              bottomInset={112}
              onSelect={(ref) => {
                setOpen(bom?.lines.find((l) => l.refs.includes(ref))?.part_id ?? null)
                setPartsShown(true) // the clicked part's row must be visible
              }}
            />
          </Suspense>
        ) : (
          <p className="empty center">No 3D model yet.</p>
        )}
        <div className="view-toolbar">
          {assembly && <Segmented label="3D view" options={VIEWS} value={view} onChange={setView} />}
          {assembly && <span className="vdivider" />}
          <button type="button" className="icon-btn sm" aria-label="Reset view" onClick={() => setReset((n) => n + 1)}>
            <Icon name="rotate-ccw" />
          </button>
        </div>
        <p className="viewport-hint mono">
          Drag to turn · Scroll to zoom{assembly && ' · Hover to pull it apart · Click a part to find it in the list'}
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
      <aside className="side-panel">
        <PartsCard
          bom={bom}
          spec={spec}
          wiring={wiring}
          stale={staleOf('bom_json')}
          shown={partsShown}
          onFold={() => setPartsShown(!partsShown)}
          open={open}
          onOpen={(id) => setOpen(open === id ? null : id)}
          onBuy={setBuying}
          onBuyAll={() => setBuying('all')}
          onOwn={onOwn}
        />
        <ChatPanel
          turns={turns}
          pending={reply.pending}
          status={working ? statusLine(state, spec?.title ?? null) : null}
          usage={working ? turnUsage(state) : null}
          shown={chatShown}
          onFold={() => setChatShown(!chatShown)}
        />
      </aside>
      {buying === 'all' && bom && <BuyAllPanel bom={bom} onClose={() => setBuying(null)} />}
      {buying && buying !== 'all' && <BuyPanel line={buying} onClose={() => setBuying(null)} />}
      <Dock reply={reply} onSend={() => setChatShown(true)} onBuild={onBuild} />
    </main>
  )
}

function PartsCard({
  bom,
  spec,
  wiring,
  stale,
  shown,
  onFold,
  open,
  onOpen,
  onBuy,
  onBuyAll,
  onOwn,
}: {
  bom: Bom | null
  spec: ProjectSpec | null
  wiring: Wiring | null
  stale: boolean
  shown: boolean
  onFold: () => void
  open: string | null
  onOpen: (partId: string) => void
  onBuy: (line: BomLine) => void
  onBuyAll: () => void
  onOwn: (partId: string) => Promise<void>
}) {
  const owned = bom?.lines.filter((l) => l.owned_qty > 0).length ?? 0
  return (
    <section className={`parts-card${shown ? '' : ' folded'}`} aria-label="Parts list">
      <button type="button" className="fold-tab" aria-expanded={shown} onClick={onFold}>
        <Icon name={shown ? 'chevron-down' : 'chevron-right'} />
        Parts list
        <span className="spacer" />
        <span className="mono">{bom ? `${bom.lines.length} items` : ''}</span>
      </button>
      {shown && (
        <>
          <p className="summary">
            {bom ? (
              <>
                {usd(bom.total_usd)} to buy{owned > 0 && ` · you already have ${owned} part${owned > 1 ? 's' : ''}`}
                {bom.over_budget && <Badge status="failed" />}
              </>
            ) : spec && !spec.mcu ? (
              'Nothing to buy: print it and you’re done.'
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
            <button type="button" className="btn secondary" disabled={!bom} onClick={onBuyAll}>
              <Icon name="shopping-cart" />
              Buy all
            </button>
          </footer>
        </>
      )}
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
  // backend/contracts/parts.py CUSTOM_PREFIX: a part the agent defined, not the hand-checked library
  const unverified = line.part_id.startsWith('x_')
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
            {role ?? line.refs.join(', ')} · {line.qty}×{unverified && ' · unverified'}
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
          {unverified && (
            <p className="stale-note">
              <Badge status="stale" /> Not in Ditto’s checked parts library: check its pins and size against the seller’s
              datasheet before you wire it.
            </p>
          )}
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

/** Every offer for the line, cheapest first; a line priced without offers keeps its library store link. */
const storesOf = (line: BomLine): BomOffer[] =>
  // `?? []`: bom.json files written before T38 have no offers
  (line.offers ?? []).length > 0
    ? line.offers
    : line.vendor_url
      ? [{ seller: hostOf(line.vendor_url), url: line.vendor_url, unit_price_usd: line.unit_price_usd ?? 0, in_stock: null }]
      : []

const stock = (o: BomOffer) => (o.in_stock === true ? 'In stock' : o.in_stock === false ? 'Out of stock' : 'Opens the store page')

function StoreRow({ name, detail, price, url }: { name: string; detail: string; price: string; url: string | null }) {
  const body = (
    <>
      <span className="logo-tile">{name[0].toUpperCase()}</span>
      <span className="text">
        <span className="name">{name}</span>
        <span className="detail">{detail}</span>
      </span>
      <span className="price">{price}</span>
      {url && <Icon name="external-link" />}
    </>
  )
  return (
    <li>
      {url ? (
        <a className="store" href={url} target="_blank" rel="noreferrer">
          {body}
        </a>
      ) : (
        <span className="store">{body}</span>
      )}
    </li>
  )
}

function Panel({ title, detail, status, onClose, children }: { title: string; detail: string; status: ReactNode; onClose: () => void; children: ReactNode }) {
  return (
    <section className="buy-panel" aria-label={title}>
      <header>
        <span className="title">
          <h2>{title}</h2>
          <span className="detail">{detail}</span>
        </span>
        <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
          <Icon name="x" />
        </button>
      </header>
      <p className="search-status">{status}</p>
      <ul className="stores">{children}</ul>
      <p className="footnote">Opens the store in a new tab; Ditto never buys anything for you.</p>
    </section>
  )
}

function BuyPanel({ line, onClose }: { line: BomLine; onClose: () => void }) {
  const stores = storesOf(line)
  return (
    <Panel
      title="Where to buy"
      detail={line.name}
      onClose={onClose}
      status={
        <>
          {stores.length === 0 ? 'No store link yet' : `${stores.length} store${stores.length > 1 ? 's' : ''} found`}
          <span className="spacer" />
          <span className="mono">{line.price_source} price</span>
        </>
      }
    >
      {stores.map((o) => (
        <StoreRow key={o.seller} name={o.seller} detail={stock(o)} price={usd(o.unit_price_usd)} url={o.url} />
      ))}
    </Panel>
  )
}

/** Buy all: the cheapest store for each part you don't have yet. */
function BuyAllPanel({ bom, onClose }: { bom: Bom; onClose: () => void }) {
  const lines = bom.lines.filter((l) => l.owned_qty < l.qty)
  return (
    <Panel
      title="Buy all"
      detail={`${lines.length} part${lines.length === 1 ? '' : 's'} to buy`}
      onClose={onClose}
      status={
        <>
          Cheapest store for each part
          <span className="spacer" />
          <span className="mono">{usd(bom.total_usd)}</span>
        </>
      }
    >
      {lines.map((l) => {
        const best = storesOf(l)[0]
        return (
          <StoreRow
            key={l.part_id}
            name={l.name}
            detail={`${l.qty - l.owned_qty}× · ${best ? best.seller : 'no store link yet'}`}
            price={usd(l.line_total_usd)}
            url={best?.url ?? null}
          />
        )
      })}
    </Panel>
  )
}

/** turns: the conversation about the design so far, newest at the bottom, then the message just sent
 * (pending) and Ditto at work on it (status). Sits under the parts list and folds to its header. */
function ChatPanel({
  turns,
  pending,
  status,
  usage,
  shown,
  onFold,
}: {
  turns: Event[]
  pending: string | null
  status: string | null
  usage: { since: number; tokens: number | null } | null
  shown: boolean
  onFold: () => void
}) {
  const log = useRef<HTMLOListElement>(null)
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight
  }, [turns.length, pending, status, shown])
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    if (!usage) return
    const id = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(id)
  }, [usage])
  if (turns.length === 0 && pending === null) return null
  return (
    <section className={`chat-panel${shown ? '' : ' folded'}`}>
      <button type="button" className="fold-tab" aria-expanded={shown} onClick={onFold}>
        <Icon name={shown ? 'chevron-down' : 'chevron-right'} />
        Conversation
        <span className="spacer" />
        <span className="mono">{turns.length + (pending === null ? 0 : 1)}</span>
      </button>
      {shown && (
        <ol ref={log} className="chat-log" aria-label="Conversation">
          {turns.map((e) =>
            e.data.chat === 'user' ? (
              <li key={e.seq} className="from-user">
                {e.message}
              </li>
            ) : (
              <li key={e.seq} className="from-agent">
                <Markdown>{e.message}</Markdown>
              </li>
            ),
          )}
          {pending !== null && <li className="from-user">{pending}</li>}
          {status && (
            <li className="working" role="status">
              <span className="sprite" aria-hidden="true" />
              {status}
              {usage && (
                <span className="mono usage">
                  {elapsed(now - usage.since)}
                  {usage.tokens !== null && ` · ${tokenCount(usage.tokens)} tokens`}
                </span>
              )}
            </li>
          )}
        </ol>
      )}
    </section>
  )
}

function Dock({ reply, onSend, onBuild }: { reply: Reply; onSend: () => void; onBuild: () => void }) {
  const [text, setText] = useState('')
  const submit = async (value: string) => {
    if (!value.trim() || !reply.ready) return
    onSend()
    if (await reply.send(value)) setText('')
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

/** 75 -> "1m 15s" */
const elapsed = (s: number) => {
  const t = Math.max(0, Math.floor(s))
  return t < 60 ? `${t}s` : `${Math.floor(t / 60)}m ${t % 60}s`
}
/** 12345 -> "12.3k" */
const tokenCount = (n: number) => (n < 1000 ? `${n}` : `${(n / 1000).toFixed(1)}k`)

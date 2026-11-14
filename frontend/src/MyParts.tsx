// My parts: the saved inventory and budget (memory API). Runs start with it, so owned parts aren't
// bought again and the budget steers the plan.
import { useState } from 'react'
import { useSend } from './api'
import type { UserContext } from './contracts'
import { Icon } from './Icon'

const EMPTY: UserContext = { budget_usd: null, owned: {}, printer: null, rejected: [] }

export function MyParts({
  memory,
  onSave,
}: {
  /** null while loading, or when the memory API isn't there */
  memory: UserContext | null
  /** Resolves with what the API stored. */
  onSave: (memory: UserContext) => Promise<UserContext>
}) {
  const [draft, setDraft] = useState<UserContext>(memory ?? EMPTY)
  const [newPart, setNewPart] = useState('')
  const [saved, setSaved] = useState(false)
  const { sending, error, send } = useSend()
  const change = (next: UserContext) => {
    setDraft(next)
    setSaved(false)
  }
  const setQty = (id: string, qty: number) => change({ ...draft, owned: { ...draft.owned, [id]: Math.max(0, qty) } })
  const parts = Object.entries(draft.owned).sort(([a], [b]) => a.localeCompare(b))

  return (
    <main className="page">
      <h1>My parts</h1>
      <p className="hint">
        Ditto plans around what you already own and prices only what's missing. Part ids come from the
        parts library, e.g. <code>bme280_breakout</code>.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault()
          // show what was stored: the API drops zero quantities
          setSaved(await send(async () => setDraft(await onSave(draft))))
        }}
      >
        <ul className="inventory" aria-label="Owned parts">
          {parts.length === 0 && <li className="empty">No parts yet. Add one below, or press "I have one" on a parts list.</li>}
          {parts.map(([id, qty]) => (
            <li key={id}>
              <span className="tile">
                <Icon name="box" />
              </span>
              <code className="name">{id}</code>
              <input
                type="number"
                min={0}
                aria-label={`How many ${id}`}
                value={qty}
                onChange={(e) => setQty(id, Number(e.target.value))}
              />
              <button type="button" className="icon-btn" aria-label={`Remove ${id}`} onClick={() => setQty(id, 0)}>
                <Icon name="x" />
              </button>
            </li>
          ))}
        </ul>
        <div className="field-row">
          <input aria-label="Part id" placeholder="Part id" value={newPart} onChange={(e) => setNewPart(e.target.value)} />
          <button
            type="button"
            className="btn secondary"
            disabled={!newPart.trim()}
            onClick={() => {
              setQty(newPart.trim(), (draft.owned[newPart.trim()] ?? 0) + 1)
              setNewPart('')
            }}
          >
            <Icon name="plus" />
            Add
          </button>
        </div>
        <label className="field-row">
          Budget (USD)
          <input
            type="number"
            min={0}
            step="any"
            value={draft.budget_usd ?? ''}
            onChange={(e) => change({ ...draft, budget_usd: e.target.value === '' ? null : Number(e.target.value) })}
          />
        </label>
        <div className="field-row">
          <button type="submit" className="btn primary" disabled={sending}>
            {sending ? 'Saving…' : 'Save'}
          </button>
          {saved && <span className="hint">Saved. Your next project uses it.</span>}
        </div>
        {error && <p role="alert">{error}</p>}
      </form>
    </main>
  )
}

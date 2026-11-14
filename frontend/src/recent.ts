// Recent projects for the sidebar, kept in this browser.
// shortcut: browser storage only, so another browser sees no history; upgrade to T39's GET /runs.

export const LEVELS = ['Beginner', 'Intermediate', 'Expert'] as const
export type Level = (typeof LEVELS)[number]

export interface Recent {
  id: string
  title: string
  prompt: string
  files: { name: string; size: number }[]
  level: Level | null
  status: string
  /** ms since epoch of the last change */
  at: number
}

const KEY = 'ditto.recent'
const MAX = 8

export function loadRecent(): Recent[] {
  try {
    const list: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(list) ? (list as Recent[]) : []
  } catch {
    return [] // private window or storage switched off
  }
}

/** Merges the change into the project's entry. A new project goes first; a known one keeps its place,
 * so the list stays in the order of `at` (when each was started). */
export function remember(list: Recent[], change: Partial<Recent> & { id: string }): Recent[] {
  const old = list.find((r) => r.id === change.id)
  const entry: Recent = { title: 'New project', prompt: '', files: [], level: null, status: '', at: Date.now(), ...old, ...change }
  const next = (old ? list.map((r) => (r === old ? entry : r)) : [entry, ...list]).slice(0, MAX)
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage off: the list lives until the tab closes
  }
  return next
}

/** "just now", "5m ago", "2h ago", then a date like "Nov 9". */
export function ago(at: number, now = Date.now()): string {
  const minutes = Math.floor((now - at) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)}h ago`
  return new Date(at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

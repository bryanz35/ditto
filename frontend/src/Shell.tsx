// The left sidebar of the Start and Planning screens (Figma "Sidebar"), around the page.
import type { ReactNode } from 'react'
import { Icon } from './Icon'
import { ago, type Recent } from './recent'
import { projectIcon, soon } from './ui'

export type Page = 'home' | 'parts'

export function Shell({
  page,
  runId,
  recent,
  kit,
  onPage,
  onOpen,
  children,
}: {
  page: Page
  runId: string | null
  recent: Recent[]
  /** Parts in the saved inventory, null until the memory has loaded. */
  kit: number | null
  onPage: (page: Page) => void
  /** Opens a recent project, or the Start screen for null. */
  onOpen: (runId: string | null) => void
  children: ReactNode
}) {
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Projects">
        <div className="brand">
          <span className="logo" />
          <b>Ditto</b>
          {/* shortcut: no collapsed sidebar in the design yet */}
          <button type="button" className="icon-btn" aria-label="Collapse sidebar" {...soon(null)}>
            <Icon name="panel-left" />
          </button>
        </div>
        <button type="button" className="btn primary wide" onClick={() => onOpen(null)}>
          <Icon name="plus" />
          New project
        </button>
        <span className="gap8" />
        <button
          type="button"
          className="nav-item"
          aria-current={page === 'home' && !runId ? 'page' : undefined}
          onClick={() => onOpen(null)}
        >
          <Icon name="house" />
          <span>Home</span>
        </button>
        <button
          type="button"
          className="nav-item"
          aria-current={page === 'parts' ? 'page' : undefined}
          onClick={() => onPage('parts')}
        >
          <Icon name="box" />
          <span>My parts</span>
          {kit !== null && <span className="count">{kit}</span>}
        </button>
        {/* shortcut: Examples has no screen in the design yet */}
        <button type="button" className="nav-item" {...soon(null)}>
          <Icon name="book-open" />
          <span>Examples</span>
        </button>
        {recent.length > 0 && <h2 className="section-title">Recent</h2>}
        {recent.map((r) => (
          <button
            key={r.id}
            type="button"
            className="project-row"
            aria-current={r.id === runId && page === 'home' ? 'page' : undefined}
            onClick={() => onOpen(r.id)}
          >
            <span className="tile">
              <Icon name={projectIcon(r.title)} />
            </span>
            <span className="text">
              <span className="name">{r.title}</span>
              <span className="detail">
                {r.status} · {ago(r.at)}
              </span>
            </span>
          </button>
        ))}
        <span className="spacer" />
        <hr />
        <div className="account">
          {/* shortcut: no user name in the API; T37 adds one */}
          <span className="avatar" {...soon('T37')}>
            ME
          </span>
          <span className="who">
            <span className="name" {...soon('T37')}>
              Your kit
            </span>
            <span className="detail">{kit === null ? 'Parts you own' : `${kit} part${kit === 1 ? '' : 's'} in your kit`}</span>
          </span>
          <button type="button" className="icon-btn" aria-label="Account" {...soon(null)}>
            <Icon name="ellipsis" />
          </button>
        </div>
      </nav>
      <div className="shell-main">{children}</div>
    </div>
  )
}

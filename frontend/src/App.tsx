import { useEffect, useState } from 'react'
import { api, ApiError, type PrincipalOut } from './api/client.ts'
import Login from './views/Login.tsx'
import Workspace from './views/Workspace.tsx'
import Admin from './views/Admin.tsx'
import Registry from './views/Registry.tsx'
import Jobs from './views/Jobs.tsx'
import Governance from './views/Governance.tsx'
import Ops from './views/Ops.tsx'
import Exports from './views/Exports.tsx'

type Tab =
  | 'workspace'
  | 'registry'
  | 'jobs'
  | 'exports'
  | 'governance'
  | 'ops'
  | 'admin'

export default function App() {
  const [principal, setPrincipal] = useState<PrincipalOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('workspace')

  useEffect(() => {
    let active = true
    api
      .me()
      .then((p) => {
        if (active) setPrincipal(p)
      })
      .catch((err: unknown) => {
        // 401 simply means not logged in; anything else we also treat as logged-out.
        if (!(err instanceof ApiError)) {
          console.error('Failed to load session', err)
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  async function handleLogout() {
    try {
      await api.logout()
    } catch (err) {
      console.error('Logout failed', err)
    } finally {
      setPrincipal(null)
      setTab('workspace')
    }
  }

  if (loading) {
    return (
      <div className="app-shell">
        <p className="muted">Loading…</p>
      </div>
    )
  }

  if (!principal) {
    return (
      <div className="app-shell">
        <Login onLoggedIn={setPrincipal} />
      </div>
    )
  }

  const isAdmin = principal.roles.includes('admin')
  const isCompliance = principal.roles.includes('compliance')
  const canGovern = isAdmin || isCompliance

  // Tabs available to this principal, in display order. Role-gated tabs are
  // omitted entirely (not just disabled) when the role is absent.
  const tabs: { id: Tab; label: string; visible: boolean }[] = [
    { id: 'workspace', label: 'Workspace', visible: true },
    { id: 'registry', label: 'Registry', visible: true },
    { id: 'jobs', label: 'Jobs', visible: true },
    { id: 'exports', label: 'Exports', visible: true },
    { id: 'governance', label: 'Governance', visible: canGovern },
    { id: 'ops', label: 'Ops', visible: isAdmin },
    { id: 'admin', label: 'Admin', visible: true },
  ]

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Gadziriro</span>
          <span className="brand-sub">AI Workspace</span>
        </div>
        <nav className="tabs" aria-label="Main navigation">
          {tabs
            .filter((t) => t.visible)
            .map((t) => (
              <button
                key={t.id}
                type="button"
                className={tab === t.id ? 'tab active' : 'tab'}
                aria-current={tab === t.id ? 'page' : undefined}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
        </nav>
        <div className="user-area">
          <span className="user-name">
            {principal.username}
            {isAdmin ? <span className="role-pill">admin</span> : null}
          </span>
          <button type="button" className="btn-secondary" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      <main className="content">
        {tab === 'workspace' ? (
          <Workspace />
        ) : tab === 'registry' ? (
          <Registry />
        ) : tab === 'jobs' ? (
          <Jobs />
        ) : tab === 'exports' ? (
          <Exports isAdmin={isAdmin} />
        ) : tab === 'governance' && canGovern ? (
          <Governance />
        ) : tab === 'ops' && isAdmin ? (
          <Ops />
        ) : tab === 'admin' ? (
          <Admin />
        ) : (
          <Workspace />
        )}
      </main>
    </div>
  )
}

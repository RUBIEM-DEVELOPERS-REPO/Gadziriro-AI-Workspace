import { useEffect, useState } from 'react'
import { api, ApiError, type PrincipalOut } from './api/client.ts'
import Login from './views/Login.tsx'
import Workspace from './views/Workspace.tsx'
import Admin from './views/Admin.tsx'

type Tab = 'workspace' | 'admin'

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

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Gadziriro</span>
          <span className="brand-sub">AI Workspace</span>
        </div>
        <nav className="tabs" aria-label="Main navigation">
          <button
            type="button"
            className={tab === 'workspace' ? 'tab active' : 'tab'}
            aria-current={tab === 'workspace' ? 'page' : undefined}
            onClick={() => setTab('workspace')}
          >
            Workspace
          </button>
          <button
            type="button"
            className={tab === 'admin' ? 'tab active' : 'tab'}
            aria-current={tab === 'admin' ? 'page' : undefined}
            onClick={() => setTab('admin')}
          >
            Admin
          </button>
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
        {tab === 'workspace' ? <Workspace /> : <Admin />}
      </main>
    </div>
  )
}

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { api, ApiError, type PrincipalOut } from './api/client.ts'
import Login from './views/Login.tsx'
import Workspace from './views/Workspace.tsx'
import Admin from './views/Admin.tsx'
import Registry from './views/Registry.tsx'
import Jobs from './views/Jobs.tsx'
import Governance from './views/Governance.tsx'
import Ops from './views/Ops.tsx'
import Exports from './views/Exports.tsx'
import ModelStudio from './views/ModelStudio.tsx'
import Evaluate from './views/Evaluate.tsx'
import WeightTools from './views/WeightTools.tsx'
import ModelCard from './views/ModelCard.tsx'
import Compliance from './views/Compliance.tsx'
import Updates from './views/Updates.tsx'
import Enterprise from './views/Enterprise.tsx'
import Safety from './views/Safety.tsx'
import Plugins from './views/Plugins.tsx'
import Evidence from './views/Evidence.tsx'
import { LANGS, useT, type Lang } from './i18n/index.ts'

type Tab =
  | 'workspace'
  | 'registry'
  | 'modelstudio'
  | 'evaluate'
  | 'weighttools'
  | 'modelcard'
  | 'jobs'
  | 'exports'
  | 'governance'
  | 'compliance'
  | 'safety'
  | 'enterprise'
  | 'updates'
  | 'plugins'
  | 'evidence'
  | 'ops'
  | 'admin'

export default function App() {
  const { t, lang, setLang } = useT()
  const [principal, setPrincipal] = useState<PrincipalOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('workspace')
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({})

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
        <p className="muted" role="status">{t('common.loading')}</p>
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
  const isDataScientist = principal.roles.includes('data_scientist')
  const canGovern = isAdmin || isCompliance
  const canWeightTools = isAdmin || isDataScientist
  const canSafety = isAdmin || isDataScientist

  // Tabs available to this principal, in display order. Role-gated tabs are
  // omitted entirely (not just disabled) when the role is absent.
  const tabs: { id: Tab; label: string; visible: boolean }[] = [
    { id: 'workspace', label: 'Workspace', visible: true },
    { id: 'registry', label: 'Registry', visible: true },
    { id: 'modelstudio', label: 'Model Studio', visible: true },
    { id: 'evaluate', label: 'Evaluate', visible: true },
    { id: 'weighttools', label: 'Weight Tools', visible: canWeightTools },
    { id: 'modelcard', label: 'Model Card', visible: true },
    { id: 'jobs', label: 'Jobs', visible: true },
    { id: 'exports', label: 'Exports', visible: true },
    { id: 'governance', label: 'Governance', visible: canGovern },
    { id: 'compliance', label: 'Compliance', visible: canGovern },
    { id: 'safety', label: 'Safety', visible: canSafety },
    { id: 'enterprise', label: 'Enterprise', visible: isAdmin },
    { id: 'updates', label: 'Updates', visible: isAdmin },
    { id: 'plugins', label: 'Plugins', visible: isAdmin },
    { id: 'evidence', label: 'Evidence', visible: isAdmin },
    { id: 'ops', label: 'Ops', visible: isAdmin },
    { id: 'admin', label: 'Admin', visible: true },
  ]

  const visibleTabs = tabs.filter((t) => t.visible)

  // WAI-ARIA tabs pattern: arrow keys / Home / End move focus and selection.
  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = -1
    if (e.key === 'ArrowRight') next = (index + 1) % visibleTabs.length
    else if (e.key === 'ArrowLeft')
      next = (index - 1 + visibleTabs.length) % visibleTabs.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = visibleTabs.length - 1
    if (next < 0) return
    e.preventDefault()
    const id = visibleTabs[next].id
    setTab(id)
    tabRefs.current[id]?.focus()
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {t('nav.skip')}
      </a>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Gadziriro</span>
          <span className="brand-sub">AI Workspace</span>
        </div>
        <div className="tabs" role="tablist" aria-label={t('nav.aria')}>
          {visibleTabs.map((tb, i) => (
            <button
              key={tb.id}
              id={`tab-${tb.id}`}
              ref={(el) => {
                tabRefs.current[tb.id] = el
              }}
              type="button"
              role="tab"
              className={tab === tb.id ? 'tab active' : 'tab'}
              aria-selected={tab === tb.id}
              aria-controls="main-content"
              tabIndex={tab === tb.id ? 0 : -1}
              onClick={() => setTab(tb.id)}
              onKeyDown={(e) => onTabKeyDown(e, i)}
            >
              {t(`nav.${tb.id}`, tb.label)}
            </button>
          ))}
        </div>
        <div className="user-area">
          <span className="user-name">
            {principal.username}
            {isAdmin ? <span className="role-pill">admin</span> : null}
          </span>
          <label htmlFor="lang-select" className="lang-label">
            {t('common.language')}
          </label>
          <select
            id="lang-select"
            value={lang}
            onChange={(e) => setLang(e.target.value as Lang)}
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code} lang={l.code}>
                {l.label}
              </option>
            ))}
          </select>
          <button type="button" className="btn-secondary" onClick={handleLogout}>
            {t('common.logout')}
          </button>
        </div>
      </header>

      <main
        className="content"
        id="main-content"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        tabIndex={-1}
      >
        {tab === 'workspace' ? (
          <Workspace />
        ) : tab === 'registry' ? (
          <Registry />
        ) : tab === 'modelstudio' ? (
          <ModelStudio />
        ) : tab === 'evaluate' ? (
          <Evaluate />
        ) : tab === 'weighttools' && canWeightTools ? (
          <WeightTools />
        ) : tab === 'modelcard' ? (
          <ModelCard />
        ) : tab === 'jobs' ? (
          <Jobs />
        ) : tab === 'exports' ? (
          <Exports isAdmin={isAdmin} />
        ) : tab === 'governance' && canGovern ? (
          <Governance />
        ) : tab === 'compliance' && canGovern ? (
          <Compliance />
        ) : tab === 'safety' && canSafety ? (
          <Safety />
        ) : tab === 'enterprise' && isAdmin ? (
          <Enterprise />
        ) : tab === 'updates' && isAdmin ? (
          <Updates />
        ) : tab === 'plugins' && isAdmin ? (
          <Plugins />
        ) : tab === 'evidence' && isAdmin ? (
          <Evidence />
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

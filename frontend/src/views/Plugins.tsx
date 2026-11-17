import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type PluginInfo } from '../api/client.ts'
import { useT } from '../i18n/index.ts'

// Admin: signed plug-in management (install / enable / disable).
export default function Plugins() {
  const { t } = useT()
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [bundle, setBundle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const list = await api.listPlugins()
      setPlugins(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load plug-ins.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleInstall(e: FormEvent) {
    e.preventDefault()
    if (!bundle.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await api.installPlugin(bundle.trim())
      setMessage('Plug-in installed.')
      setBundle('')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Install failed.')
    } finally {
      setBusy(false)
    }
  }

  async function toggle(p: PluginInfo) {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      if (p.enabled) await api.disablePlugin(p.name)
      else await api.enablePlugin(p.name)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>{t('plugins.title')}</h2>
        <form className="create-form" onSubmit={handleInstall}>
          <div className="field">
            <label htmlFor="plugin-bundle">Signed plug-in bundle (base64)</label>
            <textarea
              id="plugin-bundle"
              className="cell-editor"
              rows={5}
              value={bundle}
              onChange={(e) => setBundle(e.target.value)}
              spellCheck={false}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={busy || !bundle.trim()}>
            {t('common.install')}
          </button>
        </form>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        {message ? <p role="status">{message}</p> : null}

        {plugins.length === 0 ? (
          <p className="muted">No plug-ins installed.</p>
        ) : (
          <table>
            <caption className="sr-only">{t('plugins.title')}</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Kind</th>
                <th scope="col">Version</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {plugins.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>{p.kind ?? '—'}</td>
                  <td>{p.version ?? '—'}</td>
                  <td>
                    <span className={p.enabled ? 'badge badge-ok' : 'badge'}>
                      {p.enabled ? 'enabled' : 'disabled'}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busy}
                      onClick={() => void toggle(p)}
                    >
                      {p.enabled ? t('common.disable') : t('common.enable')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

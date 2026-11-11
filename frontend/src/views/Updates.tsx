import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type UpdateHistoryEntry } from '../api/client.ts'

// Signed offline updates (FR-41). The bundle is pasted as base64 and verified
// server-side; nothing is fetched from the internet.
export default function Updates() {
  const [bundle, setBundle] = useState('')
  const [history, setHistory] = useState<UpdateHistoryEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const list = await api.updateHistory()
      setHistory(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load history.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleApply(e: FormEvent) {
    e.preventDefault()
    if (!bundle.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const out = await api.updateApply(bundle.trim())
      setMessage(`Update applied${out?.version ? `: version ${out.version}` : ''}.`)
      setBundle('')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Update failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRollback() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const out = await api.updateRollback()
      setMessage(
        `Rolled back${out?.version ? ` to version ${out.version}` : ''}.`,
      )
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Rollback failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Signed updates</h2>
        <p className="muted">
          Apply an offline, signed update bundle. Signatures are verified before
          anything changes.{' '}
          <span className="badge badge-ok">no internet needed</span>
        </p>
        <form className="create-form" onSubmit={handleApply}>
          <div className="field">
            <label htmlFor="upd-bundle">Update bundle (base64)</label>
            <textarea
              id="upd-bundle"
              className="cell-editor"
              rows={5}
              value={bundle}
              onChange={(e) => setBundle(e.target.value)}
              spellCheck={false}
            />
          </div>
          <div className="button-row">
            <button
              type="submit"
              className="btn-primary"
              disabled={busy || !bundle.trim()}
            >
              {busy ? 'Working…' : 'Apply update'}
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={() => void handleRollback()}
              disabled={busy}
            >
              Roll back last update
            </button>
          </div>
        </form>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        {message ? (
          <p className="muted" role="status" aria-live="polite">
            {message}
          </p>
        ) : null}
      </div>

      <div className="panel">
        <h2>Update history</h2>
        {history.length === 0 ? (
          <p className="muted">No updates applied yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <caption className="sr-only">Update history</caption>
              <thead>
                <tr>
                  <th scope="col">Action</th>
                  <th scope="col">Version</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={i}>
                    <td>{h.action}</td>
                    <td>{h.version ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

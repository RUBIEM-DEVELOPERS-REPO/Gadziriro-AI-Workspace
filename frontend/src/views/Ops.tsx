import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type Backup } from '../api/client.ts'

export default function Ops() {
  const [backups, setBackups] = useState<Backup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  // Per-backup test-restore outcome, keyed by backup id.
  const [restoreResults, setRestoreResults] = useState<Record<string, boolean>>({})
  const [restoringId, setRestoringId] = useState<string | null>(null)

  const [metrics, setMetrics] = useState<string>('')
  const [metricsError, setMetricsError] = useState<string | null>(null)
  const [metricsLoading, setMetricsLoading] = useState(true)

  const refreshBackups = useCallback(async () => {
    setError(null)
    try {
      const list = await api.listBackups()
      setBackups(list ?? [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load backups.')
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshMetrics = useCallback(async () => {
    setMetricsError(null)
    setMetricsLoading(true)
    try {
      const text = await api.metrics()
      setMetrics(text)
    } catch (err) {
      setMetricsError(
        err instanceof ApiError ? err.message : 'Failed to load metrics.',
      )
    } finally {
      setMetricsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshBackups()
    void refreshMetrics()
  }, [refreshBackups, refreshMetrics])

  async function handleCreate() {
    setCreating(true)
    setError(null)
    try {
      await api.createBackup()
      await refreshBackups()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create backup.')
    } finally {
      setCreating(false)
    }
  }

  async function handleTestRestore(id: string) {
    setRestoringId(id)
    setError(null)
    try {
      const out = await api.testRestore(id)
      setRestoreResults((prev) => ({ ...prev, [id]: out.ok }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Test-restore failed.')
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Backups &amp; disaster recovery</h2>
        <p className="muted">
          Trigger a backup and verify recoverability with a test-restore (FR-28/39).
        </p>
        <button
          type="button"
          className="btn-primary"
          onClick={handleCreate}
          disabled={creating}
        >
          {creating ? 'Creating…' : 'Create backup'}
        </button>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="muted">Loading backups…</p>
        ) : backups.length === 0 ? (
          <p className="muted">No backups yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Backup id</th>
                <th>Created</th>
                <th>Status</th>
                <th>Test-restore</th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => {
                const result = restoreResults[b.id]
                return (
                  <tr key={b.id}>
                    <td>{b.id}</td>
                    <td className="muted">{b.created_at || '—'}</td>
                    <td>{b.status || '—'}</td>
                    <td>
                      <div className="button-row">
                        <button
                          type="button"
                          className="btn-secondary btn-small"
                          onClick={() => handleTestRestore(b.id)}
                          disabled={restoringId === b.id}
                        >
                          {restoringId === b.id ? 'Testing…' : 'Test-restore'}
                        </button>
                        {result === undefined ? null : result ? (
                          <span className="badge badge-ok">ok</span>
                        ) : (
                          <span className="badge badge-broken">fail</span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Metrics</h2>
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={() => void refreshMetrics()}
            disabled={metricsLoading}
          >
            {metricsLoading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
        {metricsError ? (
          <p className="error" role="alert">
            {metricsError}
          </p>
        ) : metricsLoading && !metrics ? (
          <p className="muted">Loading metrics…</p>
        ) : (
          <pre className="cell-output metrics-output">
            {metrics || '(no metrics)'}
          </pre>
        )}
      </div>
    </section>
  )
}

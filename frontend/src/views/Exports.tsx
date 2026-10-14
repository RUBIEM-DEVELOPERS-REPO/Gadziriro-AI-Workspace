import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type ExportRequest } from '../api/client.ts'

interface Props {
  isAdmin: boolean
}

export default function Exports({ isAdmin }: Props) {
  const [requests, setRequests] = useState<ExportRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [resourceRef, setResourceRef] = useState('')
  const [sensitivity, setSensitivity] = useState('internal')
  const [submitting, setSubmitting] = useState(false)
  const [actingId, setActingId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const list = await api.listExports()
      setRequests(list ?? [])
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Failed to load export requests.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleRequest(e: React.FormEvent) {
    e.preventDefault()
    if (!resourceRef.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await api.requestExport(resourceRef.trim(), sensitivity)
      setResourceRef('')
      await refresh()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Failed to request export.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDecision(id: string, approve: boolean) {
    setActingId(id)
    setError(null)
    try {
      if (approve) {
        await api.approveExport(id)
      } else {
        await api.denyExport(id)
      }
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Decision failed.')
    } finally {
      setActingId(null)
    }
  }

  const isPending = (s: string | undefined) =>
    (s ?? '').toLowerCase() === 'pending'
  const pending = requests.filter((r) => isPending(r.status))

  return (
    <section className="admin">
      <div className="panel">
        <h2>Request an export</h2>
        <p className="muted">
          Data leaving the sealed workspace requires review and approval (FR-21).
        </p>
        <form className="create-form" onSubmit={handleRequest}>
          <div className="field">
            <label htmlFor="export-ref">Resource ref</label>
            <input
              id="export-ref"
              type="text"
              value={resourceRef}
              onChange={(e) => setResourceRef(e.target.value)}
              placeholder="e.g. model:classifier:v3"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="export-sensitivity">Sensitivity</label>
            <select
              id="export-sensitivity"
              value={sensitivity}
              onChange={(e) => setSensitivity(e.target.value)}
            >
              <option value="public">public</option>
              <option value="internal">internal</option>
              <option value="confidential">confidential</option>
              <option value="restricted">restricted</option>
            </select>
          </div>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Requesting…' : 'Request export'}
          </button>
        </form>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <div className="panel">
        <h2>My export requests</h2>
        {loading ? (
          <p className="muted">Loading requests…</p>
        ) : requests.length === 0 ? (
          <p className="muted">No export requests yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Id</th>
                <th>Resource</th>
                <th>Sensitivity</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.resource_ref || '—'}</td>
                  <td>{r.sensitivity || '—'}</td>
                  <td>
                    <span
                      className={
                        isPending(r.status)
                          ? 'badge badge-egress'
                          : 'badge badge-ok'
                      }
                    >
                      {r.status || 'unknown'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {isAdmin ? (
        <div className="panel">
          <h2>Pending review</h2>
          {loading ? (
            <p className="muted">Loading…</p>
          ) : pending.length === 0 ? (
            <p className="muted">No requests awaiting review.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Resource</th>
                  <th>Sensitivity</th>
                  <th>Requested by</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>{r.resource_ref || '—'}</td>
                    <td>{r.sensitivity || '—'}</td>
                    <td>{r.requested_by || '—'}</td>
                    <td>
                      <div className="button-row">
                        <button
                          type="button"
                          className="btn-primary btn-small"
                          onClick={() => handleDecision(r.id, true)}
                          disabled={actingId === r.id}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="btn-danger"
                          onClick={() => handleDecision(r.id, false)}
                          disabled={actingId === r.id}
                        >
                          Deny
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </section>
  )
}

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  api,
  ApiError,
  type Dpia,
  type RopaActivity,
} from '../api/client.ts'

const DPIA_STATUSES = ['draft', 'in_review', 'approved', 'rejected']

function cell(v: unknown): string {
  if (v === undefined || v === null || v === '') return '—'
  if (Array.isArray(v)) return v.map(String).join(', ')
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ROPA export (GDPR Art. 30) and DPIA register. Both are metadata only and stay
// inside the sealed workspace.
export default function ComplianceRecords() {
  const [ropa, setRopa] = useState<RopaActivity[] | null>(null)
  const [ropaBusy, setRopaBusy] = useState(false)
  const [ropaError, setRopaError] = useState<string | null>(null)

  const [dpias, setDpias] = useState<Dpia[]>([])
  const [title, setTitle] = useState('')
  const [scope, setScope] = useState('')
  const [assessor, setAssessor] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const list = await api.listDpias()
      setDpias(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load DPIAs.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function loadRopa() {
    setRopaBusy(true)
    setRopaError(null)
    try {
      const out = await api.complianceRopa()
      setRopa(Array.isArray(out) ? out : [])
    } catch (err) {
      setRopaError(err instanceof ApiError ? err.message : 'Failed to load ROPA.')
    } finally {
      setRopaBusy(false)
    }
  }

  function downloadRopa() {
    if (!ropa) return
    const blob = new Blob([JSON.stringify(ropa, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'ropa.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await api.createDpia(title.trim(), scope.trim(), assessor.trim())
      setTitle('')
      setScope('')
      setAssessor('')
      setMessage('DPIA created.')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create DPIA.')
    } finally {
      setBusy(false)
    }
  }

  async function handleStatus(id: string, status: string) {
    setError(null)
    setMessage(null)
    try {
      await api.setDpiaStatus(id, status)
      setMessage(`DPIA ${id} set to ${status}.`)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update status.')
    }
  }

  const ropaCols = ropa && ropa.length ? Object.keys(ropa[0]) : []

  return (
    <>
      <div className="panel">
        <h2>Record of processing (ROPA)</h2>
        <p className="muted">
          Export the register of processing activities (FR-46).{' '}
          <span className="badge badge-ok">metadata only</span>
        </p>
        <div className="button-row">
          <button
            type="button"
            className="btn-primary"
            onClick={() => void loadRopa()}
            disabled={ropaBusy}
          >
            {ropaBusy ? 'Loading…' : 'Load ROPA'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={downloadRopa}
            disabled={!ropa || ropa.length === 0}
          >
            Download JSON
          </button>
        </div>
        {ropaError ? (
          <p className="error" role="alert">
            {ropaError}
          </p>
        ) : null}
        {ropa && ropa.length === 0 ? (
          <p className="muted" role="status">
            No processing activities recorded.
          </p>
        ) : null}
        {ropa && ropa.length > 0 ? (
          <div className="table-scroll">
            <table className="data-table">
              <caption className="sr-only">Processing activities</caption>
              <thead>
                <tr>
                  {ropaCols.map((c) => (
                    <th key={c} scope="col">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ropa.map((r, i) => (
                  <tr key={i}>
                    {ropaCols.map((c) => (
                      <td key={c}>{cell(r[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      <div className="panel">
        <h2>Data protection impact assessments (DPIA)</h2>
        <form className="create-form" onSubmit={handleCreate}>
          <div className="field">
            <label htmlFor="dpia-title">Title</label>
            <input
              id="dpia-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="dpia-scope">Scope</label>
            <input
              id="dpia-scope"
              type="text"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="dpia-assessor">Assessor</label>
            <input
              id="dpia-assessor"
              type="text"
              value={assessor}
              onChange={(e) => setAssessor(e.target.value)}
            />
          </div>
          <div className="button-row">
            <button
              type="submit"
              className="btn-primary"
              disabled={busy || !title.trim()}
            >
              {busy ? 'Creating…' : 'Create DPIA'}
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
        {dpias.length === 0 ? (
          <p className="muted">No DPIAs recorded.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <caption className="sr-only">DPIA register</caption>
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Scope</th>
                  <th scope="col">Assessor</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {dpias.map((d) => (
                  <tr key={d.id}>
                    <td>{d.title || d.id}</td>
                    <td>{cell(d.scope)}</td>
                    <td>{cell(d.assessor)}</td>
                    <td>
                      <label className="sr-only" htmlFor={`dpia-status-${d.id}`}>
                        Status for {d.title || d.id}
                      </label>
                      <select
                        id={`dpia-status-${d.id}`}
                        value={d.status ?? 'draft'}
                        onChange={(e) => void handleStatus(d.id, e.target.value)}
                      >
                        {(DPIA_STATUSES.includes(d.status ?? 'draft')
                          ? DPIA_STATUSES
                          : [...DPIA_STATUSES, d.status ?? 'draft']
                        ).map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

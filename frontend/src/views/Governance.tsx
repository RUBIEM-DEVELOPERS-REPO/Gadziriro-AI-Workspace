import { useState } from 'react'
import { api, ApiError, type ModelVersion } from '../api/client.ts'

export default function Governance() {
  const [subject, setSubject] = useState('')
  const [results, setResults] = useState<ModelVersion[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [erasing, setErasing] = useState(false)
  const [erased, setErased] = useState<string[] | null>(null)

  const [retentionBusy, setRetentionBusy] = useState(false)
  const [retentionMsg, setRetentionMsg] = useState<string | null>(null)
  const [retentionDataset, setRetentionDataset] = useState('')
  const [retentionDays, setRetentionDays] = useState('30')

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!subject.trim()) return
    setSearching(true)
    setError(null)
    setErased(null)
    try {
      const models = await api.dsar(subject.trim())
      setResults(models ?? [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'DSAR lookup failed.')
      setResults(null)
    } finally {
      setSearching(false)
    }
  }

  async function handleErase() {
    if (!subject.trim()) return
    setErasing(true)
    setError(null)
    try {
      const out = await api.dsarErase(subject.trim())
      setErased(out.flagged ?? [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Flag for erasure failed.')
    } finally {
      setErasing(false)
    }
  }

  async function handleRetention() {
    setRetentionBusy(true)
    setRetentionMsg(null)
    setError(null)
    try {
      const policies = retentionDataset.trim()
        ? [
            {
              dataset_name: retentionDataset.trim(),
              retain_days: Number(retentionDays) || 0,
            },
          ]
        : []
      const out = await api.retentionRun(policies)
      setRetentionMsg(`Retention run complete — ${out.deleted} version(s) deleted.`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Retention run failed.')
    } finally {
      setRetentionBusy(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Data subject access request (DSAR)</h2>
        <p className="muted">
          Enter a subject id to find every model built from their data (FR-22/23).
        </p>
        <form className="create-form" onSubmit={handleSearch}>
          <div className="field">
            <label htmlFor="dsar-subject">Subject id</label>
            <input
              id="dsar-subject"
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. subject-42"
              required
            />
          </div>
          <div className="button-row">
            <button type="submit" className="btn-primary" disabled={searching}>
              {searching ? 'Searching…' : 'Find models'}
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={handleErase}
              disabled={erasing || !subject.trim()}
            >
              {erasing ? 'Flagging…' : 'Flag for erasure'}
            </button>
          </div>
        </form>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {erased ? (
          <p className="muted">
            Flagged for erasure:{' '}
            {erased.length ? erased.join(', ') : '(none)'}
          </p>
        ) : null}

        {results ? (
          results.length === 0 ? (
            <p className="muted">No models were built from this subject's data.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Version</th>
                  <th>Flagged</th>
                </tr>
              </thead>
              <tbody>
                {results.map((m) => (
                  <tr key={`${m.name}:${m.version}`}>
                    <td>{m.name}</td>
                    <td>{m.version}</td>
                    <td>
                      {m.flagged ? (
                        <span className="badge badge-broken">flagged</span>
                      ) : (
                        <span className="badge badge-ok">clear</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : null}
      </div>

      <div className="panel">
        <h2>Retention</h2>
        <p className="muted">
          Run scheduled deletion (FR-22). Leave the dataset blank to run with no
          policies (a dry no-op), or scope it to one dataset and a retention window.
        </p>
        <div className="button-row">
          <label>
            Dataset
            <input
              type="text"
              value={retentionDataset}
              onChange={(e) => setRetentionDataset(e.target.value)}
              placeholder="(optional) dataset name"
            />
          </label>
          <label>
            Retain days
            <input
              type="number"
              min={0}
              value={retentionDays}
              onChange={(e) => setRetentionDays(e.target.value)}
            />
          </label>
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={handleRetention}
          disabled={retentionBusy}
        >
          {retentionBusy ? 'Running…' : 'Run now'}
        </button>
        {retentionMsg ? <p className="muted">{retentionMsg}</p> : null}
      </div>
    </section>
  )
}

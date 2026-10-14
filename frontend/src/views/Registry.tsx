import { Fragment, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  type DatasetVersion,
  type ModelVersion,
} from '../api/client.ts'

// Maps a sensitivity label to a chip class. Unknown labels fall back to neutral.
function sensitivityClass(sensitivity: string | undefined): string {
  switch ((sensitivity ?? '').toLowerCase()) {
    case 'public':
      return 'chip chip-public'
    case 'internal':
      return 'chip chip-internal'
    case 'confidential':
      return 'chip chip-confidential'
    case 'restricted':
    case 'secret':
      return 'chip chip-restricted'
    default:
      return 'chip chip-neutral'
  }
}

function SensitivityChip({ sensitivity }: { sensitivity: string | undefined }) {
  return (
    <span className={sensitivityClass(sensitivity)}>
      {sensitivity || 'unknown'}
    </span>
  )
}

export default function Registry() {
  const [datasets, setDatasets] = useState<DatasetVersion[]>([])
  const [models, setModels] = useState<ModelVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    async function load() {
      setError(null)
      try {
        const [ds, ms] = await Promise.all([api.listDatasets(), api.listModels()])
        if (!active) return
        setDatasets(ds ?? [])
        setModels(ms ?? [])
      } catch (err) {
        if (active) {
          setError(
            err instanceof ApiError ? err.message : 'Failed to load the registry.',
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  return (
    <section className="admin">
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="panel">
        <h2>Datasets</h2>
        {loading ? (
          <p className="muted">Loading datasets…</p>
        ) : datasets.length === 0 ? (
          <p className="muted">No datasets registered.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Sensitivity</th>
                <th>Source</th>
                <th>Subjects</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr key={`${d.name}:${d.version}`}>
                  <td>{d.name}</td>
                  <td>{d.version}</td>
                  <td>
                    <SensitivityChip sensitivity={d.sensitivity} />
                  </td>
                  <td>{d.source || '—'}</td>
                  <td>{(d.subjects ?? []).length}</td>
                  <td className="muted">{d.created_at || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h2>Models</h2>
        {loading ? (
          <p className="muted">Loading models…</p>
        ) : models.length === 0 ? (
          <p className="muted">No models registered.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Sensitivity</th>
                <th>Flagged</th>
                <th>Created</th>
                <th>Lineage</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => {
                const key = `${m.name}:${m.version}`
                const open = expanded === key
                return (
                  <Fragment key={key}>
                    <tr>
                      <td>{m.name}</td>
                      <td>{m.version}</td>
                      <td>
                        <SensitivityChip sensitivity={m.sensitivity} />
                      </td>
                      <td>
                        {m.flagged ? (
                          <span className="badge badge-broken">flagged</span>
                        ) : (
                          <span className="badge badge-ok">clear</span>
                        )}
                      </td>
                      <td className="muted">{m.created_at || '—'}</td>
                      <td>
                        <button
                          type="button"
                          className="btn-secondary btn-small"
                          onClick={() => setExpanded(open ? null : key)}
                          aria-expanded={open}
                        >
                          {open ? 'Hide' : 'Show'}
                        </button>
                      </td>
                    </tr>
                    {open ? (
                      <tr className="lineage-row">
                        <td colSpan={6}>
                          <div className="lineage">
                            <div className="stat">
                              <span className="stat-label">Dataset refs</span>
                              <span className="stat-value">
                                {(m.lineage?.dataset_refs ?? []).join(', ') || '—'}
                              </span>
                            </div>
                            <div className="stat">
                              <span className="stat-label">Code ref</span>
                              <span className="stat-value">
                                {m.lineage?.code_ref || '—'}
                              </span>
                            </div>
                            <div className="stat">
                              <span className="stat-label">Hardware</span>
                              <span className="stat-value">
                                {m.lineage?.hardware || '—'}
                              </span>
                            </div>
                            <div className="stat">
                              <span className="stat-label">Run id</span>
                              <span className="stat-value">
                                {m.lineage?.run_id || '—'}
                              </span>
                            </div>
                            <div className="stat stat-wide">
                              <span className="stat-label">Params</span>
                              <pre className="cell-output">
                                {JSON.stringify(m.lineage?.params ?? {}, null, 2)}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

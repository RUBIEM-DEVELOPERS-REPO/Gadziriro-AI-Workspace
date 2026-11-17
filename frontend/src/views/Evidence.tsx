import { useCallback, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  type EvidenceExportOut,
  type EvidenceManifest,
} from '../api/client.ts'
import { useT } from '../i18n/index.ts'

// Admin: export a compliance evidence pack and list prior packs.
export default function Evidence() {
  const { t } = useT()
  const [packs, setPacks] = useState<EvidenceManifest[]>([])
  const [last, setLast] = useState<EvidenceExportOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const list = await api.listEvidence()
      setPacks(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load packs.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleExport() {
    setBusy(true)
    setError(null)
    try {
      setLast(await api.exportEvidence())
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Export failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>{t('evidence.title')}</h2>
        <button
          type="button"
          className="btn-primary"
          disabled={busy}
          onClick={() => void handleExport()}
        >
          {busy ? t('common.loading') : t('evidence.export')}
        </button>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        {last ? (
          <div role="status">
            <p>
              Pack <code>{last.pack_key}</code> — audit chain{' '}
              <span className={last.audit_ok ? 'badge badge-ok' : 'badge'}>
                {last.audit_ok ? 'verified' : 'NOT verified'}
              </span>
            </p>
            {last.generated_at ? <p className="muted">{last.generated_at}</p> : null}
            {Array.isArray(last.sections) && last.sections.length > 0 ? (
              <ul>
                {last.sections.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <h3>Prior packs</h3>
        {packs.length === 0 ? (
          <p className="muted">No evidence packs yet.</p>
        ) : (
          <table>
            <caption className="sr-only">Prior evidence packs</caption>
            <thead>
              <tr>
                <th scope="col">Pack</th>
                <th scope="col">Generated</th>
                <th scope="col">Audit</th>
                <th scope="col">Sections</th>
              </tr>
            </thead>
            <tbody>
              {packs.map((p, i) => (
                <tr key={p.pack_key ?? i}>
                  <td>{p.pack_key ?? '—'}</td>
                  <td>{p.generated_at ?? '—'}</td>
                  <td>{p.audit_ok === undefined ? '—' : p.audit_ok ? 'ok' : 'failed'}</td>
                  <td>{Array.isArray(p.sections) ? p.sections.join(', ') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

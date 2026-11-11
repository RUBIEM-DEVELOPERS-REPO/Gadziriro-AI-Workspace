import { useState, type FormEvent } from 'react'
import { api, ApiError, type EgressReport } from '../api/client.ts'

function splitList(v: string): string[] {
  return v
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function cell(v: unknown): string {
  if (v === undefined || v === null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// Per-dataset ACLs and the egress report: what left the machine, and what was
// blocked.
export default function Enterprise() {
  const [dataset, setDataset] = useState('')
  const [allowRoles, setAllowRoles] = useState('')
  const [allowUsers, setAllowUsers] = useState('')
  const [denyUsers, setDenyUsers] = useState('')
  const [aclBusy, setAclBusy] = useState(false)
  const [aclError, setAclError] = useState<string | null>(null)
  const [aclMsg, setAclMsg] = useState<string | null>(null)

  const [since, setSince] = useState('')
  const [report, setReport] = useState<EgressReport | null>(null)
  const [repBusy, setRepBusy] = useState(false)
  const [repError, setRepError] = useState<string | null>(null)

  async function handleLoadAcl() {
    if (!dataset.trim()) return
    setAclBusy(true)
    setAclError(null)
    setAclMsg(null)
    try {
      const acl = await api.getDatasetAcl(dataset.trim())
      setAllowRoles((acl?.allow_roles ?? []).join(', '))
      setAllowUsers((acl?.allow_users ?? []).join(', '))
      setDenyUsers((acl?.deny_users ?? []).join(', '))
      setAclMsg('ACL loaded.')
    } catch (err) {
      setAclError(err instanceof ApiError ? err.message : 'Failed to load ACL.')
    } finally {
      setAclBusy(false)
    }
  }

  async function handleSaveAcl(e: FormEvent) {
    e.preventDefault()
    if (!dataset.trim()) return
    setAclBusy(true)
    setAclError(null)
    setAclMsg(null)
    try {
      await api.setDatasetAcl(dataset.trim(), {
        allow_roles: splitList(allowRoles),
        allow_users: splitList(allowUsers),
        deny_users: splitList(denyUsers),
      })
      setAclMsg(`ACL saved for ${dataset.trim()}.`)
    } catch (err) {
      setAclError(err instanceof ApiError ? err.message : 'Failed to save ACL.')
    } finally {
      setAclBusy(false)
    }
  }

  async function handleReport(e: FormEvent) {
    e.preventDefault()
    setRepBusy(true)
    setRepError(null)
    try {
      setReport(await api.egressReport(since.trim() || undefined))
    } catch (err) {
      setRepError(
        err instanceof ApiError ? err.message : 'Failed to load egress report.',
      )
    } finally {
      setRepBusy(false)
    }
  }

  const entries = report?.entries ?? []
  const cols = entries.length ? Object.keys(entries[0]) : []

  return (
    <section className="admin">
      <div className="panel">
        <h2>Dataset access control</h2>
        <p className="muted">
          Restrict who can read a dataset. Deny entries always win. Separate
          values with commas.
        </p>
        <form className="create-form" onSubmit={handleSaveAcl}>
          <div className="field">
            <label htmlFor="acl-dataset">Dataset name</label>
            <input
              id="acl-dataset"
              type="text"
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="acl-roles">Allowed roles</label>
            <input
              id="acl-roles"
              type="text"
              value={allowRoles}
              onChange={(e) => setAllowRoles(e.target.value)}
              placeholder="e.g. data_scientist, compliance"
            />
          </div>
          <div className="field">
            <label htmlFor="acl-users">Allowed users</label>
            <input
              id="acl-users"
              type="text"
              value={allowUsers}
              onChange={(e) => setAllowUsers(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="acl-deny">Denied users</label>
            <input
              id="acl-deny"
              type="text"
              value={denyUsers}
              onChange={(e) => setDenyUsers(e.target.value)}
            />
          </div>
          <div className="button-row">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void handleLoadAcl()}
              disabled={aclBusy || !dataset.trim()}
            >
              Load current ACL
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={aclBusy || !dataset.trim()}
            >
              {aclBusy ? 'Working…' : 'Save ACL'}
            </button>
          </div>
        </form>
        {aclError ? (
          <p className="error" role="alert">
            {aclError}
          </p>
        ) : null}
        {aclMsg ? (
          <p className="muted" role="status" aria-live="polite">
            {aclMsg}
          </p>
        ) : null}
      </div>

      <div className="panel">
        <h2>Egress report</h2>
        <p className="muted">
          Everything that tried to leave this machine.{' '}
          <span className="badge badge-egress">egress is approval-gated</span>
        </p>
        <form className="create-form" onSubmit={handleReport}>
          <div className="field">
            <label htmlFor="egress-since">Since (ISO date, optional)</label>
            <input
              id="egress-since"
              type="text"
              value={since}
              onChange={(e) => setSince(e.target.value)}
              placeholder="2026-01-01"
            />
          </div>
          <div className="button-row">
            <button type="submit" className="btn-primary" disabled={repBusy}>
              {repBusy ? 'Loading…' : 'Load report'}
            </button>
          </div>
        </form>
        {repError ? (
          <p className="error" role="alert">
            {repError}
          </p>
        ) : null}
        {report ? (
          <div role="status" aria-live="polite">
            <p>
              <span className="badge badge-ok">
                approved {report.approved_count ?? 0}
              </span>{' '}
              <span className="badge badge-broken">
                blocked {report.denied_count ?? 0}
              </span>{' '}
              <span className="muted">
                total {report.total ?? entries.length}
                {report.generated_at ? ` · generated ${report.generated_at}` : ''}
              </span>
            </p>
            {entries.length === 0 ? (
              <p className="muted">No egress events in this period.</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <caption className="sr-only">Egress events</caption>
                  <thead>
                    <tr>
                      {cols.map((c) => (
                        <th key={c} scope="col">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((en, i) => (
                      <tr key={i}>
                        {cols.map((c) =>
                          c === 'approved' ? (
                            <td key={c}>
                              {en.approved ? (
                                <span className="badge badge-ok">approved</span>
                              ) : (
                                <span className="badge badge-broken">blocked</span>
                              )}
                            </td>
                          ) : (
                            <td key={c}>{cell(en[c])}</td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </section>
  )
}

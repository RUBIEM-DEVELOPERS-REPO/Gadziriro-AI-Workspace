import { useCallback, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  type EffectivePolicy,
  type Incident,
  type LicenseCheckResult,
  type PolicyPack,
} from '../api/client.ts'

const DEFAULT_PACKS = ['hipaa', 'gdpr', 'soc2', 'zw-dpa']

// Derive a stable pack id from whatever shape the backend returns.
function packId(p: PolicyPack): string {
  return String(p.id ?? p.name ?? '')
}

export default function Compliance() {
  // --- Policy packs ---
  const [packOptions, setPackOptions] = useState<string[]>(DEFAULT_PACKS)
  const [enabled, setEnabled] = useState<string[]>([])
  const [effective, setEffective] = useState<EffectivePolicy | null>(null)
  const [policyBusy, setPolicyBusy] = useState(false)
  const [policyError, setPolicyError] = useState<string | null>(null)

  // --- Licensing ---
  const [licModel, setLicModel] = useState('')
  const [licUse, setLicUse] = useState('')
  const [licDest, setLicDest] = useState('')
  const [licBusy, setLicBusy] = useState(false)
  const [licResult, setLicResult] = useState<LicenseCheckResult | null>(null)
  const [licDenied, setLicDenied] = useState<string | null>(null)
  const [licError, setLicError] = useState<string | null>(null)

  // --- Incidents ---
  const [incTitle, setIncTitle] = useState('')
  const [incSeverity, setIncSeverity] = useState('medium')
  const [incBreach, setIncBreach] = useState(false)
  const [incBusy, setIncBusy] = useState(false)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [incError, setIncError] = useState<string | null>(null)
  const [breachReport, setBreachReport] = useState<string | null>(null)
  const [breachForId, setBreachForId] = useState<string | null>(null)

  // --- DSAR ---
  const [subject, setSubject] = useState('')
  const [dsarBusy, setDsarBusy] = useState(false)
  const [dsarResult, setDsarResult] = useState<string | null>(null)
  const [dsarError, setDsarError] = useState<string | null>(null)

  // --- Support bundle ---
  const [bundleBusy, setBundleBusy] = useState(false)
  const [bundleResult, setBundleResult] = useState<string | null>(null)
  const [bundleError, setBundleError] = useState<string | null>(null)

  const refreshIncidents = useCallback(async () => {
    try {
      const list = await api.listIncidents()
      setIncidents(Array.isArray(list) ? list : [])
    } catch (err) {
      setIncError(
        err instanceof ApiError ? err.message : 'Failed to load incidents.',
      )
    }
  }, [])

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const packs = await api.policyPacks()
        if (!active) return
        if (Array.isArray(packs) && packs.length) {
          const ids = packs.map(packId).filter(Boolean)
          if (ids.length) setPackOptions(ids)
        }
      } catch {
        // Fall back to the default pack list.
      }
    }
    void load()
    void refreshIncidents()
    return () => {
      active = false
    }
  }, [refreshIncidents])

  function togglePack(id: string) {
    setEnabled((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id],
    )
  }

  async function handleEffective() {
    setPolicyBusy(true)
    setPolicyError(null)
    setEffective(null)
    try {
      const out = await api.policyEffective(enabled)
      setEffective(out)
    } catch (err) {
      setPolicyError(
        err instanceof ApiError ? err.message : 'Failed to resolve policy.',
      )
    } finally {
      setPolicyBusy(false)
    }
  }

  async function handleLicense(e: React.FormEvent) {
    e.preventDefault()
    if (!licModel.trim() || !licUse.trim()) return
    setLicBusy(true)
    setLicError(null)
    setLicResult(null)
    setLicDenied(null)
    try {
      const out = await api.licensingCheck(
        licModel.trim(),
        licUse.trim(),
        licDest.trim() || undefined,
      )
      setLicResult(out)
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        // Surface the denial message rather than a generic error.
        setLicDenied(err.message || 'Use denied by license.')
      } else {
        setLicError(
          err instanceof ApiError ? err.message : 'License check failed.',
        )
      }
    } finally {
      setLicBusy(false)
    }
  }

  async function handleCreateIncident(e: React.FormEvent) {
    e.preventDefault()
    if (!incTitle.trim()) return
    setIncBusy(true)
    setIncError(null)
    try {
      await api.createIncident(incTitle.trim(), incSeverity, incBreach)
      setIncTitle('')
      setIncBreach(false)
      await refreshIncidents()
    } catch (err) {
      setIncError(
        err instanceof ApiError ? err.message : 'Failed to open incident.',
      )
    } finally {
      setIncBusy(false)
    }
  }

  async function handleBreachReport(id: string) {
    setBreachForId(id)
    setBreachReport(null)
    setIncError(null)
    try {
      const report = await api.incidentBreachReport(id)
      setBreachReport(report)
    } catch (err) {
      setIncError(
        err instanceof ApiError ? err.message : 'Failed to load breach report.',
      )
    }
  }

  async function handleDsar(action: 'export' | 'erase') {
    if (!subject.trim()) return
    setDsarBusy(true)
    setDsarError(null)
    setDsarResult(null)
    try {
      const out =
        action === 'export'
          ? await api.dsarSubjectExport(subject.trim())
          : await api.dsarSubjectErase(subject.trim())
      setDsarResult(
        typeof out === 'string' ? out : JSON.stringify(out, null, 2),
      )
    } catch (err) {
      setDsarError(err instanceof ApiError ? err.message : 'DSAR action failed.')
    } finally {
      setDsarBusy(false)
    }
  }

  async function handleBundle() {
    setBundleBusy(true)
    setBundleError(null)
    setBundleResult(null)
    try {
      const out = await api.supportBundle()
      setBundleResult(
        typeof out === 'string' ? out : JSON.stringify(out, null, 2),
      )
    } catch (err) {
      setBundleError(
        err instanceof ApiError ? err.message : 'Failed to build support bundle.',
      )
    } finally {
      setBundleBusy(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Policy packs</h2>
        <p className="muted">
          Enable compliance packs; the effective settings are computed with
          strictest-wins, and provenance shows which pack set each value (FR-24).
        </p>
        <div className="checkbox-row">
          {packOptions.map((id) => (
            <label key={id} className="checkbox-label">
              <input
                type="checkbox"
                checked={enabled.includes(id)}
                onChange={() => togglePack(id)}
              />
              {id}
            </label>
          ))}
        </div>
        <div className="button-row">
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleEffective()}
            disabled={policyBusy}
          >
            {policyBusy ? 'Resolving…' : 'Resolve effective policy'}
          </button>
        </div>
        {policyError ? (
          <p className="error" role="alert">
            {policyError}
          </p>
        ) : null}
        {effective ? (
          <>
            <p className="muted">
              Strictest-wins: when packs conflict, the most restrictive setting
              is applied.
            </p>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Setting</th>
                  <th>Value</th>
                  <th>Set by</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(effective.settings ?? {}).map(([k, v]) => {
                  const by = (effective.provenance ?? {})[k]
                  return (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>
                        {typeof v === 'object'
                          ? JSON.stringify(v)
                          : String(v)}
                      </td>
                      <td className="muted">
                        {by === undefined
                          ? '—'
                          : typeof by === 'object'
                            ? JSON.stringify(by)
                            : String(by)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </>
        ) : null}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Licensing check</h2>
          <span className="badge badge-egress">exports need approval</span>
        </div>
        <p className="muted">
          Confirm an intended use is permitted by the model license before it
          leaves the workspace (FR-48).
        </p>
        <form className="create-form" onSubmit={handleLicense}>
          <div className="field">
            <label htmlFor="lic-model">Model</label>
            <input
              id="lic-model"
              type="text"
              value={licModel}
              onChange={(e) => setLicModel(e.target.value)}
              placeholder="e.g. llama-3.1-8b"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="lic-use">Intended use</label>
            <input
              id="lic-use"
              type="text"
              value={licUse}
              onChange={(e) => setLicUse(e.target.value)}
              placeholder="e.g. commercial-inference"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="lic-dest">Destination (optional)</label>
            <input
              id="lic-dest"
              type="text"
              value={licDest}
              onChange={(e) => setLicDest(e.target.value)}
              placeholder="e.g. external-partner"
            />
          </div>
          <button type="submit" className="btn-primary" disabled={licBusy}>
            {licBusy ? 'Checking…' : 'Check license'}
          </button>
        </form>
        {licError ? (
          <p className="error" role="alert">
            {licError}
          </p>
        ) : null}
        {licDenied ? (
          <p>
            <span className="badge badge-broken">denied</span>{' '}
            <span className="muted">{licDenied}</span>
          </p>
        ) : null}
        {licResult ? (
          <p>
            {licResult.ok ? (
              <span className="badge badge-ok">allowed</span>
            ) : (
              <span className="badge badge-broken">denied</span>
            )}{' '}
            {licResult.reason || licResult.detail ? (
              <span className="muted">
                {licResult.reason || licResult.detail}
              </span>
            ) : null}
          </p>
        ) : null}
      </div>

      <div className="panel">
        <h2>Incident response</h2>
        <p className="muted">
          Open an incident and generate a breach report when personal data is
          affected (FR-38).
        </p>
        <form className="create-form" onSubmit={handleCreateIncident}>
          <div className="field">
            <label htmlFor="inc-title">Title</label>
            <input
              id="inc-title"
              type="text"
              value={incTitle}
              onChange={(e) => setIncTitle(e.target.value)}
              placeholder="e.g. unauthorized access attempt"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="inc-sev">Severity</label>
            <select
              id="inc-sev"
              value={incSeverity}
              onChange={(e) => setIncSeverity(e.target.value)}
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={incBreach}
              onChange={(e) => setIncBreach(e.target.checked)}
            />
            Personal-data breach
          </label>
          <button type="submit" className="btn-primary" disabled={incBusy}>
            {incBusy ? 'Opening…' : 'Open incident'}
          </button>
        </form>

        {incError ? (
          <p className="error" role="alert">
            {incError}
          </p>
        ) : null}

        {incidents.length === 0 ? (
          <p className="muted">No incidents recorded.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Id</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Breach</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => (
                <tr key={inc.id}>
                  <td>{inc.id}</td>
                  <td>{inc.title || '—'}</td>
                  <td>{inc.severity || '—'}</td>
                  <td>
                    {inc.breach ? (
                      <span className="badge badge-broken">breach</span>
                    ) : (
                      <span className="badge badge-ok">none</span>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn-secondary btn-small"
                      onClick={() => void handleBreachReport(inc.id)}
                    >
                      View report
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {breachReport !== null ? (
          <div className="field">
            <label>Breach report — incident {breachForId}</label>
            <pre className="cell-output model-card">{breachReport}</pre>
          </div>
        ) : null}
      </div>

      <div className="panel">
        <h2>Data subject requests (DSAR)</h2>
        <p className="muted">
          Export or erase all data held for a subject (FR-45). Exports leave the
          sealed workspace and are logged.
        </p>
        <div className="field">
          <label htmlFor="dsar-subj">Subject id</label>
          <input
            id="dsar-subj"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="e.g. subject-42"
          />
        </div>
        <div className="button-row">
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleDsar('export')}
            disabled={dsarBusy || !subject.trim()}
          >
            {dsarBusy ? 'Working…' : 'Export'}
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={() => void handleDsar('erase')}
            disabled={dsarBusy || !subject.trim()}
          >
            Erase
          </button>
        </div>
        {dsarError ? (
          <p className="error" role="alert">
            {dsarError}
          </p>
        ) : null}
        {dsarResult ? <pre className="cell-output">{dsarResult}</pre> : null}
      </div>

      <div className="panel">
        <h2>Support bundle</h2>
        <p className="muted">
          Collect logs and evidence for support or an audit (FR-40). The bundle
          stays in the workspace until an export is approved.
        </p>
        <button
          type="button"
          className="btn-primary"
          onClick={() => void handleBundle()}
          disabled={bundleBusy}
        >
          {bundleBusy ? 'Building…' : 'Build support bundle'}
        </button>
        {bundleError ? (
          <p className="error" role="alert">
            {bundleError}
          </p>
        ) : null}
        {bundleResult ? <pre className="cell-output">{bundleResult}</pre> : null}
      </div>
    </section>
  )
}

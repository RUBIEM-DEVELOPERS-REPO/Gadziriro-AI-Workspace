import { useEffect, useState } from 'react'
import {
  api,
  ApiError,
  type AuditVerifyOut,
  type HardwareReport,
} from '../api/client.ts'

export default function Admin() {
  const [hardware, setHardware] = useState<HardwareReport | null>(null)
  const [hwError, setHwError] = useState<string | null>(null)

  const [audit, setAudit] = useState<AuditVerifyOut | null>(null)
  const [auditError, setAuditError] = useState<string | null>(null)
  const [auditForbidden, setAuditForbidden] = useState(false)

  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    async function load() {
      const hwP = api
        .hardware()
        .then((h) => {
          if (active) setHardware(h)
        })
        .catch((err: unknown) => {
          if (active) {
            setHwError(
              err instanceof ApiError ? err.message : 'Failed to load hardware report.',
            )
          }
        })

      const auditP = api
        .auditVerify()
        .then((a) => {
          if (active) setAudit(a)
        })
        .catch((err: unknown) => {
          if (!active) return
          if (err instanceof ApiError && err.status === 403) {
            setAuditForbidden(true)
          } else {
            setAuditError(
              err instanceof ApiError ? err.message : 'Failed to verify audit chain.',
            )
          }
        })

      await Promise.all([hwP, auditP])
      if (active) setLoading(false)
    }

    void load()
    return () => {
      active = false
    }
  }, [])

  return (
    <section className="admin">
      <div className="panel">
        <h2>Hardware report</h2>
        {loading && !hardware && !hwError ? (
          <p className="muted">Loading hardware report…</p>
        ) : hwError ? (
          <p className="error" role="alert">
            {hwError}
          </p>
        ) : hardware ? (
          <div className="hardware-grid">
            <div className="stat">
              <span className="stat-label">GPU present</span>
              <span className="stat-value">{hardware.gpu_present ? 'Yes' : 'No'}</span>
            </div>
            <div className="stat">
              <span className="stat-label">GPU count</span>
              <span className="stat-value">{hardware.gpu_count}</span>
            </div>
            <div className="stat">
              <span className="stat-label">GPU memory (MB)</span>
              <span className="stat-value">
                {hardware.gpu_memory_mb.length
                  ? hardware.gpu_memory_mb.join(', ')
                  : '—'}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">CPU count</span>
              <span className="stat-value">{hardware.cpu_count}</span>
            </div>
            <div className="stat">
              <span className="stat-label">RAM (MB)</span>
              <span className="stat-value">{hardware.ram_mb}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Disk free (GB)</span>
              <span className="stat-value">{hardware.disk_free_gb}</span>
            </div>
            <div className="stat stat-wide">
              <span className="stat-label">Supported methods</span>
              <span className="stat-value">
                {hardware.supported_methods.length
                  ? hardware.supported_methods.join(', ')
                  : '—'}
              </span>
            </div>
            <div className="stat stat-wide">
              <span className="stat-label">Recommended model sizes</span>
              <span className="stat-value">
                {hardware.recommended_model_sizes.length
                  ? hardware.recommended_model_sizes.join(', ')
                  : '—'}
              </span>
            </div>
            {hardware.warnings.length > 0 ? (
              <div className="stat stat-wide">
                <span className="stat-label">Warnings</span>
                <ul className="warnings">
                  {hardware.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="panel">
        <h2>Audit chain</h2>
        {auditForbidden ? (
          <p className="muted">admin only</p>
        ) : loading && !audit && !auditError ? (
          <p className="muted">Verifying audit chain…</p>
        ) : auditError ? (
          <p className="error" role="alert">
            {auditError}
          </p>
        ) : audit ? (
          <div className="audit">
            <p>
              Status:{' '}
              {audit.ok ? (
                <span className="badge badge-ok">OK</span>
              ) : (
                <span className="badge badge-broken">BROKEN</span>
              )}
            </p>
            <p className="muted">Entries verified: {audit.count}</p>
            {!audit.ok && audit.broken_at !== undefined ? (
              <p className="error">Chain broke at entry #{audit.broken_at}</p>
            ) : null}
            {audit.detail ? <p className="muted">{audit.detail}</p> : null}
          </div>
        ) : null}
      </div>
    </section>
  )
}

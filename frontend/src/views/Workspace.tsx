import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type SessionOut } from '../api/client.ts'

export default function Workspace() {
  const [sessions, setSessions] = useState<SessionOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [newSessionId, setNewSessionId] = useState('')
  const [gpuMemory, setGpuMemory] = useState('')
  const [creating, setCreating] = useState(false)

  const [activeId, setActiveId] = useState<string | null>(null)
  const [code, setCode] = useState('print("hello from Gadziriro")')
  const [output, setOutput] = useState<string>('')
  const [running, setRunning] = useState(false)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const list = await api.listSessions()
      setSessions(list)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load sessions.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newSessionId.trim()) return
    setCreating(true)
    setError(null)
    try {
      const mem = gpuMemory.trim() ? Number(gpuMemory) : undefined
      const created = await api.createSession(
        newSessionId.trim(),
        Number.isFinite(mem) ? mem : undefined,
      )
      setNewSessionId('')
      setGpuMemory('')
      setActiveId(created.session_id)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create session.')
    } finally {
      setCreating(false)
    }
  }

  async function handleStop(id: string) {
    setError(null)
    try {
      await api.stopSession(id)
      if (activeId === id) setActiveId(null)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to stop session.')
    }
  }

  async function handleRun() {
    if (!activeId) return
    setRunning(true)
    setError(null)
    try {
      const result = await api.runCell(activeId, code)
      setOutput(result.output ?? JSON.stringify(result, null, 2))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to run cell.')
    } finally {
      setRunning(false)
    }
  }

  const active = sessions.find((s) => s.session_id === activeId) ?? null

  return (
    <section className="workspace">
      <div className="panel sessions-panel">
        <h2>Sessions</h2>

        <form className="create-form" onSubmit={handleCreate}>
          <div className="field">
            <label htmlFor="session-id">New session id</label>
            <input
              id="session-id"
              type="text"
              value={newSessionId}
              onChange={(e) => setNewSessionId(e.target.value)}
              placeholder="e.g. notebook-1"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="gpu-mem">GPU memory (MB, optional)</label>
            <input
              id="gpu-mem"
              type="number"
              min="0"
              value={gpuMemory}
              onChange={(e) => setGpuMemory(e.target.value)}
              placeholder="e.g. 8192"
            />
          </div>
          <button type="submit" className="btn-primary" disabled={creating}>
            {creating ? 'Creating…' : 'Create session'}
          </button>
        </form>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="muted">Loading sessions…</p>
        ) : sessions.length === 0 ? (
          <p className="muted">No sessions yet. Create one to get started.</p>
        ) : (
          <ul className="session-list">
            {sessions.map((s) => (
              <li
                key={s.session_id}
                className={s.session_id === activeId ? 'session active' : 'session'}
              >
                <button
                  type="button"
                  className="session-open"
                  onClick={() => setActiveId(s.session_id)}
                  aria-pressed={s.session_id === activeId}
                >
                  <span className="session-name">{s.session_id}</span>
                  <span className="session-status">{s.status}</span>
                </button>
                <div className="session-meta">
                  {s.allow_egress ? (
                    <span className="badge badge-egress">Network enabled</span>
                  ) : (
                    <span className="badge badge-sealed">No network (sealed)</span>
                  )}
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={() => handleStop(s.session_id)}
                  >
                    Stop
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel notebook-panel">
        <h2>Notebook</h2>
        {!active ? (
          <p className="muted">Select or create a session to open the notebook.</p>
        ) : (
          <>
            <div className="notebook-header">
              <span className="session-name">{active.session_id}</span>
              {active.allow_egress ? (
                <span className="badge badge-egress">Network enabled</span>
              ) : (
                <span className="badge badge-sealed" title="Egress is blocked (FR-20)">
                  No network (sealed)
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="cell-code">Cell</label>
              <textarea
                id="cell-code"
                className="cell-editor"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                rows={8}
                spellCheck={false}
              />
            </div>
            <button
              type="button"
              className="btn-primary"
              onClick={handleRun}
              disabled={running}
            >
              {running ? 'Running…' : 'Run'}
            </button>

            <div className="field">
              <label htmlFor="cell-output">Output</label>
              <pre id="cell-output" className="cell-output" aria-live="polite">
                {output || '(no output yet)'}
              </pre>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

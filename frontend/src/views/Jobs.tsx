import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type Job } from '../api/client.ts'

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [command, setCommand] = useState('')
  const [project, setProject] = useState('')
  const [gpuMemory, setGpuMemory] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const list = await api.listJobs()
      setJobs(list ?? [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load jobs.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Split the command string into argv tokens on whitespace.
    const argv = command.trim().split(/\s+/).filter(Boolean)
    if (argv.length === 0 || !project.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const mem = gpuMemory.trim() ? Number(gpuMemory) : undefined
      await api.submitJob(
        argv,
        project.trim(),
        mem !== undefined && Number.isFinite(mem) ? mem : undefined,
      )
      setCommand('')
      setProject('')
      setGpuMemory('')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit job.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Submit a job</h2>
        <form className="create-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="job-command">Command</label>
            <input
              id="job-command"
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="e.g. python train.py --epochs 3"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="job-project">Project</label>
            <input
              id="job-project"
              type="text"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              placeholder="e.g. vision-pilot"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="job-gpu">GPU memory (MB, optional)</label>
            <input
              id="job-gpu"
              type="number"
              min="0"
              value={gpuMemory}
              onChange={(e) => setGpuMemory(e.target.value)}
              placeholder="e.g. 8192"
            />
          </div>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit job'}
          </button>
        </form>
      </div>

      <div className="panel">
        <h2>Jobs</h2>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        {loading ? (
          <p className="muted">Loading jobs…</p>
        ) : jobs.length === 0 ? (
          <p className="muted">No jobs submitted yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Job id</th>
                <th>User</th>
                <th>Project</th>
                <th>Status</th>
                <th>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id}>
                  <td>{j.job_id}</td>
                  <td>{j.user || '—'}</td>
                  <td>{j.project || '—'}</td>
                  <td>
                    <span className="badge badge-ok">{j.status || 'unknown'}</span>
                  </td>
                  <td className="muted">{j.submitted_at || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

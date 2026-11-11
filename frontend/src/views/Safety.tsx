import { useState, type FormEvent } from 'react'
import {
  api,
  ApiError,
  type BiasResult,
  type RedTeamResult,
} from '../api/client.ts'

function unsafeList(r: RedTeamResult): unknown[] {
  return Array.isArray(r.unsafe) ? r.unsafe : []
}

// Bias and red-team checks run locally against a registered model.
export default function Safety() {
  const [modelRef, setModelRef] = useState('')
  const [template, setTemplate] = useState('The {group} applicant is')
  const [groups, setGroups] = useState('male, female')
  const [biasBusy, setBiasBusy] = useState(false)
  const [bias, setBias] = useState<BiasResult | null>(null)
  const [biasError, setBiasError] = useState<string | null>(null)

  const [rtBusy, setRtBusy] = useState(false)
  const [redteam, setRedteam] = useState<RedTeamResult | null>(null)
  const [rtError, setRtError] = useState<string | null>(null)

  async function handleBias(e: FormEvent) {
    e.preventDefault()
    if (!modelRef.trim() || !template.trim()) return
    const g = groups
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
    setBiasBusy(true)
    setBiasError(null)
    setBias(null)
    try {
      setBias(
        await api.safetyBias(modelRef.trim(), [
          { template: template.trim(), groups: g },
        ]),
      )
    } catch (err) {
      setBiasError(err instanceof ApiError ? err.message : 'Bias check failed.')
    } finally {
      setBiasBusy(false)
    }
  }

  async function handleRedteam() {
    if (!modelRef.trim()) return
    setRtBusy(true)
    setRtError(null)
    setRedteam(null)
    try {
      setRedteam(await api.safetyRedteam(modelRef.trim()))
    } catch (err) {
      setRtError(err instanceof ApiError ? err.message : 'Red-team run failed.')
    } finally {
      setRtBusy(false)
    }
  }

  const unsafeFound = redteam
    ? unsafeList(redteam).length > 0 ||
      (typeof redteam.unsafe === 'number' && redteam.unsafe > 0)
    : false

  return (
    <section className="admin">
      <div className="panel">
        <h2>Model safety</h2>
        <p className="muted">
          Run fairness and red-team checks locally; prompts never leave the
          workspace. <span className="badge badge-ok">sealed</span>
        </p>
        <div className="field">
          <label htmlFor="safety-model">Model ref</label>
          <input
            id="safety-model"
            type="text"
            value={modelRef}
            onChange={(e) => setModelRef(e.target.value)}
            placeholder="name@version"
          />
        </div>
      </div>

      <div className="panel">
        <h2>Bias check</h2>
        <form className="create-form" onSubmit={handleBias}>
          <div className="field">
            <label htmlFor="bias-template">
              Prompt template (use {'{group}'} as the placeholder)
            </label>
            <input
              id="bias-template"
              type="text"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="bias-groups">Groups (comma separated)</label>
            <input
              id="bias-groups"
              type="text"
              value={groups}
              onChange={(e) => setGroups(e.target.value)}
            />
          </div>
          <div className="button-row">
            <button
              type="submit"
              className="btn-primary"
              disabled={biasBusy || !modelRef.trim()}
            >
              {biasBusy ? 'Running…' : 'Run bias check'}
            </button>
          </div>
        </form>
        {biasError ? (
          <p className="error" role="alert">
            {biasError}
          </p>
        ) : null}
        {bias ? (
          <p role="status" aria-live="polite">
            {bias.passed ? (
              <span className="badge badge-ok">passed</span>
            ) : (
              <span className="badge badge-broken">failed</span>
            )}{' '}
            <span className="muted">
              disparity{' '}
              {typeof bias.disparity === 'number'
                ? bias.disparity.toFixed(3)
                : '—'}
            </span>
          </p>
        ) : null}
      </div>

      <div className="panel">
        <h2>Red-team</h2>
        <div className="button-row">
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleRedteam()}
            disabled={rtBusy || !modelRef.trim()}
          >
            {rtBusy ? 'Running…' : 'Run red-team suite'}
          </button>
        </div>
        {rtError ? (
          <p className="error" role="alert">
            {rtError}
          </p>
        ) : null}
        {redteam ? (
          <div role="status" aria-live="polite">
            <p>
              {unsafeFound ? (
                <span className="badge badge-broken">unsafe findings</span>
              ) : (
                <span className="badge badge-ok">no unsafe outputs</span>
              )}{' '}
              <span className="muted">
                passed {redteam.passed ?? '—'} of {redteam.total ?? '—'}
              </span>
            </p>
            {unsafeList(redteam).length > 0 ? (
              <ul>
                {unsafeList(redteam).map((u, i) => (
                  <li key={i}>{typeof u === 'string' ? u : JSON.stringify(u)}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  )
}

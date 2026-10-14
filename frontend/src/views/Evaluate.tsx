import { useState } from 'react'
import {
  api,
  ApiError,
  type ComparisonResult,
  type EvalResult,
  type EvalSample,
} from '../api/client.ts'

interface Row {
  prompt: string
  expected: string
  weight: string
}

const emptyRow = (): Row => ({ prompt: '', expected: '', weight: '' })

// Turns the editable rows into the API suite shape, dropping blank rows.
function toSuite(rows: Row[]): EvalSample[] {
  return rows
    .filter((r) => r.prompt.trim() || r.expected.trim())
    .map((r) => {
      const sample: EvalSample = {
        prompt: r.prompt,
        expected: r.expected,
      }
      const w = Number(r.weight)
      if (r.weight.trim() && !Number.isNaN(w)) sample.weight = w
      return sample
    })
}

export default function Evaluate() {
  const [rows, setRows] = useState<Row[]>([emptyRow(), emptyRow()])

  // Single-model eval
  const [modelRef, setModelRef] = useState('')
  const [suiteName, setSuiteName] = useState('')
  const [running, setRunning] = useState(false)
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null)
  const [evalError, setEvalError] = useState<string | null>(null)

  // Compare two models
  const [aRef, setARef] = useState('')
  const [bRef, setBRef] = useState('')
  const [comparing, setComparing] = useState(false)
  const [comparison, setComparison] = useState<ComparisonResult | null>(null)
  const [compareError, setCompareError] = useState<string | null>(null)

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  function addRow() {
    setRows((prev) => [...prev, emptyRow()])
  }

  function removeRow(i: number) {
    setRows((prev) =>
      prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev,
    )
  }

  async function handleRun() {
    if (!modelRef.trim()) return
    const suite = toSuite(rows)
    if (suite.length === 0) {
      setEvalError('Add at least one prompt/expected row.')
      return
    }
    setRunning(true)
    setEvalError(null)
    setEvalResult(null)
    try {
      const out = await api.evalRun(
        modelRef.trim(),
        suite,
        suiteName.trim() || undefined,
      )
      setEvalResult(out)
    } catch (err) {
      setEvalError(err instanceof ApiError ? err.message : 'Evaluation failed.')
    } finally {
      setRunning(false)
    }
  }

  async function handleCompare() {
    if (!aRef.trim() || !bRef.trim()) return
    const suite = toSuite(rows)
    if (suite.length === 0) {
      setCompareError('Add at least one prompt/expected row.')
      return
    }
    setComparing(true)
    setCompareError(null)
    setComparison(null)
    try {
      const out = await api.evalCompare(aRef.trim(), bRef.trim(), suite)
      setComparison(out)
    } catch (err) {
      setCompareError(
        err instanceof ApiError ? err.message : 'Comparison failed.',
      )
    } finally {
      setComparing(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Question set</h2>
        <p className="muted">
          A small evaluation suite. Each row is a prompt, its expected answer,
          and an optional weight (FR-11/13). The same set is used for the single
          run and the comparison below.
        </p>
        <table className="data-table">
          <thead>
            <tr>
              <th>Prompt</th>
              <th>Expected</th>
              <th>Weight</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>
                  <input
                    type="text"
                    value={r.prompt}
                    onChange={(e) => updateRow(i, { prompt: e.target.value })}
                    placeholder="prompt"
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={r.expected}
                    onChange={(e) => updateRow(i, { expected: e.target.value })}
                    placeholder="expected"
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="any"
                    value={r.weight}
                    onChange={(e) => updateRow(i, { weight: e.target.value })}
                    placeholder="1"
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={() => removeRow(i)}
                    disabled={rows.length <= 1}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="button-row">
          <button type="button" className="btn-secondary btn-small" onClick={addRow}>
            Add row
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>Run evaluation</h2>
        <form
          className="create-form"
          onSubmit={(e) => {
            e.preventDefault()
            void handleRun()
          }}
        >
          <div className="field">
            <label htmlFor="ev-ref">Model ref</label>
            <input
              id="ev-ref"
              type="text"
              value={modelRef}
              onChange={(e) => setModelRef(e.target.value)}
              placeholder="e.g. model:claims-classifier:v1"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="ev-suite">Suite name (optional)</label>
            <input
              id="ev-suite"
              type="text"
              value={suiteName}
              onChange={(e) => setSuiteName(e.target.value)}
              placeholder="e.g. smoke-set"
            />
          </div>
          <button type="submit" className="btn-primary" disabled={running}>
            {running ? 'Running…' : 'Run eval'}
          </button>
        </form>

        {evalError ? (
          <p className="error" role="alert">
            {evalError}
          </p>
        ) : null}

        {evalResult ? (
          <div className="result-block">
            <div className="hardware-grid">
              <div className="stat">
                <span className="stat-label">Model ref</span>
                <span className="stat-value">{evalResult.model_ref || '—'}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Score</span>
                <span className="stat-value">{evalResult.score ?? '—'}</span>
              </div>
            </div>
            {evalResult.samples && evalResult.samples.length ? (
              <div className="field">
                <label>Samples</label>
                <pre className="cell-output">
                  {JSON.stringify(evalResult.samples, null, 2)}
                </pre>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="panel">
        <h2>Compare two models</h2>
        <p className="muted">
          Scores both refs on the question set above and reports the delta.
        </p>
        <form
          className="create-form"
          onSubmit={(e) => {
            e.preventDefault()
            void handleCompare()
          }}
        >
          <div className="field">
            <label htmlFor="cmp-a">Model A ref</label>
            <input
              id="cmp-a"
              type="text"
              value={aRef}
              onChange={(e) => setARef(e.target.value)}
              placeholder="e.g. model:classifier:v1"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="cmp-b">Model B ref</label>
            <input
              id="cmp-b"
              type="text"
              value={bRef}
              onChange={(e) => setBRef(e.target.value)}
              placeholder="e.g. model:classifier:v2"
              required
            />
          </div>
          <button type="submit" className="btn-primary" disabled={comparing}>
            {comparing ? 'Comparing…' : 'Compare'}
          </button>
        </form>

        {compareError ? (
          <p className="error" role="alert">
            {compareError}
          </p>
        ) : null}

        {comparison ? (
          <div className="result-block">
            <div className="hardware-grid">
              <div className="stat">
                <span className="stat-label">{comparison.a_ref || 'A'}</span>
                <span className="stat-value">{comparison.score_a ?? '—'}</span>
              </div>
              <div className="stat">
                <span className="stat-label">{comparison.b_ref || 'B'}</span>
                <span className="stat-value">{comparison.score_b ?? '—'}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Delta</span>
                <span className="stat-value">
                  {comparison.score_delta ?? '—'}
                </span>
              </div>
            </div>
            {comparison.sample_diffs && comparison.sample_diffs.length ? (
              <div className="field">
                <label>Sample diffs</label>
                <pre className="cell-output">
                  {JSON.stringify(comparison.sample_diffs, null, 2)}
                </pre>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  )
}

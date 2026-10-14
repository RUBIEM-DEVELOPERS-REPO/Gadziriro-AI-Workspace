import { useState } from 'react'
import { api, ApiError, type WeightToolResult } from '../api/client.ts'

// Renders a WeightToolResult defensively: surface the model ref + summary when
// present, and always fall back to the full payload so nothing is hidden.
function ResultView({ result }: { result: WeightToolResult }) {
  const { model_ref, summary, ...rest } = result
  return (
    <div className="result-block">
      {model_ref ? (
        <div className="stat">
          <span className="stat-label">Result model ref</span>
          <span className="stat-value">{model_ref}</span>
        </div>
      ) : null}
      {summary !== undefined ? (
        <div className="field">
          <label>Summary</label>
          <pre className="cell-output">
            {typeof summary === 'string'
              ? summary
              : JSON.stringify(summary, null, 2)}
          </pre>
        </div>
      ) : null}
      {Object.keys(rest).length ? (
        <div className="field">
          <label>Details</label>
          <pre className="cell-output">{JSON.stringify(rest, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  )
}

export default function WeightTools() {
  // Merge
  const [mergeRefs, setMergeRefs] = useState('')
  const [mergeOutput, setMergeOutput] = useState('')
  const [mergeBusy, setMergeBusy] = useState(false)
  const [mergeResult, setMergeResult] = useState<WeightToolResult | null>(null)
  const [mergeError, setMergeError] = useState<string | null>(null)

  // Quantize
  const [quantRef, setQuantRef] = useState('')
  const [quantMethod, setQuantMethod] = useState('GPTQ')
  const [quantBits, setQuantBits] = useState('4')
  const [quantOutput, setQuantOutput] = useState('')
  const [quantBusy, setQuantBusy] = useState(false)
  const [quantResult, setQuantResult] = useState<WeightToolResult | null>(null)
  const [quantError, setQuantError] = useState<string | null>(null)

  // Prune
  const [pruneRef, setPruneRef] = useState('')
  const [pruneSparsity, setPruneSparsity] = useState('0.5')
  const [pruneOutput, setPruneOutput] = useState('')
  const [pruneBusy, setPruneBusy] = useState(false)
  const [pruneResult, setPruneResult] = useState<WeightToolResult | null>(null)
  const [pruneError, setPruneError] = useState<string | null>(null)

  // Inspect
  const [inspName, setInspName] = useState('')
  const [inspVersion, setInspVersion] = useState('')
  const [inspBusy, setInspBusy] = useState(false)
  const [inspResult, setInspResult] = useState<WeightToolResult | null>(null)
  const [inspError, setInspError] = useState<string | null>(null)

  async function handleMerge(e: React.FormEvent) {
    e.preventDefault()
    const refs = mergeRefs
      .split(/[\n,]/)
      .map((r) => r.trim())
      .filter(Boolean)
    if (refs.length === 0) return
    setMergeBusy(true)
    setMergeError(null)
    setMergeResult(null)
    try {
      const out = await api.weightMerge({
        model_refs: refs,
        output_name: mergeOutput.trim() || undefined,
      })
      setMergeResult(out)
    } catch (err) {
      setMergeError(err instanceof ApiError ? err.message : 'Merge failed.')
    } finally {
      setMergeBusy(false)
    }
  }

  async function handleQuantize(e: React.FormEvent) {
    e.preventDefault()
    if (!quantRef.trim()) return
    setQuantBusy(true)
    setQuantError(null)
    setQuantResult(null)
    try {
      const bits = Number(quantBits)
      const out = await api.weightQuantize({
        model_ref: quantRef.trim(),
        method: quantMethod,
        ...(quantBits.trim() && !Number.isNaN(bits) ? { bits } : {}),
        output_name: quantOutput.trim() || undefined,
      })
      setQuantResult(out)
    } catch (err) {
      setQuantError(
        err instanceof ApiError ? err.message : 'Quantization failed.',
      )
    } finally {
      setQuantBusy(false)
    }
  }

  async function handlePrune(e: React.FormEvent) {
    e.preventDefault()
    if (!pruneRef.trim()) return
    setPruneBusy(true)
    setPruneError(null)
    setPruneResult(null)
    try {
      const sparsity = Number(pruneSparsity)
      const out = await api.weightPrune({
        model_ref: pruneRef.trim(),
        ...(pruneSparsity.trim() && !Number.isNaN(sparsity) ? { sparsity } : {}),
        output_name: pruneOutput.trim() || undefined,
      })
      setPruneResult(out)
    } catch (err) {
      setPruneError(err instanceof ApiError ? err.message : 'Prune failed.')
    } finally {
      setPruneBusy(false)
    }
  }

  async function handleInspect(e: React.FormEvent) {
    e.preventDefault()
    if (!inspName.trim() || !inspVersion.trim()) return
    setInspBusy(true)
    setInspError(null)
    setInspResult(null)
    try {
      const out = await api.weightInspect(inspName.trim(), inspVersion.trim())
      setInspResult(out)
    } catch (err) {
      setInspError(err instanceof ApiError ? err.message : 'Inspect failed.')
    } finally {
      setInspBusy(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <div className="panel-head">
          <h2>Merge</h2>
          <span className="badge badge-sealed">sealed · no egress</span>
        </div>
        <p className="muted">
          Combine two or more model refs into a new merged model (FR-12).
        </p>
        <form className="create-form" onSubmit={handleMerge}>
          <div className="field">
            <label htmlFor="mg-refs">Model refs</label>
            <textarea
              id="mg-refs"
              rows={2}
              value={mergeRefs}
              onChange={(e) => setMergeRefs(e.target.value)}
              placeholder="one ref per line or comma-separated"
            />
          </div>
          <div className="field">
            <label htmlFor="mg-out">Output name (optional)</label>
            <input
              id="mg-out"
              type="text"
              value={mergeOutput}
              onChange={(e) => setMergeOutput(e.target.value)}
              placeholder="e.g. merged-model"
            />
          </div>
          <button type="submit" className="btn-primary" disabled={mergeBusy}>
            {mergeBusy ? 'Merging…' : 'Merge'}
          </button>
        </form>
        {mergeError ? (
          <p className="error" role="alert">
            {mergeError}
          </p>
        ) : null}
        {mergeResult ? <ResultView result={mergeResult} /> : null}
      </div>

      <div className="panel">
        <h2>Quantize</h2>
        <p className="muted">
          Reduce precision to shrink the model and speed up serving (FR-12).
        </p>
        <form className="create-form" onSubmit={handleQuantize}>
          <div className="field">
            <label htmlFor="qt-ref">Model ref</label>
            <input
              id="qt-ref"
              type="text"
              value={quantRef}
              onChange={(e) => setQuantRef(e.target.value)}
              placeholder="e.g. model:classifier:v1"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="qt-method">Method</label>
            <select
              id="qt-method"
              value={quantMethod}
              onChange={(e) => setQuantMethod(e.target.value)}
            >
              <option value="GPTQ">GPTQ</option>
              <option value="AWQ">AWQ</option>
              <option value="GGUF">GGUF</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="qt-bits">Bits (optional)</label>
            <input
              id="qt-bits"
              type="number"
              min={1}
              value={quantBits}
              onChange={(e) => setQuantBits(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="qt-out">Output name (optional)</label>
            <input
              id="qt-out"
              type="text"
              value={quantOutput}
              onChange={(e) => setQuantOutput(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={quantBusy}>
            {quantBusy ? 'Quantizing…' : 'Quantize'}
          </button>
        </form>
        {quantError ? (
          <p className="error" role="alert">
            {quantError}
          </p>
        ) : null}
        {quantResult ? <ResultView result={quantResult} /> : null}
      </div>

      <div className="panel">
        <h2>Prune</h2>
        <p className="muted">
          Remove redundant weights at a target sparsity (FR-12).
        </p>
        <form className="create-form" onSubmit={handlePrune}>
          <div className="field">
            <label htmlFor="pr-ref">Model ref</label>
            <input
              id="pr-ref"
              type="text"
              value={pruneRef}
              onChange={(e) => setPruneRef(e.target.value)}
              placeholder="e.g. model:classifier:v1"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="pr-sparsity">Sparsity (0–1, optional)</label>
            <input
              id="pr-sparsity"
              type="number"
              step="any"
              min={0}
              max={1}
              value={pruneSparsity}
              onChange={(e) => setPruneSparsity(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="pr-out">Output name (optional)</label>
            <input
              id="pr-out"
              type="text"
              value={pruneOutput}
              onChange={(e) => setPruneOutput(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={pruneBusy}>
            {pruneBusy ? 'Pruning…' : 'Prune'}
          </button>
        </form>
        {pruneError ? (
          <p className="error" role="alert">
            {pruneError}
          </p>
        ) : null}
        {pruneResult ? <ResultView result={pruneResult} /> : null}
      </div>

      <div className="panel">
        <h2>Inspect</h2>
        <p className="muted">
          Look up a registered model version and its weight summary (FR-12).
        </p>
        <form className="create-form" onSubmit={handleInspect}>
          <div className="field">
            <label htmlFor="in-name">Name</label>
            <input
              id="in-name"
              type="text"
              value={inspName}
              onChange={(e) => setInspName(e.target.value)}
              placeholder="e.g. classifier"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="in-version">Version</label>
            <input
              id="in-version"
              type="text"
              value={inspVersion}
              onChange={(e) => setInspVersion(e.target.value)}
              placeholder="e.g. v1"
              required
            />
          </div>
          <button type="submit" className="btn-primary" disabled={inspBusy}>
            {inspBusy ? 'Inspecting…' : 'Inspect'}
          </button>
        </form>
        {inspError ? (
          <p className="error" role="alert">
            {inspError}
          </p>
        ) : null}
        {inspResult ? <ResultView result={inspResult} /> : null}
      </div>
    </section>
  )
}

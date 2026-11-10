import { useState } from 'react'
import {
  api,
  ApiError,
  type ModelExportResult,
  type TrainingResult,
} from '../api/client.ts'

export default function ModelStudio() {
  // --- Fine-tune form state ---
  const [baseModel, setBaseModel] = useState('')
  const [method, setMethod] = useState('lora')
  const [datasetRefs, setDatasetRefs] = useState('')
  const [outputName, setOutputName] = useState('')
  const [hyperparams, setHyperparams] = useState('')
  const [training, setTraining] = useState(false)
  const [result, setResult] = useState<TrainingResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // --- Export panel state ---
  const [exportRef, setExportRef] = useState('')
  const [exportFormat, setExportFormat] = useState('safetensors')
  const [exporting, setExporting] = useState(false)
  const [exportResult, setExportResult] = useState<ModelExportResult | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  async function handleFinetune(e: React.FormEvent) {
    e.preventDefault()
    if (!baseModel.trim() || !outputName.trim()) return
    setTraining(true)
    setError(null)
    setResult(null)

    let hp: Record<string, unknown> | undefined
    if (hyperparams.trim()) {
      try {
        hp = JSON.parse(hyperparams) as Record<string, unknown>
      } catch {
        setError('Hyperparameters must be valid JSON.')
        setTraining(false)
        return
      }
    }

    const refs = datasetRefs
      .split(/[\n,]/)
      .map((r) => r.trim())
      .filter(Boolean)

    try {
      const out = await api.finetune({
        base_model: baseModel.trim(),
        method,
        dataset_refs: refs,
        output_name: outputName.trim(),
        ...(hp ? { hyperparams: hp } : {}),
      })
      setResult(out)
      // Prefill the export panel with the freshly produced model ref.
      if (out?.model_ref) setExportRef(out.model_ref)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fine-tune run failed.')
    } finally {
      setTraining(false)
    }
  }

  async function handleExport(e: React.FormEvent) {
    e.preventDefault()
    if (!exportRef.trim()) return
    setExporting(true)
    setExportError(null)
    setExportResult(null)
    try {
      const out = await api.modelExport(exportRef.trim(), exportFormat)
      setExportResult(out)
    } catch (err) {
      setExportError(
        err instanceof ApiError ? err.message : 'Model export failed.',
      )
    } finally {
      setExporting(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <div className="panel-head">
          <h2>Fine-tune a model</h2>
          <span className="badge badge-sealed">sealed · no egress</span>
        </div>
        <p className="muted">
          Training runs stay inside the sealed workspace (FR-10/15). Produced
          weights are registered with full lineage.
        </p>
        <form className="create-form" onSubmit={handleFinetune}>
          <div className="field">
            <label htmlFor="fs-base">Base model</label>
            <input
              id="fs-base"
              type="text"
              value={baseModel}
              onChange={(e) => setBaseModel(e.target.value)}
              placeholder="e.g. llama-3.1-8b"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="fs-method">Method</label>
            <select
              id="fs-method"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              <option value="lora">lora</option>
              <option value="qlora">qlora</option>
              <option value="full">full</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="fs-datasets">Dataset refs</label>
            <textarea
              id="fs-datasets"
              rows={2}
              value={datasetRefs}
              onChange={(e) => setDatasetRefs(e.target.value)}
              placeholder="one ref per line or comma-separated, e.g. ds:claims:v2"
            />
          </div>
          <div className="field">
            <label htmlFor="fs-output">Output name</label>
            <input
              id="fs-output"
              type="text"
              value={outputName}
              onChange={(e) => setOutputName(e.target.value)}
              placeholder="e.g. claims-classifier"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="fs-hyper">Hyperparameters (JSON, optional)</label>
            <textarea
              id="fs-hyper"
              className="cell-editor"
              rows={3}
              value={hyperparams}
              onChange={(e) => setHyperparams(e.target.value)}
              placeholder='{"epochs": 3, "lr": 0.0002}'
            />
          </div>
          <button type="submit" className="btn-primary" disabled={training}>
            {training ? 'Running…' : 'Run fine-tune'}
          </button>
        </form>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {result ? (
          <div className="result-block">
            <div className="hardware-grid">
              <div className="stat">
                <span className="stat-label">Model ref</span>
                <span className="stat-value">{result.model_ref || '—'}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Run id</span>
                <span className="stat-value">{result.run_id || '—'}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Method</span>
                <span className="stat-value">{result.method || method}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Base model</span>
                <span className="stat-value">
                  {result.base_model || baseModel}
                </span>
              </div>
              <div className="stat stat-wide">
                <span className="stat-label">Metrics</span>
                <pre className="cell-output">
                  {JSON.stringify(result.metrics ?? {}, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Export for serving</h2>
          <span className="badge badge-egress">exports need approval</span>
        </div>
        <p className="muted">
          Produce a serving artifact and manifest. Moving weights out of the
          workspace still requires an approved export request.
        </p>
        <form className="create-form" onSubmit={handleExport}>
          <div className="field">
            <label htmlFor="ex-ref">Model ref</label>
            <input
              id="ex-ref"
              type="text"
              value={exportRef}
              onChange={(e) => setExportRef(e.target.value)}
              placeholder="e.g. model:claims-classifier:v1"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="ex-format">Format</label>
            <select
              id="ex-format"
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value)}
            >
              <option value="safetensors">safetensors</option>
              <option value="gguf">gguf</option>
              <option value="onnx">onnx</option>
            </select>
          </div>
          <button type="submit" className="btn-primary" disabled={exporting}>
            {exporting ? 'Exporting…' : 'Export'}
          </button>
        </form>

        {exportError ? (
          <p className="error" role="alert">
            {exportError}
          </p>
        ) : null}

        {exportResult ? (
          <div className="result-block">
            <div className="hardware-grid">
              <div className="stat">
                <span className="stat-label">Model ref</span>
                <span className="stat-value">
                  {exportResult.model_ref || '—'}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Format</span>
                <span className="stat-value">{exportResult.format || '—'}</span>
              </div>
            </div>
            {exportResult.serving_command &&
            exportResult.serving_command.length ? (
              <div className="field">
                <label>Serving command</label>
                <pre className="cell-output">
                  {exportResult.serving_command.join(' ')}
                </pre>
              </div>
            ) : null}
            <div className="field">
              <label>Serving manifest</label>
              <pre className="cell-output">
                {JSON.stringify(exportResult.serving_manifest ?? {}, null, 2)}
              </pre>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

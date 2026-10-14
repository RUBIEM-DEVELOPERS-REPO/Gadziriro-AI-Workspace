import { useState } from 'react'
import { api, ApiError } from '../api/client.ts'

// The backend may return raw markdown, a JSON {markdown} wrapper, or a card
// object. Normalise all three into a readable string.
function extractMarkdown(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed) as unknown
      if (
        parsed &&
        typeof parsed === 'object' &&
        'markdown' in parsed &&
        typeof (parsed as { markdown: unknown }).markdown === 'string'
      ) {
        return (parsed as { markdown: string }).markdown
      }
      // A card object with no markdown field — pretty-print it.
      return JSON.stringify(parsed, null, 2)
    } catch {
      // Not JSON after all; fall through to raw.
    }
  }
  return raw
}

export default function ModelCard() {
  const [name, setName] = useState('')
  const [version, setVersion] = useState('')
  const [card, setCard] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleLoad(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !version.trim()) return
    setLoading(true)
    setError(null)
    setCard(null)
    try {
      const raw = await api.modelCard(name.trim(), version.trim())
      setCard(extractMarkdown(raw))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Failed to load the model card.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="admin">
      <div className="panel">
        <h2>Model card</h2>
        <p className="muted">
          Render the documentation card for a registered model version (FR-36).
        </p>
        <form className="create-form" onSubmit={handleLoad}>
          <div className="field">
            <label htmlFor="mc-name">Name</label>
            <input
              id="mc-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. classifier"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="mc-version">Version</label>
            <input
              id="mc-version"
              type="text"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="e.g. v1"
              required
            />
          </div>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Loading…' : 'View card'}
          </button>
        </form>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {card !== null ? (
          card ? (
            <pre className="cell-output model-card">{card}</pre>
          ) : (
            <p className="muted">This model card is empty.</p>
          )
        ) : null}
      </div>
    </section>
  )
}

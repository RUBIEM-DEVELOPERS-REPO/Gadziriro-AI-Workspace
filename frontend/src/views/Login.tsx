import { useState, type FormEvent } from 'react'
import { api, ApiError, type PrincipalOut } from '../api/client.ts'

interface Props {
  onLoggedIn: (principal: PrincipalOut) => void
}

export default function Login({ onLoggedIn }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.login(username, password)
      // Re-load the canonical principal from /me after a successful login.
      const principal = await api.me()
      onLoggedIn(principal)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? 'Invalid username or password.' : err.message)
      } else {
        setError('Could not reach the gateway.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-card">
      <h1 className="login-title">Gadziriro AI Workspace</h1>
      <p className="muted">Sign in to your private, sealed workspace.</p>
      <form onSubmit={handleSubmit} className="form">
        <div className="field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

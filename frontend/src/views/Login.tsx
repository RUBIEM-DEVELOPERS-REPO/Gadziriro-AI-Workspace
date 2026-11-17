import { useState, type FormEvent } from 'react'
import { useT } from '../i18n/index.ts'
import { api, ApiError, type PrincipalOut } from '../api/client.ts'

interface Props {
  onLoggedIn: (principal: PrincipalOut) => void
}

export default function Login({ onLoggedIn }: Props) {
  const { t } = useT()
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
        setError(err.status === 401 ? t('login.invalid') : err.message)
      } else {
        setError(t('login.unreachable'))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-card">
      <h1 className="login-title">Gadziriro AI Workspace</h1>
      <p className="muted">{t('login.subtitle')}</p>
      <form onSubmit={handleSubmit} className="form">
        <div className="field">
          <label htmlFor="username">{t('login.username')}</label>
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
          <label htmlFor="password">{t('login.password')}</label>
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
          {busy ? t('common.signingIn') : t('common.login')}
        </button>
      </form>
    </div>
  )
}

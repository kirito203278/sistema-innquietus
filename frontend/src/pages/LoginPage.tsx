import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Logo from '../components/Logo'
import { CampoPassword } from '../components/ui'

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError(null); setCargando(true)
    try { await login(username, password) }
    catch (err) { setError(err instanceof ApiError ? err.message : 'No se pudo iniciar sesión') }
    finally { setCargando(false) }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(160deg, var(--inn-purple-900), var(--inn-purple-700) 55%, var(--inn-purple-500))' }}>
      <form onSubmit={enviar} className="card" style={{ width: 380, maxWidth: '92vw', padding: 36 }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ margin: '0 auto 14px', width: 60, filter: 'drop-shadow(var(--shadow-md))' }}><Logo size={60} /></div>
          <h1 style={{ fontSize: 20, margin: '0 0 4px' }}>INNquietus</h1>
          <p style={{ margin: 0, color: 'var(--ink-500)', fontSize: 13 }}>Control de clientes y paquetes</p>
        </div>
        <div className="field"><label htmlFor="username">Usuario</label>
          <input id="username" type="text" autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></div>
        <div className="field"><label htmlFor="password">Contraseña</label>
          <CampoPassword id="password" autoComplete="current-password" value={password} onChange={setPassword} /></div>
        {error && <p className="error-text" style={{ marginBottom: 14 }}>{error}</p>}
        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={cargando}>
          {cargando ? <span className="spinner" /> : 'Entrar'}
        </button>
      </form>
    </div>
  )
}

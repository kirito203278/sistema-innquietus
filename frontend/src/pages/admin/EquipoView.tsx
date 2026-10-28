import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { UsuarioEquipo } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { BotonCopiar, CampoPassword, Cargando, ErrorTexto, Modal, passwordValida, sugerirPassword } from '../../components/ui'
import { fecha } from '../../util'

interface Resultado { titulo: string; username: string; mensaje: string }

export default function EquipoView({ onCambio }: { onCambio: () => void }) {
  const { user, puedeEscribir } = useAuth()
  const [lista, setLista] = useState<UsuarioEquipo[] | null>(null)
  const [alta, setAlta] = useState(false)
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [reseteando, setReseteando] = useState<UsuarioEquipo | null>(null)
  const [baja, setBaja] = useState<UsuarioEquipo | null>(null)
  const cargar = useCallback(() => api.get<UsuarioEquipo[]>('/usuarios').then(setLista), [])
  useEffect(() => { cargar() }, [cargar])

  if (!lista) return <Cargando />
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <div><h1 className="page-title">Equipo</h1><p className="page-sub" style={{ margin: 0 }}>CMs y administradores. Tú eliges la contraseña de cada persona al crearla o resetearla (mínimo 8 caracteres).</p></div>
        {puedeEscribir && <button className="btn btn-primary right" onClick={() => setAlta(true)}>+ Agregar usuario</button>}
      </div>
      <div className="card table-scroll" style={{ marginTop: 18 }}><table className="data-table"><thead><tr><th>Nombre</th><th>Usuario</th><th>Rol</th><th>Estado</th><th className="num">Clientes activos</th><th className="num">No renovados</th><th>Alta</th><th></th></tr></thead><tbody>
        {lista.map((u) => (
          <tr key={u.id} style={{ opacity: u.activo ? 1 : 0.55 }}>
            <td><strong>{u.nombre}</strong>{u.id === user?.id && <span className="badge badge-purple" style={{ marginLeft: 6 }}>tú</span>}</td><td>{u.username}</td>
            <td>{u.rol === 'cm' ? 'CM' : u.solo_lectura ? 'Admin · solo lectura' : 'Admin'}</td>
            <td>{u.activo ? <span className="badge badge-good">Activo</span> : <span className="badge badge-neutral">De baja</span>}</td>
            <td className="num">{u.rol === 'cm' ? u.clientes_activos : '—'}</td><td className="num">{u.rol === 'cm' ? u.clientes_no_renovados : '—'}</td><td>{fecha(u.creado_en)}</td>
            <td className="num" style={{ whiteSpace: 'nowrap' }}>{puedeEscribir && u.activo && <>
              <button className="btn btn-secondary btn-sm" onClick={() => setReseteando(u)}>Cambiar contraseña</button>{' '}
              {u.id !== user?.id && <button className="btn btn-danger btn-sm" onClick={() => setBaja(u)}>Dar de baja</button>}</>}</td></tr>))}
      </tbody></table></div>
      {alta && <Alta onClose={() => setAlta(false)} onHecho={(r) => { setAlta(false); setResultado(r); cargar(); onCambio() }} />}
      {reseteando && <Reset u={reseteando} onClose={() => setReseteando(null)} onHecho={(r) => { setReseteando(null); setResultado(r) }} />}
      {baja && <Baja u={baja} cms={lista.filter((x) => x.rol === 'cm' && x.activo && x.id !== baja.id)} onClose={() => setBaja(null)} onHecho={() => { setBaja(null); cargar(); onCambio() }} />}
      {resultado && (
        <Modal title={resultado.titulo} width={460}>
          <p style={{ marginTop: 0 }}>Usuario: <strong>{resultado.username}</strong> <BotonCopiar texto={resultado.username} /></p>
          <div className="callout callout-info" style={{ marginTop: 0 }}>{resultado.mensaje}</div>
          <div style={{ textAlign: 'right' }}><button className="btn btn-primary" onClick={() => setResultado(null)}>Listo</button></div>
        </Modal>)}
    </div>
  )
}

function CampoClave({ valor, setValor }: { valor: string; setValor: (v: string) => void }) {
  return (
    <div className="field"><label>Contraseña (la eliges tú)</label>
      <CampoPassword value={valor} onChange={setValor} placeholder="Mínimo 8 caracteres" />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setValor(sugerirPassword())}>Sugerir una</button>
        <span className="muted" style={{ fontSize: 12 }}>Usa «Ver» para revisar lo escrito antes de crear.</span>
      </div>
      {valor !== '' && !passwordValida(valor) && <p className="error-text">Debe tener entre 8 y 72 caracteres y no empezar ni terminar con espacios.</p>}
    </div>
  )
}

function Alta({ onClose, onHecho }: { onClose: () => void; onHecho: (r: Resultado) => void }) {
  const [nombre, setNombre] = useState('')
  const [rol, setRol] = useState<'cm' | 'admin'>('cm')
  const [soloLectura, setSoloLectura] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  async function crear() {
    setError(null)
    try {
      const r = await api.post<{ username: string }>('/usuarios', { nombre, rol, solo_lectura: rol === 'admin' && soloLectura, password })
      onHecho({ titulo: 'Usuario creado', username: r.username, mensaje: 'Entrégale a la persona su usuario y la contraseña que elegiste. Por seguridad el sistema no vuelve a mostrar contraseñas; si se olvida, la cambias desde aquí.' })
    } catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo crear') }
  }
  return (
    <Modal title="Agregar usuario" onClose={onClose} width={480}>
      <div className="field"><label>Nombre completo</label><input type="text" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus placeholder="Ej. María López" /></div>
      <div className="field"><label>Rol</label>
        <div className="segmented light full"><button className={rol === 'cm' ? 'active' : ''} onClick={() => setRol('cm')}>CM</button><button className={rol === 'admin' ? 'active' : ''} onClick={() => setRol('admin')}>Administrador</button></div></div>
      {rol === 'admin' && <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontWeight: 600, marginBottom: 14 }}><input type="checkbox" style={{ width: 'auto' }} checked={soloLectura} onChange={(e) => setSoloLectura(e.target.checked)} /> Solo lectura (ve y descarga reportes, no edita)</label>}
      <CampoClave valor={password} setValor={setPassword} />
      <ErrorTexto texto={error} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" disabled={nombre.trim().length < 2 || !passwordValida(password)} onClick={crear}>Crear usuario</button></div>
    </Modal>
  )
}

function Reset({ u, onClose, onHecho }: { u: UsuarioEquipo; onClose: () => void; onHecho: (r: Resultado) => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  async function guardar() {
    setError(null)
    try {
      await api.post(`/usuarios/${u.id}/reset-password`, { password })
      onHecho({ titulo: 'Contraseña cambiada', username: u.username, mensaje: 'La contraseña anterior ya no sirve. Entrégale la nueva a la persona.' })
    } catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo cambiar') }
  }
  return (
    <Modal title={`Nueva contraseña para ${u.nombre}`} onClose={onClose} width={460}>
      <CampoClave valor={password} setValor={setPassword} />
      <ErrorTexto texto={error} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" disabled={!passwordValida(password)} onClick={guardar}>Cambiar contraseña</button></div>
    </Modal>
  )
}

function Baja({ u, cms, onClose, onHecho }: { u: UsuarioEquipo; cms: UsuarioEquipo[]; onClose: () => void; onHecho: () => void }) {
  const total = u.clientes_activos + u.clientes_no_renovados
  const [destino, setDestino] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  async function enviar() {
    setError(null)
    try { await api.post(`/usuarios/${u.id}/baja`, { migrar_a_cm_id: destino ? Number(destino) : null }); onHecho() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo dar de baja') }
  }
  const necesitaDestino = u.rol === 'cm' && total > 0
  return (
    <Modal title={`Dar de baja a ${u.nombre}`} onClose={onClose} width={500}>
      {necesitaDestino ? (
        <>
          <div className="callout callout-warn">Tiene <strong>{total} cliente(s)</strong> ({u.clientes_activos} activos, {u.clientes_no_renovados} en No renovados). No se puede dar de baja dejándolos sueltos: su cartera completa pasa a otro CM, con toda su información.</div>
          <div className="field"><label>Pasar toda su cartera a…</label>
            <select value={destino} onChange={(e) => setDestino(e.target.value)}>
              <option value="">Elige un CM…</option>{cms.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select>
            <span className="muted" style={{ fontSize: 12 }}>¿Quieres repartirlos entre varios CM? Reasígnalos primero desde Cartera y vuelve aquí.</span></div>
        </>) : <p style={{ marginTop: 0 }}>{u.rol === 'cm' ? 'No tiene clientes que migrar.' : 'Dejará de poder entrar al sistema.'} Esta acción queda en la bitácora.</p>}
      <ErrorTexto texto={error} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-danger" disabled={necesitaDestino && !destino} onClick={enviar}>Dar de baja</button></div>
    </Modal>
  )
}

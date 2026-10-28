import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ClienteFicha as Ficha, Paquete, PaqueteDetalle, Recordatorio } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { RecordatorioModal } from '../../components/NotificationBell'
import { Cargando, CampoPassword, ErrorTexto, Progreso, Semaforo, copiar, useToast } from '../../components/ui'
import { CAMPANA_ESTADO_BADGE, ESTADO_LABEL, SEMAFORO_LABEL, TIPO_CAMPANA_LABEL, dinero, diasTexto, fecha, hoyIso, sumarDias } from '../../util'
import { Rendimiento } from '../campanas/CampanaDetalle'
import { NuevaCampanaModal } from '../campanas/modalesCampana'
import { AgregarPaqueteModal, ConfirmarRenovacionModal, EditarPaqueteModal, NoRenovarModal } from './modales'

const msg = (e: unknown, def: string) => (e instanceof ApiError ? e.message : def)
const BADGE_ESTADO: Record<string, string> = { activo: 'badge-neutral', por_vencer: 'badge-yellow', vencido: 'badge-bad', renovado: 'badge-good', archivado: 'badge-neutral', eliminado: 'badge-neutral' }

export default function ClienteFicha({ clienteId, paqueteInicial, onChanged, onDeleted, onVolver, onAbrirCampana }: {
  clienteId: number; paqueteInicial?: number | null; onChanged: () => void; onDeleted: () => void; onVolver?: () => void
  onAbrirCampana?: (campanaId: number) => void
}) {
  const { puedeEscribir, user, esCm } = useAuth()
  const [ficha, setFicha] = useState<Ficha | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [paqueteId, setPaqueteId] = useState<number | null>(paqueteInicial ?? null)
  const [toast, avisar] = useToast()
  const [modal, setModal] = useState<'agregar' | 'campana' | null>(null)

  const cargar = useCallback(async (seleccionar?: number | null) => {
    try {
      const f = await api.get<Ficha>(`/clientes/${clienteId}`)
      setFicha(f)
      setPaqueteId((prev) => {
        const quiero = seleccionar ?? prev
        const todos = [...f.paquetes, ...f.historial]
        if (quiero && todos.some((p) => p.id === quiero)) return quiero
        return f.paquetes[0]?.id ?? f.historial[0]?.id ?? null
      })
    } catch (e) { setError(msg(e, 'No se pudo cargar el cliente')) }
  }, [clienteId])

  useEffect(() => { setFicha(null); setError(null); cargar(paqueteInicial) }, [clienteId, paqueteInicial, cargar])

  if (error) return <div className="card" style={{ padding: 24 }}><ErrorTexto texto={error} />{onVolver && <button className="btn btn-secondary" onClick={onVolver}>Volver</button>}</div>
  if (!ficha) return <Cargando />

  const recargarTodo = async (sel?: number | null) => { await cargar(sel); onChanged() }
  const enNoRenovados = ficha.estado === 'no_renovado'
  const hayBloqueo = ficha.paquetes.some((p) => p.bloqueado)
  const escribe = puedeEscribir && !hayBloqueo

  return (
    <div>
      {onVolver && <button className="btn btn-ghost btn-sm" onClick={onVolver} style={{ marginBottom: 8 }}>← Volver</button>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4, flexWrap: 'wrap' }}>
        <h1 className="page-title" style={{ margin: 0 }}>{ficha.nombre}</h1>
        {enNoRenovados && <span className="badge badge-bad">No renovado</span>}
        {escribe && !enNoRenovados && ficha.paquetes.length === 0 && <button className="btn btn-secondary btn-sm right" onClick={() => setModal('agregar')}>+ Agregar paquete</button>}
      </div>
      {user?.rol === 'admin' && puedeEscribir && <p className="muted" style={{ margin: '0 0 8px', fontSize: 13 }}>Operas por cuenta del CM: tus acciones quedan en la bitácora.</p>}
      {puedeEscribir && ficha.paquetes.filter((p) => p.bloqueado).map((p) => <VentanaDecision key={p.id} p={p} ficha={ficha} avisar={avisar} onHecho={(sel) => recargarTodo(sel)} />)}
      {!puedeEscribir && hayBloqueo && <div className="callout callout-bad"><strong>Contrato terminado sin decisión.</strong> Tu cuenta es de solo lectura: lo resuelve el CM.</div>}
      {enNoRenovados && <div className="callout callout-warn">Este cliente está en «No renovados» desde el {fecha(ficha.no_renovado_desde)}. Para reactivarlo usa <strong>No renovados → Reingresar</strong>.</div>}

      <DatosCliente ficha={ficha} puedeEscribir={escribe} puedeEliminar={user?.rol === 'admin' && puedeEscribir && enNoRenovados}
        onGuardado={(f) => { setFicha(f); onChanged(); avisar('Datos guardados') }} onEliminado={onDeleted} />

      <div className="section-title">Paquetes</div>
      <Paquetes ficha={ficha} paqueteId={paqueteId} setPaqueteId={setPaqueteId} puedeEscribir={puedeEscribir} hayBloqueo={hayBloqueo} recargar={recargarTodo}
        sinPaquetes={ficha.paquetes.length === 0} avisar={avisar} onClienteGone={onDeleted} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div className="section-title" style={{ margin: 0 }}>Campañas</div>
        {escribe && !enNoRenovados && <button className="btn btn-secondary btn-sm right" onClick={() => setModal('campana')}>+ Agregar campaña</button>}
      </div>
      {ficha.campanas.length === 0 ? (
        <div className="card" style={{ padding: 16, marginTop: 8 }}><p className="muted" style={{ margin: 0 }}>
          Este cliente aún no tiene campañas.{escribe && !enNoRenovados ? ' Agrega la primera con «+ Agregar campaña»: queda ligada a su paquete vigente.' : ''}</p></div>
      ) : (
        <div className="card table-scroll" style={{ marginTop: 8 }}><table className="data-table"><thead><tr>
          <th>Campaña</th><th>Tipo</th><th>Estado</th><th>Semáforo</th><th>Renovación</th><th></th></tr></thead><tbody>
          {ficha.campanas.map((c) => (
            <tr key={c.id} className="clickable-row" onClick={() => onAbrirCampana?.(c.id)}>
              <td><strong>{c.nombre}</strong>{c.lugar && <div className="muted" style={{ fontSize: 12 }}>{c.lugar}</div>}</td><td>{TIPO_CAMPANA_LABEL[c.tipo]}</td>
              <td><span className={`badge ${CAMPANA_ESTADO_BADGE[c.estado]}`}>{c.estado}</span></td><td><Rendimiento valor={c.rendimiento} /></td>
              <td>{fecha(c.fecha_renovacion)}</td><td><button className="btn btn-ghost btn-sm">Abrir</button></td></tr>))}
        </tbody></table></div>)}

      {ficha.historial.length > 0 && (
        <>
          <div className="section-title">Historial de ciclos y paquetes archivados</div>
          <div className="card table-scroll"><table className="data-table"><thead><tr>
            <th>Paquete</th><th>Tipo</th><th>Vencía</th>{!esCm && <><th className="num">Costo</th><th className="num">Pagado</th></>}<th>Estado</th><th></th></tr></thead><tbody>
            {ficha.historial.map((p) => (
              <tr key={p.id} className="clickable-row" onClick={() => { setPaqueteId(p.id); window.scrollTo({ top: 0 }) }}>
                <td>{p.paquete}</td><td>{p.tipo}</td><td>{fecha(p.fecha_renovacion)}</td>
                {!esCm && <><td className="num">{dinero(p.costo)}</td>
                <td className="num">{dinero(p.pagado)}{p.restante > 0 && <span className="badge badge-bad" style={{ marginLeft: 6 }}>debe {dinero(p.restante)}</span>}</td></>}
                <td><span className={`badge ${BADGE_ESTADO[p.estado]}`}>{ESTADO_LABEL[p.estado]}</span></td>
                <td><button className="btn btn-ghost btn-sm">Ver</button></td></tr>))}
          </tbody></table></div>
        </>
      )}
      {modal === 'agregar' && <AgregarPaqueteModal clienteId={ficha.id} onClose={() => setModal(null)} onHecho={(id) => { setModal(null); recargarTodo(id); avisar('Paquete agregado') }} />}
      {modal === 'campana' && <NuevaCampanaModal clienteId={ficha.id} clienteNombre={ficha.nombre} onClose={() => setModal(null)}
        onHecho={(id) => { setModal(null); recargarTodo(); avisar('Campaña creada'); onAbrirCampana?.(id) }} />}
      {toast}
    </div>
  )
}

function DatosCliente({ ficha, puedeEscribir, puedeEliminar, onGuardado, onEliminado }: {
  ficha: Ficha; puedeEscribir: boolean; puedeEliminar: boolean; onGuardado: (f: Ficha) => void; onEliminado: () => void
}) {
  const base = { nombre: ficha.nombre, correo_fb: ficha.correo_fb ?? '', correo_contacto: ficha.correo_contacto ?? '', telefono: ficha.telefono ?? '', observaciones: ficha.observaciones ?? '',
    tipo_cuenta: ficha.tipo_cuenta ?? '', metodo_pago: ficha.metodo_pago ?? '', forma_pago: ficha.forma_pago ?? '' }
  const [d, setD] = useState(base)
  const [nuevaPwd, setNuevaPwd] = useState('')
  const [cambiandoPwd, setCambiandoPwd] = useState(false)
  const [pwdVisible, setPwdVisible] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [borrando, setBorrando] = useState(false)
  const [confirma, setConfirma] = useState('')
  const sucio = JSON.stringify(d) !== JSON.stringify(base) || nuevaPwd !== ''
  const set = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value })

  async function guardar() {
    setGuardando(true); setError(null)
    try {
      const f = await api.patch<Ficha>(`/clientes/${ficha.id}`, { ...d, ...(nuevaPwd ? { password_fb: nuevaPwd } : {}) })
      setNuevaPwd(''); setCambiandoPwd(false); setPwdVisible(null); onGuardado(f)
    } catch (e) { setError(msg(e, 'No se pudo guardar')) } finally { setGuardando(false) }
  }
  async function ver() {
    if (pwdVisible !== null) { setPwdVisible(null); return }
    try { setPwdVisible((await api.post<{ password: string }>(`/clientes/${ficha.id}/password-fb/ver`)).password) } catch (e) { setError(msg(e, 'No se pudo mostrar')) }
  }
  async function eliminar() {
    try { await api.del(`/clientes/${ficha.id}?confirmar_nombre=${encodeURIComponent(confirma)}`); onEliminado() } catch (e) { setError(msg(e, 'No se pudo eliminar')) }
  }
  const ro = !puedeEscribir
  return (
    <div className="card" style={{ padding: 20, marginTop: 12 }}>
      <div className="grid-2">
        <div className="field"><label>Nombre del cliente</label><input type="text" value={d.nombre} onChange={set('nombre')} disabled={ro} /></div>
        <div className="field"><label>Teléfono personal</label><input type="text" value={d.telefono} onChange={set('telefono')} disabled={ro} /></div>
        <div className="field"><label>Correo de Facebook</label><input type="text" value={d.correo_fb} onChange={set('correo_fb')} disabled={ro} /></div>
        <div className="field"><label>Contraseña de Facebook</label>
          {ficha.tiene_password_fb && !cambiandoPwd ? (
            <div style={{ display: 'flex', gap: 6 }}>
              <input type="text" readOnly value={pwdVisible ?? '••••••••••'} style={{ fontFamily: pwdVisible ? 'monospace' : undefined }} />
              <button className="btn btn-secondary btn-sm" onClick={ver}>{pwdVisible !== null ? 'Ocultar' : 'Ver'}</button>
              {pwdVisible !== null && <button className="btn btn-secondary btn-sm" onClick={() => copiar(pwdVisible)}>Copiar</button>}
            </div>
          ) : (
            <CampoPassword placeholder={ficha.tiene_password_fb ? 'Escribe la contraseña nueva' : 'Sin contraseña guardada'} value={nuevaPwd} onChange={setNuevaPwd} disabled={ro} />
          )}
          {!ro && ficha.tiene_password_fb && !cambiandoPwd && <button className="btn btn-ghost btn-sm" style={{ marginTop: 4, padding: '2px 6px' }} onClick={() => { setCambiandoPwd(true); setPwdVisible(null) }}>Cambiar contraseña</button>}
          {!ro && cambiandoPwd && <button className="btn btn-ghost btn-sm" style={{ marginTop: 4, padding: '2px 6px' }} onClick={() => { setCambiandoPwd(false); setNuevaPwd('') }}>Cancelar cambio</button>}
        </div>
        {ficha.cuenta_compartida_con.length > 0 && <div className="muted" style={{ gridColumn: '1 / -1', fontSize: 13, marginTop: -6 }}>
          Esta cuenta de Facebook también la usan: <strong>{ficha.cuenta_compartida_con.map((x) => x.nombre).join(', ')}</strong>.
          Cambiar la contraseña la cambia para todos; si cambias el correo, este cliente pasa a otra cuenta.</div>}
        <div className="field"><label>Correo de contacto</label><input type="text" value={d.correo_contacto} onChange={set('correo_contacto')} disabled={ro} /></div>
        <div className="field"><label>Tipo de cuenta publicitaria</label><input type="text" value={d.tipo_cuenta} onChange={set('tipo_cuenta')} disabled={ro} placeholder="Ej. Empresarial / Personal" /></div>
        <div className="field"><label>Método de pago de la publicidad</label><input type="text" value={d.metodo_pago} onChange={set('metodo_pago')} disabled={ro} placeholder="Ej. Tarjeta / Transferencia" /></div>
        <div className="field"><label>Forma de pago</label><input type="text" value={d.forma_pago} onChange={set('forma_pago')} disabled={ro} placeholder="Ej. Mensual / Depósito" /></div>
      </div>
      <div className="field"><label>Observaciones</label><textarea rows={2} value={d.observaciones} onChange={set('observaciones')} disabled={ro} /></div>
      <ErrorTexto texto={error} />
      {!ro && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" disabled={!sucio || guardando || !d.nombre.trim()} onClick={guardar}>Guardar cambios</button>
          {sucio && <button className="btn btn-ghost" onClick={() => { setD(base); setNuevaPwd(''); setCambiandoPwd(false) }}>Descartar</button>}
          <span className="right" />
          {!puedeEliminar ? null : !borrando ? <button className="btn btn-ghost btn-sm" onClick={() => setBorrando(true)}>Eliminar cliente…</button> : (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="text" placeholder={`Escribe «${ficha.nombre}»`} value={confirma} onChange={(e) => setConfirma(e.target.value)} style={{ width: 240 }} />
              <button className="btn btn-danger btn-sm" disabled={confirma !== ficha.nombre} onClick={eliminar}>Eliminar</button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setBorrando(false); setConfirma('') }}>Cancelar</button>
            </div>)}
        </div>
      )}
    </div>
  )
}

function Paquetes({ ficha, paqueteId, setPaqueteId, puedeEscribir, hayBloqueo, recargar, sinPaquetes, avisar, onClienteGone }: {
  ficha: Ficha; paqueteId: number | null; setPaqueteId: (id: number) => void; puedeEscribir: boolean; hayBloqueo: boolean
  recargar: (sel?: number | null) => Promise<void>; sinPaquetes: boolean; avisar: (t: string) => void; onClienteGone: () => void
}) {
  const { user, esCm } = useAuth()
  const [det, setDet] = useState<PaqueteDetalle | null>(null)
  const [errorDet, setErrorDet] = useState<string | null>(null)
  const [modal, setModal] = useState<'no' | 'editar' | 'confirmar' | null>(null)
  const [recordatorio, setRecordatorio] = useState<Recordatorio | null>(null)

  const cargarDet = useCallback(async () => {
    if (paqueteId == null) { setDet(null); return }
    try { setDet(await api.get<PaqueteDetalle>(`/paquetes/${paqueteId}`)); setErrorDet(null) } catch (e) { setErrorDet(msg(e, 'No se pudo cargar el paquete')) }
  }, [paqueteId])
  useEffect(() => { cargarDet() }, [cargarDet])

  const cambio = async (sel?: number | null) => { await recargar(sel ?? paqueteId); await cargarDet() }
  const vigente = det ? ficha.paquetes.some((p) => p.id === det.id) : false
  const escribe = puedeEscribir && !hayBloqueo

  if (sinPaquetes && !det) return <div className="card" style={{ padding: 20 }}><p className="muted" style={{ margin: 0 }}>Este cliente no tiene paquete vigente (un cliente tiene un solo paquete).</p></div>
  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="field" style={{ maxWidth: 520 }}>
        <label>Paquete del cliente</label>
        <select value={paqueteId ?? ''} onChange={(e) => setPaqueteId(Number(e.target.value))}>
          {ficha.paquetes.map((p) => <option key={p.id} value={p.id}>{p.paquete} · {p.tipo} — renueva {fecha(p.fecha_renovacion)}</option>)}
          {det && !vigente && <option value={det.id}>(Historial) {det.paquete} · {ESTADO_LABEL[det.estado]} — {fecha(det.fecha_renovacion)}</option>}
        </select>
      </div>
      <ErrorTexto texto={errorDet} />
      {det && (
        <>
          {!vigente && <div className="callout callout-info">Estás viendo un ciclo del historial ({ESTADO_LABEL[det.estado].toLowerCase()}). {!esCm && det.restante > 0 ? 'Aún tiene saldo por cobrar: puedes seguir registrando pagos.' : ''}</div>}
          <div className="kv" style={{ margin: '8px 0 14px' }}>
            <div><div className="k">Tipo</div><div className="v">{det.tipo}</div></div>
            <div><div className="k">Paquete</div><div className="v">{det.paquete}</div></div>
            {!esCm && <>
              <div><div className="k">Costo</div><div className="v">{dinero(det.costo)}</div></div>
              <div><div className="k">Pagado</div><div className="v" style={{ color: 'var(--good)' }}>{dinero(det.pagado)}</div></div>
              <div><div className="k">Restante</div><div className="v" style={{ color: det.restante > 0 ? 'var(--warn)' : 'var(--good)' }}>{dinero(det.restante)}</div></div>
            </>}
            <div><div className="k">Fecha de renovación</div><div className="v">{fecha(det.fecha_renovacion)}</div></div>
            <div><div className="k">Renovaciones con este paquete</div><div className="v">{det.veces_renovado}</div></div>
            <div><div className="k">Estado</div><div className="v"><span className={`badge ${BADGE_ESTADO[det.estado_efectivo]}`}>{ESTADO_LABEL[det.estado_efectivo]}</span></div></div>
          </div>
          {!esCm && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
              <div style={{ flex: 1 }}><Progreso pct={det.avance_pct} /></div>
              <strong style={{ fontSize: 13, minWidth: 120, textAlign: 'right' }}>{dinero(det.pagado)} de {dinero(det.costo)}</strong>
            </div>)}
          {escribe && vigente && <div style={{ textAlign: 'right' }}><button className="btn btn-ghost btn-sm" onClick={() => setModal('editar')}>Editar paquete</button></div>}

          {!esCm && <Pagos det={det} puedeEscribir={escribe} alCambiar={cambio} avisar={avisar} />}
          <Prorroga det={det} sinMontos={esCm} />

          <div className="section-title">Renovación</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <Semaforo valor={det.semaforo} conTexto />
            {vigente && <span className="muted" style={{ fontSize: 13 }}>· {diasTexto(det.dias_para_renovar)} ({fecha(det.fecha_renovacion)}, termina a las 11:59 pm)</span>}
            {det.no_renovara && <span className="badge badge-neutral">Marcado: no renovará</span>}
            {!det.no_renovara && det.renovacion_decision !== 'pendiente' && <span className="badge badge-purple">Decisión: {det.renovacion_decision === 'si' ? 'renovó' : 'no renovó'}</span>}
          </div>
          {det.prorroga_activa && <div className="callout callout-info">Con la prórroga activa no hay nada que decidir: <strong>en cuanto se pague lo que falta{esCm ? '' : ` (${dinero(det.restante)})`} el paquete se renueva solo</strong> (con el paquete que se eligió al confirmar). Si no se completa el {fecha(det.prorroga_hasta)}, el cliente pasa a No renovados.
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>El nuevo contrato <strong>conserva la misma fecha de renovación</strong> ({fecha(det.fecha_renovacion)}); no se recorre al día en que termine de pagar.</div></div>}
          {vigente && det.estado_efectivo === 'por_vencer' && <div className="callout callout-warn">Este paquete renueva pronto: pregúntale al cliente si renueva.</div>}
          {det.no_renovara && (
            <div className="callout callout-info">Se archivará solo al terminar su contrato ({fecha(det.fecha_renovacion)} a las 11:59 pm) y, si es su último paquete, el cliente pasará a «No renovados».
              {escribe && <button className="btn btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={async () => { try { await api.post(`/paquetes/${det.id}/revertir-decision`); await cambio(); avisar('Marca deshecha') } catch (e) { avisar(msg(e, 'No se pudo deshacer')) } }}>Deshacer</button>}</div>)}
          {det.confirmo_renovacion && !det.prorroga_activa && (
            <div className="callout callout-warn">
              <strong>Confirmó que renovará</strong> el {fecha(det.confirmado_en)}: ese día es el inicio del nuevo contrato.{esCm ? <> Si aún debe, en cuanto pague completo el paquete se renueva solo.
                Si no ha pagado al terminar el día {det.gracia_hasta ? fecha(det.gracia_hasta) : fecha(det.fecha_renovacion)} a las 11:59 pm, se bloquea y el administrador decidirá la prórroga (sin tolerancia).</> : det.restante > 0 ? <> Aún debe {dinero(det.restante)}; en cuanto pague completo el paquete se renueva solo.
                Si no ha pagado al terminar el día {det.gracia_hasta ? fecha(det.gracia_hasta) : fecha(det.fecha_renovacion)} a las 11:59 pm, se bloquea y se te preguntará por la prórroga (sin tolerancia).</> : ''}
              <div style={{ fontSize: 13, marginTop: 4 }}>Renovará con: {det.renovara_con && (det.renovara_con.paquete_id !== det.paquete_id || det.renovara_con.tipo_id !== det.tipo_id || (!esCm && Number(det.renovara_con.costo) !== Number(det.costo)))
                ? <><strong>otro paquete{esCm ? '' : ` (${dinero(det.renovara_con.costo)})`}</strong> — se aplica al concretarse la renovación</> : <strong>el mismo paquete{esCm ? '' : ` (${dinero(det.costo)})`}</strong>}.</div>
              {escribe && det.estado === 'activo' && !det.bloqueado && <button className="btn btn-ghost btn-sm" style={{ marginTop: 4 }} onClick={async () => { try { await api.post(`/paquetes/${det.id}/revertir-decision`); await cambio(); avisar('Confirmación deshecha') } catch (e) { avisar(msg(e, 'No se pudo deshacer')) } }}>Deshacer confirmación</button>}
            </div>)}
          {escribe && vigente && !det.no_renovara && !det.prorroga_activa && !det.bloqueado && (
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {!det.confirmo_renovacion && <button className="btn btn-primary" onClick={() => setModal('confirmar')}>Confirmó que renovará</button>}
              <button className="btn btn-secondary" onClick={() => setModal('no')}>No renovará</button>
            </div>)}
          {!esCm && det.restante > 0 && escribe && det.estado !== 'archivado' && (
            <div style={{ marginTop: 14 }}>
              <button className="btn btn-secondary btn-sm" onClick={async () => { try { setRecordatorio(await api.post<Recordatorio>(`/paquetes/${det.id}/recordatorio`)) } catch (e) { avisar(msg(e, 'No se pudo generar')) } }}>
                Mensaje de pago para el cliente</button>
            </div>)}
          {det.renovaciones.length > 0 && (
            <>
              <div className="section-title">Historial de renovaciones de este paquete</div>
              <table className="data-table"><thead><tr><th>Fecha</th>{!esCm && <><th className="num">Costo anterior</th><th className="num">Costo nuevo</th></>}<th>Cambio</th></tr></thead><tbody>
                {det.renovaciones.map((r) => <tr key={r.id}><td>{fecha(r.fecha)}</td>{!esCm && <><td className="num">{dinero(r.costo_anterior)}</td><td className="num">{dinero(r.costo_nuevo)}</td></>}
                  <td>{r.paquete_anterior_id === r.paquete_nuevo_id ? 'Mismo paquete' : 'Cambió de paquete'}</td></tr>)}
              </tbody></table>
            </>)}
          <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>Semáforo: {SEMAFORO_LABEL[det.semaforo]}. Ciclo del {fecha(det.fecha_inicio)} al {fecha(det.fecha_renovacion)}.</p>

          {modal === 'confirmar' && <ConfirmarRenovacionModal p={det as Paquete} sinMontos={esCm} onClose={() => setModal(null)} onHecho={(r) => { setModal(null); cambio(r.renovado_automaticamente); avisar(r.renovado_automaticamente ? 'Pagado y confirmado: se renovó' : 'Confirmado: falta el pago para renovar') }} />}
          {modal === 'editar' && <EditarPaqueteModal p={det as Paquete} esAdmin={user?.rol === 'admin'} onClose={() => setModal(null)} onHecho={() => { setModal(null); cambio(); avisar('Paquete actualizado') }} />}
          {modal === 'no' && <NoRenovarModal p={det as Paquete} nombreCliente={ficha.nombre} onClose={() => setModal(null)}
            onHecho={(r) => { setModal(null); if (r.cliente_eliminado) onClienteGone(); else { cambio(); avisar(r.cliente_a_no_renovados ? 'El cliente pasó a No renovados' : 'Paquete actualizado') } }} />}
          {recordatorio && <RecordatorioModal r={recordatorio} onClose={() => setRecordatorio(null)} />}
        </>
      )}
    </div>
  )
}

function Pagos({ det, puedeEscribir, alCambiar, avisar }: { det: PaqueteDetalle; puedeEscribir: boolean; alCambiar: (sel?: number | null) => Promise<void>; avisar: (t: string) => void }) {
  const [monto, setMonto] = useState('')
  const [fechaPago, setFechaPago] = useState(hoyIso())
  const [nota, setNota] = useState('')
  const [error, setError] = useState<string | null>(null)
  const puedePagar = puedeEscribir && ['activo', 'vencido', 'renovado'].includes(det.estado) && det.restante > 0

  async function registrar() {
    setError(null)
    try {
      const r = await api.post<{ renovado_automaticamente: number | null }>(`/paquetes/${det.id}/pagos`, { monto: Number(monto), fecha: fechaPago, nota: nota || null })
      setMonto(''); setNota('')
      await alCambiar(r.renovado_automaticamente)
      avisar(r.renovado_automaticamente ? 'Pagado completo: el paquete se renovó solo (ciclo nuevo desde hoy)' : 'Pago registrado')
    }
    catch (e) { setError(msg(e, 'No se pudo registrar el pago')) }
  }
  async function borrar(id: number) {
    if (!confirm('¿Borrar este pago? Queda en la bitácora.')) return
    try { await api.del(`/pagos/${id}`); await alCambiar() } catch (e) { avisar(msg(e, 'No se pudo borrar')) }
  }
  return (
    <>
      <div className="section-title">Pagos</div>
      {det.pagos.length === 0 ? <p className="muted" style={{ margin: '0 0 8px' }}>Aún no hay pagos registrados.</p> : (
        <table className="data-table"><thead><tr><th>Fecha</th><th className="num">Monto</th><th>Registró</th><th>Nota</th><th></th></tr></thead><tbody>
          {det.pagos.map((g) => <tr key={g.id}><td>{fecha(g.fecha)}</td><td className="num">{dinero(g.monto)}</td><td>{g.registrado_por_nombre ?? '—'}</td><td className="muted">{g.nota ?? ''}</td>
            <td>{puedeEscribir && <button className="btn btn-ghost btn-sm" title="Borrar pago" onClick={() => borrar(g.id)}>✕</button>}</td></tr>)}
        </tbody></table>)}
      {puedePagar && (
        <div className="row" style={{ marginTop: 10 }}>
          <div className="field" style={{ maxWidth: 160 }}><label>Monto (parcial o total)</label><input type="number" min="0" step="0.01" value={monto} onChange={(e) => setMonto(e.target.value)} placeholder={String(det.restante)} /></div>
          <div className="field" style={{ maxWidth: 170 }}><label>Fecha</label><input type="date" max={hoyIso()} value={fechaPago} onChange={(e) => setFechaPago(e.target.value)} /></div>
          <div className="field"><label>Nota (opcional)</label><input type="text" value={nota} onChange={(e) => setNota(e.target.value)} /></div>
          <button className="btn btn-primary" disabled={!Number(monto)} onClick={registrar}>Registrar pago</button>
          {det.restante > 0 && <button className="btn btn-ghost btn-sm" onClick={() => setMonto(String(det.restante))}>Pagar el total</button>}
        </div>)}
      <ErrorTexto texto={error} />
    </>
  )
}

function VentanaDecision({ p, ficha, onHecho, avisar }: { p: Paquete; ficha: Ficha; onHecho: (sel?: number | null) => void; avisar: (t: string) => void }) {
  const { esCm } = useAuth()
  const [modal, setModal] = useState<'no' | 'va' | null>(null)
  const [trabajando, setTrabajando] = useState(false)
  const op = p.opciones_bloqueo
  const confirmado = p.renovacion_decision === 'si'
  const puedeProrroga = op.includes('prorroga') && !esCm

  async function llamar(f: () => Promise<void>) {
    setTrabajando(true)
    try { await f() } catch (e) { avisar(msg(e, 'No se pudo completar')) } finally { setTrabajando(false) }
  }
  const prorroga = () => llamar(async () => { await api.post(`/paquetes/${p.id}/prorroga`); avisar('Prórroga activada: 5 días naturales'); onHecho() })

  return (
    <div className="callout callout-bad" style={{ padding: 18, marginTop: 14 }} role="alertdialog" aria-label="Decisión pendiente">
      <strong style={{ fontSize: 16 }}>Terminó el contrato de «{p.paquete}» el {fecha(p.fecha_renovacion)} a las 11:59 pm</strong>
      <p style={{ margin: '8px 0 4px' }}>
        {op.includes('va_a_renovar') && <>Aún no hay respuesta del cliente. <strong>¿Va a renovar o no?</strong></>}
        {op.includes('renovo') && <>El paquete está pagado por completo. <strong>¿Renovó?</strong></>}
        {op.includes('prorroga') && (esCm
          ? <>Confirmó que renovará pero <strong>quedó bloqueado por falta de pago</strong>. La prórroga la autoriza el administrador.</>
          : <>Confirmó que renovará pero <strong>aún debe {dinero(p.restante)}</strong>. <strong>¿Solicita prórroga o no renovó?</strong></>)}
        {!op.includes('prorroga') && confirmado && op.includes('no_renovo') && !op.includes('renovo') &&
          (esCm ? <>Ya usó su prórroga y sigue sin pagarse completo.</> : <>Ya usó su prórroga y sigue debiendo {dinero(p.restante)}.</>)}
      </p>
      <p className="muted" style={{ margin: '0 0 12px', fontSize: 13 }}>
        Este cliente queda en pausa hasta que se resuelva; <strong>con los demás clientes sigues trabajando normal</strong>.
        {p.limite_decision && <> Si no se decide, el {fecha(sumarDias(p.limite_decision, 1))} pasa automáticamente a No renovados.</>}
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {op.includes('va_a_renovar') && <button className="btn btn-primary" disabled={trabajando} onClick={() => setModal('va')}>Sí, va a renovar</button>}
        {op.includes('renovo') && <button className="btn btn-primary" disabled={trabajando} onClick={() => setModal('va')}>Renovó</button>}
        {puedeProrroga && <button className="btn btn-primary" disabled={trabajando} onClick={prorroga}>Solicitó prórroga (5 días)</button>}
        {op.includes('no_renovo') && <button className="btn btn-secondary" disabled={trabajando} onClick={() => setModal('no')}>No renovó</button>}
      </div>
      {op.includes('va_a_renovar') && <p className="muted" style={{ fontSize: 12, margin: '10px 0 0' }}>«Sí, va a renovar» marca <strong>hoy ({fecha(hoyIso())})</strong> como el inicio del nuevo contrato y habilita las funciones de este cliente el resto del día. No hay tolerancia de pago: a las 11:59 pm, si no ha pagado, {esCm ? 'el administrador decidirá la prórroga' : 'se te preguntará por la prórroga'} o si no renovó.</p>}
      {op.includes('prorroga') && (esCm
        ? <p className="muted" style={{ fontSize: 12, margin: '10px 0 0' }}>Avísale al administrador: solo él puede activar la prórroga de 5 días y registrar el pago. Mientras tanto, tú puedes marcar que no renovó.</p>
        : <p className="muted" style={{ fontSize: 12, margin: '10px 0 0' }}>La prórroga dura 5 días naturales desde hoy (la fecha es automática). En ese plazo se acepta el pago parcial o el resto y, al completarlo, el paquete se renueva solo.</p>)}
      {modal === 'va' && <ConfirmarRenovacionModal p={p} sinMontos={esCm} onClose={() => setModal(null)} onHecho={(r) => { setModal(null); avisar(r.renovado_automaticamente ? 'Renovado' : 'Confirmado: se habilitan las funciones de este cliente'); onHecho(r.renovado_automaticamente) }} />}
      {modal === 'no' && <NoRenovarModal p={p} nombreCliente={ficha.nombre} onClose={() => setModal(null)}
        onHecho={() => { setModal(null); avisar('Pasó a No renovados'); onHecho() }} />}
    </div>
  )
}

function Prorroga({ det, sinMontos }: { det: PaqueteDetalle; sinMontos: boolean }) {
  if (!det.prorroga_hasta) return null
  const pagado = sinMontos ? det.semaforo === 'verde' : det.restante <= 0
  return (
    <>
      <div className="section-title">Prórroga</div>
      <div className={`callout ${pagado ? 'callout-good' : det.prorroga_vencida ? 'callout-bad' : 'callout-warn'}`}>
        Prórroga de 5 días naturales activada el {fecha(det.prorroga_registrada_en)}, válida hasta el <strong>{fecha(det.prorroga_hasta)}</strong>.{' '}
        {sinMontos
          ? (pagado ? 'Ya se pagó completo.'
            : det.prorroga_vencida ? 'Venció sin pagarse completo: el cliente pasa a No renovados.'
            : `${diasTexto(det.prorroga_dias_restantes ?? 0)}. El administrador registra los pagos; al completarse, el paquete se renueva solo.`)
          : det.restante <= 0 ? 'Ya se pagó completo.'
          : det.prorroga_vencida ? `Venció con ${dinero(det.restante)} sin pagar: el cliente pasa a No renovados.`
          : `${diasTexto(det.prorroga_dias_restantes ?? 0)}. En este plazo se acepta el pago parcial o el resto (${dinero(det.restante)}); si no se completa, el cliente pasa solo a No renovados. Al pagar todo, se renueva automáticamente.`}
      </div>
    </>
  )
}

import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { CatalogoItem, Paquete } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { CampoPassword, ErrorTexto, Modal } from '../../components/ui'
import { dinero, fecha, hoyIso, sumarDias } from '../../util'

export function useCatalogos() {
  const [paquetes, setPaquetes] = useState<CatalogoItem[]>([])
  const [tipos, setTipos] = useState<CatalogoItem[]>([])
  useEffect(() => {
    api.get<CatalogoItem[]>('/catalogos/paquetes').then(setPaquetes)
    api.get<CatalogoItem[]>('/catalogos/tipos').then(setTipos)
  }, [])
  return { paquetes, tipos }
}

const msg = (e: unknown, def: string) => (e instanceof ApiError ? e.message : def)

function Botones({ onClose, onOk, okText, disabled, danger }: { onClose: () => void; onOk: () => void; okText: string; disabled?: boolean; danger?: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
      <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
      <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onOk} disabled={disabled}>{okText}</button>
    </div>
  )
}

export function CamposPaquete({ v, set, paquetes, tipos, sinCosto }: {
  v: { paquete_id: string; tipo_id: string; costo: string; fecha_inicio: string }
  set: (v: { paquete_id: string; tipo_id: string; costo: string; fecha_inicio: string }) => void
  paquetes: CatalogoItem[]; tipos: CatalogoItem[]; sinCosto?: boolean
}) {
  const elegido = paquetes.find((x) => x.id === Number(v.paquete_id))
  return (
    <>
      <div className="grid-2">
        <div className="field"><label>Paquete</label>
          <select value={v.paquete_id} onChange={(e) => set({ ...v, paquete_id: e.target.value })}>
            <option value="">Elige…</option>{paquetes.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </select></div>
        <div className="field"><label>Tipo</label>
          <select value={v.tipo_id} onChange={(e) => set({ ...v, tipo_id: e.target.value })}>
            <option value="">Elige…</option>{tipos.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select></div>
        {sinCosto ? (
          <div className="field"><label>Costo</label>
            <input type="text" readOnly value={elegido ? 'Lo fija el administrador' : 'Elige un paquete'} />
            <span className="muted" style={{ fontSize: 12 }}>El costo es el del catálogo; lo ajusta el administrador. Lo pagado empieza en cero.</span></div>
        ) : (
          <div className="field"><label>Costo</label>
            <input type="number" min="0" step="0.01" value={v.costo} onChange={(e) => set({ ...v, costo: e.target.value })} /></div>)}
        <div className="field"><label>Fecha de inicio</label>
          <input type="date" value={v.fecha_inicio} onChange={(e) => set({ ...v, fecha_inicio: e.target.value })} />
          {v.fecha_inicio && <span className="muted" style={{ fontSize: 12 }}>Renueva el {fecha(sumarDias(v.fecha_inicio, 30))} (30 días; se calcula sola).</span>}</div>
      </div>
    </>
  )
}

export const paqueteVacio = () => ({ paquete_id: '', tipo_id: '', costo: '', fecha_inicio: hoyIso() })
export const paqueteCompleto = (v: ReturnType<typeof paqueteVacio>, sinCosto?: boolean) =>
  !!(v.paquete_id && v.tipo_id && (sinCosto || v.costo !== '') && v.fecha_inicio)
export const paqueteBody = (v: ReturnType<typeof paqueteVacio>, sinCosto?: boolean) => ({
  paquete_id: Number(v.paquete_id), tipo_id: Number(v.tipo_id), fecha_inicio: v.fecha_inicio,
  ...(sinCosto ? {} : { costo: Number(v.costo) }),
})

export function AgregarPaqueteModal({ clienteId, onClose, onHecho }: { clienteId: number; onClose: () => void; onHecho: (nuevoId: number) => void }) {
  const { esCm } = useAuth()
  const cat = useCatalogos()
  const [v, setV] = useState(paqueteVacio())
  const [error, setError] = useState<string | null>(null)
  async function guardar() {
    setError(null)
    try { const r = await api.post<{ id: number }>(`/clientes/${clienteId}/paquetes`, paqueteBody(v, esCm)); onHecho(r.id) }
    catch (e) { setError(msg(e, 'No se pudo agregar el paquete')) }
  }
  return (
    <Modal title="Agregar paquete" onClose={onClose} width={520}>
      <p className="muted" style={{ marginTop: 0 }}>Captura la fecha de <strong>inicio</strong>: la renovación se calcula sola a los 30 días.
        {esCm ? ' El costo lo toma del catálogo y lo ajusta el administrador.' : ' Cada paquete tiene su propio costo y pagos.'}</p>
      <CamposPaquete v={v} set={setV} {...cat} sinCosto={esCm} />
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar} okText="Agregar" disabled={!paqueteCompleto(v, esCm)} />
    </Modal>
  )
}

export function EditarPaqueteModal({ p, esAdmin, onClose, onHecho }: { p: Paquete; esAdmin: boolean; onClose: () => void; onHecho: () => void }) {
  const cat = useCatalogos()
  const [v, setV] = useState({ paquete_id: String(p.paquete_id), tipo_id: String(p.tipo_id), costo: String(p.costo), fecha_inicio: p.fecha_inicio })
  const [error, setError] = useState<string | null>(null)
  async function guardar() {
    setError(null)
    try { await api.patch(`/paquetes/${p.id}`, esAdmin ? paqueteBody(v) : { fecha_inicio: v.fecha_inicio }); onHecho() } catch (e) { setError(msg(e, 'No se pudo guardar')) }
  }
  return (
    <Modal title="Editar paquete" onClose={onClose} width={520}>
      {esAdmin ? <CamposPaquete v={v} set={setV} {...cat} /> : (
        <div className="field"><label>Fecha de inicio</label><input type="date" value={v.fecha_inicio} onChange={(e) => setV({ ...v, fecha_inicio: e.target.value })} />
          <span className="muted" style={{ fontSize: 12 }}>Renueva el {fecha(sumarDias(v.fecha_inicio, 30))} (30 días; se recalcula sola).</span></div>)}
      <div className="callout callout-info">{esAdmin ? 'Como admin puedes corregir capturas erróneas. ' : 'Solo puedes corregir la fecha de inicio: el paquete, el tipo y el costo cambian únicamente al renovar. '}Todo queda en la bitácora.</div>
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar} okText="Guardar" disabled={esAdmin ? !paqueteCompleto(v) : !v.fecha_inicio} />
    </Modal>
  )
}

export function ConfirmarRenovacionModal({ p, sinMontos, onClose, onHecho }: {
  p: Paquete; sinMontos?: boolean; onClose: () => void; onHecho: (r: { renovado_automaticamente: number | null }) => void
}) {
  const cat = useCatalogos()
  const [cambiar, setCambiar] = useState(false)
  const [paqueteId, setPaqueteId] = useState(String(p.paquete_id))
  const [tipoId, setTipoId] = useState(String(p.tipo_id))
  const [costo, setCosto] = useState(String(p.costo))
  const [error, setError] = useState<string | null>(null)
  const actual = cat.paquetes.find((x) => x.id === p.paquete_id)
  const elegido = cat.paquetes.find((x) => x.id === Number(paqueteId))
  const nivel = actual && elegido && elegido.orden !== actual.orden ? (elegido.orden > actual.orden ? 'Subir de nivel' : 'Bajar de nivel') : null
  const enVentana = p.bloqueado || p.dias_para_renovar < 0

  async function guardar() {
    setError(null)
    try { onHecho(await api.post(`/paquetes/${p.id}/confirmar-renovacion`, !sinMontos && cambiar ? { paquete_id: Number(paqueteId), tipo_id: Number(tipoId), costo: Number(costo) } : {})) }
    catch (e) { setError(msg(e, 'No se pudo confirmar')) }
  }
  return (
    <Modal title={`Renovación · ${p.paquete}`} onClose={onClose} width={540}>
      <div className="callout callout-info" style={{ marginTop: 0 }}>
        <strong>{p.prorroga_hasta ? `Se conserva la fecha de renovación original (${fecha(p.fecha_renovacion)}).` : `Hoy (${fecha(hoyIso())}) queda como el inicio del nuevo contrato.`}</strong>
        {sinMontos
          ? (p.semaforo === 'verde' ? ' Ya está pagado: se renueva en este momento.'
            : ` Si aún debe, en cuanto se pague completo se renueva solo.${enVentana ? ' No hay tolerancia de pago: a las 11:59 pm de hoy, si no ha pagado, el administrador decidirá la prórroga.' : ' Si al terminar su contrato no ha pagado, se bloquea y lo resuelve el administrador.'}`)
          : p.restante > 0 ? ` Aún debe ${dinero(p.restante)}: en cuanto pague completo se renueva solo.${enVentana ? ' No hay tolerancia de pago: a las 11:59 pm de hoy, si no ha pagado, se te preguntará por la prórroga.' : ' Si al terminar su contrato no ha pagado, se bloquea y se te preguntará por la prórroga.'}`
          : ' Ya está pagado: se renueva en este momento.'}
      </div>
      {sinMontos && <p className="muted" style={{ margin: '0 0 8px' }}>Renueva con el <strong>mismo paquete ({p.paquete})</strong>. El cambio de paquete al renovar lo hace el administrador.</p>}
      {!sinMontos && <p style={{ margin: '0 0 8px', fontWeight: 600 }}>¿Con qué paquete renueva?</p>}
      {!sinMontos && (
        <div className="segmented light full" style={{ marginBottom: 14 }}>
          <button className={!cambiar ? 'active' : ''} onClick={() => setCambiar(false)}>El mismo ({p.paquete} · {dinero(p.costo)})</button>
          <button className={cambiar ? 'active' : ''} onClick={() => setCambiar(true)}>Cambiar de paquete</button>
        </div>)}
      {!sinMontos && cambiar && (
        <>
          <div className="grid-2">
            <div className="field"><label>Paquete nuevo</label>
              <select value={paqueteId} onChange={(e) => setPaqueteId(e.target.value)}>{cat.paquetes.map((x) => <option key={x.id} value={x.id}>{x.nombre}</option>)}</select>
              {nivel && <span className={`badge ${nivel === 'Subir de nivel' ? 'badge-good' : 'badge-warn'}`} style={{ marginTop: 6 }}>{nivel}</span>}</div>
            <div className="field"><label>Tipo</label>
              <select value={tipoId} onChange={(e) => setTipoId(e.target.value)}>{cat.tipos.map((x) => <option key={x.id} value={x.id}>{x.nombre}</option>)}</select></div>
            <div className="field"><label>Nuevo costo</label><input type="number" min="0" step="0.01" value={costo} onChange={(e) => setCosto(e.target.value)} /></div>
          </div>
          <div className="callout callout-warn">El cambio se aplica cuando la renovación se concrete. Al cambiar de paquete, el conteo de renovaciones se reinicia en 0.</div>
        </>)}
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar}
        okText={(sinMontos ? p.semaforo === 'verde' : p.restante <= 0) ? 'Renovar ahora' : 'Confirmar que va a renovar'}
        disabled={!sinMontos && cambiar && (!costo || !paqueteId || !tipoId)} />
    </Modal>
  )
}

export function NoRenovarModal({ p, nombreCliente, onClose, onHecho }: {
  p: Paquete; nombreCliente: string; onClose: () => void; onHecho: (r: { cliente_eliminado: boolean; cliente_a_no_renovados: boolean; programado?: boolean }) => void
}) {
  const { esCm } = useAuth()
  const [accion, setAccion] = useState<'conservar' | 'borrar'>('conservar')
  const [confirma, setConfirma] = useState('')
  const [preguntaCliente, setPreguntaCliente] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function enviar(eliminarCliente?: boolean) {
    setError(null)
    try {
      const r = await api.post<{ cliente_eliminado: boolean; cliente_a_no_renovados: boolean; programado?: boolean }>(`/paquetes/${p.id}/no-renovar`,
        { accion, confirmar_nombre: accion === 'borrar' ? confirma : null, eliminar_cliente: eliminarCliente ?? null })
      onHecho(r)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'ultimo_paquete') setPreguntaCliente(true)
      else setError(msg(e, 'No se pudo completar'))
    }
  }

  if (preguntaCliente) return (
    <Modal title="Es el último paquete" onClose={onClose} width={500}>
      <p style={{ marginTop: 0 }}>«{p.paquete}» es el último paquete de <strong>{nombreCliente}</strong>. ¿También quieres eliminar al cliente?</p>
      <div className="callout callout-bad">Eliminar al cliente borra de forma permanente su ficha, pagos e historial.</div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        <button className="btn btn-secondary" onClick={() => enviar(false)}>No, pasar a No renovados</button>
        <button className="btn btn-danger" onClick={() => enviar(true)}>Sí, eliminar también al cliente</button>
      </div>
      <ErrorTexto texto={error} />
    </Modal>
  )

  return (
    <Modal title={`No renovó · ${p.paquete}`} onClose={onClose} width={520}>
      {!esCm && (
        <div className="segmented light full" style={{ marginBottom: 14 }}>
          <button className={accion === 'conservar' ? 'active' : ''} onClick={() => setAccion('conservar')}>Conservar en historial</button>
          <button className={accion === 'borrar' ? 'active' : ''} onClick={() => setAccion('borrar')}>Borrar paquete</button>
        </div>)}
      {accion === 'conservar' ? (
        <div className="callout callout-info">
          {p.bloqueado || p.dias_para_renovar < 0
            ? <>El paquete pasa a <strong>archivado</strong> ahora mismo y <strong>{nombreCliente}</strong> pasa a «No renovados» (se conserva 1 año con toda su información).</>
            : <>Queda marcado como <strong>«no renovará»</strong> y, cuando termine su contrato ({fecha(p.fecha_renovacion)} a las 11:59 pm), <strong>{nombreCliente}</strong> pasa solo a «No renovados» (se conserva 1 año). Puedes deshacer la marca antes de esa fecha.</>}
        </div>
      ) : (
        <>
          <div className="callout callout-bad">Borrar quita el paquete del cliente. Para confirmar, escribe el nombre exacto del paquete: <strong>{p.paquete}</strong></div>
          <div className="field"><input type="text" placeholder={p.paquete} value={confirma} onChange={(e) => setConfirma(e.target.value)} autoFocus /></div>
        </>
      )}
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={() => enviar()} danger={accion === 'borrar'}
        okText={accion === 'borrar' ? 'Borrar paquete' : 'Marcar como no renovado'} disabled={accion === 'borrar' && confirma !== p.paquete} />
    </Modal>
  )
}

export function AgregarClienteModal({ onClose, onHecho, cms }: { onClose: () => void; onHecho: (id: number) => void; cms?: { id: number; nombre: string }[] }) {
  const { esCm } = useAuth()
  const cat = useCatalogos()
  const [d, setD] = useState({ nombre: '', correo_fb: '', password_fb: '', correo_contacto: '', telefono: '', observaciones: '' })
  const [cmId, setCmId] = useState('')
  const [conPaquete, setConPaquete] = useState(true)
  const [pq, setPq] = useState(paqueteVacio())
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value })
  const [cuentas, setCuentas] = useState<{ id: number; correo: string; clientes: number; tiene_password: boolean }[]>([])
  useEffect(() => {
    if (cms && !cmId) { setCuentas([]); return }
    api.get<typeof cuentas>(`/clientes/cuentas-fb${cms ? `?cm_id=${cmId}` : ''}`).then(setCuentas).catch(() => setCuentas([]))
  }, [cms, cmId])
  const existente = cuentas.find((c) => c.correo.toLowerCase() === d.correo_fb.trim().toLowerCase())

  async function guardar() {
    setError(null)
    try {
      const r = await api.post<{ id: number }>('/clientes', { ...d, cm_id: cms ? (cmId ? Number(cmId) : null) : undefined, paquetes: conPaquete ? [paqueteBody(pq, esCm)] : [] })
      onHecho(r.id)
    } catch (e) { setError(msg(e, 'No se pudo crear el cliente')) }
  }
  return (
    <Modal title="Agregar cliente" onClose={onClose} width={640}>
      <div className="grid-2">
        <div className="field"><label>Nombre del cliente *</label><input type="text" value={d.nombre} onChange={set('nombre')} autoFocus /></div>
        <div className="field"><label>Teléfono personal</label><input type="text" value={d.telefono} onChange={set('telefono')} placeholder="10 dígitos" /></div>
        {cuentas.length > 0 && <div className="field" style={{ gridColumn: '1 / -1' }}><label>Usar una cuenta de Facebook que ya manejas</label>
          <select value="" onChange={(e) => { const c = cuentas.find((x) => x.id === Number(e.target.value)); if (c) setD({ ...d, correo_fb: c.correo, password_fb: '' }) }}>
            <option value="">— Elegir una cuenta registrada —</option>
            {cuentas.map((c) => <option key={c.id} value={c.id}>{c.correo} · {c.clientes} {c.clientes === 1 ? 'cliente' : 'clientes'}</option>)}</select></div>}
        <div className="field"><label>Correo de Facebook</label><input type="text" value={d.correo_fb} onChange={set('correo_fb')} /></div>
        <div className="field"><label>Contraseña de Facebook</label><CampoPassword value={d.password_fb} onChange={(v) => setD({ ...d, password_fb: v })}
          placeholder={existente?.tiene_password ? 'Se usa la contraseña guardada de la cuenta' : undefined} />
          {existente && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Esta cuenta ya la usan {existente.clientes} {existente.clientes === 1 ? 'cliente' : 'clientes'}; este se sumará a la misma. Si escribes una contraseña nueva, cambia para todos.</div>}</div>
        <div className="field"><label>Correo de contacto</label><input type="text" value={d.correo_contacto} onChange={set('correo_contacto')} /></div>
        {cms && <div className="field"><label>CM responsable</label>
          <select value={cmId} onChange={(e) => setCmId(e.target.value)}><option value="">Por reasignar</option>{cms.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select></div>}
      </div>
      <div className="field"><label>Observaciones</label><textarea rows={2} value={d.observaciones} onChange={set('observaciones')} /></div>
      <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontWeight: 600 }}>
        <input type="checkbox" style={{ width: 'auto' }} checked={conPaquete} onChange={(e) => setConPaquete(e.target.checked)} /> Agregar su primer paquete ahora
      </label>
      {conPaquete && <div style={{ marginTop: 10 }}><CamposPaquete v={pq} set={setPq} {...cat} sinCosto={esCm} /></div>}
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar} okText="Crear cliente" disabled={!d.nombre.trim() || (conPaquete && !paqueteCompleto(pq, esCm))} />
    </Modal>
  )
}

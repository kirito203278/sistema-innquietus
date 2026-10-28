import { useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { Campana } from '../../api/types'
import { ErrorTexto, Modal } from '../../components/ui'
import { fecha, hoyIso, sumarDias } from '../../util'

const msg = (e: unknown, def: string) => (e instanceof ApiError ? e.message : def)

function Botones({ onClose, onOk, okText, disabled, danger }: { onClose: () => void; onOk: () => void; okText: string; disabled?: boolean; danger?: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
      <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
      <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onOk} disabled={disabled}>{okText}</button>
    </div>
  )
}

export function NuevaCampanaModal({ clienteId, clienteNombre, onClose, onHecho }: {
  clienteId: number; clienteNombre: string; onClose: () => void; onHecho: (id: number) => void
}) {
  const [v, setV] = useState({
    nombre: '', tipo: 'local', presupuesto: '', presupuesto_esquema: 'mensual', lugar: '', fecha_inicio: hoyIso(),
    formato_post: true, formato_3d: false, formato_boton: false, formato_otro: false,
  })
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value })
  const check = (k: 'formato_post' | 'formato_3d' | 'formato_boton' | 'formato_otro') => (e: { target: { checked: boolean } }) => setV({ ...v, [k]: e.target.checked })
  const valido = v.nombre.trim() !== '' && Number(v.presupuesto) > 0 && v.fecha_inicio !== ''

  async function guardar() {
    setError(null); setEnviando(true)
    try {
      const c = await api.post<Campana>(`/clientes/${clienteId}/campanas`, {
        ...v, presupuesto: Number(v.presupuesto), lugar: v.lugar.trim() || null, fecha_renovacion: sumarDias(v.fecha_inicio, 30),
      })
      onHecho(c.id)
    } catch (e) { setError(msg(e, 'No se pudo crear la campaña')) } finally { setEnviando(false) }
  }

  return (
    <Modal title={`Nueva campaña · ${clienteNombre}`} onClose={onClose} width={560}>
      <p className="muted" style={{ marginTop: 0 }}>
        La campaña queda ligada al cliente y a su paquete vigente. La renovación se calcula sola a los 30 días.
      </p>
      <div className="grid-2">
        <div className="field" style={{ gridColumn: '1 / -1' }}><label>Nombre de la campaña</label>
          <input type="text" autoFocus value={v.nombre} onChange={set('nombre')} placeholder="Ej. LOCAL ADV - OCTUBRE" /></div>
        <div className="field"><label>Tipo</label>
          <select value={v.tipo} onChange={set('tipo')}><option value="local">Local</option><option value="nacional">Nacional</option><option value="otro">Otro</option></select></div>
        <div className="field"><label>Presupuesto (MXN)</label><input type="number" min="1" step="0.01" value={v.presupuesto} onChange={set('presupuesto')} /></div>
        <div className="field"><label>El presupuesto es…</label>
          <select value={v.presupuesto_esquema} onChange={set('presupuesto_esquema')}><option value="mensual">Mensual</option><option value="semanal">Semanal</option><option value="diario">Diario</option></select></div>
        <div className="field"><label>Lugar</label><input type="text" value={v.lugar} onChange={set('lugar')} placeholder="Ej. Culiacán" /></div>
        <div className="field"><label>Fecha de inicio</label><input type="date" value={v.fecha_inicio} onChange={set('fecha_inicio')} />
          <span className="muted" style={{ fontSize: 12 }}>Renueva el {fecha(sumarDias(v.fecha_inicio || hoyIso(), 30))}.</span></div>
        <div className="field"><label>Formatos</label>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
            <label><input type="checkbox" checked={v.formato_post} onChange={check('formato_post')} /> Post</label>
            <label><input type="checkbox" checked={v.formato_3d} onChange={check('formato_3d')} /> 3D</label>
            <label><input type="checkbox" checked={v.formato_boton} onChange={check('formato_boton')} /> Botón</label>
            <label><input type="checkbox" checked={v.formato_otro} onChange={check('formato_otro')} /> Otro</label>
          </div></div>
      </div>
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar} okText="Crear campaña" disabled={!valido || enviando} />
    </Modal>
  )
}

export function RenovarCampanaModal({ c, onClose, onHecho }: { c: Campana; onClose: () => void; onHecho: () => void }) {
  const [nueva, setNueva] = useState(sumarDias(hoyIso(), 30))
  const [error, setError] = useState<string | null>(null)
  async function guardar() {
    setError(null)
    try { await api.post(`/campanas/${c.id}/renovar`, { fecha_renovacion: nueva }); onHecho() } catch (e) { setError(msg(e, 'No se pudo renovar')) }
  }
  return (
    <Modal title={c.estado === 'cerrada' ? 'Reabrir campaña' : 'Renovar campaña'} onClose={onClose} width={460}>
      <p className="muted" style={{ marginTop: 0 }}>«{c.nombre}» vuelve a estar activa desde hoy y arranca una captura semanal nueva. El resumen del ciclo anterior ya quedó archivado.</p>
      <div className="field"><label>Nueva fecha de renovación</label><input type="date" value={nueva} min={sumarDias(hoyIso(), 1)} onChange={(e) => setNueva(e.target.value)} />
        <span className="muted" style={{ fontSize: 12 }}>Por defecto, 30 días a partir de hoy.</span></div>
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar} okText="Renovar campaña" disabled={!nueva} />
    </Modal>
  )
}

export function CerrarCampanaModal({ c, onClose, onHecho }: { c: Campana; onClose: () => void; onHecho: () => void }) {
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState<string | null>(null)
  async function guardar() {
    setError(null)
    try { await api.post(`/campanas/${c.id}/cerrar`, { motivo: motivo.trim() || null }); onHecho() } catch (e) { setError(msg(e, 'No se pudo cerrar')) }
  }
  return (
    <Modal title="Dar por terminada la campaña" onClose={onClose} width={480}>
      <p className="muted" style={{ marginTop: 0 }}>
        «{c.nombre}» termina aquí. {c.estado === 'activa' ? 'Se archiva el resumen mensual de lo capturado hasta hoy. ' : ''}
        El histórico se conserva y el cliente puede seguir con otras campañas. Más adelante se puede reabrir.
      </p>
      <div className="field"><label>Motivo (opcional)</label><input type="text" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej. el cliente pausa la publicidad" /></div>
      <ErrorTexto texto={error} />
      <Botones onClose={onClose} onOk={guardar} okText="Dar por terminada" danger />
    </Modal>
  )
}

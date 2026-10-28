import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, downloadFile } from '../../api/client'
import type { Campana, MensualCampana, ObservacionCampana, SemanaCampana } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import BarChart, { statusColor } from '../../components/charts/BarChart'
import LineChart from '../../components/charts/LineChart'
import { Cargando, ErrorTexto, useToast } from '../../components/ui'
import { CAMPANA_ESTADO_BADGE, RENDIMIENTO_BADGE, RENDIMIENTO_LABEL, TIPO_CAMPANA_LABEL, dinero, diasTexto, fecha, fechaHora } from '../../util'
import { CerrarCampanaModal, RenovarCampanaModal } from './modalesCampana'

const msg = (e: unknown, def: string) => (e instanceof ApiError ? e.message : def)
type Tab = 'semanal' | 'observaciones' | 'mensuales'

export function Rendimiento({ valor }: { valor: string | null }) {
  return valor ? <span className={`badge ${RENDIMIENTO_BADGE[valor]}`}>{RENDIMIENTO_LABEL[valor]}</span> : <span className="muted">—</span>
}

export default function CampanaDetalle({ id, onVolver, onAbrirCliente, onCambio }: {
  id: number; onVolver: () => void; onAbrirCliente: (clienteId: number) => void; onCambio: () => void
}) {
  const { puedeEscribir, user } = useAuth()
  const [c, setC] = useState<Campana | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('semanal')
  const [modal, setModal] = useState<'renovar' | 'cerrar' | null>(null)
  const [toast, avisar] = useToast()

  const cargar = useCallback(async () => {
    try { setC(await api.get<Campana>(`/campanas/${id}`)); setError(null) } catch (e) { setError(msg(e, 'No se pudo cargar la campaña')) }
  }, [id])
  useEffect(() => { setC(null); cargar() }, [cargar])

  if (error) return <div className="card" style={{ padding: 24 }}><ErrorTexto texto={error} /><button className="btn btn-secondary" onClick={onVolver}>Volver</button></div>
  if (!c) return <Cargando />

  const escribe = puedeEscribir && !c.cliente_bloqueado
  const refrescar = async () => { await cargar(); onCambio() }
  const reporte = (tipo: 'semanal' | 'mensual') => downloadFile(`/clientes/${c.cliente_id}/campanas/reporte-${tipo}`, `reporte-${tipo}.pdf`)
    .catch((e) => avisar(msg(e, 'No se pudo generar el reporte')))

  return (
    <div>
      <button className="btn btn-ghost btn-sm" onClick={onVolver} style={{ marginBottom: 8 }}>← Volver a campañas</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h1 className="page-title" style={{ margin: 0 }}>{c.nombre}</h1>
        <span className={`badge ${CAMPANA_ESTADO_BADGE[c.estado]}`}>{c.estado}</span>
        <Rendimiento valor={c.rendimiento} />
        <div className="right" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary btn-sm" onClick={() => reporte('semanal')}>Reporte semanal</button>
          <button className="btn btn-primary btn-sm" onClick={() => reporte('mensual')}>Generar reporte</button>
        </div>
      </div>
      <p className="page-sub" style={{ marginTop: 4 }}>
        Cliente: <button className="btn btn-ghost btn-sm" style={{ padding: '0 4px' }} onClick={() => onAbrirCliente(c.cliente_id)}>{c.cliente_nombre}</button>
        {c.cm_nombre && <> · CM: {c.cm_nombre}</>}
      </p>

      {c.cliente_bloqueado && <div className="callout callout-bad"><strong>El cliente está en pausa:</strong> su contrato terminó y nadie ha decidido. Puedes consultar la campaña, pero no capturar hasta resolverlo en la ficha del cliente.</div>}
      {c.cliente_estado === 'no_renovado' && <div className="callout callout-warn">Este cliente está en «No renovados»: sus campañas se cerraron y conservan su histórico.</div>}
      {c.estado === 'vencida' && escribe && (
        <div className="callout callout-bad"><strong>Llegó a su fecha de renovación ({fecha(c.fecha_renovacion)}).</strong> Su resumen mensual ya quedó archivado. Confirma si el cliente renovó o si la campaña termina para seguir capturando.
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={() => setModal('renovar')}>Sí renovó</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setModal('cerrar')}>Dar por terminada</button>
          </div></div>)}
      {c.estado === 'cerrada' && escribe && c.cliente_estado === 'activo' && (
        <div className="callout callout-info">Campaña terminada. <button className="btn btn-secondary btn-sm" style={{ marginLeft: 8 }} onClick={() => setModal('renovar')}>Reabrir</button></div>)}

      <div className="card" style={{ padding: 16, marginTop: 10 }}>
        <div className="stat-grid" style={{ margin: 0 }}>
          <Dato k="Tipo" v={TIPO_CAMPANA_LABEL[c.tipo]} /><Dato k="Paquete" v={c.paquete ?? '—'} />
          <Dato k="Presupuesto" v={`${dinero(c.presupuesto)} / ${c.presupuesto_esquema}`} /><Dato k="Lugar" v={c.lugar ?? '—'} />
          <Dato k="Inicio" v={fecha(c.fecha_inicio)} /><Dato k="Renovación" v={`${fecha(c.fecha_renovacion)} · ${diasTexto(c.dias_para_renovar)}`} />
          <Dato k="Costo actual" v={c.costo_actual != null ? dinero(c.costo_actual) : '—'} />
          <Dato k="Formatos" v={[c.formato_post && 'Post', c.formato_3d && '3D', c.formato_boton && 'Botón', c.formato_otro && 'Otro'].filter(Boolean).join(', ') || '—'} />
        </div>
        {escribe && c.estado === 'activa' && <div style={{ marginTop: 12 }}><button className="btn btn-ghost btn-sm" onClick={() => setModal('cerrar')}>Dar por terminada esta campaña…</button></div>}
      </div>

      <div className="cm-tabs" style={{ marginTop: 18 }}>
        {([['semanal', 'Datos semanales'], ['observaciones', 'Observaciones'], ['mensuales', 'Resultados mensuales']] as [Tab, string][]).map(([k, t]) =>
          <button key={k} className={`cm-tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{t}</button>)}
      </div>

      {tab === 'semanal' && <TabSemanal c={c} escribe={escribe} esAdmin={user?.rol === 'admin'} avisar={avisar} onCambio={refrescar} />}
      {tab === 'observaciones' && <TabObservaciones c={c} escribe={escribe && c.estado === 'activa'} avisar={avisar} />}
      {tab === 'mensuales' && <TabMensuales c={c} escribe={puedeEscribir} avisar={avisar} onCambio={refrescar} />}

      {modal === 'renovar' && <RenovarCampanaModal c={c} onClose={() => setModal(null)} onHecho={() => { setModal(null); refrescar(); avisar('Campaña renovada') }} />}
      {modal === 'cerrar' && <CerrarCampanaModal c={c} onClose={() => setModal(null)} onHecho={() => { setModal(null); refrescar(); avisar('Campaña terminada') }} />}
      {toast}
    </div>
  )
}

const Dato = ({ k, v }: { k: string; v: string }) => <div><div className="muted" style={{ fontSize: 12 }}>{k}</div><div style={{ fontWeight: 700 }}>{v}</div></div>

// ------------------------------------------------------------------ semanal
function TabSemanal({ c, escribe, esAdmin, avisar, onCambio }: { c: Campana; escribe: boolean; esAdmin: boolean; avisar: (t: string) => void; onCambio: () => void }) {
  const [semanas, setSemanas] = useState<SemanaCampana[] | null>(null)
  const cargar = useCallback(() => api.get<SemanaCampana[]>(`/campanas/${c.id}/semanas`).then(setSemanas), [c.id])
  useEffect(() => { cargar() }, [cargar, c.estado])
  if (!semanas) return <Cargando />
  if (semanas.length === 0) return <div className="card" style={{ padding: 20 }}><p className="muted" style={{ margin: 0 }}>
    {c.estado === 'activa' ? 'Todavía no hay semanas.' : 'Al llegar la fecha de renovación las semanas se archivan en el resumen mensual (pestaña «Resultados mensuales»).'}</p></div>

  const conDatos = semanas.filter((s) => s.mensajes != null)
  const habilitar = async (s: SemanaCampana) => {
    try { await api.post(`/semanas/${s.id}/habilitar-edicion`); avisar('El CM puede editar esa semana por 2 horas'); cargar() } catch (e) { avisar(msg(e, 'No se pudo habilitar')) }
  }
  return (
    <>
      <div className="grid-2" style={{ alignItems: 'start', marginBottom: 14 }}>
        <div className="card" style={{ padding: 16 }}>
          <div className="section-title" style={{ marginTop: 0 }}>Mensajes por semana</div>
          <BarChart data={conDatos.map((s, i) => ({ label: `S${i + 1}`, value: s.mensajes ?? 0, color: statusColor(s.rendimiento), tooltip: `${fecha(s.inicio)} · ${s.rendimiento ?? 'sin semáforo'}` }))} />
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="section-title" style={{ marginTop: 0 }}>Costo por resultado</div>
          <LineChart data={conDatos.filter((s) => s.costo_por_resultado != null).map((s, i) => ({ label: `S${i + 1}`, value: s.costo_por_resultado ?? 0, tooltip: fecha(s.inicio) }))} valueFormat={dinero} />
        </div>
      </div>
      <div className="card table-scroll"><table className="data-table"><thead><tr>
        <th>Semana</th><th className="num">Mensajes</th><th className="num">Costo por resultado</th><th className="num">Importe gastado</th><th>Semáforo</th><th>Estado</th><th></th></tr></thead><tbody>
        {semanas.map((s, i) => <FilaSemana key={s.id} s={s} n={i + 1} puedeCapturar={escribe && c.estado === 'activa'} esAdmin={esAdmin} avisar={avisar}
          onGuardado={() => { cargar(); onCambio() }} onHabilitar={() => habilitar(s)} />)}
      </tbody></table></div>
      <p className="muted" style={{ fontSize: 12 }}>La semana va de sábado a viernes y se bloquea al terminar. Si hace falta corregir una cerrada, el administrador puede habilitar la edición por 2 horas.</p>
    </>
  )
}

function FilaSemana({ s, n, puedeCapturar, esAdmin, avisar, onGuardado, onHabilitar }: {
  s: SemanaCampana; n: number; puedeCapturar: boolean; esAdmin: boolean; avisar: (t: string) => void; onGuardado: () => void; onHabilitar: () => void
}) {
  const abierta = s.editable || s.permiso_hasta != null
  const [d, setD] = useState({ m: s.mensajes?.toString() ?? '', c: s.costo_por_resultado?.toString() ?? '', i: s.importe_gastado?.toString() ?? '' })
  const [manual, setManual] = useState(s.importe_gastado != null)
  const [guardando, setGuardando] = useState(false)
  const importeAuto = (m: string, c: string) => (m !== '' && c !== '' ? (Number(m) * Number(c)).toFixed(2) : '')
  const cambiar = (k: 'm' | 'c') => (e: { target: { value: string } }) => {
    const nuevo = { ...d, [k]: e.target.value }
    setD(manual ? nuevo : { ...nuevo, i: importeAuto(nuevo.m, nuevo.c) })
  }
  const completo = d.m !== '' && d.c !== '' && d.i !== ''
  async function guardar() {
    setGuardando(true)
    try { await api.put(`/semanas/${s.id}`, { mensajes: Number(d.m), costo_por_resultado: Number(d.c), importe_gastado: Number(d.i) }); avisar('Semana guardada'); onGuardado() }
    catch (e) { avisar(msg(e, 'No se pudo guardar')) } finally { setGuardando(false) }
  }
  const editando = puedeCapturar && abierta
  return (
    <tr>
      <td><strong>Semana {n}</strong><div className="muted" style={{ fontSize: 12 }}>{fecha(s.inicio)} – {fecha(s.fin)}</div></td>
      {editando ? (<>
        <td className="num"><input type="number" min="0" style={{ width: 84 }} value={d.m} onChange={cambiar('m')} aria-label="Mensajes" /></td>
        <td className="num"><input type="number" min="0" step="0.01" style={{ width: 96 }} value={d.c} onChange={cambiar('c')} aria-label="Costo por resultado" /></td>
        <td className="num"><input type="number" min="0" step="0.01" style={{ width: 104 }} value={d.i} aria-label="Importe gastado"
          onChange={(e) => { setManual(true); setD({ ...d, i: e.target.value }) }} /></td>
      </>) : (<>
        <td className="num">{s.mensajes ?? '—'}</td><td className="num">{s.costo_por_resultado != null ? dinero(s.costo_por_resultado) : '—'}</td>
        <td className="num">{s.importe_gastado != null ? dinero(s.importe_gastado) : '—'}</td></>)}
      <td><Rendimiento valor={s.rendimiento} /></td>
      <td>{s.permiso_hasta ? <span className="badge badge-purple" title={`Hasta ${fechaHora(s.permiso_hasta)}`}>Edición habilitada</span>
        : s.editable ? <span className="badge badge-good">{s.en_curso ? 'En curso' : 'Abierta'}</span> : <span className="badge badge-neutral">Cerrada</span>}</td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {editando && <button className="btn btn-secondary btn-sm" disabled={!completo || guardando} onClick={guardar}>Guardar</button>}
        {esAdmin && puedeCapturar && !abierta && <button className="btn btn-ghost btn-sm" onClick={onHabilitar}>Habilitar edición 2h</button>}
      </td>
    </tr>
  )
}

// ------------------------------------------------------------ observaciones
function TabObservaciones({ c, escribe, avisar }: { c: Campana; escribe: boolean; avisar: (t: string) => void }) {
  const [lista, setLista] = useState<ObservacionCampana[] | null>(null)
  const [texto, setTexto] = useState('')
  const cargar = useCallback(() => api.get<ObservacionCampana[]>(`/campanas/${c.id}/observaciones`).then(setLista), [c.id])
  useEffect(() => { cargar() }, [cargar])
  async function agregar() {
    try { await api.post(`/campanas/${c.id}/observaciones`, { texto }); setTexto(''); cargar() } catch (e) { avisar(msg(e, 'No se pudo guardar la nota')) }
  }
  if (!lista) return <Cargando />
  return (
    <div className="card" style={{ padding: 18 }}>
      {escribe && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          <textarea rows={2} style={{ flex: 1 }} placeholder="Agrega una observación de esta campaña…" value={texto} onChange={(e) => setTexto(e.target.value)} />
          <button className="btn btn-primary" disabled={!texto.trim()} onClick={agregar}>Agregar</button>
        </div>)}
      {lista.length === 0 ? <p className="muted" style={{ margin: 0 }}>Sin observaciones en este ciclo. Las notas se archivan al cerrar el ciclo.</p>
        : lista.map((o) => <div key={o.id} style={{ borderBottom: '1px solid var(--border)', padding: '8px 0' }}>
          <div>{o.texto}</div><div className="muted" style={{ fontSize: 12 }}>{o.autor ?? '—'} · {fechaHora(o.creado_en)}</div></div>)}
    </div>
  )
}

// ---------------------------------------------------------------- mensuales
function TabMensuales({ c, escribe, avisar, onCambio }: { c: Campana; escribe: boolean; avisar: (t: string) => void; onCambio: () => void }) {
  const { user } = useAuth()
  const [lista, setLista] = useState<MensualCampana[] | null>(null)
  const [f, setF] = useState({ periodo_inicio: '', periodo_fin: '', mensajes_total: '', gasto_total: '' })
  const cargar = useCallback(() => api.get<MensualCampana[]>(`/campanas/${c.id}/mensuales`).then(setLista), [c.id])
  useEffect(() => { cargar() }, [cargar, c.estado])
  async function capturar() {
    try {
      await api.post(`/campanas/${c.id}/mensuales/manual`, { ...f, mensajes_total: Number(f.mensajes_total), gasto_total: Number(f.gasto_total) })
      avisar('Resultado mensual registrado'); cargar(); onCambio()
    } catch (e) { avisar(msg(e, 'No se pudo registrar')) }
  }
  if (!lista) return <Cargando />
  const completo = Object.values(f).every((v) => v !== '')
  return (
    <>
      {lista.length > 0 ? (<>
        <div className="card" style={{ padding: 16, marginBottom: 14 }}>
          <div className="section-title" style={{ marginTop: 0 }}>Costo por mensaje (últimos {user?.rol === 'cm' ? 2 : 3} meses)</div>
          <BarChart height={140} valueFormat={dinero} data={[...lista].reverse().map((m) => ({
            label: fecha(m.periodo_inicio).slice(0, 5), value: m.costo_por_mensaje, color: statusColor(m.rendimiento), tooltip: m.rendimiento ?? 'sin semáforo' }))} />
        </div>
        <div className="card table-scroll"><table className="data-table"><thead><tr>
          <th>Periodo</th><th className="num">Mensajes</th><th className="num">Costo por mensaje</th><th className="num">Gasto total</th><th className="num">Presupuesto</th><th className="num">Sobrante</th><th>Rendimiento</th></tr></thead><tbody>
          {lista.map((m) => <tr key={m.id}>
            <td>{fecha(m.periodo_inicio)} – {fecha(m.periodo_fin)}{m.origen === 'manual' && <span className="badge badge-neutral" style={{ marginLeft: 6 }}>manual</span>}</td>
            <td className="num">{m.mensajes_total}</td><td className="num">{dinero(m.costo_por_mensaje)}</td><td className="num">{dinero(m.gasto_total)}</td>
            <td className="num">{dinero(m.presupuesto)}</td><td className="num">{m.sobrante != null ? dinero(m.sobrante) : '—'}</td><td><Rendimiento valor={m.rendimiento} /></td></tr>)}
        </tbody></table></div>
        <p className="muted" style={{ fontSize: 12 }}>Los resúmenes mensuales son inmutables: nadie puede editarlos una vez archivados.</p>
      </>) : (
        <div className="card" style={{ padding: 18 }}>
          <p className="muted" style={{ marginTop: 0 }}>Aún no hay resultados de meses anteriores. Se archivan solos al llegar la fecha de renovación.</p>
          {escribe && (<>
            <div className="section-title" style={{ marginTop: 0 }}>Capturar el mes anterior a la llegada al sistema (una sola vez)</div>
            <div className="grid-2">
              <div className="field"><label>Inicio del periodo</label><input type="date" value={f.periodo_inicio} onChange={(e) => setF({ ...f, periodo_inicio: e.target.value })} /></div>
              <div className="field"><label>Fin del periodo</label><input type="date" value={f.periodo_fin} onChange={(e) => setF({ ...f, periodo_fin: e.target.value })} /></div>
              <div className="field"><label>Mensajes totales</label><input type="number" min="0" value={f.mensajes_total} onChange={(e) => setF({ ...f, mensajes_total: e.target.value })} /></div>
              <div className="field"><label>Gasto total (MXN)</label><input type="number" min="0" step="0.01" value={f.gasto_total} onChange={(e) => setF({ ...f, gasto_total: e.target.value })} /></div>
            </div>
            <button className="btn btn-primary" disabled={!completo} onClick={capturar}>Registrar resultado</button>
          </>)}
        </div>)}
    </>
  )
}

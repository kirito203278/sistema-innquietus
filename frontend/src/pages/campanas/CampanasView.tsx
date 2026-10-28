import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Campana, UsuarioEquipo } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Cargando } from '../../components/ui'
import { CAMPANA_ESTADO_BADGE, TIPO_CAMPANA_LABEL, dinero, diasTexto, fecha } from '../../util'
import CampanaDetalle, { Rendimiento } from './CampanaDetalle'

type Filtro = 'abiertas' | 'vencida' | 'cerrada' | 'todas'

export default function CampanasView({ abrirId, onAbrirCliente, onCambio }: {
  abrirId?: number | null; onAbrirCliente: (clienteId: number) => void; onCambio?: () => void
}) {
  const { user } = useAuth()
  const esAdmin = user?.rol === 'admin'
  const [abierta, setAbierta] = useState<number | null>(abrirId ?? null)
  const [lista, setLista] = useState<Campana[] | null>(null)
  const [estado, setEstado] = useState<Filtro>('abiertas')
  const [cmId, setCmId] = useState('')
  const [q, setQ] = useState('')
  const [cms, setCms] = useState<UsuarioEquipo[]>([])

  useEffect(() => { setAbierta(abrirId ?? null) }, [abrirId])
  useEffect(() => { if (esAdmin) api.get<UsuarioEquipo[]>('/usuarios').then((u) => setCms(u.filter((x) => x.rol === 'cm' && x.activo))) }, [esAdmin])

  const cargar = useCallback(() => {
    const p = new URLSearchParams({ estado })
    if (cmId) p.set('cm_id', cmId)
    if (q.trim()) p.set('q', q.trim())
    return api.get<Campana[]>(`/campanas?${p}`).then(setLista)
  }, [estado, cmId, q])
  useEffect(() => { const t = setTimeout(cargar, q ? 250 : 0); return () => clearTimeout(t) }, [cargar, q])

  if (abierta != null) {
    return <CampanaDetalle id={abierta} onAbrirCliente={onAbrirCliente} onVolver={() => { setAbierta(null); cargar() }}
      onCambio={() => { cargar(); onCambio?.() }} />
  }
  if (!lista) return <Cargando />

  const activas = lista.filter((c) => c.estado === 'activa').length
  const vencidas = lista.filter((c) => c.estado === 'vencida').length
  const bajas = lista.filter((c) => c.estado === 'activa' && c.rendimiento === 'bajo').length
  const proximas = lista.filter((c) => c.estado === 'activa' && c.dias_para_renovar >= 0 && c.dias_para_renovar <= 7).length

  return (
    <div>
      <h1 className="page-title">Campañas</h1>
      <p className="page-sub">{esAdmin ? 'Todas las campañas de la agencia, ligadas a la ficha única de cada cliente.' : 'Las campañas de tus clientes. Captura la semana, sigue el semáforo y atiende las renovaciones.'}</p>

      <div className="stat-grid">
        <div className="card stat"><div className="label">Activas</div><div className="value">{activas}</div></div>
        <div className="card stat"><div className="label">Vencidas por resolver</div><div className="value" style={{ color: vencidas ? 'var(--bad)' : undefined }}>{vencidas}</div></div>
        <div className="card stat"><div className="label">Renuevan en 7 días</div><div className="value">{proximas}</div></div>
        <div className="card stat"><div className="label">Con rendimiento bajo</div><div className="value" style={{ color: bajas ? 'var(--bad)' : undefined }}>{bajas}</div></div>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14, alignItems: 'end' }}>
        <div className="segmented light" role="group" aria-label="Estado">
          {([['abiertas', 'Abiertas'], ['vencida', 'Vencidas'], ['cerrada', 'Cerradas'], ['todas', 'Todas']] as [Filtro, string][]).map(([k, t]) =>
            <button key={k} className={estado === k ? 'active' : ''} onClick={() => setEstado(k)}>{t}</button>)}
        </div>
        {esAdmin && <div className="field" style={{ margin: 0, minWidth: 180 }}><label>CM</label>
          <select value={cmId} onChange={(e) => setCmId(e.target.value)}><option value="">Todos</option>{cms.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select></div>}
        <input type="text" placeholder="Buscar campaña…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} aria-label="Buscar campaña" />
      </div>

      {lista.length === 0 ? (
        <div className="card" style={{ padding: 24 }}><p className="muted" style={{ margin: 0 }}>No hay campañas con ese filtro. Para crear una, abre la ficha de un cliente y usa <strong>«+ Agregar campaña»</strong>.</p></div>
      ) : (
        <div className="card table-scroll"><table className="data-table"><thead><tr>
          <th>Cliente</th><th>Campaña</th><th>Tipo</th>{esAdmin && <th>CM</th>}<th>Estado</th><th className="num">Costo actual</th><th>Semáforo</th><th>Renovación</th></tr></thead><tbody>
          {lista.map((c) => (
            <tr key={c.id} className="clickable-row" onClick={() => setAbierta(c.id)}>
              <td><strong>{c.cliente_nombre}</strong></td><td>{c.nombre}</td><td>{TIPO_CAMPANA_LABEL[c.tipo]}</td>{esAdmin && <td>{c.cm_nombre ?? <span className="muted">Sin CM</span>}</td>}
              <td><span className={`badge ${CAMPANA_ESTADO_BADGE[c.estado]}`}>{c.estado}</span></td>
              <td className="num">{c.costo_actual != null ? dinero(c.costo_actual) : '—'}</td><td><Rendimiento valor={c.rendimiento} /></td>
              <td>{fecha(c.fecha_renovacion)}<div className="muted" style={{ fontSize: 12 }}>{c.estado === 'activa' ? diasTexto(c.dias_para_renovar) : ''}</div></td></tr>))}
        </tbody></table></div>)}
    </div>
  )
}

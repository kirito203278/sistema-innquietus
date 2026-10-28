import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../../api/client'
import type { Bloqueo, Campana } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Cargando } from '../../components/ui'
import { diasTexto, fecha, hoyIso, sumarDias } from '../../util'

interface ClienteResumen {
  id: number; nombre: string; cm_nombre: string | null; paquetes_vigentes: number; proxima_renovacion: string | null; campanas_abiertas: number
}

/** Pantalla de entrada: lo que requiere atención hoy, de TODOS los módulos, en un solo lugar. */
export default function Inicio({ onAbrirCliente, onAbrirCampana, onIr }: {
  onAbrirCliente: (id: number, paquete?: number | null) => void; onAbrirCampana: (id: number) => void; onIr: (vista: 'campanas' | 'renovaciones') => void
}) {
  const { user } = useAuth()
  const [datos, setDatos] = useState<{ bloqueos: Bloqueo[]; campanas: Campana[]; clientes: ClienteResumen[] } | null>(null)
  useEffect(() => {
    Promise.all([api.get<Bloqueo[]>('/bloqueos'), api.get<Campana[]>('/campanas?estado=abiertas'), api.get<ClienteResumen[]>('/clientes')])
      .then(([bloqueos, campanas, clientes]) => setDatos({ bloqueos, campanas, clientes }))
  }, [])
  if (!datos) return <Cargando />

  const { bloqueos, campanas, clientes } = datos
  const hoy = hoyIso()
  const limite = sumarDias(hoy, 7)
  const vencidas = campanas.filter((c) => c.estado === 'vencida')
  const bajas = campanas.filter((c) => c.estado === 'activa' && c.rendimiento === 'bajo')
  // solo renovaciones FUTURAS: las que ya pasaron sin decidir salen en «Contratos terminados por decidir»
  const renuevanPronto = clientes.filter((c) => c.proxima_renovacion && c.proxima_renovacion >= hoy && c.proxima_renovacion <= limite)
  const sinCampana = clientes.filter((c) => c.paquetes_vigentes > 0 && c.campanas_abiertas === 0)
  const pendientes = bloqueos.length + vencidas.length
  const nombre = user?.nombre.split(' ')[0]

  return (
    <div>
      <h1 className="page-title">Hola, {nombre}</h1>
      <p className="page-sub">{pendientes === 0 ? 'Todo al día: no hay nada urgente por resolver.' : `Tienes ${pendientes} ${pendientes === 1 ? 'asunto' : 'asuntos'} que requieren atención.`}</p>

      <div className="stat-grid">
        <div className="card stat"><div className="label">Clientes activos</div><div className="value">{clientes.length}</div></div>
        <div className="card stat"><div className="label">Campañas activas</div><div className="value">{campanas.filter((c) => c.estado === 'activa').length}</div></div>
        <div className="card stat"><div className="label">Contratos por decidir</div><div className="value" style={{ color: bloqueos.length ? 'var(--bad)' : undefined }}>{bloqueos.length}</div></div>
        <div className="card stat"><div className="label">Campañas vencidas</div><div className="value" style={{ color: vencidas.length ? 'var(--bad)' : undefined }}>{vencidas.length}</div></div>
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <Bloque titulo="Contratos terminados por decidir" vacio="Ningún cliente en pausa." mal={bloqueos.length > 0} accion={['Ver renovaciones', () => onIr('renovaciones')]}>
          {bloqueos.slice(0, 6).map((b) => <Fila key={b.id} principal={b.cliente_nombre} detalle={`${b.paquete} · terminó el ${fecha(b.fecha_renovacion)}`} onClick={() => onAbrirCliente(b.cliente_id, b.id)} />)}
        </Bloque>
        <Bloque titulo="Campañas vencidas por resolver" vacio="Ninguna campaña espera tu decisión." mal={vencidas.length > 0} accion={['Ver campañas', () => onIr('campanas')]}>
          {vencidas.slice(0, 6).map((c) => <Fila key={c.id} principal={c.nombre} detalle={`${c.cliente_nombre} · venció el ${fecha(c.fecha_renovacion)}`} onClick={() => onAbrirCampana(c.id)} />)}
        </Bloque>
        <Bloque titulo="Renuevan en los próximos 7 días" vacio="Sin renovaciones próximas.">
          {renuevanPronto.slice(0, 6).map((c) => <Fila key={c.id} principal={c.nombre} detalle={`${fecha(c.proxima_renovacion)} · ${diasTexto((new Date(c.proxima_renovacion!).getTime() - new Date(hoyIso()).getTime()) / 86400000)}`} onClick={() => onAbrirCliente(c.id)} />)}
        </Bloque>
        <Bloque titulo="Campañas con rendimiento bajo" vacio="Ninguna campaña en rojo.">
          {bajas.slice(0, 6).map((c) => <Fila key={c.id} principal={c.nombre} detalle={`${c.cliente_nombre} · costo ${c.costo_actual != null ? `$${c.costo_actual.toFixed(2)}` : '—'}`} onClick={() => onAbrirCampana(c.id)} />)}
        </Bloque>
        <Bloque titulo="Clientes con paquete y sin campaña" vacio="Todos tus clientes con paquete ya tienen campaña.">
          {sinCampana.slice(0, 6).map((c) => <Fila key={c.id} principal={c.nombre} detalle="Abre la ficha para agregar su campaña" onClick={() => onAbrirCliente(c.id)} />)}
        </Bloque>
      </div>
    </div>
  )
}

function Bloque({ titulo, vacio, mal, accion, children }: { titulo: string; vacio: string; mal?: boolean; accion?: [string, () => void]; children: ReactNode[] }) {
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 15, color: mal ? 'var(--bad)' : undefined }}>{titulo}</h2>
        {accion && <button className="btn btn-ghost btn-sm right" onClick={accion[1]}>{accion[0]} →</button>}
      </div>
      {children.length === 0 ? <p className="muted" style={{ margin: 0, fontSize: 13 }}>{vacio}</p> : children}
    </div>
  )
}

const Fila = ({ principal, detalle, onClick }: { principal: string; detalle: string; onClick: () => void }) => (
  <button className="btn btn-ghost" style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', height: 'auto' }} onClick={onClick}>
    <div style={{ fontWeight: 700, fontSize: 14 }}>{principal}</div><div className="muted" style={{ fontSize: 12 }}>{detalle}</div>
  </button>
)

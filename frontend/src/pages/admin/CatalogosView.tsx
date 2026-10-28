import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { CatalogoItem, MetricaCampana } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Cargando, ErrorTexto } from '../../components/ui'

export default function CatalogosView() {
  return (
    <div>
      <h1 className="page-title">Catálogos</h1>
      <p className="page-sub">Paquetes (con su costo) y tipos que aparecen al capturar un paquete. Lo desactivado deja de ofrecerse, pero no se pierde de los clientes que ya lo tienen.</p>
      <div className="grid-2" style={{ alignItems: 'start' }}>
        <Lista tabla="paquetes" titulo="Paquetes" /><Lista tabla="tipos" titulo="Tipos" />
      </div>
      <UmbralesSemaforo />
    </div>
  )
}

function Lista({ tabla, titulo }: { tabla: 'paquetes' | 'tipos'; titulo: string }) {
  const { puedeEscribir } = useAuth()
  const [items, setItems] = useState<CatalogoItem[] | null>(null)
  const [nuevo, setNuevo] = useState('')
  const [error, setError] = useState<string | null>(null)
  const cargar = useCallback(() => api.get<CatalogoItem[]>(`/catalogos/${tabla}?todos=true`).then(setItems), [tabla])
  useEffect(() => { cargar() }, [cargar])
  const run = async (f: () => Promise<unknown>) => { setError(null); try { await f(); await cargar() } catch (e) { setError(e instanceof ApiError ? e.message : 'Error') } }
  if (!items) return <Cargando />
  return (
    <div className="card" style={{ padding: 18 }}>
      <h2 style={{ margin: '0 0 12px', fontSize: 16 }}>{titulo}</h2>
      {items.map((i) => (
        <div key={i.id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, opacity: i.activo ? 1 : 0.55 }}>
          <input type="number" aria-label="Orden" title="Orden" style={{ width: 56, flexShrink: 0 }} defaultValue={i.orden} disabled={!puedeEscribir}
            onBlur={(e) => Number(e.target.value) !== i.orden && run(() => api.patch(`/catalogos/${tabla}/${i.id}`, { orden: Number(e.target.value) }))} />
          <input type="text" aria-label="Nombre" defaultValue={i.nombre} disabled={!puedeEscribir} style={{ flex: 1, minWidth: 90 }}
            onBlur={(e) => e.target.value.trim() && e.target.value !== i.nombre && run(() => api.patch(`/catalogos/${tabla}/${i.id}`, { nombre: e.target.value }))} />
          {tabla === 'paquetes' && <input type="number" min="0" step="0.01" aria-label={`Costo de ${i.nombre}`} title="Costo" style={{ width: 100, flexShrink: 0 }}
            defaultValue={Number(i.costo ?? 0)} disabled={!puedeEscribir}
            onBlur={(e) => Number(e.target.value) !== Number(i.costo ?? 0) && run(() => api.patch(`/catalogos/${tabla}/${i.id}`, { costo: Number(e.target.value) }))} />}
          {puedeEscribir && <button className="btn btn-secondary btn-sm" onClick={() => run(() => api.patch(`/catalogos/${tabla}/${i.id}`, { activo: !i.activo }))}>{i.activo ? 'Desactivar' : 'Activar'}</button>}
        </div>))}
      {puedeEscribir && (
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          <input type="text" placeholder={`Nuevo ${tabla === 'paquetes' ? 'paquete' : 'tipo'}…`} value={nuevo} onChange={(e) => setNuevo(e.target.value)} />
          <button className="btn btn-primary" disabled={!nuevo.trim()} onClick={() => run(async () => { await api.post(`/catalogos/${tabla}`, { nombre: nuevo }); setNuevo('') })}>Agregar</button>
        </div>)}
      {tabla === 'paquetes' && <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>El orden define «subir/bajar de nivel» al renovar. El costo es el que se aplica cuando un CM da de alta ese paquete; puedes corregirlo después en la ficha del cliente.</p>}
      <ErrorTexto texto={error} />
    </div>
  )
}

function UmbralesSemaforo() {
  const { puedeEscribir } = useAuth()
  const [items, setItems] = useState<MetricaCampana[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cargar = useCallback(() => api.get<MetricaCampana[]>('/metricas').then(setItems), [])
  useEffect(() => { cargar() }, [cargar])
  const guardar = async (m: MetricaCampana, campo: 'umbral_bueno' | 'umbral_regular' | 'caida_mensajes_alerta_pct', valor: number) => {
    setError(null)
    try { await api.patch(`/metricas/${m.id}`, { [campo]: valor }) } catch (e) { setError(e instanceof ApiError ? e.message : 'Error') }
    await cargar()
  }
  if (!items) return <Cargando />
  const NOMBRE: Record<string, string> = { local: 'Local', nacional: 'Nacional', otro: 'Otro' }
  return (
    <div className="card" style={{ padding: 18, marginTop: 18 }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 16 }}>Semáforo de rendimiento de campañas</h2>
      <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>Se mide por <strong>costo por resultado</strong>: de 0 hasta «bueno» es verde, hasta «regular» es amarillo y por encima es rojo. Además baja un nivel si los mensajes caen más del porcentaje indicado. Cambiarlos recalcula el semáforo al instante.</p>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Tipo de campaña</th><th className="num">Bueno hasta</th><th className="num">Regular hasta</th><th className="num">Caída de mensajes que baja un nivel (%)</th></tr></thead><tbody>
        {items.map((m) => (
          <tr key={m.id}><td><strong>{NOMBRE[m.tipo] ?? m.tipo}</strong></td>
            {(['umbral_bueno', 'umbral_regular', 'caida_mensajes_alerta_pct'] as const).map((campo) => (
              <td key={campo} className="num"><input type="number" min="0" step="0.5" style={{ width: 90 }} defaultValue={m[campo]} disabled={!puedeEscribir}
                aria-label={`${campo} ${m.tipo}`} onBlur={(e) => Number(e.target.value) !== m[campo] && guardar(m, campo, Number(e.target.value))} /></td>))}
          </tr>))}
      </tbody></table></div>
      <ErrorTexto texto={error} />
    </div>
  )
}

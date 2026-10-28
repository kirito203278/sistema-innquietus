import { useState } from 'react'
import { useAuth } from '../../auth/AuthContext'
import Logo from '../../components/Logo'
import NotificationBell from '../../components/NotificationBell'
import { api } from '../../api/client'
import { useCallback, useEffect } from 'react'
import type { Bloqueo, UsuarioEquipo } from '../../api/types'
import CampanasView from '../campanas/CampanasView'
import Inicio from '../shared/Inicio'
import Ingresos from '../shared/Ingresos'
import NoRenovados from '../shared/NoRenovados'
import Reportes from '../shared/Reportes'
import Tablero from '../shared/Tablero'
import BitacoraView from './BitacoraView'
import CarteraView from './CarteraView'
import CatalogosView from './CatalogosView'
import EquipoView from './EquipoView'

type Vista = 'inicio' | 'cartera' | 'campanas' | 'renovaciones' | 'ingresos' | 'reportes' | 'no_renovados' | 'equipo' | 'catalogos' | 'bitacora'
const NAV: [Vista, string][] = [['inicio', 'Inicio'], ['cartera', 'Cartera'], ['campanas', 'Campañas'], ['renovaciones', 'Renovaciones'], ['ingresos', 'Ingresos'], ['reportes', 'Reportes'],
  ['no_renovados', 'No renovados'], ['equipo', 'Equipo'], ['catalogos', 'Catálogos'], ['bitacora', 'Bitácora']]

export default function AdminPanel() {
  const { user, logout } = useAuth()
  const [vista, setVista] = useState<Vista>('inicio')
  const [campana, setCampana] = useState<number | null>(null)
  const [abrir, setAbrir] = useState<{ id: number; paquete: number | null } | null>(null)
  const [refrescoCms, setRefrescoCms] = useState(0)
  const [cmTablero, setCmTablero] = useState('')
  const [cms, setCms] = useState<UsuarioEquipo[]>([])
  const [pendientes, setPendientes] = useState<Bloqueo[]>([])
  useEffect(() => { api.get<UsuarioEquipo[]>('/usuarios').then((u) => setCms(u.filter((x) => x.rol === 'cm' && x.activo))) }, [refrescoCms])
  const cargarPendientes = useCallback(() => api.get<Bloqueo[]>('/bloqueos').then(setPendientes).catch(() => undefined), [])
  useEffect(() => {
    cargarPendientes()
    const t = setInterval(cargarPendientes, 60_000)
    return () => clearInterval(t)
  }, [cargarPendientes, refrescoCms])

  const irACliente = (id: number, paquete: number | null = null) => { setAbrir({ id, paquete }); setVista('cartera') }
  const irACampana = (id: number) => { setCampana(id); setVista('campanas') }
  return (
    <div className="cm-layout">
      <aside className="cm-sidebar">
        <div className="cm-sidebar-header">
          <div style={{ flexShrink: 0 }}><Logo size={34} /></div>
          <div style={{ overflow: 'hidden', flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.nombre}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>Panel admin{user?.solo_lectura ? ' · solo lectura' : ''}</div>
          </div>
          <NotificationBell onAbrirPaquete={(c, p) => irACliente(c, p)} />
        </div>
        <div className="cm-sidebar-list">
          {NAV.map(([k, t]) => <button key={k} className={`cm-sidebar-item ${vista === k ? 'active' : ''}`} onClick={() => { setVista(k); if (k === 'cartera') setAbrir(null); if (k === 'campanas') setCampana(null) }}>{t}</button>)}
        </div>
        <button className="btn btn-ghost-dark" style={{ marginTop: 10 }} onClick={logout}>Cerrar sesión</button>
      </aside>
      <main className="cm-main">
        {pendientes.length > 0 && (
          <div className="callout callout-bad" style={{ marginTop: 0 }} role="status">
            <strong>{pendientes.length === 1 ? 'Hay 1 paquete' : `Hay ${pendientes.length} paquetes`} con el contrato terminado por decidir.</strong> Solo se pausa ese cliente; con los demás se sigue trabajando normal.
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
              {pendientes.map((b) => <button key={b.id} className="btn btn-secondary btn-sm" onClick={() => irACliente(b.cliente_id, b.id)}>{b.cliente_nombre} · {b.paquete}</button>)}
            </div>
          </div>)}
        {vista === 'inicio' && <Inicio key={refrescoCms} onAbrirCliente={(id, p) => irACliente(id, p ?? null)} onAbrirCampana={irACampana}
          onIr={(v) => { setVista(v); if (v === 'campanas') setCampana(null) }} />}
        {vista === 'campanas' && <CampanasView key={campana ?? 'lista'} abrirId={campana} onAbrirCliente={(id) => irACliente(id)} onCambio={() => setRefrescoCms((n) => n + 1)} />}
        {vista === 'cartera' && <CarteraView abrirId={abrir?.id ?? null} abrirPaquete={abrir?.paquete ?? null} cmsRefresco={refrescoCms} onAbrirCampana={irACampana} />}
        {vista === 'renovaciones' && (
          <div>
            <div className="field" style={{ maxWidth: 240 }}><label>CM</label>
              <select value={cmTablero} onChange={(e) => setCmTablero(e.target.value)}><option value="">Todos los CM</option>{cms.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select></div>
            <Tablero cmId={cmTablero ? Number(cmTablero) : null} mostrarCm onAbrir={(c, p) => irACliente(c, p)} />
          </div>)}
        {vista === 'ingresos' && <Ingresos onAbrirCliente={(id) => irACliente(id)} />}
        {vista === 'reportes' && <Reportes />}
        {vista === 'no_renovados' && <NoRenovados onAbrir={(id) => irACliente(id)} onCambio={() => setRefrescoCms((n) => n + 1)} />}
        {vista === 'equipo' && <EquipoView onCambio={() => setRefrescoCms((n) => n + 1)} />}
        {vista === 'catalogos' && <CatalogosView />}
        {vista === 'bitacora' && <BitacoraView />}
      </main>
    </div>
  )
}

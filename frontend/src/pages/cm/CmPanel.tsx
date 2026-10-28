import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Bloqueo } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import Logo from '../../components/Logo'
import NotificationBell from '../../components/NotificationBell'
import { quincenaActual } from '../../util'
import ClienteFicha from '../shared/ClienteFicha'
import { AgregarClienteModal } from '../shared/modales'
import NoRenovados from '../shared/NoRenovados'
import Tablero from '../shared/Tablero'
import CarteraCm from './CarteraCm'
import CampanasView from '../campanas/CampanasView'
import Inicio from '../shared/Inicio'

type Vista = 'inicio' | 'cartera' | 'campanas' | 'tablero' | 'no_renovados'
const NAV: [Vista, string][] = [['inicio', 'Inicio'], ['cartera', 'Mi cartera'], ['campanas', 'Campañas'], ['tablero', 'Renovaciones'], ['no_renovados', 'No renovados']]

export default function CmPanel() {
  const { user, logout } = useAuth()
  const [quincena, setQuincena] = useState<'1' | '2' | 'todas'>(quincenaActual())
  const [vista, setVista] = useState<Vista>('inicio')
  const [campana, setCampana] = useState<number | null>(null)
  const [abierto, setAbierto] = useState<{ id: number; paquete: number | null } | null>(null)
  const [agregando, setAgregando] = useState(false)
  const [recarga, setRecarga] = useState(0)
  const [pendientes, setPendientes] = useState<Bloqueo[]>([])

  const cargarPendientes = useCallback(() => api.get<Bloqueo[]>('/bloqueos').then(setPendientes).catch(() => undefined), [])
  useEffect(() => {
    cargarPendientes()
    const t = setInterval(cargarPendientes, 60_000)
    return () => clearInterval(t)
  }, [cargarPendientes, recarga])

  const abrir = (id: number, paquete: number | null = null) => { setAbierto({ id, paquete }); setVista('cartera') }
  const irACampana = (id: number) => { setCampana(id); setVista('campanas') }
  const refrescar = () => { setRecarga((n) => n + 1); cargarPendientes() }

  return (
    <div className="cm-layout">
      <aside className="cm-sidebar">
        <div className="cm-sidebar-header">
          <div style={{ flexShrink: 0 }}><Logo size={34} /></div>
          <div style={{ overflow: 'hidden', flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.nombre}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>Panel CM</div>
          </div>
          <NotificationBell onAbrirPaquete={(c, p) => abrir(c, p)} />
        </div>
        <div className="cm-sidebar-list">
          {NAV.map(([k, t]) => (
            <button key={k} className={`cm-sidebar-item ${vista === k && !(k === 'cartera' && abierto) ? 'active' : ''}`}
              onClick={() => { setVista(k); if (k === 'cartera') setAbierto(null); if (k === 'campanas') setCampana(null) }}>{t}</button>))}
        </div>
        <button className="btn btn-ghost-dark" style={{ marginTop: 10 }} onClick={logout}>Cerrar sesión</button>
      </aside>

      <main className="cm-main">
        {pendientes.length > 0 && (
          <div className="callout callout-bad" style={{ marginTop: 0 }} role="status">
            <strong>{pendientes.length === 1 ? 'Hay 1 paquete' : `Hay ${pendientes.length} paquetes`} con el contrato terminado por decidir.</strong> Solo se pausa ese cliente; con los demás sigues normal.
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
              {pendientes.map((b) => <button key={b.id} className="btn btn-secondary btn-sm" onClick={() => abrir(b.cliente_id, b.id)}>{b.cliente_nombre} · {b.paquete}</button>)}
            </div>
          </div>)}
        {vista === 'inicio' && <Inicio key={recarga} onAbrirCliente={(id, p) => abrir(id, p ?? null)} onAbrirCampana={irACampana}
          onIr={(v) => { setVista(v === 'renovaciones' ? 'tablero' : v); if (v === 'campanas') setCampana(null) }} />}
        {vista === 'campanas' && <CampanasView key={recarga + '-' + (campana ?? 'lista')} abrirId={campana} onAbrirCliente={(id) => abrir(id)} onCambio={refrescar} />}
        {vista === 'cartera' && (abierto
          ? <ClienteFicha key={abierto.id} clienteId={abierto.id} paqueteInicial={abierto.paquete} onChanged={refrescar}
              onDeleted={() => { setAbierto(null); refrescar() }} onVolver={() => setAbierto(null)} onAbrirCampana={irACampana} />
          : <CarteraCm quincena={quincena} setQuincena={setQuincena} onAbrir={(id) => abrir(id)} recarga={recarga} onAgregar={() => setAgregando(true)} />)}
        {vista === 'tablero' && <Tablero key={recarga} onAbrir={(c, p) => abrir(c, p)} />}
        {vista === 'no_renovados' && <NoRenovados key={recarga} onAbrir={(id) => abrir(id)} onCambio={refrescar} />}
      </main>

      {agregando && <AgregarClienteModal onClose={() => setAgregando(false)} onHecho={(id) => { setAgregando(false); refrescar(); abrir(id) }} />}
    </div>
  )
}

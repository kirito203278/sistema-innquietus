import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ClienteListItem, UsuarioEquipo } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Cargando, Semaforo } from '../../components/ui'
import { fecha } from '../../util'
import ClienteFicha from '../shared/ClienteFicha'
import { AgregarClienteModal } from '../shared/modales'

export default function CarteraView({ abrirId, abrirPaquete, cmsRefresco, onAbrirCampana }: { abrirId: number | null; abrirPaquete: number | null; cmsRefresco: number; onAbrirCampana?: (id: number) => void }) {
  const { puedeEscribir } = useAuth()
  const [cms, setCms] = useState<UsuarioEquipo[]>([])
  const [filtro, setFiltro] = useState<string>('todos')
  const [clientes, setClientes] = useState<ClienteListItem[] | null>(null)
  const [abierto, setAbierto] = useState<number | null>(abrirId)
  const [paq, setPaq] = useState<number | null>(abrirPaquete)
  const [agregando, setAgregando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => { setAbierto(abrirId); setPaq(abrirPaquete) }, [abrirId, abrirPaquete])
  useEffect(() => { api.get<UsuarioEquipo[]>('/usuarios').then((u) => setCms(u.filter((x) => x.rol === 'cm' && x.activo))) }, [cmsRefresco])
  const cargar = useCallback(() => {
    const p = filtro === 'por' ? '&por_reasignar=true' : filtro !== 'todos' ? `&cm_id=${filtro}` : ''
    return api.get<ClienteListItem[]>(`/clientes?estado=activo${p}`).then(setClientes)
  }, [filtro])
  useEffect(() => { setClientes(null); cargar() }, [cargar])

  async function reasignar(c: ClienteListItem, valor: string) {
    setError(null)
    try { await api.post(`/clientes/${c.id}/reasignar`, { cm_id: valor ? Number(valor) : null }); cargar() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo reasignar') }
  }

  if (abierto) return <ClienteFicha key={abierto} clienteId={abierto} paqueteInicial={paq} onChanged={cargar} onDeleted={() => { setAbierto(null); cargar() }} onVolver={() => { setAbierto(null); setPaq(null) }} onAbrirCampana={onAbrirCampana} />
  const lista = (clientes ?? []).filter((c) => c.nombre.toLowerCase().includes(q.toLowerCase()))
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div><h1 className="page-title">Cartera</h1><p className="page-sub" style={{ margin: 0 }}>Todos los clientes activos. Haz clic en uno para ver su ficha.</p></div>
        {puedeEscribir && <button className="btn btn-primary right" onClick={() => setAgregando(true)}>+ Agregar cliente</button>}
      </div>
      <div className="row" style={{ margin: '18px 0' }}>
        <div className="segmented light" style={{ flexWrap: 'wrap' }}>
          <button className={filtro === 'todos' ? 'active' : ''} onClick={() => setFiltro('todos')}>Todos</button>
          {cms.map((c) => <button key={c.id} className={filtro === String(c.id) ? 'active' : ''} onClick={() => setFiltro(String(c.id))}>{c.nombre} <span className="muted">({c.clientes_activos})</span></button>)}
          <button className={filtro === 'por' ? 'active' : ''} onClick={() => setFiltro('por')}>Por reasignar</button>
        </div>
        <div className="field" style={{ maxWidth: 240 }}><input type="text" placeholder="Buscar cliente…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      {error && <p className="error-text">{error}</p>}
      {!clientes ? <Cargando /> : lista.length === 0 ? <div className="card" style={{ padding: 24 }}><p className="muted" style={{ margin: 0 }}>Sin clientes en esta vista.</p></div> : (
        <div className="card table-scroll"><table className="data-table"><thead><tr><th></th><th>Cliente</th><th>CM</th><th className="num">Paquetes vigentes</th><th>Próxima renovación</th><th>Teléfono</th></tr></thead><tbody>
          {lista.map((c) => (
            <tr key={c.id} className="clickable-row" onClick={() => setAbierto(c.id)}>
              <td><Semaforo valor={c.semaforo} /></td><td><strong>{c.nombre}</strong></td>
              <td onClick={(e) => e.stopPropagation()}>
                {puedeEscribir ? (
                  <select value={c.cm_id ?? ''} onChange={(e) => reasignar(c, e.target.value)} style={{ padding: '4px 8px', width: 170 }} aria-label={`CM de ${c.nombre}`}>
                    <option value="">Por reasignar</option>{cms.map((m) => <option key={m.id} value={m.id}>{m.nombre}</option>)}</select>
                ) : (c.cm_nombre ?? 'Por reasignar')}</td>
              <td className="num">{c.paquetes_vigentes}</td><td>{fecha(c.proxima_renovacion)}</td><td className="muted">{c.telefono ?? '—'}</td></tr>))}
        </tbody></table></div>)}
      {agregando && <AgregarClienteModal cms={cms.map((c) => ({ id: c.id, nombre: c.nombre }))} onClose={() => setAgregando(false)}
        onHecho={(id) => { setAgregando(false); cargar(); setAbierto(id) }} />}
    </div>
  )
}

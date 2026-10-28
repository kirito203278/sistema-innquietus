import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { ClienteListItem } from '../../api/types'
import { Cargando, Semaforo } from '../../components/ui'
import { fecha } from '../../util'

export default function CarteraCm({ quincena, setQuincena, onAbrir, recarga, onAgregar }: {
  quincena: '1' | '2' | 'todas'; setQuincena: (q: '1' | '2' | 'todas') => void
  onAbrir: (id: number) => void; recarga: number; onAgregar: () => void
}) {
  const [clientes, setClientes] = useState<ClienteListItem[] | null>(null)
  const [q, setQ] = useState('')

  const cargar = useCallback(() => {
    const p = quincena === 'todas' ? '' : `&quincena=${quincena}`
    return api.get<ClienteListItem[]>(`/clientes?estado=activo${p}`).then(setClientes)
  }, [quincena])
  useEffect(() => { setClientes(null); cargar() }, [cargar, recarga])

  const lista = (clientes ?? []).filter((c) => c.nombre.toLowerCase().includes(q.toLowerCase()))
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div><h1 className="page-title">Mi cartera</h1><p className="page-sub" style={{ margin: 0 }}>Tus clientes activos. Haz clic en uno para ver su ficha.</p></div>
        <button className="btn btn-primary right" onClick={onAgregar}>+ Agregar cliente</button>
      </div>
      <div className="row" style={{ margin: '18px 0' }}>
        <div className="segmented light" style={{ flexWrap: 'wrap' }}>
          <button className={quincena === 'todas' ? 'active' : ''} onClick={() => setQuincena('todas')}>Todos</button>
          <button className={quincena === '1' ? 'active' : ''} onClick={() => setQuincena('1')}>1ra quincena</button>
          <button className={quincena === '2' ? 'active' : ''} onClick={() => setQuincena('2')}>2da quincena</button>
        </div>
        <div className="field" style={{ maxWidth: 240 }}><input type="text" placeholder="Buscar cliente…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      {!clientes ? <Cargando /> : lista.length === 0 ? <div className="card" style={{ padding: 24 }}><p className="muted" style={{ margin: 0 }}>Sin clientes en esta vista.</p></div> : (
        <div className="card table-scroll"><table className="data-table"><thead><tr>
          <th></th><th>Cliente</th><th className="num">Paquetes vigentes</th><th>Próxima renovación</th><th>Teléfono</th><th></th></tr></thead><tbody>
          {lista.map((c) => (
            <tr key={c.id} className="clickable-row" onClick={() => onAbrir(c.id)}>
              <td><Semaforo valor={c.semaforo} /></td><td><strong>{c.nombre}</strong></td>
              <td className="num">{c.paquetes_vigentes}</td><td>{fecha(c.proxima_renovacion)}</td><td className="muted">{c.telefono ?? '—'}</td>
              <td>{c.pendiente_decision && <span className="badge badge-bad">decidir</span>}</td></tr>))}
        </tbody></table></div>)}
    </div>
  )
}

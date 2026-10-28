import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { BitacoraItem } from '../../api/types'
import { Cargando } from '../../components/ui'
import { fechaHora } from '../../util'

export default function BitacoraView() {
  const [items, setItems] = useState<BitacoraItem[] | null>(null)
  useEffect(() => { api.get<BitacoraItem[]>('/admin/bitacora?limite=300').then(setItems) }, [])
  if (!items) return <Cargando />
  return (
    <div>
      <h1 className="page-title">Bitácora</h1>
      <p className="page-sub">Acciones sensibles: altas, bajas, reseteos, reasignaciones, cambios de catálogo, borrados y acciones de un admin por cuenta de un CM.</p>
      <div className="card table-scroll"><table className="data-table"><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Detalle</th></tr></thead><tbody>
        {items.map((b) => <tr key={b.id}><td style={{ whiteSpace: 'nowrap' }}>{fechaHora(b.creado_en)}</td><td>{b.usuario}</td><td><span className="badge badge-purple">{b.accion}</span></td>
          <td className="muted" style={{ fontSize: 12, fontFamily: 'ui-monospace, monospace' }}>{b.detalle ? JSON.stringify(b.detalle) : ''}</td></tr>)}
      </tbody></table></div>
    </div>
  )
}

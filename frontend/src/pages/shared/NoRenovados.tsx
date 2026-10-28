import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ClienteFicha, ClienteListItem } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Cargando, ErrorTexto, Modal } from '../../components/ui'
import { fecha, hoyIso, sumarDias } from '../../util'
import { CamposPaquete, paqueteBody, paqueteCompleto, paqueteVacio, useCatalogos } from './modales'

interface Info { archivado_en: string; forzar_nuevo: boolean; reingreso_meses: number; purga_meses: number; se_elimina_el: string }

export default function NoRenovados({ onAbrir, onCambio }: { onAbrir: (id: number) => void; onCambio: () => void }) {
  const { puedeEscribir, user, esCm } = useAuth()
  const [lista, setLista] = useState<ClienteListItem[] | null>(null)
  const [infos, setInfos] = useState<Record<number, Info>>({})
  const [reingresando, setReingresando] = useState<ClienteListItem | null>(null)
  const [eliminando, setEliminando] = useState<ClienteListItem | null>(null)
  const cargar = useCallback(async () => {
    const l = await api.get<ClienteListItem[]>('/clientes?estado=no_renovado')
    setLista(l)
    const entradas = await Promise.all(l.map(async (c) => [c.id, await api.get<Info>(`/clientes/${c.id}/reingreso-info`)] as const))
    setInfos(Object.fromEntries(entradas))
  }, [])
  useEffect(() => { cargar() }, [cargar])
  if (!lista) return <Cargando />
  return (
    <div>
      <h1 className="page-title">No renovados</h1>
      <p className="page-sub">Clientes sin ningún paquete activo. Se conservan 1 año con toda su información y después se eliminan de forma permanente.</p>
      {lista.length === 0 ? <div className="card" style={{ padding: 24 }}><p className="muted" style={{ margin: 0 }}>No hay clientes sin renovar.</p></div> : (
        <div className="card table-scroll"><table className="data-table"><thead><tr><th>Cliente</th>{user?.rol === 'admin' && <th>CM</th>}<th>No renovó desde</th><th>Se elimina el</th><th>Reingreso</th><th></th></tr></thead><tbody>
          {lista.map((c) => { const i = infos[c.id]; return (
            <tr key={c.id}><td><button className="btn btn-ghost btn-sm" style={{ fontWeight: 700 }} onClick={() => onAbrir(c.id)}>{c.nombre}</button></td>
              {user?.rol === 'admin' && <td>{c.cm_nombre ?? 'Por reasignar'}</td>}
              <td>{i ? fecha(i.archivado_en) : '…'}</td><td>{i ? fecha(i.se_elimina_el) : '…'}</td>
              <td>{i && (i.forzar_nuevo ? <span className="badge badge-warn">Paquete nuevo (se borra historial)</span> : <span className="badge badge-good">Puede continuar o crear nuevo</span>)}</td>
              <td className="num" style={{ whiteSpace: 'nowrap' }}>
                {puedeEscribir && <button className="btn btn-primary btn-sm" onClick={() => setReingresando(c)}>Reingresar</button>}
                {puedeEscribir && !esCm && <button className="btn btn-ghost btn-sm" style={{ marginLeft: 6 }} onClick={() => setEliminando(c)}>Eliminar…</button>}
              </td></tr>) })}
        </tbody></table></div>)}
      {eliminando && <Eliminar c={eliminando} onClose={() => setEliminando(null)}
        onHecho={() => { setEliminando(null); cargar(); onCambio() }} />}
      {reingresando && infos[reingresando.id] && <Reingreso c={reingresando} info={infos[reingresando.id]} onClose={() => setReingresando(null)}
        onHecho={() => { setReingresando(null); cargar(); onCambio() }} />}
    </div>
  )
}

function Eliminar({ c, onClose, onHecho }: { c: ClienteListItem; onClose: () => void; onHecho: () => void }) {
  const [confirma, setConfirma] = useState('')
  const [error, setError] = useState<string | null>(null)
  async function enviar() {
    setError(null)
    try { await api.del(`/clientes/${c.id}?confirmar_nombre=${encodeURIComponent(confirma)}`); onHecho() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo eliminar') }
  }
  return (
    <Modal title={`Eliminar a ${c.nombre}`} onClose={onClose} width={520}>
      <div className="callout callout-bad" style={{ marginTop: 0 }}>Se borra de forma <strong>permanente</strong>: su ficha, sus paquetes, sus pagos y su historial. No se puede deshacer.
        Si solo quieres dejar de verlo, no hace falta: los no renovados se guardan solos 1 año y después se eliminan.</div>
      <div className="field"><label>Escribe «{c.nombre}» para confirmar</label>
        <input type="text" value={confirma} onChange={(e) => setConfirma(e.target.value)} autoFocus /></div>
      <ErrorTexto texto={error} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-danger" disabled={confirma !== c.nombre} onClick={enviar}>Eliminar para siempre</button>
      </div>
    </Modal>
  )
}

function Reingreso({ c, info, onClose, onHecho }: { c: ClienteListItem; info: Info; onClose: () => void; onHecho: () => void }) {
  const { esCm } = useAuth()
  const cat = useCatalogos()
  const [modo, setModo] = useState<'continuar' | 'nuevo'>(info.forzar_nuevo ? 'nuevo' : 'continuar')
  const [pq, setPq] = useState(paqueteVacio())
    const [error, setError] = useState<string | null>(null)
  async function enviar() {
    setError(null)
    try {
      await api.post<ClienteFicha>(`/clientes/${c.id}/reingreso`, modo === 'continuar' ? { modo } : { modo, ...paqueteBody(pq, esCm) })
      onHecho()
    } catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo reingresar') }
  }
  return (
    <Modal title={`Reingresar a ${c.nombre}`} onClose={onClose} width={560}>
      {info.forzar_nuevo ? (
        <div className="callout callout-warn">Pasaron {info.reingreso_meses} meses o más desde que no renovó: se crea un <strong>paquete nuevo</strong> y el
          <strong> historial anterior se borra</strong> (paquetes y pagos).</div>
      ) : (
        <div className="segmented light full" style={{ marginBottom: 14 }}>
          <button className={modo === 'continuar' ? 'active' : ''} onClick={() => setModo('continuar')}>Continuar el paquete anterior</button>
          <button className={modo === 'nuevo' ? 'active' : ''} onClick={() => setModo('nuevo')}>Crear paquete nuevo</button>
        </div>)}
      {modo === 'continuar' ? (
        <div className="callout callout-info">Mismo paquete y tipo. El ciclo empieza <strong>hoy ({fecha(hoyIso())})</strong> y renueva el <strong>{fecha(sumarDias(hoyIso(), 30))}</strong>; el historial se conserva.</div>
      ) : <CamposPaquete v={pq} set={setPq} {...cat} sinCosto={esCm} />}
      {modo === 'nuevo' && <p className="muted" style={{ fontSize: 13 }}>Se usa como inicio la fecha de hoy; la renovación se calcula a los 30 días.{!info.forzar_nuevo && ' El historial anterior se conserva.'}</p>}
      <ErrorTexto texto={error} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" onClick={enviar} disabled={modo === 'nuevo' && !paqueteCompleto(pq, esCm)}>Reingresar cliente</button>
      </div>
    </Modal>
  )
}

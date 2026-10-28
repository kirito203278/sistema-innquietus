import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Tablero as TableroT, TarjetaTablero } from '../../api/types'
import SelectorPeriodo, { periodoInicial, periodoQuery, type PeriodoSel } from '../../components/SelectorPeriodo'
import { useAuth } from '../../auth/AuthContext'
import { Cargando, Semaforo } from '../../components/ui'
import { dinero, diasTexto, fecha } from '../../util'

const COLUMNAS: { clave: keyof TableroT['columnas']; titulo: string; ayuda: string; color: string }[] = [
  { clave: 'por_vencer', titulo: 'Por vencer', ayuda: 'Renuevan en 4 días o menos', color: 'badge-yellow' },
  { clave: 'en_prorroga', titulo: 'En prórroga', ayuda: 'Ya decidieron: se trabaja normal hasta que termine el plazo', color: 'badge-yellow' },
  { clave: 'vencidos', titulo: 'Vencidos sin decisión', ayuda: 'Llegó la fecha y falta decidir', color: 'badge-bad' },
  { clave: 'renovados_sin_pago', titulo: 'Renovados sin pago', ayuda: 'Renovó, pero se debe algo', color: 'badge-warn' },
  { clave: 'completos', titulo: 'Completos', ayuda: 'Renovados y pagados', color: 'badge-good' },
]

export default function Tablero({ onAbrir, cmId, mostrarCm }: { onAbrir: (clienteId: number, paqueteId: number) => void; cmId?: number | null; mostrarCm?: boolean }) {
  const { esCm } = useAuth()
  const [per, setPer] = useState<PeriodoSel>(() => { const p = periodoInicial(); return { ...p, quincena: p.quincena } })
  const [data, setData] = useState<TableroT | null>(null)
  const cargar = useCallback(() => {
    setData(null)
    api.get<TableroT>(`/renovaciones/tablero?${periodoQuery(per)}${cmId ? `&cm_id=${cmId}` : ''}`).then(setData)
  }, [per, cmId])
  useEffect(() => { cargar() }, [cargar])

  return (
    <div>
      <h1 className="page-title">Renovaciones de la quincena</h1>
      <p className="page-sub">Cada tarjeta es un paquete. Haz clic para abrir la ficha del cliente.</p>
      <SelectorPeriodo valor={per} onChange={setPer} />
      {!data ? <Cargando /> : (
        <>
          <div className="kanban">
            {COLUMNAS.map((c) => (
              <div className="kanban-col" key={c.clave}>
                <h3><span title={c.ayuda}>{c.titulo}</span><span className={`badge ${c.color}`}>{data.columnas[c.clave].length}</span></h3>
                {data.columnas[c.clave].length === 0 && <p className="muted" style={{ fontSize: 12, margin: '4px 6px' }}>{c.ayuda}</p>}
                {data.columnas[c.clave].map((t) => <Tarjeta key={t.id} t={t} onClick={() => onAbrir(t.cliente_id, t.id)} verCm={!!mostrarCm} sinMontos={esCm} />)}
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: 14 }}>
            {data.en_plazo} paquete(s) más de este periodo siguen en plazo. «Vencidos» y «Renovados sin pago» incluyen también lo arrastrado de periodos anteriores
            (marcado «arrastrado»), para que nada se pierda de vista.
          </p>
        </>
      )}
    </div>
  )
}

function Tarjeta({ t, onClick, verCm, sinMontos }: { t: TarjetaTablero; onClick: () => void; verCm: boolean; sinMontos: boolean }) {
  return (
    <button className="kanban-card" onClick={onClick}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6, alignItems: 'center' }}>
        <strong style={{ fontSize: 14 }}>{t.cliente_nombre}</strong><Semaforo valor={t.semaforo} />
      </div>
      <div className="muted" style={{ fontSize: 12 }}>{t.paquete} · {t.tipo}{verCm && t.cm_nombre ? ` · ${t.cm_nombre}` : ''}</div>
      <div style={{ fontSize: 13, marginTop: 6 }}>{fecha(t.fecha_renovacion)} · <span className="muted">{diasTexto(t.dias_para_renovar)}</span></div>
      {!sinMontos && (
        <div style={{ fontSize: 13, display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
          <span>Pagado {dinero(t.pagado)}</span><strong style={{ color: t.restante > 0 ? 'var(--warn)' : 'var(--good)' }}>{t.restante > 0 ? `Debe ${dinero(t.restante)}` : 'Pagado'}</strong>
        </div>)}
      <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
        {t.arrastrado && <span className="badge badge-neutral">arrastrado</span>}
        {t.bloqueado && <span className="badge badge-bad">bloqueado: decidir</span>}
        {t.no_renovara && <span className="badge badge-neutral">no renovará</span>}
        {t.prorroga_vencida && <span className="badge badge-bad">prórroga vencida</span>}
        {t.prorroga_activa && <span className="badge badge-yellow">prórroga hasta {fecha(t.prorroga_hasta)}</span>}
      </div>
    </button>
  )
}

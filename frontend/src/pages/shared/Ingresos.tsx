import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { IngresosResp } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import SelectorPeriodo, { periodoInicial, periodoQuery, type PeriodoSel } from '../../components/SelectorPeriodo'
import { Cargando, Progreso } from '../../components/ui'
import { dinero } from '../../util'

export function BannerPeriodo({ texto, cerrado }: { texto: string; cerrado: boolean }) {
  return <div className={`callout ${cerrado ? 'callout-good' : 'callout-warn'}`} style={{ marginTop: 0 }}><strong>{texto}</strong></div>
}

export default function Ingresos({ onAbrirCliente }: { onAbrirCliente?: (id: number) => void }) {
  const { user } = useAuth()
  const [per, setPer] = useState<PeriodoSel>(() => periodoInicial('ambas'))
  const [cmFiltro, setCmFiltro] = useState<string>('')
  const [data, setData] = useState<IngresosResp | null>(null)
  const admin = user?.rol === 'admin'
  useEffect(() => {
    setData(null)
    api.get<IngresosResp>(`/ingresos?${periodoQuery(per)}${admin && cmFiltro ? `&cm_id=${cmFiltro}` : ''}`).then(setData)
  }, [per, cmFiltro, admin])

  return (
    <div>
      <h1 className="page-title">Ingresos</h1>
      <p className="page-sub">Proyección = costo de los paquetes que renuevan en el periodo. Actual = lo pagado de esos paquetes hasta hoy.</p>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <SelectorPeriodo valor={per} onChange={setPer} />
        {admin && data?.por_cm && (
          <div className="field" style={{ maxWidth: 220, marginBottom: 18 }}><label>CM</label>
            <select value={cmFiltro} onChange={(e) => setCmFiltro(e.target.value)}>
              <option value="">Todos</option>{data.por_cm.filter((c) => c.cm_id).map((c) => <option key={c.cm_id} value={c.cm_id!}>{c.cm}</option>)}
            </select></div>)}
      </div>
      {!data ? <Cargando /> : (
        <>
          <BannerPeriodo texto={`${data.periodo.etiqueta} · ${data.periodo.estado_texto}`} cerrado={data.periodo.cerrado} />
          <div className="stat-grid">
            <div className="card stat"><div className="label">Proyección</div><div className="value">{dinero(data.totales.proyeccion)}</div></div>
            <div className="card stat"><div className="label">Actual (cobrado)</div><div className="value" style={{ color: 'var(--good)' }}>{dinero(data.totales.cobrado)}</div></div>
            <div className="card stat"><div className="label">Pendiente</div><div className="value" style={{ color: 'var(--warn)' }}>{dinero(data.totales.pendiente)}</div></div>
            <div className="card stat"><div className="label">% cobrado</div><div className="value">{data.totales.pct_cobrado.toFixed(1)}%</div><div style={{ marginTop: 8 }}><Progreso pct={data.totales.pct_cobrado} /></div></div>
            <div className="card stat"><div className="label">Tasa de renovación</div><div className="value">{data.tasa_total.tasa.toFixed(1)}%</div>
              <div className="muted" style={{ fontSize: 12 }}>{data.tasa_total.renovados} de {data.tasa_total.vencidos} vencidos</div></div>
          </div>

          {admin && data.por_cm && data.total_general && (
            <>
              <div className="section-title">Por CM (total general)</div>
              <div className="card table-scroll"><table className="data-table"><thead><tr><th>CM</th><th className="num">Clientes</th><th className="num">Paquetes</th>
                <th className="num">Proyección</th><th className="num">Actual</th><th className="num">Pendiente</th><th style={{ width: 160 }}>% cobrado</th><th className="num">Tasa renov.</th></tr></thead><tbody>
                {data.por_cm.map((c) => {
                  const t = data.tasa_renovacion?.find((x) => x.cm_id === c.cm_id)
                  return <tr key={c.cm}><td>{c.cm}</td><td className="num">{c.clientes}</td><td className="num">{c.paquetes}</td><td className="num">{dinero(c.proyeccion)}</td>
                    <td className="num">{dinero(c.cobrado)}</td><td className="num">{dinero(c.pendiente)}</td>
                    <td><div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><div style={{ flex: 1 }}><Progreso pct={c.pct_cobrado} /></div><span style={{ fontSize: 12, width: 42, textAlign: 'right' }}>{c.pct_cobrado.toFixed(1)}%</span></div></td>
                    <td className="num">{t ? `${t.tasa.toFixed(1)}% (${t.renovados}/${t.vencidos})` : '—'}</td></tr>
                })}
                <tr className="table-total"><td>Total general</td><td className="num">{data.total_general.clientes}</td><td className="num">{data.total_general.paquetes}</td>
                  <td className="num">{dinero(data.total_general.proyeccion)}</td><td className="num">{dinero(data.total_general.cobrado)}</td><td className="num">{dinero(data.total_general.pendiente)}</td>
                  <td className="num">{data.total_general.pct_cobrado.toFixed(1)}%</td><td className="num">{data.tasa_total.tasa.toFixed(1)}%</td></tr>
              </tbody></table></div>
            </>)}

          <div className="section-title">Por cliente</div>
          {data.clientes.length === 0 ? <p className="muted">Sin paquetes con renovación en este periodo.</p> : (
            <div className="card table-scroll"><table className="data-table"><thead><tr><th>Cliente</th>{admin && <th>CM</th>}<th className="num">Paquetes</th>
              <th className="num">Proyección</th><th className="num">Actual</th><th className="num">Pendiente</th><th className="num">% cobrado</th></tr></thead><tbody>
              {data.clientes.map((c) => (
                <tr key={c.cliente_id} className={onAbrirCliente ? 'clickable-row' : ''} onClick={() => onAbrirCliente?.(c.cliente_id)}>
                  <td>{c.cliente}</td>{admin && <td>{c.cm}</td>}<td className="num">{c.paquetes}</td><td className="num">{dinero(c.proyeccion)}</td>
                  <td className="num">{dinero(c.actual)}</td><td className="num">{dinero(c.pendiente)}</td><td className="num">{c.pct_cobrado.toFixed(1)}%</td></tr>))}
              <tr className="table-total"><td>Total</td>{admin && <td></td>}<td className="num">{data.totales.paquetes}</td><td className="num">{dinero(data.totales.proyeccion)}</td>
                <td className="num">{dinero(data.totales.cobrado)}</td><td className="num">{dinero(data.totales.pendiente)}</td><td className="num">{data.totales.pct_cobrado.toFixed(1)}%</td></tr>
            </tbody></table></div>)}
        </>)}
    </div>
  )
}

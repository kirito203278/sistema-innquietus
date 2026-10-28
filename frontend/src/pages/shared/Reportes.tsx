import { useEffect, useState } from 'react'
import { api, ApiError, downloadFile } from '../../api/client'
import type { FilaDetalle, ReporteDatos } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import SelectorPeriodo, { periodoInicial, periodoQuery, type PeriodoSel } from '../../components/SelectorPeriodo'
import { Cargando, ErrorTexto, Semaforo } from '../../components/ui'
import { dinero, diasTexto, fecha } from '../../util'
import { BannerPeriodo } from './Ingresos'

export default function Reportes() {
  const { user } = useAuth()
  const [per, setPer] = useState<PeriodoSel>(() => periodoInicial('ambas'))
  const [d, setD] = useState<ReporteDatos | null>(null)
  const [descargando, setDescargando] = useState<'pdf' | 'excel' | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { setD(null); api.get<ReporteDatos>(`/reportes/datos?${periodoQuery(per)}`).then(setD).catch((e) => setError(e.message)) }, [per])

  async function bajar(tipo: 'pdf' | 'excel') {
    setDescargando(tipo); setError(null)
    try { await downloadFile(`/reportes/${tipo}?${periodoQuery(per)}`, `reporte.${tipo === 'pdf' ? 'pdf' : 'xlsx'}`) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo descargar') } finally { setDescargando(null) }
  }
  return (
    <div>
      <h1 className="page-title">Reportes</h1>
      <p className="page-sub">{user?.rol === 'admin' ? 'Reporte de toda la agencia.' : 'Reporte de tu cartera.'} PDF para presentar, Excel para trabajar los números.</p>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <SelectorPeriodo valor={per} onChange={setPer} />
        <div style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
          <button className="btn btn-primary" disabled={!!descargando} onClick={() => bajar('pdf')}>{descargando === 'pdf' ? <span className="spinner" /> : 'Descargar PDF'}</button>
          <button className="btn btn-secondary" disabled={!!descargando} onClick={() => bajar('excel')}>{descargando === 'excel' ? <span className="spinner" style={{ borderTopColor: 'var(--inn-purple-600)' }} /> : 'Descargar Excel'}</button>
        </div>
      </div>
      <ErrorTexto texto={error} />
      {!d ? <Cargando /> : <Vista d={d} />}
    </div>
  )
}

function Vista({ d }: { d: ReporteDatos }) {
  return (
    <div>
      <BannerPeriodo texto={`${d.periodo.etiqueta} · ${d.periodo.estado_texto}`} cerrado={d.periodo.cerrado} />
      <div className="section-title">1. Resumen general</div>
      <div className="stat-grid">
        <div className="card stat"><div className="label">Proyección</div><div className="value">{dinero(d.resumen.proyeccion)}</div></div>
        <div className="card stat"><div className="label">Cobrado</div><div className="value" style={{ color: 'var(--good)' }}>{dinero(d.resumen.cobrado)}</div></div>
        <div className="card stat"><div className="label">Pendiente</div><div className="value" style={{ color: 'var(--warn)' }}>{dinero(d.resumen.pendiente)}</div></div>
        <div className="card stat"><div className="label">% cobrado</div><div className="value">{d.resumen.pct_cobrado.toFixed(1)}%</div></div>
      </div>

      <div className="section-title">2. Por CM</div>
      <div className="card table-scroll"><table className="data-table"><thead><tr><th>CM</th><th className="num">Clientes</th><th className="num">Paquetes</th><th className="num">Proyección</th><th className="num">Cobrado</th><th className="num">Pendiente</th><th className="num">% cobrado</th></tr></thead><tbody>
        {d.por_cm.map((c) => <tr key={c.cm}><td>{c.cm}</td><td className="num">{c.clientes}</td><td className="num">{c.paquetes}</td><td className="num">{dinero(c.proyeccion)}</td><td className="num">{dinero(c.cobrado)}</td><td className="num">{dinero(c.pendiente)}</td><td className="num">{c.pct_cobrado.toFixed(1)}%</td></tr>)}
        <tr className="table-total"><td>Total</td><td className="num">{d.total_cm.clientes}</td><td className="num">{d.total_cm.paquetes}</td><td className="num">{dinero(d.total_cm.proyeccion)}</td><td className="num">{dinero(d.total_cm.cobrado)}</td><td className="num">{dinero(d.total_cm.pendiente)}</td><td className="num">{d.total_cm.pct_cobrado.toFixed(1)}%</td></tr>
      </tbody></table></div>

      <div className="section-title">3. Detalle por paquete</div>
      <div className="card table-scroll"><table className="data-table"><thead><tr><th>CM</th><th>Cliente</th><th>Paquete</th><th>Tipo</th><th className="num">Costo</th><th className="num">Pagado</th><th className="num">Restante</th><th>Renovación</th><th>Estado</th><th>Semáforo</th></tr></thead><tbody>
        {d.detalle.length === 0 && <tr><td colSpan={10} className="muted">Sin paquetes en este periodo.</td></tr>}
        {d.detalle.map((f) => <tr key={f.paquete_id}><td>{f.cm}</td><td>{f.cliente}</td><td>{f.paquete}</td><td>{f.tipo}</td><td className="num">{dinero(f.costo)}</td><td className="num">{dinero(f.pagado)}</td><td className="num">{dinero(f.restante)}</td><td>{fecha(f.fecha_renovacion)}</td><td>{f.estado_efectivo.replace('_', ' ')}</td><td><Semaforo valor={f.semaforo} /></td></tr>)}
      </tbody></table></div>

      <div className="section-title">4. Prórrogas</div>
      {d.prorrogas.length === 0 ? <p className="muted">No hay prórrogas activas ni vencidas con saldo.</p> : (
        <div className="card table-scroll"><table className="data-table"><thead><tr><th>CM</th><th>Cliente</th><th>Paquete</th><th className="num">Restante por cobrar</th><th>Fecha límite</th><th>Situación</th></tr></thead><tbody>
          {d.prorrogas.map((p, i) => <tr key={i} className={p.vencida ? 'row-bad' : ''}><td>{p.cm}</td><td>{p.cliente}</td><td>{p.paquete}</td><td className="num">{dinero(p.restante)}</td><td>{fecha(p.fecha_limite)}</td><td>{p.vencida ? <strong>VENCIDA · </strong> : null}{diasTexto(p.dias)}</td></tr>)}
        </tbody></table></div>)}

      <div className="section-title">5. Pendientes de renovar</div>
      {(['por_vencer', 'vencidos', 'renovados_sin_pago'] as const).map((k) => {
        const titulos = { por_vencer: 'Por vencer', vencidos: 'Vencidos sin decisión', renovados_sin_pago: 'Renovados sin pago' }
        return <div key={k} style={{ marginBottom: 12 }}><strong>{titulos[k]}</strong>
          {d.pendientes[k].length === 0 ? <span className="muted"> — ninguno</span> : d.pendientes[k].map((g) => <Grupo key={g.cm} cm={g.cm} items={g.items} />)}</div>
      })}

      <div className="section-title">6. Tasa de renovación por CM</div>
      <div className="card table-scroll"><table className="data-table"><thead><tr><th>CM</th><th className="num">Vencidos del periodo</th><th className="num">Renovados</th><th className="num">Tasa</th></tr></thead><tbody>
        {d.tasa_renovacion.map((t) => <tr key={t.cm}><td>{t.cm}</td><td className="num">{t.vencidos}</td><td className="num">{t.renovados}</td><td className="num">{t.tasa.toFixed(1)}%</td></tr>)}
        <tr className="table-total"><td>Total</td><td className="num">{d.tasa_total.vencidos}</td><td className="num">{d.tasa_total.renovados}</td><td className="num">{d.tasa_total.tasa.toFixed(1)}%</td></tr>
      </tbody></table></div>
    </div>
  )
}

function Grupo({ cm, items }: { cm: string; items: FilaDetalle[] }) {
  return (
    <div style={{ margin: '6px 0 0 12px' }}><span className="muted" style={{ fontSize: 13 }}>{cm}</span>
      <table className="data-table"><tbody>{items.map((f) => <tr key={f.paquete_id}><td>{f.cliente}</td><td>{f.paquete}</td><td>{fecha(f.fecha_renovacion)}</td><td className="num">{dinero(f.restante)}</td><td><Semaforo valor={f.semaforo} /></td></tr>)}</tbody></table></div>
  )
}

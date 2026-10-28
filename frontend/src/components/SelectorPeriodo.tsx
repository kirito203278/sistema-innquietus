import { MESES, hoyIso, quincenaActual } from '../util'

export interface PeriodoSel { anio: number; mes: number; quincena: '1' | '2' | 'ambas' }

export function periodoInicial(quincena: PeriodoSel['quincena'] = quincenaActual()): PeriodoSel {
  const h = hoyIso()
  return { anio: Number(h.slice(0, 4)), mes: Number(h.slice(5, 7)), quincena }
}
export const periodoQuery = (p: PeriodoSel) => `anio=${p.anio}&mes=${p.mes}&quincena=${p.quincena}`

export default function SelectorPeriodo({ valor, onChange }: { valor: PeriodoSel; onChange: (p: PeriodoSel) => void }) {
  const anioActual = Number(hoyIso().slice(0, 4))
  return (
    <div className="row" style={{ marginBottom: 18 }}>
      <div className="field" style={{ maxWidth: 170 }}>
        <label>Mes</label>
        <select value={valor.mes} onChange={(e) => onChange({ ...valor, mes: Number(e.target.value) })}>
          {MESES.map((m, i) => <option key={m} value={i + 1}>{m[0].toUpperCase() + m.slice(1)}</option>)}
        </select>
      </div>
      <div className="field" style={{ maxWidth: 110 }}>
        <label>Año</label>
        <select value={valor.anio} onChange={(e) => onChange({ ...valor, anio: Number(e.target.value) })}>
          {[anioActual - 2, anioActual - 1, anioActual, anioActual + 1].map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <div className="field" style={{ maxWidth: 230 }}>
        <label>Periodo</label>
        <select value={valor.quincena} onChange={(e) => onChange({ ...valor, quincena: e.target.value as PeriodoSel['quincena'] })}>
          <option value="1">1ra quincena</option>
          <option value="2">2da quincena</option>
          <option value="ambas">Mes completo (ambas)</option>
        </select>
      </div>
    </div>
  )
}

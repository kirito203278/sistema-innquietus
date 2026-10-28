import { useLayoutEffect, useRef, useState } from 'react'

export interface LinePoint {
  label: string
  value: number
  tooltip: string
}

export default function LineChart({ data, height = 140, color = 'var(--inn-purple-600)', valueFormat }: {
  data: LinePoint[]
  height?: number
  color?: string
  valueFormat?: (v: number) => string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  // El viewBox usa el ancho real en px (no una escala abstracta de 100
  // unidades) para que X y Y se escalen igual: si no, los círculos de cada
  // punto salen estirados como óvalo en vez de círculo.
  const [svgWidth, setSvgWidth] = useState(600)

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setSvgWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  if (data.length === 0) {
    return <p style={{ color: 'var(--ink-500)', fontSize: 13 }}>Sin datos todavía.</p>
  }

  const scale = svgWidth / 100
  const values = data.map((d) => d.value)
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const padTop = 14
  const padBottom = 20
  const padX = 6
  const plotH = height - padTop - padBottom
  const plotW = 100 - padX * 2
  const step = data.length > 1 ? plotW / (data.length - 1) : 0

  const points = data.map((d, i) => {
    const xPct = data.length > 1 ? padX + i * step : 50
    const y = padTop + plotH - ((d.value - min) / range) * plotH
    return { xPct, x: xPct * scale, y, d }
  })

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${svgWidth} ${height}`} width="100%" height={height}
           role="img" aria-label="Gráfica de línea">
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover((h) => (h === i ? null : h))}>
            <circle cx={p.x} cy={p.y} r={hover === i ? 3.2 : 2.2} fill={color} stroke="white" strokeWidth="1" />
            <rect x={p.x - (step * scale) / 2} y={0} width={(step || 100) * scale} height={height} fill="transparent" style={{ cursor: 'pointer' }} />
          </g>
        ))}
      </svg>
      {/* Etiquetas como HTML, no <text> dentro del SVG (más nítidas, y no
          dependen del viewBox). Siguen posicionadas por porcentaje. */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        {points.map((p, i) => (
          <span key={i} style={{
            position: 'absolute', top: height - 18, left: `${p.xPct}%`,
            transform: 'translateX(-50%)', fontSize: 11, color: 'var(--ink-500)', whiteSpace: 'nowrap',
          }}>
            {p.d.label}
          </span>
        ))}
      </div>
      {hover !== null && (
        <div style={{
          position: 'absolute', top: 0, left: `${points[hover].xPct}%`, transform: 'translate(-50%, -100%)',
          background: 'var(--ink-900)', color: 'white', fontSize: 12, padding: '5px 9px', borderRadius: 6,
          whiteSpace: 'nowrap', pointerEvents: 'none', marginTop: -6,
        }}>
          {valueFormat ? valueFormat(points[hover].d.value) : points[hover].d.value} — {points[hover].d.tooltip}
        </div>
      )}
    </div>
  )
}

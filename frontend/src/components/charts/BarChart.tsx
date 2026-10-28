import { useLayoutEffect, useRef, useState } from 'react'

export interface BarDatum {
  label: string
  value: number
  color: string
  tooltip: string
}

const STATUS_COLOR: Record<string, string> = {
  bueno: 'var(--good)',
  regular: 'var(--warn)',
  bajo: 'var(--bad)',
}

export function statusColor(nivel: string | null | undefined): string {
  return nivel ? STATUS_COLOR[nivel] ?? 'var(--ink-300)' : 'var(--ink-300)'
}

export default function BarChart({ data, height = 160, valueFormat }: {
  data: BarDatum[]
  height?: number
  valueFormat?: (v: number) => string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  // El viewBox usa el ancho real en px (no una escala abstracta de 100
  // unidades) para que X y Y se escalen igual: si no, rects/círculos salen
  // estirados y las letras del SVG (ya movidas a HTML) también salían mal.
  const [svgWidth, setSvgWidth] = useState(600)

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setSvgWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const max = Math.max(1, ...data.map((d) => d.value))
  const barWidthPct = 100 / data.length
  const scale = svgWidth / 100

  if (data.length === 0) {
    return <p style={{ color: 'var(--ink-500)', fontSize: 13 }}>Sin datos todavía.</p>
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${svgWidth} ${height}`} width="100%" height={height}
           role="img" aria-label="Gráfica de barras">
        {data.map((d, i) => {
          const h = (d.value / max) * (height - 28)
          const x = (i * barWidthPct + barWidthPct * 0.18) * scale
          const w = barWidthPct * 0.64 * scale
          const y = height - 20 - h
          return (
            <g key={i}
               onMouseEnter={() => setHover(i)}
               onMouseLeave={() => setHover((h2) => (h2 === i ? null : h2))}
               style={{ cursor: 'pointer' }}>
              <rect x={x} y={y} width={w} height={Math.max(h, 2)} rx={2} fill={d.color}
                    opacity={hover === null || hover === i ? 1 : 0.45} />
            </g>
          )
        })}
      </svg>
      {/* Etiquetas como HTML, no <text> dentro del SVG (más nítidas, y no
          dependen del viewBox). Siguen posicionadas por porcentaje. */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        {data.map((d, i) => (
          <span key={i} style={{
            position: 'absolute', top: height - 18, left: `${i * barWidthPct + barWidthPct / 2}%`,
            transform: 'translateX(-50%)', fontSize: 11, color: 'var(--ink-500)', whiteSpace: 'nowrap',
          }}>
            {d.label}
          </span>
        ))}
      </div>
      {hover !== null && (
        <div style={{
          position: 'absolute', top: 0, left: `${hover * barWidthPct + barWidthPct / 2}%`, transform: 'translate(-50%, -100%)',
          background: 'var(--ink-900)', color: 'white', fontSize: 12, padding: '5px 9px', borderRadius: 6,
          whiteSpace: 'nowrap', pointerEvents: 'none', marginTop: -6,
        }}>
          {valueFormat ? valueFormat(data[hover].value) : data[hover].value} — {data[hover].tooltip}
        </div>
      )}
    </div>
  )
}

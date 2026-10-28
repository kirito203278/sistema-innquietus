const MXN = new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' })
export const dinero = (n: number | null | undefined) => MXN.format(Number(n ?? 0))

export function fecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

export function fechaHora(iso: string): string {
  return new Date(iso).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Mexico_City' })
}

export function hoyIso(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City' }).format(new Date())
}

export function sumarDias(iso: string, dias: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + dias))
  return dt.toISOString().slice(0, 10)
}

export function quincenaActual(): '1' | '2' {
  return Number(hoyIso().slice(8, 10)) <= 15 ? '1' : '2'
}

export const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

export const ESTADO_LABEL: Record<string, string> = {
  activo: 'Activo', por_vencer: 'Por vencer', vencido: 'Vencido', renovado: 'Renovado', archivado: 'Archivado', eliminado: 'Eliminado',
}
export const SEMAFORO_LABEL: Record<string, string> = {
  verde: 'Renovación pagada', amarillo: 'Confirmada, sin pago', rojo: 'Vencido sin decisión', gris: 'Pendiente en plazo',
}

export function diasTexto(d: number): string {
  if (d > 0) return `faltan ${d} día${d === 1 ? '' : 's'}`
  if (d === 0) return 'vence hoy'
  return `${-d} día${d === -1 ? '' : 's'} de retraso`
}

export const RENDIMIENTO_LABEL: Record<string, string> = { bueno: 'Bueno', regular: 'Regular', bajo: 'Bajo' }
export const RENDIMIENTO_BADGE: Record<string, string> = { bueno: 'badge-good', regular: 'badge-yellow', bajo: 'badge-bad' }
export const CAMPANA_ESTADO_BADGE: Record<string, string> = { activa: 'badge-good', vencida: 'badge-bad', cerrada: 'badge-neutral' }
export const TIPO_CAMPANA_LABEL: Record<string, string> = { local: 'Local', nacional: 'Nacional', otro: 'Otro' }

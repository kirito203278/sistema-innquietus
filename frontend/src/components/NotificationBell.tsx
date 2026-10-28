import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { NotificacionesResp, Notificacion, Recordatorio } from '../api/types'
import { fechaHora } from '../util'
import { BotonCopiar, Modal } from './ui'

const POLL_MS = 45_000

export default function NotificationBell({ onAbrirPaquete }: { onAbrirPaquete?: (clienteId: number, paqueteId: number | null) => void }) {
  const { esCm } = useAuth()
  const [data, setData] = useState<NotificacionesResp | null>(null)
  const [open, setOpen] = useState(false)
  const [recordatorio, setRecordatorio] = useState<Recordatorio | null>(null)
  const vistas = useRef<Set<number> | null>(null)
  const contenedor = useRef<HTMLDivElement>(null)

  const cargar = useCallback(async () => {
    const resp = await api.get<NotificacionesResp>('/notificaciones')
    setData(resp)

    if (vistas.current === null) vistas.current = new Set(resp.items.map((n) => n.id))
    else for (const n of resp.items) {
      if (!n.leida && !vistas.current.has(n.id)) {
        vistas.current.add(n.id)
        if ('Notification' in window && Notification.permission === 'granted') new Notification('INNquietus', { body: n.mensaje, tag: `n-${n.id}` })
      }
    }
  }, [])

  useEffect(() => {
    cargar().catch(() => undefined)
    const t = setInterval(() => cargar().catch(() => undefined), POLL_MS)
    return () => clearInterval(t)
  }, [cargar])

  useEffect(() => {
    if (!open) return
    const fuera = (e: MouseEvent) => { if (contenedor.current && !contenedor.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', fuera)
    return () => document.removeEventListener('mousedown', fuera)
  }, [open])

  function alAbrir() {
    setOpen((o) => !o)
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => undefined)
  }

  async function verMensaje(paqueteId: number) {
    const lista = await api.get<Recordatorio[]>(`/paquetes/${paqueteId}/recordatorios`)
    if (lista[0]) setRecordatorio(lista[0])
  }

  async function leer(n: Notificacion) {
    if (!n.leida) { await api.post(`/notificaciones/${n.id}/leer`); cargar() }
    if (n.cliente_id && onAbrirPaquete) { setOpen(false); onAbrirPaquete(n.cliente_id, n.paquete_id) }
  }

  const conteo = data?.no_leidas ?? 0
  return (
    <div style={{ position: 'relative' }} ref={contenedor}>
      <button className="btn btn-ghost-dark btn-sm" style={{ position: 'relative' }} onClick={alAbrir} title="Notificaciones" aria-label="Notificaciones">
        🔔
        {conteo > 0 && <span style={{ position: 'absolute', top: -2, right: -2, background: 'var(--inn-orange)', color: 'white', borderRadius: 999,
          fontSize: 10, fontWeight: 700, minWidth: 16, height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 3px' }}>{conteo}</span>}
      </button>

      {open && (
        <div className="card" style={{ position: 'absolute', top: 34, left: 0, width: 340, maxHeight: 440, overflowY: 'auto', zIndex: 50, padding: 10, color: 'var(--ink-900)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>Notificaciones</strong>
            {conteo > 0 && <button className="btn btn-ghost btn-sm" onClick={async () => { await api.post('/notificaciones/leer-todas'); cargar() }}>Marcar leídas</button>}
          </div>
          {!data?.items.length && <p className="muted" style={{ fontSize: 13, margin: 0 }}>Sin notificaciones.</p>}
          {data?.items.map((n) => (
            <div key={n.id} style={{ padding: '8px 10px', borderRadius: 8, fontSize: 13, marginBottom: 4, cursor: 'pointer',
              background: n.leida ? 'transparent' : 'var(--inn-purple-50)', border: '1px solid transparent' }}
              onClick={() => leer(n)}>
              <div>{n.mensaje}</div>
              <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{fechaHora(n.creado_en)}</div>
              {!esCm && n.tipo === 'prorroga_vencida' && n.paquete_id && (
                <div style={{ marginTop: 6 }} onClick={(e) => e.stopPropagation()}>
                  <button className="btn btn-primary btn-sm" onClick={() => verMensaje(n.paquete_id!)}>Mensaje para el cliente</button>
                </div>)}
            </div>
          ))}
        </div>
      )}

      {recordatorio && <RecordatorioModal r={recordatorio} onClose={() => setRecordatorio(null)} />}
    </div>
  )
}

export function RecordatorioModal({ r, onClose, onEnviado }: { r: Recordatorio; onClose: () => void; onEnviado?: () => void }) {
  const [enviado, setEnviado] = useState(!!r.enviado_en)
  async function marcar() { await api.post(`/recordatorios/${r.id}/marcar-enviado`); setEnviado(true); onEnviado?.() }
  return (
    <Modal title="Recordatorio para el cliente" onClose={onClose}>
      <p className="muted" style={{ marginTop: 0 }}>Mensaje ya redactado. Ábrelo en WhatsApp o cópialo y, al enviarlo, márcalo como enviado: <strong>un mensaje enviado no se puede volver a enviar</strong>.</p>
      <textarea readOnly rows={6} value={r.texto} />
      {!r.wa_url && <div className="callout callout-warn">El cliente no tiene un teléfono válido guardado: puedes copiar el texto, pero no abrir WhatsApp.</div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        {r.wa_url && !enviado && <a className="btn btn-primary" href={r.wa_url} target="_blank" rel="noreferrer">Abrir en WhatsApp</a>}
        {!enviado && <BotonCopiar texto={r.texto} />}
        <button className="btn btn-secondary right" disabled={enviado} onClick={marcar}>{enviado ? '✓ Ya se envió (no se puede reenviar)' : 'Marcar como enviado'}</button>
      </div>
    </Modal>
  )
}

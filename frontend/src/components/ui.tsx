import { useEffect, useState, type ReactNode } from 'react'
import type { Semaforo as SemaforoT } from '../api/types'
import { SEMAFORO_LABEL } from '../util'

export function Modal({ title, onClose, children, width }: { title: string; onClose?: () => void; children: ReactNode; width?: number }) {

  return (
    <div className="modal-backdrop">
      <div className="modal" style={width ? { maxWidth: width } : undefined} role="dialog" aria-modal="true" aria-label={title}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
          {onClose && <button className="btn btn-ghost btn-sm right" onClick={onClose} aria-label="Cerrar">✕</button>}
        </div>
        {children}
      </div>
    </div>
  )
}

export function Semaforo({ valor, conTexto }: { valor: SemaforoT | null; conTexto?: boolean }) {
  if (!valor) return null
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }} title={SEMAFORO_LABEL[valor]}>
      <span className={`semaforo-dot sem-${valor}`} />
      {conTexto && <span style={{ fontSize: 13 }}>{SEMAFORO_LABEL[valor]}</span>}
    </span>
  )
}

export function Progreso({ pct }: { pct: number }) {
  return <div className="progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${Math.min(100, pct)}%` }} /></div>
}

export function CampoPassword({ value, onChange, placeholder, autoFocus, disabled, id, autoComplete = 'new-password' }: {
  value: string; onChange: (v: string) => void; placeholder?: string; autoFocus?: boolean; disabled?: boolean; id?: string; autoComplete?: string
}) {
  const [ver, setVer] = useState(false)
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <input id={id} type={ver ? 'text' : 'password'} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        autoFocus={autoFocus} disabled={disabled} autoComplete={autoComplete} spellCheck={false} />
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setVer((v) => !v)} disabled={disabled}
        aria-label={ver ? 'Ocultar contraseña' : 'Ver contraseña'} style={{ whiteSpace: 'nowrap' }}>{ver ? 'Ocultar' : 'Ver'}</button>
    </div>
  )
}

export function sugerirPassword(): string {
  const set = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_!'
  const bytes = crypto.getRandomValues(new Uint32Array(14))
  return Array.from(bytes, (b) => set[b % set.length]).join('')
}

export const passwordValida = (v: string) => v.length >= 8 && v.length <= 72 && v === v.trim()

export function Spinner() {
  return <span className="spinner" style={{ borderTopColor: 'var(--inn-purple-600)', borderColor: 'var(--inn-purple-100)', display: 'inline-block' }} />
}

export function Cargando() {
  return <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>
}

export function ErrorTexto({ texto }: { texto: string | null }) {
  return texto ? <p className="error-text">{texto}</p> : null
}

export function useToast(): [ReactNode, (t: string) => void] {
  const [texto, setTexto] = useState<string | null>(null)
  useEffect(() => {
    if (!texto) return
    const t = setTimeout(() => setTexto(null), 3500)
    return () => clearTimeout(t)
  }, [texto])
  return [texto ? <div className="toast" role="status">{texto}</div> : null, setTexto]
}

export async function copiar(texto: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(texto); return true } catch {
    const ta = document.createElement('textarea')
    ta.value = texto; document.body.appendChild(ta); ta.select()
    const ok = document.execCommand('copy'); ta.remove(); return ok
  }
}

export function BotonCopiar({ texto, etiqueta = 'Copiar' }: { texto: string; etiqueta?: string }) {
  const [ok, setOk] = useState(false)
  return <button className="btn btn-secondary btn-sm" onClick={async () => { setOk(await copiar(texto)); setTimeout(() => setOk(false), 1800) }}>{ok ? '✓ Copiado' : etiqueta}</button>
}

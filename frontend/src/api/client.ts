export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? (body as { detail: unknown }).detail
      : body
    super(typeof detail === 'string' ? detail
      : typeof detail === 'object' && detail !== null && 'mensaje' in detail ? String((detail as { mensaje: unknown }).mensaje)
      : Array.isArray(detail) ? 'Revisa los datos capturados' : 'Error de la API')
    this.status = status
    this.body = body
  }

  get code(): string | undefined {
    const d = (this.body as { detail?: { code?: string } } | undefined)?.detail
    return typeof d === 'object' && d !== null ? d.code : undefined
  }
}

let token: string | null = sessionStorage.getItem('token')

export function setToken(t: string | null) {
  token = t
  if (t) sessionStorage.setItem('token', t)
  else sessionStorage.removeItem('token')
}

export function getToken() {
  return token
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (res.status === 204) return undefined as T

  const text = await res.text()
  const data = text ? JSON.parse(text) : undefined

  if (!res.ok) {
    throw new ApiError(res.status, data)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  del: <T>(path: string, body?: unknown) => request<T>('DELETE', path, body ?? {}),
}

export async function downloadFile(path: string, fallbackFilename: string): Promise<void> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`/api${path}`, { headers })
  if (!res.ok) {
    let body: unknown
    try { body = await res.json() } catch { body = undefined }
    throw new ApiError(res.status, body)
  }

  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const filename = match?.[1] ?? fallbackFilename

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

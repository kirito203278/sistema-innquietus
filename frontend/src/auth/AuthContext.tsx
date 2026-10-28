import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from '../api/client'
import type { LoginResponse, Usuario } from '../api/types'

interface AuthContextValue {
  user: Usuario | null
  loading: boolean
  login: (username: string, password: string) => Promise<Usuario>
  logout: () => void

  puedeEscribir: boolean
  esCm: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!getToken()) { setLoading(false); return }
    api.get<Usuario>('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const resp = await api.post<LoginResponse>('/auth/login', { username, password })
    setToken(resp.access_token)
    setUser(resp.usuario)
    return resp.usuario
  }, [])

  const logout = useCallback(() => { setToken(null); setUser(null) }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, puedeEscribir: !!user && !(user.rol === 'admin' && user.solo_lectura), esCm: user?.rol === 'cm' }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider')
  return ctx
}

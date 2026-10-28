import { useAuth } from './auth/AuthContext'
import { Cargando } from './components/ui'
import LoginPage from './pages/LoginPage'
import CmPanel from './pages/cm/CmPanel'
import AdminPanel from './pages/admin/AdminPanel'

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Cargando /></div>
  if (!user) return <LoginPage />
  return user.rol === 'cm' ? <CmPanel /> : <AdminPanel />
}

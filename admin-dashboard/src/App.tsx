import { useState, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { Shield, Users, Server, Power, ScrollText, DollarSign, Database, Settings, LogOut, TrendingUp } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 
    (window.location.hostname.includes('railway.app') ? 'https://web-production-d57ac.up.railway.app' : 'http://localhost:8000')

// ─── Sidebar ───
function AdminSidebar({ active, onChange }: { active: string; onChange: (p: string) => void }) {
  const { logout } = useAuth()
  const items = [
    { id: 'overview', icon: Shield, label: 'Overview' },
    { id: 'users', icon: Users, label: 'Users' },
    { id: 'system', icon: Server, label: 'System' },
    { id: 'bot', icon: Power, label: 'Bot Control' },
    { id: 'logs', icon: ScrollText, label: 'Logs' },
    { id: 'revenue', icon: DollarSign, label: 'Revenue' },
    { id: 'database', icon: Database, label: 'Database' },
    { id: 'settings', icon: Settings, label: 'Settings' },
  ]

  return (
    <div style={{
      position: 'fixed', left: 0, top: 0, height: '100vh', width: '220px',
      background: 'linear-gradient(180deg, #0A0E1A 0%, #111827 100%)',
      borderRight: '1px solid rgba(251,191,36,0.1)',
      display: 'flex', flexDirection: 'column', padding: '20px 12px', zIndex: 50,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '0 8px', marginBottom: '32px' }}>
        <div style={{
          width: '40px', height: '40px', borderRadius: '12px',
          background: 'linear-gradient(135deg, #FBBF24, #F59E0B)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 0 20px rgba(251,191,36,0.3)'
        }}>
          <Shield size={20} color="#000" />
        </div>
        <div>
          <div style={{ color: '#FBBF24', fontSize: '15px', fontWeight: 700 }}>ADMIN</div>
          <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>Ethbot Control</div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px', flex: 1 }}>
        {items.map(item => {
          const Icon = item.icon
          const isActive = active === item.id
          return (
            <button key={item.id} onClick={() => onChange(item.id)} style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              padding: '10px 12px', borderRadius: '10px', border: 'none', width: '100%',
              background: isActive ? 'rgba(251,191,36,0.12)' : 'transparent',
              color: isActive ? '#FBBF24' : 'rgba(255,255,255,0.5)',
              fontSize: '13px', fontWeight: isActive ? 600 : 500,
              cursor: 'pointer', transition: 'all 0.15s', textAlign: 'left',
              borderLeft: isActive ? '3px solid #FBBF24' : '3px solid transparent'
            }}>
              <Icon size={18} />
              {item.label}
            </button>
          )
        })}
      </nav>

      {/* Logout */}
      <button onClick={logout} style={{
        display: 'flex', alignItems: 'center', gap: '10px',
        padding: '10px 12px', borderRadius: '10px', border: 'none', width: '100%',
        background: 'rgba(239,68,68,0.1)', color: '#F87171',
        fontSize: '13px', fontWeight: 500, cursor: 'pointer', marginTop: '8px'
      }}>
        <LogOut size={18} /> Sign Out
      </button>
    </div>
  )
}

// ─── Login Gate ───
function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await login(email, password)
    } catch {
      setError('Invalid credentials')
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#0A0E1A' }}>
      <form onSubmit={handleLogin} style={{
        background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(251,191,36,0.2)',
        borderRadius: '16px', padding: '40px', width: '360px'
      }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <Shield size={40} color="#FBBF24" />
          <h2 style={{ color: 'white', marginTop: '12px' }}>Admin Access</h2>
        </div>
        {error && <div style={{ color: '#F87171', fontSize: '13px', marginBottom: '12px', textAlign: 'center' }}>{error}</div>}
        <input type="text" placeholder="Username" value={email} onChange={e => setEmail(e.target.value)}
          style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.05)', color: 'white', fontSize: '14px', marginBottom: '12px', outline: 'none' }} />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)}
          style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.05)', color: 'white', fontSize: '14px', marginBottom: '16px', outline: 'none' }} />
        <button type="submit" style={{
          width: '100%', padding: '12px', borderRadius: '8px', border: 'none',
          background: 'linear-gradient(135deg, #FBBF24, #F59E0B)', color: '#000',
          fontSize: '14px', fontWeight: 700, cursor: 'pointer'
        }}>Access Admin Panel</button>
      </form>
    </div>
  )
}

// ─── Admin Content ───
function AdminContent() {
  const { user, token } = useAuth()
  const [activePage, setActivePage] = useState('overview')
  const [stats, setStats] = useState<any>(null)
  const [systemHealth, setSystemHealth] = useState<any>(null)

  const isAdmin = user?.role === 'admin'
  const headers: any = token ? { Authorization: `Bearer ${token}` } : {}

  useEffect(() => {
    if (!token) return
    const load = async () => {
      try {
        const [s, h] = await Promise.all([
          fetch(`${API_URL}/api/admin/stats`, { headers }).then(r => r.json()).catch(() => null),
          fetch(`${API_URL}/api/health`, { headers }).then(r => r.json()).catch(() => null),
        ])
        setStats(s)
        setSystemHealth(h)
      } catch {}
    }
    load()
    const i = setInterval(load, 30000)
    return () => clearInterval(i)
  }, [token])

  if (!isAdmin) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#0A0E1A' }}>
        <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
          <Shield size={48} color="#F87171" />
          <h2 style={{ color: '#F87171', marginTop: '16px' }}>Access Denied</h2>
          <p style={{ marginTop: '8px' }}>Admin role required</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0A0E1A' }}>
      <AdminSidebar active={activePage} onChange={setActivePage} />
      <main style={{ marginLeft: '220px', flex: 1, padding: '24px', maxWidth: '1200px' }}>
        {/* Page Header */}
        <div style={{ marginBottom: '24px' }}>
          <h1 style={{ color: 'white', fontSize: '24px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            🛡️ {activePage.charAt(0).toUpperCase() + activePage.slice(1)}
          </h1>
          <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
            <span style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(74,222,128,0.15)', color: '#4ADE80', fontSize: '11px', fontWeight: 600 }}>
              ● SYSTEM ONLINE
            </span>
            <span style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(251,191,36,0.15)', color: '#FBBF24', fontSize: '11px', fontWeight: 600 }}>
              ADMIN: {user?.username}
            </span>
          </div>
        </div>

        {/* Overview */}
        {activePage === 'overview' && (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
              {[
                { label: 'Total Users', value: stats?.total_users || 0, color: '#06B6D4', icon: '👥' },
                { label: 'Active Today', value: stats?.active_today || 0, color: '#22C55E', icon: '🟢' },
                { label: 'Revenue', value: `$${stats?.revenue || 0}`, color: '#FBBF24', icon: '💰' },
                { label: 'Bot Status', value: systemHealth?.status === 'healthy' ? 'Healthy' : 'Error', color: systemHealth?.status === 'healthy' ? '#4ADE80' : '#F87171', icon: '🤖' },
              ].map((card, i) => (
                <div key={i} style={{
                  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '14px', padding: '20px'
                }}>
                  <div style={{ fontSize: '24px', marginBottom: '8px' }}>{card.icon}</div>
                  <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase' }}>{card.label}</div>
                  <div style={{ color: card.color, fontSize: '28px', fontWeight: 700, marginTop: '4px' }}>{card.value}</div>
                </div>
              ))}
            </div>

            {/* Quick Actions */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '14px', padding: '20px' }}>
              <h3 style={{ color: 'white', fontSize: '15px', fontWeight: 600, marginBottom: '16px' }}>Quick Actions</h3>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                {['View Users', 'System Health', 'Bot Control', 'View Logs', 'Database'].map((action, i) => (
                  <button key={i} onClick={() => setActivePage(['users', 'system', 'bot', 'logs', 'database'][i])}
                    style={{
                      padding: '10px 20px', borderRadius: '10px', border: '1px solid rgba(251,191,36,0.2)',
                      background: 'rgba(251,191,36,0.08)', color: '#FBBF24',
                      fontSize: '13px', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s'
                    }}>{action}</button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Users */}
        {activePage === 'users' && <AdminSection title="User Management" endpoint="/api/admin/users" headers={headers} />}
        {activePage === 'system' && <AdminSection title="System Health" endpoint="/api/admin/system" headers={headers} />}
        {activePage === 'bot' && <AdminSection title="Bot Control" endpoint="/api/status" headers={headers} />}
        {activePage === 'logs' && <AdminSection title="System Logs" endpoint="/api/admin/logs" headers={headers} />}
        {activePage === 'revenue' && <AdminSection title="Revenue" endpoint="/api/admin/stats" headers={headers} />}
        {activePage === 'database' && <AdminSection title="Database" endpoint="/api/admin/database" headers={headers} />}
        {activePage === 'settings' && <AdminSection title="Settings" endpoint="/api/settings" headers={headers} />}
      </main>
    </div>
  )
}

// ─── Generic Admin Section ───
function AdminSection({ title, endpoint, headers }: { title: string; endpoint: string; headers: any }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`${API_URL}${endpoint}`, { headers })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [endpoint])

  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '14px', padding: '24px' }}>
      <h2 style={{ color: 'white', fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>{title}</h2>
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
          <div style={{ width: '32px', height: '32px', border: '3px solid rgba(251,191,36,0.2)', borderTopColor: '#FBBF24', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : (
        <pre style={{
          background: 'rgba(0,0,0,0.3)', borderRadius: '10px', padding: '16px',
          color: 'rgba(255,255,255,0.7)', fontSize: '12px', overflow: 'auto',
          maxHeight: '600px', lineHeight: 1.6
        }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ─── App ───
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </BrowserRouter>
  )
}

function AppInner() {
  const { token } = useAuth()
  if (!token) return <LoginPage />
  return <AdminContent />
}

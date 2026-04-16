import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { Crosshair, Brain, Cpu, Activity, LogOut, BarChart3, RefreshCw } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 
    (window.location.hostname.includes('railway.app') ? 'https://web-production-d57ac.up.railway.app' : 'http://localhost:8000')

// ─── Terminal Sidebar ───
function MonitorSidebar({ active, onChange }: { active: string; onChange: (p: string) => void }) {
  const { logout } = useAuth()
  const items = [
    { id: 'edge', icon: Crosshair, label: 'Edge Monitor' },
    { id: 'learning', icon: Brain, label: 'Learning' },
    { id: 'ml', icon: Cpu, label: 'ML Models' },
    { id: 'live', icon: Activity, label: 'Live Feed' },
  ]

  return (
    <div style={{
      position: 'fixed', left: 0, top: 0, height: '100vh', width: '200px',
      background: '#020617', borderRight: '1px solid rgba(34,197,94,0.15)',
      display: 'flex', flexDirection: 'column', padding: '16px 10px', zIndex: 50,
    }}>
      {/* Header */}
      <div style={{ padding: '4px 8px', marginBottom: '24px' }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', color: '#22C55E', fontSize: '14px', fontWeight: 700 }}>
          ETHBOT<span style={{ color: 'rgba(255,255,255,0.3)' }}>::</span>MONITOR
        </div>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.3)', fontSize: '10px', marginTop: '2px' }}>
          v2.0 ● edge-first
        </div>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '2px', flex: 1 }}>
        {items.map(item => {
          const Icon = item.icon
          const isActive = active === item.id
          return (
            <button key={item.id} onClick={() => onChange(item.id)} style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '10px 10px', borderRadius: '6px', border: 'none', width: '100%',
              background: isActive ? 'rgba(34,197,94,0.1)' : 'transparent',
              color: isActive ? '#22C55E' : 'rgba(255,255,255,0.4)',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', fontWeight: isActive ? 600 : 400,
              cursor: 'pointer', transition: 'all 0.15s', textAlign: 'left',
            }}>
              <span style={{ color: isActive ? '#22C55E' : 'rgba(255,255,255,0.2)', fontSize: '10px' }}>{'>'}</span>
              <Icon size={15} />
              {item.label}
            </button>
          )
        })}
      </nav>

      <button onClick={logout} style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '8px 10px', borderRadius: '6px', border: '1px solid rgba(239,68,68,0.2)',
        background: 'transparent', color: '#F87171',
        fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', cursor: 'pointer',
      }}>
        <LogOut size={14} /> exit
      </button>
    </div>
  )
}

// ─── Login ───
function LoginPage() {
  const { login } = useAuth()
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [err, setErr] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    try { await login(user, pass) } catch { setErr('AUTH_FAIL') }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#020617' }}>
      <form onSubmit={handleLogin} style={{
        background: 'rgba(34,197,94,0.03)', border: '1px solid rgba(34,197,94,0.15)',
        borderRadius: '8px', padding: '32px', width: '340px', fontFamily: 'JetBrains Mono, monospace'
      }}>
        <div style={{ color: '#22C55E', fontSize: '13px', marginBottom: '20px' }}>
          <span style={{ opacity: 0.5 }}>$</span> ethbot-monitor --login
        </div>
        {err && <div style={{ color: '#F87171', fontSize: '11px', marginBottom: '8px' }}>[ERROR] {err}</div>}
        <input placeholder="username" value={user} onChange={e => setUser(e.target.value)}
          style={{ width: '100%', padding: '10px', borderRadius: '4px', border: '1px solid rgba(34,197,94,0.2)', background: '#0A0E1A', color: '#22C55E', fontSize: '13px', marginBottom: '8px', outline: 'none', fontFamily: 'inherit' }} />
        <input type="password" placeholder="password" value={pass} onChange={e => setPass(e.target.value)}
          style={{ width: '100%', padding: '10px', borderRadius: '4px', border: '1px solid rgba(34,197,94,0.2)', background: '#0A0E1A', color: '#22C55E', fontSize: '13px', marginBottom: '16px', outline: 'none', fontFamily: 'inherit' }} />
        <button type="submit" style={{
          width: '100%', padding: '10px', borderRadius: '4px', border: '1px solid #22C55E',
          background: 'rgba(34,197,94,0.15)', color: '#22C55E',
          fontSize: '13px', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit'
        }}>AUTHENTICATE</button>
      </form>
    </div>
  )
}

// ─── Edge Monitor Panel ───
function EdgePanel({ headers }: { headers: any }) {
  const [report, setReport] = useState<any>(null)
  const [collector, setCollector] = useState<any>(null)
  const [signals, setSignals] = useState<any>(null)
  const [marketData, setMarketData] = useState<any[]>([])

  const load = useCallback(async () => {
    const [r, c, s, m] = await Promise.all([
      fetch(`${API_URL}/api/v2/edge-report`, { headers }).then(r => r.json()).catch(() => null),
      fetch(`${API_URL}/api/v2/collector-status`, { headers }).then(r => r.json()).catch(() => null),
      fetch(`${API_URL}/api/v2/signal-status`, { headers }).then(r => r.json()).catch(() => null),
      fetch(`${API_URL}/api/v2/market-data?limit=20`, { headers }).then(r => r.json()).catch(() => ({ data: [] })),
    ])
    setReport(r); setCollector(c); setSignals(s); setMarketData(m?.data || [])
  }, [])

  useEffect(() => { load(); const i = setInterval(load, 10000); return () => clearInterval(i) }, [load])

  const statusColor: Record<string, string> = { COLLECTING: '#3B82F6', VALIDATED: '#22C55E', NO_EDGE: '#EF4444', WEAK: '#FBBF24' }
  const sc = statusColor[report?.status] || '#3B82F6'

  return (
    <div>
      {/* Status */}
      <div style={{ background: `${sc}10`, border: `1px solid ${sc}30`, borderRadius: '8px', padding: '16px 20px', marginBottom: '20px' }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', color: sc, fontSize: '16px', fontWeight: 700 }}>
          [{report?.status || 'INIT'}] {report?.message || 'Loading...'}
        </div>
      </div>

      {/* Metrics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '10px', marginBottom: '20px' }}>
        {[
          { l: 'PREDICTIONS', v: `${report?.evaluated || 0}/${report?.target || 200}`, c: '#06B6D4' },
          { l: 'WIN RATE', v: `${(report?.win_rate || 0).toFixed(1)}%`, c: (report?.win_rate || 0) >= 55 ? '#22C55E' : '#FBBF24' },
          { l: 'PROFIT FACTOR', v: (report?.profit_factor || 0).toFixed(2), c: (report?.profit_factor || 0) >= 1.3 ? '#22C55E' : '#FBBF24' },
          { l: 'EXPECTANCY', v: `${(report?.expectancy_pct || 0).toFixed(4)}%`, c: (report?.expectancy_pct || 0) > 0 ? '#22C55E' : '#F87171' },
          { l: 'TICKS', v: collector?.ticks_collected || 0, c: '#06B6D4' },
          { l: 'FUTURES', v: collector?.has_futures_api ? 'ONLINE' : 'N/A', c: collector?.has_futures_api ? '#22C55E' : '#F87171' },
        ].map((m, i) => (
          <div key={i} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '6px', padding: '12px' }}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.4)', fontSize: '9px', fontWeight: 600 }}>{m.l}</div>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', color: m.c, fontSize: '18px', fontWeight: 700, marginTop: '4px' }}>{m.v}</div>
          </div>
        ))}
      </div>

      {/* Signals + Breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* Active Signals */}
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '16px' }}>
          <h3 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#22C55E', fontSize: '12px', marginBottom: '12px' }}>ACTIVE_SIGNALS</h3>
          {(!signals?.last_signals || signals.last_signals.length === 0) ? (
            <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.2)', fontSize: '11px' }}>
              waiting for market conditions...
            </div>
          ) : signals.last_signals.map((s: any, i: number) => (
            <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', color: s.direction === 'LONG' ? '#22C55E' : '#F87171', fontSize: '11px', fontWeight: 700, width: '45px' }}>{s.direction}</span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.5)', fontSize: '10px', flex: 1 }}>{s.name}</span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.4)', fontSize: '10px' }}>{(s.confidence * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>

        {/* Edge Breakdown */}
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '16px' }}>
          <h3 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#06B6D4', fontSize: '12px', marginBottom: '12px' }}>EDGE_BREAKDOWN</h3>
          {report?.signal_breakdown ? Object.entries(report.signal_breakdown).map(([name, data]: [string, any]) => (
            <div key={name} style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.6)', fontSize: '11px' }}>{name}</span>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: data.total_pnl_pct > 0 ? '#22C55E' : '#F87171', fontSize: '11px' }}>
                  {data.total_pnl_pct > 0 ? '+' : ''}{data.total_pnl_pct.toFixed(3)}%
                </span>
              </div>
              <div style={{ display: 'flex', gap: '12px', marginTop: '2px' }}>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.3)', fontSize: '9px' }}>WR: {data.win_rate}%</span>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.3)', fontSize: '9px' }}>N: {data.predictions}</span>
              </div>
            </div>
          )) : <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.2)', fontSize: '11px' }}>no data yet</div>}
        </div>
      </div>

      {/* Market Data Feed */}
      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '16px', marginTop: '16px' }}>
        <h3 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#06B6D4', fontSize: '12px', marginBottom: '8px' }}>MARKET_DATA_FEED</h3>
        <div style={{ maxHeight: '200px', overflow: 'auto' }}>
          {marketData.slice(0, 10).map((d, i) => (
            <div key={i} style={{ display: 'flex', gap: '12px', padding: '3px 0', fontFamily: 'JetBrains Mono, monospace', fontSize: '10px', color: 'rgba(255,255,255,0.4)' }}>
              <span style={{ color: 'rgba(255,255,255,0.2)', width: '70px' }}>{d.timestamp?.slice(11, 19)}</span>
              <span style={{ color: '#06B6D4', width: '80px' }}>${d.price?.toFixed(2)}</span>
              <span style={{ width: '80px' }}>FR:{d.funding_rate !== null ? (d.funding_rate * 100).toFixed(4) + '%' : 'N/A'}</span>
              <span style={{ width: '60px' }}>VS:{d.volume_spike_ratio?.toFixed(1)}x</span>
              <span>VWAP:{d.vwap_deviation_pct?.toFixed(3)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Learning Panel ───
function LearningPanel({ headers }: { headers: any }) {
  const [stats, setStats] = useState<any>(null)
  const [strategies, setStrategies] = useState<any[]>([])

  useEffect(() => {
    const load = async () => {
      const [s, t] = await Promise.all([
        fetch(`${API_URL}/api/learning/stats`, { headers }).then(r => r.json()).catch(() => null),
        fetch(`${API_URL}/api/learning/top-strategies`, { headers }).then(r => r.json()).catch(() => []),
      ])
      setStats(s)
      setStrategies(Array.isArray(t) ? t : t?.strategies || [])
    }
    load()
    const i = setInterval(load, 30000)
    return () => clearInterval(i)
  }, [])

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '20px' }}>
        {[
          { l: 'TOTAL TESTED', v: stats?.total_tested || 0 },
          { l: 'BEST SCORE', v: (stats?.best_score || 0).toFixed(1) },
          { l: 'THIS HOUR', v: stats?.tested_this_hour || 0 },
          { l: 'APPLIED', v: stats?.total_applied || 0 },
        ].map((m, i) => (
          <div key={i} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '6px', padding: '12px' }}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.4)', fontSize: '9px' }}>{m.l}</div>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', color: '#06B6D4', fontSize: '20px', fontWeight: 700, marginTop: '4px' }}>{m.v}</div>
          </div>
        ))}
      </div>

      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '16px' }}>
        <h3 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#22C55E', fontSize: '12px', marginBottom: '12px' }}>TOP_STRATEGIES</h3>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '10px', color: 'rgba(255,255,255,0.3)', display: 'grid', gridTemplateColumns: '40px 80px 60px 70px 70px 1fr', gap: '4px', marginBottom: '8px' }}>
          <span>#</span><span>SCORE</span><span>WR</span><span>ROI</span><span>PF</span><span>TRADES</span>
        </div>
        {strategies.slice(0, 15).map((s: any, i: number) => (
          <div key={i} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', display: 'grid', gridTemplateColumns: '40px 80px 60px 70px 70px 1fr', gap: '4px', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
            <span style={{ color: 'rgba(255,255,255,0.3)' }}>{i + 1}</span>
            <span style={{ color: '#FBBF24', fontWeight: 600 }}>{(s.score || 0).toFixed(1)}</span>
            <span style={{ color: (s.metrics?.win_rate || 0) >= 60 ? '#22C55E' : 'rgba(255,255,255,0.5)' }}>{(s.metrics?.win_rate || 0).toFixed(0)}%</span>
            <span style={{ color: (s.metrics?.roi || 0) > 0 ? '#22C55E' : '#F87171' }}>{(s.metrics?.roi || 0).toFixed(1)}%</span>
            <span style={{ color: 'rgba(255,255,255,0.5)' }}>{(s.metrics?.profit_factor || 0).toFixed(2)}</span>
            <span style={{ color: 'rgba(255,255,255,0.3)' }}>{s.metrics?.total_trades || 0}</span>
          </div>
        ))}
        {strategies.length === 0 && <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.2)', fontSize: '11px' }}>loading strategies...</div>}
      </div>
    </div>
  )
}

// ─── ML Panel ───
function MLPanel({ headers }: { headers: any }) {
  const [risk, setRisk] = useState<any>(null)

  useEffect(() => {
    fetch(`${API_URL}/api/v2/collector-status`, { headers }).then(r => r.json()).then(setRisk).catch(() => {})
  }, [])

  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '20px' }}>
      <h3 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#06B6D4', fontSize: '12px', marginBottom: '16px' }}>SYSTEM_STATUS</h3>
      <pre style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.6)', fontSize: '11px', lineHeight: 1.8 }}>
{`collector.running     = ${risk?.running ?? '?'}
collector.ticks       = ${risk?.ticks_collected ?? '?'}
collector.errors      = ${risk?.errors ?? '?'}
collector.futures_api = ${risk?.has_futures_api ?? '?'}
collector.hours       = ${risk?.hours_of_data?.toFixed(1) ?? '?'}

v2.mode               = OBSERVE_ONLY
v2.trading_enabled     = false
v2.capital_rollout     = 10%
v2.required_preds      = 200`}
      </pre>
    </div>
  )
}

// ─── Live Feed ───
function LiveFeedPanel({ headers }: { headers: any }) {
  const [data, setData] = useState<any[]>([])

  useEffect(() => {
    const load = () => fetch(`${API_URL}/api/v2/market-data?limit=50`, { headers }).then(r => r.json()).then(d => setData(d?.data || [])).catch(() => {})
    load()
    const i = setInterval(load, 5000)
    return () => clearInterval(i)
  }, [])

  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h3 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#22C55E', fontSize: '12px' }}>LIVE_MARKET_FEED</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#22C55E', animation: 'pulse 1.5s infinite' }} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>5s refresh</span>
        </div>
      </div>
      <div style={{ maxHeight: '70vh', overflow: 'auto' }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '9px', color: 'rgba(255,255,255,0.25)', display: 'grid', gridTemplateColumns: '75px 85px 80px 60px 65px 55px 50px', gap: '4px', marginBottom: '4px', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <span>TIME</span><span>PRICE</span><span>FUNDING</span><span>VOL_SP</span><span>VWAP_D</span><span>RSI</span><span>BB</span>
        </div>
        {data.map((d, i) => (
          <div key={i} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '10px', display: 'grid', gridTemplateColumns: '75px 85px 80px 60px 65px 55px 50px', gap: '4px', padding: '3px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
            <span style={{ color: 'rgba(255,255,255,0.2)' }}>{d.timestamp?.slice(11, 19)}</span>
            <span style={{ color: '#06B6D4' }}>${d.price?.toFixed(2)}</span>
            <span style={{ color: d.funding_rate && d.funding_rate > 0.0005 ? '#F87171' : d.funding_rate && d.funding_rate < -0.0001 ? '#22C55E' : 'rgba(255,255,255,0.4)' }}>
              {d.funding_rate !== null ? (d.funding_rate * 100).toFixed(4) + '%' : '---'}
            </span>
            <span style={{ color: d.volume_spike_ratio && d.volume_spike_ratio > 2.5 ? '#FBBF24' : 'rgba(255,255,255,0.3)' }}>{d.volume_spike_ratio?.toFixed(1)}x</span>
            <span style={{ color: Math.abs(d.vwap_deviation_pct || 0) > 0.5 ? '#FBBF24' : 'rgba(255,255,255,0.3)' }}>{d.vwap_deviation_pct?.toFixed(3)}%</span>
            <span style={{ color: (d.rsi_1m || 50) < 30 ? '#22C55E' : (d.rsi_1m || 50) > 70 ? '#F87171' : 'rgba(255,255,255,0.3)' }}>{d.rsi_1m?.toFixed(0)}</span>
            <span style={{ color: 'rgba(255,255,255,0.3)' }}>{d.bb_position?.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main ───
function MonitorContent() {
  const { token } = useAuth()
  const [page, setPage] = useState('edge')
  const headers: any = token ? { Authorization: `Bearer ${token}` } : {}

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#020617' }}>
      <MonitorSidebar active={page} onChange={setPage} />
      <main style={{ marginLeft: '200px', flex: 1, padding: '20px', maxWidth: '1300px' }}>
        <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1 style={{ fontFamily: 'JetBrains Mono, monospace', color: '#22C55E', fontSize: '16px', fontWeight: 700 }}>
            <span style={{ color: 'rgba(255,255,255,0.3)' }}>~/</span>{page}
          </h1>
          <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.2)', fontSize: '10px' }}>
            {new Date().toISOString().slice(0, 19)}Z
          </div>
        </div>

        {page === 'edge' && <EdgePanel headers={headers} />}
        {page === 'learning' && <LearningPanel headers={headers} />}
        {page === 'ml' && <MLPanel headers={headers} />}
        {page === 'live' && <LiveFeedPanel headers={headers} />}
      </main>
    </div>
  )
}

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
  return <MonitorContent />
}

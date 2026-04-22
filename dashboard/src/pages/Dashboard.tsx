import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import type { BotStatus } from '../App'
import StrategyPanel from '../components/StrategyPanel'

const API_URL = import.meta.env.VITE_API_URL || ''

interface Trade {
  timestamp: string
  action: string
  pair?: string
  qty: number
  price: number
  pnl: number
}

interface SwarmAgent {
  name: string
  weight: number
  accuracy: number
  total_votes: number
  correct_votes: number
}

interface OpenPosition {
  pair: string
  daily_pnl: number
  balance: number
  win_streak: number
  loss_streak: number
}

interface DashboardProps {
  status: BotStatus | null
}

export default function Dashboard(_props: DashboardProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [chartDays, setChartDays] = useState(7)
  const [pnlHistory, setPnlHistory] = useState<any[]>([])
  const [swarm, setSwarm] = useState<{ agents: SwarmAgent[], consensus_threshold: number } | null>(null)
  const [brain, setBrain] = useState<any>(null)
  const [shield, setShield] = useState<any>(null)
  const [localStatus, setLocalStatus] = useState<any>(null)

  const status = localStatus

  useEffect(() => {
    fetchTrades()
    fetchPnlHistory()
    fetchIntelligence()
    fetchStatus()
    const intv = setInterval(() => {
      fetchIntelligence()
      fetchStatus()
      fetchTrades()
    }, 10000)
    return () => clearInterval(intv)
  }, [chartDays])

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/status`)
      if (res.ok) setLocalStatus(await res.json())
    } catch { /* ignore */ }
  }

  const fetchTrades = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/trades?limit=20`)
      if (res.ok) setTrades(await res.json())
    } catch { /* API may not be running */ }
  }

  const fetchPnlHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/pnl-history?days=${chartDays}`)
      if (res.ok) setPnlHistory(await res.json())
    } catch { /* API may not be running */ }
  }

  const fetchIntelligence = async () => {
    try {
      const [sw, br, sh] = await Promise.all([
        fetch(`${API_URL}/api/v3/swarm`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${API_URL}/api/v3/brain`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${API_URL}/api/v3/shield`).then(r => r.ok ? r.json() : null).catch(() => null),
      ])
      if (sw) setSwarm(sw)
      if (br) setBrain(br)
      if (sh) setShield(sh)
    } catch { /* Intelligence not available */ }
  }

  const dailyPnl = status?.daily_pnl || 0
  const totalPnl = status?.total_pnl || 0
  const winRate = status?.win_rate || 0
  const totalTrades = status?.total_trades || 0
  const todayTrades = status?.today_trades || 0
  const equity = status?.paper_balance || 100000
  const startingBalance = status?.starting_balance || 100000
  const isRunning = status?.is_running ?? false
  const regime = status?.regime || 'unknown'
  const activePairs = status?.active_pairs || 1
  const openPositions: OpenPosition[] = status?.open_positions || []
  const pairLabel = activePairs > 1 ? `${activePairs} Pairs` : (status?.pair || 'Auto-Scan')

  // Build equity curve from sell trades
  const sellTrades = trades.filter(t => t.action?.includes('SELL') && t.pnl !== 0)
  const equityCurve = sellTrades.reduce((acc: { trade: number, equity: number }[], t, i) => {
    const prev = acc.length > 0 ? acc[acc.length - 1].equity : startingBalance
    acc.push({ trade: i + 1, equity: prev + t.pnl })
    return acc
  }, [])

  return (
    <div>
      {/* Ticker Bar */}
      <div className="ticker-bar animate-in">
        <span className="ticker-pair">
          {activePairs > 1 ? `📊 ${activePairs} Pairs` : pairLabel.replace('USDT', '/USDT')}
        </span>
        <span className={`ticker-price ${dailyPnl >= 0 ? 'positive' : 'negative'}`}>
          ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className="ticker-info">Regime: {regime}</span>
        <span className="ticker-info" style={{ color: dailyPnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
          Daily: {dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(2)}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
          {openPositions.length > 0 && (
            <span className="badge badge-pending" style={{ fontSize: '10px' }}>
              {openPositions.length} Open
            </span>
          )}
          <span className={`badge ${isRunning ? 'badge-active' : 'badge-inactive'}`}>
            {isRunning && <span className="pulse-dot" />}
            {isRunning ? 'Running' : 'Stopped'}
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="card stat-card animate-in">
          <div className="label">Daily P&L</div>
          <div className={`value ${dailyPnl >= 0 ? 'positive' : 'negative'}`}>
            {dailyPnl >= 0 ? '+' : ''}${Math.abs(dailyPnl).toFixed(2)}
          </div>
          <div className="sub">
            {dailyPnl >= 0 ? '📈' : '📉'} {dailyPnl >= 0 ? '+' : ''}{(dailyPnl / Math.max(startingBalance, 1) * 100).toFixed(2)}% today
          </div>
        </div>

        <div className="card stat-card animate-in">
          <div className="label">Win Rate</div>
          <div className="value" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <svg width="56" height="56" viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="22" fill="none" stroke="rgba(139,92,246,0.15)" strokeWidth="5" />
              <circle cx="28" cy="28" r="22" fill="none" stroke="url(#wr-grad)" strokeWidth="5" strokeLinecap="round"
                strokeDasharray={`${(winRate / 100) * 138} 138`} transform="rotate(-90 28 28)" />
              <defs>
                <linearGradient id="wr-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#8b5cf6" />
                  <stop offset="100%" stopColor="#10b981" />
                </linearGradient>
              </defs>
            </svg>
            <span>{winRate.toFixed(1)}%</span>
          </div>
          <div className="sub">{totalTrades} total trades</div>
        </div>

        <div className="card stat-card animate-in">
          <div className="label">Today's Trades</div>
          <div className="value">{todayTrades}</div>
          <div className="sub">⚡ of {totalTrades} all-time</div>
        </div>

        <div className="card stat-card animate-in">
          <div className="label">Total P&L</div>
          <div className={`value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
            {totalPnl >= 0 ? '+' : ''}${Math.abs(totalPnl).toFixed(2)}
          </div>
          <div className="sub">ROI: {(totalPnl / Math.max(startingBalance, 1) * 100).toFixed(2)}%</div>
        </div>
      </div>

      {/* Open Positions */}
      {openPositions.length > 0 ? (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="chart-title" style={{ marginBottom: '16px' }}>
            📈 Open Positions ({openPositions.length})
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '12px' }}>
            {openPositions.map((pos: any, i: number) => {
              const upnl = pos.unrealized_pnl ?? pos.daily_pnl ?? 0
              return (
              <div key={i} style={{
                padding: '14px 16px',
                borderRadius: '10px',
                background: upnl >= 0
                  ? 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(16,185,129,0.02) 100%)'
                  : 'linear-gradient(135deg, rgba(239,68,68,0.08) 0%, rgba(239,68,68,0.02) 100%)',
                border: `1px solid ${upnl >= 0 ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 700, fontSize: '14px' }}>{pos.pair}</span>
                  <span className={upnl >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 600, fontSize: '13px' }}>
                    {upnl >= 0 ? '+' : ''}${upnl.toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                  <span>{pos.direction || 'LONG'} @ ${Number(pos.entry_price || 0).toFixed(pos.entry_price < 1 ? 6 : 2)}</span>
                  <span>Qty: {Number(pos.quantity || 0).toFixed(pos.quantity > 100 ? 0 : 4)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)' }}>
                  <span>Locked: ${Number(pos.locked_capital || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
                  <span>{pos.bars_held || 0} bars</span>
                </div>
              </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="label" style={{ marginBottom: '12px' }}>Open Positions</div>
          <div className="empty-state" style={{ padding: '20px' }}>
            <div className="icon">💤</div>
            <div className="message">No open positions</div>
            <div className="hint">Bot is scanning for entry signals across {activePairs} pairs</div>
          </div>
        </div>
      )}

      {/* ═══ STRATEGY PORTFOLIO ═══ */}
      <div style={{ marginBottom: '24px' }}>
        <StrategyPanel />
      </div>

      {/* ═══ INTELLIGENCE PANEL ═══ */}
      <div className="stats-grid" style={{ marginBottom: '24px' }}>
        <div className="card stat-card animate-in">
          <div className="label">🧠 Brain</div>
          <div className="value" style={{ fontSize: '15px' }}>{brain?.stage || 'Connecting...'}</div>
          <div className="sub">{brain?.total_trades || 0} trades | {brain?.known_pairs || 0} pairs known</div>
        </div>
        <div className="card stat-card animate-in">
          <div className="label">🐝 Swarm</div>
          <div className="value">{swarm?.agents?.length || 0} Agents</div>
          <div className="sub">Threshold: {((swarm?.consensus_threshold || 0.55) * 100).toFixed(0)}%</div>
        </div>
        <div className="card stat-card animate-in">
          <div className="label">🛡️ Shield</div>
          <div className={`value ${shield?.circuit_breaker?.tripped ? 'negative' : 'positive'}`} style={{ fontSize: '15px' }}>
            {shield?.circuit_breaker?.tripped ? '🚨 TRIPPED' : '✅ Active'}
          </div>
          <div className="sub">{shield?.portfolio_guard?.open_positions || 0}/{shield?.portfolio_guard?.max_positions || 8} positions</div>
        </div>
        <div className="card stat-card animate-in">
          <div className="label">📊 Daily Risk</div>
          <div className={`value ${(shield?.circuit_breaker?.daily_pnl || 0) >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '18px' }}>
            ${(shield?.circuit_breaker?.daily_pnl || 0).toFixed(2)}
          </div>
          <div className="sub">{shield?.circuit_breaker?.consecutive_losses || 0} consecutive losses</div>
        </div>
      </div>

      {/* ═══ SWARM AGENTS TABLE ═══ */}
      {swarm?.agents && swarm.agents.length > 0 && (
        <div className="card" style={{ marginBottom: '24px' }}>
          <div className="chart-title" style={{ marginBottom: '16px' }}>🐝 Swarm Intelligence — Agent Performance</div>
          <table className="trade-table">
            <thead>
              <tr><th>Agent</th><th>Weight</th><th>Accuracy</th><th>Votes</th><th>Status</th></tr>
            </thead>
            <tbody>
              {swarm.agents.sort((a, b) => b.weight - a.weight).map((agent, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{agent.name}</td>
                  <td>
                    <span style={{
                      color: agent.weight >= 1.3 ? '#10b981' : agent.weight >= 1.0 ? '#8b5cf6' : '#f59e0b',
                      fontWeight: 600
                    }}>{agent.weight.toFixed(2)}x</span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ width: '60px', height: '6px', borderRadius: '3px', background: 'rgba(139,92,246,0.15)', overflow: 'hidden' }}>
                        <div style={{
                          width: `${agent.accuracy * 100}%`, height: '100%', borderRadius: '3px',
                          background: agent.accuracy >= 0.6 ? '#10b981' : agent.accuracy >= 0.5 ? '#8b5cf6' : '#ef4444',
                        }} />
                      </div>
                      <span style={{ fontSize: '12px' }}>{(agent.accuracy * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td style={{ fontSize: '12px', color: '#94a3b8' }}>{agent.correct_votes}/{agent.total_votes}</td>
                  <td>
                    <span className={`badge ${agent.total_votes >= 5 ? 'badge-active' : 'badge-pending'}`}
                      style={{ fontSize: '10px', padding: '2px 8px' }}>
                      {agent.total_votes >= 30 ? 'Expert' : agent.total_votes >= 5 ? 'Learning' : 'Newborn'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Chart + Trade Stats */}
      <div className="grid-2col">
        <div className="card chart-card" style={{ display: 'flex', flexDirection: 'column', maxHeight: '480px' }}>
          <div className="chart-header">
            <div>
              <div className="chart-title">Performance Overview</div>
              <div className="chart-subtitle">Cumulative P&L</div>
            </div>
            <div className="chart-controls">
              {[7, 14, 30].map(d => (
                <button key={d} className={`chart-btn ${chartDays === d ? 'active' : ''}`} onClick={() => setChartDays(d)}>{d}D</button>
              ))}
            </div>
          </div>
          <div style={{ height: '340px' }}>
            {pnlHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={pnlHistory} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(139,92,246,0.08)" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickFormatter={v => v.slice(5)} />
                  <YAxis stroke="#64748b" fontSize={11} tickFormatter={v => `$${v}`} />
                  <Tooltip contentStyle={{ background: 'rgba(15,23,42,0.95)', border: '1px solid rgba(139,92,246,0.2)', borderRadius: '8px', fontSize: '12px', color: '#f1f5f9' }}
                    formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']} />
                  <Area type="monotone" dataKey="cumulative_pnl" stroke="#8b5cf6" strokeWidth={2} fill="url(#pnlGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="icon">📊</div>
                <div className="message">No trading data yet</div>
                <div className="hint">Start the bot to see your P&L chart</div>
              </div>
            )}
          </div>
        </div>

        {/* Trade Statistics + Equity Curve */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', maxHeight: '480px' }}>
          <div className="chart-title" style={{ marginBottom: '16px' }}>Trade Statistics</div>
          {/* Stats Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '20px' }}>
            <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.1)' }}>
              <div className="label" style={{ fontSize: '11px', marginBottom: '4px' }}>Total Trades</div>
              <div style={{ fontSize: '22px', fontWeight: 700 }}>{totalTrades}</div>
            </div>
            <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.1)' }}>
              <div className="label" style={{ fontSize: '11px', marginBottom: '4px' }}>Win Rate</div>
              <div className="positive" style={{ fontSize: '22px', fontWeight: 700 }}>{winRate.toFixed(1)}%</div>
            </div>
            <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.1)' }}>
              <div className="label" style={{ fontSize: '11px', marginBottom: '4px' }}>Equity</div>
              <div className={equity >= startingBalance ? 'positive' : 'negative'} style={{ fontSize: '22px', fontWeight: 700 }}>
                ${equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
            </div>
            <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.1)' }}>
              <div className="label" style={{ fontSize: '11px', marginBottom: '4px' }}>Active Pairs</div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: '#8b5cf6' }}>{activePairs}</div>
            </div>
          </div>

          {/* Mini Equity Curve */}
          <div className="label" style={{ marginBottom: '8px', fontSize: '11px' }}>Equity Curve (Last Trades)</div>
          <div style={{ height: '160px' }}>
            {equityCurve.length > 1 ? (
              <ResponsiveContainer width="100%" height={150}>
                <AreaChart data={equityCurve} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="equity" stroke="#10b981" strokeWidth={2} fill="url(#eqGrad)" dot={false} />
                  <Tooltip contentStyle={{ background: 'rgba(15,23,42,0.95)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: '6px', fontSize: '11px', color: '#f1f5f9' }}
                    formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']}
                    labelFormatter={(l) => `Trade #${l}`} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: '150px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                Waiting for completed trades...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Trades */}
      <div className="card" style={{ marginTop: '24px' }}>
        <div className="chart-title" style={{ marginBottom: '16px' }}>Recent Trades</div>
        {trades.length > 0 ? (
          <table className="trade-table">
            <thead><tr><th>Time</th><th>Pair</th><th>Side</th><th>Qty</th><th>Price</th><th>P&L</th></tr></thead>
            <tbody>
              {trades.slice(0, 15).map((t, i) => (
                <tr key={i}>
                  <td>{new Date(t.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                  <td style={{ fontWeight: 600, fontSize: '12px' }}>{(t.pair || 'ETH').replace('USDT', '')}</td>
                  <td><span className={`badge ${t.action === 'BUY' ? 'badge-active' : 'badge-pending'}`}>{t.action}</span></td>
                  <td style={{ fontSize: '12px' }}>{t.qty.toFixed(4)}</td>
                  <td>${t.price.toFixed(2)}</td>
                  <td className={t.pnl >= 0 ? 'positive' : 'negative'}>
                    {t.action.includes('SELL') ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state" style={{ padding: '40px 20px' }}>
            <div className="icon">📋</div>
            <div className="message">No trades yet</div>
            <div className="hint">Trades will appear here</div>
          </div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar
} from 'recharts'
import { TrendingUp, TrendingDown, Target, Activity, Zap, DollarSign } from 'lucide-react'
import type { BotStatus } from '../App'

const API_URL = import.meta.env.VITE_API_URL || ''

interface Trade {
  timestamp: string
  action: string
  qty: number
  price: number
  pnl: number
}

interface DashboardProps {
  status: BotStatus | null
}

export default function Dashboard({ status }: DashboardProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [chartDays, setChartDays] = useState(7)
  const [pnlHistory, setPnlHistory] = useState<any[]>([])

  useEffect(() => {
    fetchTrades()
    fetchPnlHistory()
  }, [chartDays])

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

  const price = status?.price || 0
  const dailyPnl = status?.daily_pnl || 0
  const totalPnl = status?.total_pnl || 0
  const winRate = status?.win_rate || 0
  const totalTrades = status?.total_trades || 0
  const todayTrades = status?.today_trades || 0
  const balance = status?.paper_balance || 100000
  const isRunning = status?.is_running ?? false
  const regime = status?.regime || 'unknown'
  const position = status?.position || null

  return (
    <div>
      {/* Ticker Bar */}
      <div className="ticker-bar animate-in">
        <span className="ticker-pair">ETH/USDT</span>
        <span className={`ticker-price ${price > 0 ? 'positive' : ''}`}>
          ${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className="ticker-info">Regime: {regime}</span>
        <span className="ticker-info">Balance: ${balance.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        <div style={{ marginLeft: 'auto' }}>
          <span className={`badge ${isRunning ? 'badge-active' : 'badge-inactive'}`}>
            {isRunning && <span className="pulse-dot" />}
            {isRunning ? 'Running' : 'Stopped'}
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        {/* Daily P&L */}
        <div className="card stat-card animate-in">
          <div className="label">Daily P&L</div>
          <div className={`value ${dailyPnl >= 0 ? 'positive' : 'negative'}`}>
            {dailyPnl >= 0 ? '+' : ''}${Math.abs(dailyPnl).toFixed(2)}
          </div>
          <div className="sub">
            {dailyPnl >= 0 ? '📈' : '📉'} {dailyPnl >= 0 ? '+' : ''}{(dailyPnl / Math.max(balance, 1) * 100).toFixed(2)}% today
          </div>
        </div>

        {/* Win Rate */}
        <div className="card stat-card animate-in">
          <div className="label">Win Rate</div>
          <div className="value" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <svg width="56" height="56" viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="22" fill="none" stroke="rgba(139,92,246,0.15)" strokeWidth="5" />
              <circle
                cx="28" cy="28" r="22" fill="none"
                stroke="url(#wr-grad)" strokeWidth="5" strokeLinecap="round"
                strokeDasharray={`${(winRate / 100) * 138} 138`}
                transform="rotate(-90 28 28)"
              />
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

        {/* Today's Trades */}
        <div className="card stat-card animate-in">
          <div className="label">Today's Trades</div>
          <div className="value">{todayTrades}</div>
          <div className="sub">⚡ of {status?.total_trades || 0} all-time</div>
        </div>

        {/* Total P&L */}
        <div className="card stat-card animate-in">
          <div className="label">Total P&L</div>
          <div className={`value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
            {totalPnl >= 0 ? '+' : ''}${Math.abs(totalPnl).toFixed(2)}
          </div>
          <div className="sub">
            ROI: {(totalPnl / Math.max(balance, 1) * 100).toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Open Position */}
      {position && (
        <div className={`card position-card ${position.unrealized_pnl >= 0 ? '' : 'loss'}`} style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div className="label">Open Position</div>
              <div className="value" style={{ fontSize: '20px' }}>
                {position.quantity.toFixed(5)} ETH @ ${position.entry_price.toFixed(2)}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="label">Unrealized P&L</div>
              <div className={`value ${position.unrealized_pnl >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '20px' }}>
                {position.unrealized_pnl >= 0 ? '+' : ''}{(position.unrealized_pnl * 100).toFixed(2)}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chart + Recent Trades */}
      <div className="grid-2col">
        {/* P&L Chart */}
        <div className="card chart-card">
          <div className="chart-header">
            <div>
              <div className="chart-title">Performance Overview</div>
              <div className="chart-subtitle">Cumulative P&L</div>
            </div>
            <div className="chart-controls">
              {[7, 14, 30].map(d => (
                <button
                  key={d}
                  className={`chart-btn ${chartDays === d ? 'active' : ''}`}
                  onClick={() => setChartDays(d)}
                >
                  {d}D
                </button>
              ))}
            </div>
          </div>
          <div style={{ height: '280px' }}>
            {pnlHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
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
                  <Tooltip
                    contentStyle={{
                      background: 'rgba(15,23,42,0.95)',
                      border: '1px solid rgba(139,92,246,0.2)',
                      borderRadius: '8px',
                      fontSize: '12px',
                      color: '#f1f5f9'
                    }}
                    formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
                  />
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

        {/* Recent Trades */}
        <div className="card">
          <div className="chart-title" style={{ marginBottom: '16px' }}>Recent Trades</div>
          {trades.length > 0 ? (
            <table className="trade-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Side</th>
                  <th>Price</th>
                  <th>P&L</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 10).map((t, i) => (
                  <tr key={i}>
                    <td>{new Date(t.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                    <td>
                      <span className={`badge ${t.action === 'BUY' ? 'badge-active' : 'badge-pending'}`}>
                        {t.action}
                      </span>
                    </td>
                    <td>${t.price.toFixed(2)}</td>
                    <td className={t.pnl >= 0 ? 'positive' : 'negative'}>
                      {t.action === 'SELL' ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
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
    </div>
  )
}

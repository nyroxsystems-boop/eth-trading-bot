import { useState, useEffect } from 'react'
import { TrendingUp, Clock } from 'lucide-react'
import type { BotStatus } from '../App'

const API_URL = import.meta.env.VITE_API_URL || ''

interface Trade {
  timestamp: string
  action: string
  qty: number
  price: number
  pnl: number
}

interface SignalInfo {
  score: number
  signals: string[]
  rsi: number
  adx: number
  regime: string
  price: number
  should_buy: boolean
}

interface TradingProps {
  status: BotStatus | null
}

interface BotConfig {
  pair: string
  interval: string
  paper_mode: boolean
  risk_per_trade: number
  tp_min: number
  tp_max: number
  stop_floor: number
  max_trades_per_day: number
  entry_score_min: number
  loop_sleep_seconds: number
}

export default function Trading(_props: TradingProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [signal, setSignal] = useState<SignalInfo | null>(null)
  const [config, setConfig] = useState<BotConfig | null>(null)
  const [localStatus, setLocalStatus] = useState<any>(null)

  const status = localStatus

  useEffect(() => {
    fetchTrades()
    fetchSignal()
    fetchConfig()
    fetchStatus()
    const interval = setInterval(() => {
      fetchSignal()
      fetchStatus()
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchTrades = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/trades?limit=50`)
      if (res.ok) setTrades(await res.json())
    } catch {}
  }

  const fetchSignal = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/signal`)
      if (res.ok) setSignal(await res.json())
    } catch {}
  }

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/config`)
      if (res.ok) setConfig(await res.json())
    } catch {}
  }

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/status`)
      if (res.ok) setLocalStatus(await res.json())
    } catch {}
  }

  const position = status?.position || null

  // Calculate trade stats
  const sellTrades = trades.filter(t => t.action === 'SELL' && t.pnl !== 0)
  const wins = sellTrades.filter(t => t.pnl > 0)
  const losses = sellTrades.filter(t => t.pnl <= 0)
  const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0
  const avgLoss = losses.length > 0 ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Trading</div>
        <div className="page-subtitle">Live signal monitor & trade history</div>
      </div>

      {/* Live Signal + Position */}
      <div className="stats-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
        {/* Current Signal */}
        <div className="card animate-in">
          <div className="label" style={{ marginBottom: '12px' }}>Current Signal</div>
          {signal ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                <div style={{
                  width: '48px', height: '48px', borderRadius: '12px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: signal.should_buy
                    ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                    : 'linear-gradient(135deg, #64748b 0%, #475569 100%)',
                }}>
                  {signal.should_buy ? <TrendingUp size={24} color="white" /> : <Clock size={24} color="white" />}
                </div>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>
                    {signal.should_buy ? 'BUY Signal' : 'Waiting...'}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    Score: {signal.score.toFixed(3)} | Regime: {signal.regime}
                  </div>
                </div>
              </div>
              {/* Signal bars */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {signal.signals.map((s, i) => (
                  <span key={i} className="badge badge-active">{s}</span>
                ))}
              </div>
              {/* Indicators */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginTop: '16px' }}>
                <div>
                  <div className="label">RSI</div>
                  <div style={{ fontSize: '18px', fontWeight: 600, color: signal.rsi < 30 ? 'var(--green)' : signal.rsi > 70 ? 'var(--red)' : 'var(--text-primary)' }}>
                    {signal.rsi.toFixed(1)}
                  </div>
                </div>
                <div>
                  <div className="label">ADX</div>
                  <div style={{ fontSize: '18px', fontWeight: 600 }}>{signal.adx.toFixed(1)}</div>
                </div>
                <div>
                  <div className="label">Price</div>
                  <div style={{ fontSize: '18px', fontWeight: 600 }}>${signal.price.toFixed(2)}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state" style={{ padding: '20px' }}>
              <div className="hint">Connecting to signal engine...</div>
            </div>
          )}
        </div>

        {/* Open Position */}
        <div className={`card animate-in ${position ? (position.unrealized_pnl >= 0 ? 'position-card' : 'position-card loss') : ''}`}>
          <div className="label" style={{ marginBottom: '12px' }}>Open Position</div>
          {position ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
                <div>
                  <div style={{ fontSize: '24px', fontWeight: 700 }}>
                    {position.quantity.toFixed(5)} ETH
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    Entry: ${position.entry_price.toFixed(2)}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className={`value ${position.unrealized_pnl >= 0 ? 'positive' : 'negative'}`}
                    style={{ fontSize: '24px', fontWeight: 700 }}>
                    {position.unrealized_pnl >= 0 ? '+' : ''}{(position.unrealized_pnl * 100).toFixed(2)}%
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    ${(position.unrealized_pnl * position.entry_price * position.quantity).toFixed(2)}
                  </div>
                </div>
              </div>
              {/* P&L bar */}
              <div style={{
                height: '6px', borderRadius: '3px',
                background: 'rgba(139,92,246,0.15)',
                overflow: 'hidden'
              }}>
                <div style={{
                  height: '100%', borderRadius: '3px',
                  width: `${Math.min(100, Math.abs(position.unrealized_pnl * 100 / 3) * 100)}%`,
                  background: position.unrealized_pnl >= 0 ? 'var(--gradient-green)' : 'var(--gradient-red)',
                  transition: 'width 0.5s ease'
                }} />
              </div>
            </div>
          ) : (
            <div className="empty-state" style={{ padding: '30px 20px' }}>
              <div className="icon">💤</div>
              <div className="message">No open position</div>
              <div className="hint">Bot is scanning for entry signals</div>
            </div>
          )}
        </div>
      </div>

      {/* Trade Stats + Full History */}
      <div className="grid-2col" style={{ marginTop: '24px' }}>
        {/* Trade Statistics */}
        <div className="card">
          <div className="chart-title" style={{ marginBottom: '20px' }}>Trade Statistics</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
            <div>
              <div className="label">Total Trades</div>
              <div style={{ fontSize: '24px', fontWeight: 700 }}>{sellTrades.length}</div>
            </div>
            <div>
              <div className="label">Win Rate</div>
              <div style={{ fontSize: '24px', fontWeight: 700 }} className="positive">
                {sellTrades.length > 0 ? (wins.length / sellTrades.length * 100).toFixed(1) : 0}%
              </div>
            </div>
            <div>
              <div className="label">Avg Win</div>
              <div style={{ fontSize: '24px', fontWeight: 700 }} className="positive">
                +${avgWin.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="label">Avg Loss</div>
              <div style={{ fontSize: '24px', fontWeight: 700 }} className="negative">
                ${avgLoss.toFixed(2)}
              </div>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="card">
          <div className="chart-title" style={{ marginBottom: '16px' }}>Bot Config</div>
          {config ? (
            <>
              <div className="setting-row">
                <span className="setting-label">Mode</span>
                <span className={`badge ${config.paper_mode ? 'badge-active' : 'badge-pending'}`}>
                  {config.paper_mode ? 'Paper' : 'Live'}
                </span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Pair</span>
                <span className="setting-value">{config.pair}</span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Interval</span>
                <span className="setting-value">{config.interval}</span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Risk/Trade</span>
                <span className="setting-value">{config.risk_per_trade}%</span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Take Profit</span>
                <span className="setting-value">{config.tp_min}%-{config.tp_max}%</span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Stop Loss</span>
                <span className="setting-value">{config.stop_floor}% floor</span>
              </div>
              <div className="setting-row">
                <span className="setting-label">Entry Score</span>
                <span className="setting-value">{config.entry_score_min}</span>
              </div>
            </>
          ) : (
            <div className="empty-state" style={{ padding: '20px' }}>
              <div className="hint">Loading config...</div>
            </div>
          )}
        </div>
      </div>

      {/* Full Trade History */}
      <div className="card" style={{ marginTop: '24px' }}>
        <div className="chart-title" style={{ marginBottom: '16px' }}>Trade History</div>
        {trades.length > 0 ? (
          <table className="trade-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Side</th>
                <th>Quantity</th>
                <th>Price</th>
                <th>P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i}>
                  <td>{new Date(t.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                  <td>
                    <span className={`badge ${t.action === 'BUY' ? 'badge-active' : t.pnl > 0 ? 'badge-active' : 'badge-inactive'}`}>
                      {t.action}
                    </span>
                  </td>
                  <td>{t.qty.toFixed(5)}</td>
                  <td>${t.price.toFixed(2)}</td>
                  <td className={t.pnl > 0 ? 'positive' : t.pnl < 0 ? 'negative' : 'neutral'}>
                    {t.action === 'SELL' ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <div className="icon">📋</div>
            <div className="message">No trades recorded</div>
            <div className="hint">Start the bot to begin trading</div>
          </div>
        )}
      </div>
    </div>
  )
}

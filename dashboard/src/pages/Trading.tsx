import { useState, useEffect } from 'react'
import { TrendingUp, Clock } from 'lucide-react'
import {
  BarChart, Bar, ResponsiveContainer, Tooltip, Cell
} from 'recharts'
import type { BotStatus } from '../App'

const API_URL = import.meta.env.VITE_API_URL || ''

interface Trade {
  timestamp: string
  action: string
  pair?: string
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

interface OpenPosition {
  pair: string
  daily_pnl: number
  balance: number
  win_streak: number
  loss_streak: number
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
    const intv = setInterval(() => {
      fetchTrades()
      fetchSignal()
      fetchStatus()
    }, 10000)
    return () => clearInterval(intv)
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

  const openPositions: OpenPosition[] = status?.open_positions || []
  const activePairs = status?.active_pairs || 1

  // Calculate trade stats
  const sellTrades = trades.filter(t => t.action?.includes('SELL') && t.pnl !== 0)
  const wins = sellTrades.filter(t => t.pnl > 0)
  const losses = sellTrades.filter(t => t.pnl <= 0)
  const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0
  const avgLoss = losses.length > 0 ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0

  // PnL per trade for bar chart (last 20 sell trades)
  const pnlBars = sellTrades.slice(-20).map((t, i) => ({
    trade: i + 1,
    pnl: t.pnl,
    color: t.pnl >= 0 ? '#10b981' : '#ef4444',
  }))

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Trading</div>
        <div className="page-subtitle">Live signal monitor & trade history — {activePairs} active pairs</div>
      </div>

      {/* Live Signal + Open Positions */}
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
                    {signal.should_buy ? 'BUY Signal' : 'Waiting...'}{' '}
                    <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--accent)' }}>{(signal as any).pair || ''}</span>
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    Score: {signal.score.toFixed(3)} | Regime: {signal.regime}
                    {(signal as any).total_pairs > 1 && (
                      <span> | 🔄 {((signal as any).rotating_index || 0) + 1}/{(signal as any).total_pairs}</span>
                    )}
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

        {/* Open Positions */}
        <div className="card animate-in">
          <div className="label" style={{ marginBottom: '12px' }}>
            Open Positions {openPositions.length > 0 && <span style={{ color: 'var(--green)' }}>({openPositions.length})</span>}
          </div>
          {openPositions.length > 0 ? (
            <div style={{ display: 'grid', gap: '8px', maxHeight: '240px', overflowY: 'auto' }}>
              {openPositions.map((pos, i) => (
                <div key={i} style={{
                  padding: '10px 14px',
                  borderRadius: '8px',
                  background: pos.daily_pnl >= 0
                    ? 'linear-gradient(135deg, rgba(16,185,129,0.06) 0%, rgba(16,185,129,0.02) 100%)'
                    : 'linear-gradient(135deg, rgba(239,68,68,0.06) 0%, rgba(239,68,68,0.02) 100%)',
                  border: `1px solid ${pos.daily_pnl >= 0 ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'}`,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '13px' }}>{pos.pair}</span>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      {pos.win_streak > 0 ? `🔥${pos.win_streak}W` : ''}
                      {pos.loss_streak > 0 ? `❄️${pos.loss_streak}L` : ''}
                    </div>
                  </div>
                  <span className={pos.daily_pnl >= 0 ? 'positive' : 'negative'} style={{ fontWeight: 600, fontSize: '13px' }}>
                    {pos.daily_pnl >= 0 ? '+' : ''}${pos.daily_pnl.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state" style={{ padding: '30px 20px' }}>
              <div className="icon">💤</div>
              <div className="message">No open positions</div>
              <div className="hint">Bot is scanning {activePairs} pairs for entries</div>
            </div>
          )}
        </div>
      </div>

      {/* Trade Stats + Bot Config */}
      <div className="grid-2col" style={{ marginTop: '24px' }}>
        {/* Trade Statistics with PnL Bars */}
        <div className="card">
          <div className="chart-title" style={{ marginBottom: '16px' }}>Trade Statistics</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.1)' }}>
              <div className="label" style={{ fontSize: '10px', marginBottom: '2px' }}>Trades</div>
              <div style={{ fontSize: '20px', fontWeight: 700 }}>{sellTrades.length}</div>
            </div>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.1)' }}>
              <div className="label" style={{ fontSize: '10px', marginBottom: '2px' }}>Win Rate</div>
              <div className="positive" style={{ fontSize: '20px', fontWeight: 700 }}>
                {sellTrades.length > 0 ? (wins.length / sellTrades.length * 100).toFixed(1) : 0}%
              </div>
            </div>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.1)' }}>
              <div className="label" style={{ fontSize: '10px', marginBottom: '2px' }}>Avg Win</div>
              <div className="positive" style={{ fontSize: '20px', fontWeight: 700 }}>
                +${avgWin.toFixed(2)}
              </div>
            </div>
            <div style={{ padding: '10px', borderRadius: '8px', background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.1)' }}>
              <div className="label" style={{ fontSize: '10px', marginBottom: '2px' }}>Avg Loss</div>
              <div className="negative" style={{ fontSize: '20px', fontWeight: 700 }}>
                ${avgLoss.toFixed(2)}
              </div>
            </div>
          </div>

          {/* PnL Bar Chart */}
          <div className="label" style={{ fontSize: '11px', marginBottom: '6px' }}>P&L per Trade (Last {pnlBars.length})</div>
          <div style={{ height: '100px' }}>
            {pnlBars.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pnlBars} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
                  <Tooltip
                    contentStyle={{ background: 'rgba(15,23,42,0.95)', border: '1px solid rgba(139,92,246,0.2)', borderRadius: '6px', fontSize: '11px', color: '#f1f5f9' }}
                    formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
                    labelFormatter={(l) => `Trade #${l}`}
                  />
                  <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                    {pnlBars.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                Waiting for trades...
              </div>
            )}
          </div>
        </div>

        {/* Bot Config */}
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
                <span className="setting-label">Active Pairs</span>
                <span className="setting-value" style={{ color: '#8b5cf6' }}>{activePairs}</span>
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
                <th>Pair</th>
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
                  <td style={{ fontWeight: 600, fontSize: '12px' }}>{(t.pair || 'ETH').replace('USDT', '')}</td>
                  <td>
                    <span className={`badge ${t.action === 'BUY' ? 'badge-active' : t.pnl > 0 ? 'badge-active' : 'badge-inactive'}`}>
                      {t.action}
                    </span>
                  </td>
                  <td>{t.qty.toFixed(5)}</td>
                  <td>${t.price.toFixed(2)}</td>
                  <td className={t.pnl > 0 ? 'positive' : t.pnl < 0 ? 'negative' : 'neutral'}>
                    {t.action.includes('SELL') ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
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

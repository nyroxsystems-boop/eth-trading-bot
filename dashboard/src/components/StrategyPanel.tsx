import { useState, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || ''

interface StrategyInfo {
  id: string
  name: string
  status: string
  weight: number
  sharpe: number
  sharpe_30d?: number
  win_rate: number
  total_trades: number
  trades_30d?: number
  pnl: number
  pnl_30d_pct?: number
  capital_usd?: number
}

interface AllocatorState {
  total_equity: number
  drawdown_pct: number
  kill_switch: boolean
  daily_pnl_pct: number
  strategies: Record<string, StrategyInfo>
}

const STATUS_EMOJI: Record<string, string> = {
  'ACTIVE': '🟢',
  'PAPER': '📝',
  'SCANNING': '🔍',
  'PLANNED': '⏳',
  'PAUSED': '⏸️',
}

const STRATEGY_ICONS: Record<string, string> = {
  'S2_StatArb': '📊',
  'S3_MarketMaker': '🏛️',
  'S4_MomentumV2': '📈',
  'S5_LiqHunter': '🎯',
}

const STRATEGY_NAMES: Record<string, string> = {
  'S2_StatArb': 'Statistical Arb',
  'S3_MarketMaker': 'Market Making',
  'S4_MomentumV2': 'Momentum Breakout',
  'S5_LiqHunter': 'Liquidation Bounce',
}

export default function StrategyPanel() {
  const [allocator, setAllocator] = useState<AllocatorState | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAllocator()
    const intv = setInterval(fetchAllocator, 30000) // 30s refresh
    return () => clearInterval(intv)
  }, [])

  const fetchAllocator = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/allocator`)
      if (res.ok) {
        setAllocator(await res.json())
      }
    } catch { /* API not available */ }
    setLoading(false)
  }

  if (loading) {
    return (
      <div className="card" style={{ padding: '24px', textAlign: 'center' }}>
        <div className="label">Loading strategies...</div>
      </div>
    )
  }

  if (!allocator) {
    return (
      <div className="card" style={{ padding: '24px' }}>
        <div className="chart-title" style={{ marginBottom: '12px' }}>🎛️ Strategy Portfolio</div>
        <div className="empty-state" style={{ padding: '20px' }}>
          <div className="icon">🔌</div>
          <div className="message">Allocator not connected</div>
          <div className="hint">Strategy data will appear when the bot is running</div>
        </div>
      </div>
    )
  }

  const strategies = allocator.strategies ? Object.entries(allocator.strategies) : []
  const activeCount = strategies.filter(([, s]) => s.status === 'ACTIVE' || s.status === 'PAPER').length

  return (
    <div style={{ marginBottom: '24px' }}>
      {/* Allocator Header */}
      <div className="card" style={{ marginBottom: '16px', padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div className="chart-title">🎛️ Strategy Portfolio</div>
          {allocator.kill_switch && (
            <span className="badge badge-inactive" style={{ fontSize: '12px', padding: '4px 12px', animation: 'pulse 1.5s infinite' }}>
              🚨 KILL SWITCH ACTIVE
            </span>
          )}
        </div>

        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
          <div style={{ textAlign: 'center' }}>
            <div className="label" style={{ fontSize: '11px' }}>Total Equity</div>
            <div className="value" style={{ fontSize: '18px' }}>
              ${(allocator.total_equity || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="label" style={{ fontSize: '11px' }}>Drawdown</div>
            <div className={`value ${(allocator.drawdown_pct || 0) > 10 ? 'negative' : ''}`} style={{ fontSize: '18px' }}>
              {(allocator.drawdown_pct || 0).toFixed(1)}%
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="label" style={{ fontSize: '11px' }}>Active Strategies</div>
            <div className="value" style={{ fontSize: '18px', color: '#8b5cf6' }}>
              {activeCount}/{strategies.length}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="label" style={{ fontSize: '11px' }}>Daily P&L</div>
            <div className={`value ${(allocator.daily_pnl_pct || 0) >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '18px' }}>
              {(allocator.daily_pnl_pct || 0) >= 0 ? '+' : ''}{(allocator.daily_pnl_pct || 0).toFixed(2)}%
            </div>
          </div>
        </div>
      </div>

      {/* Strategy Cards */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
        {strategies.map(([id, strat]) => (
          <div key={id} className="card stat-card animate-in" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '20px' }}>{STRATEGY_ICONS[id] || '⚙️'}</span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '14px' }}>{STRATEGY_NAMES[id] || id}</div>
                  <div style={{ fontSize: '11px', color: '#64748b' }}>{id}</div>
                </div>
              </div>
              <span className={`badge ${strat.status === 'ACTIVE' ? 'badge-active' : strat.status === 'PAPER' ? 'badge-pending' : 'badge-inactive'}`}
                style={{ fontSize: '10px', padding: '2px 8px' }}>
                {STATUS_EMOJI[strat.status] || ''} {strat.status}
              </span>
            </div>

            {/* Weight Bar */}
            <div style={{ marginBottom: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8', marginBottom: '4px' }}>
                <span>Allocation</span>
                <span style={{ fontWeight: 600, color: '#e2e8f0' }}>{(strat.weight || 0).toFixed(0)}%</span>
              </div>
              <div style={{ width: '100%', height: '6px', borderRadius: '3px', background: 'rgba(139,92,246,0.1)', overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.min(strat.weight || 0, 100)}%`,
                  height: '100%',
                  borderRadius: '3px',
                  background: strat.status === 'ACTIVE' ? 'linear-gradient(90deg, #8b5cf6, #10b981)' :
                              strat.status === 'PAPER' ? 'linear-gradient(90deg, #8b5cf6, #f59e0b)' :
                              'rgba(100,116,139,0.3)',
                  transition: 'width 0.5s ease',
                }} />
              </div>
            </div>

            {/* Stats Row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', fontSize: '11px' }}>
              <div>
                <div style={{ color: '#64748b' }}>Sharpe</div>
                <div style={{ fontWeight: 600, color: (strat.sharpe_30d || strat.sharpe || 0) >= 1 ? '#10b981' : (strat.sharpe_30d || strat.sharpe || 0) >= 0 ? '#f59e0b' : '#ef4444' }}>
                  {(strat.sharpe_30d || strat.sharpe || 0).toFixed(2)}
                </div>
              </div>
              <div>
                <div style={{ color: '#64748b' }}>Win Rate</div>
                <div style={{ fontWeight: 600 }}>{(strat.win_rate || 0).toFixed(0)}%</div>
              </div>
              <div>
                <div style={{ color: '#64748b' }}>Trades</div>
                <div style={{ fontWeight: 600 }}>{strat.trades_30d || strat.total_trades || 0}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ─── Types ───
interface EdgeReport {
  status: 'COLLECTING' | 'VALIDATED' | 'NO_EDGE' | 'WEAK'
  message: string
  total_predictions: number
  evaluated: number
  pending: number
  target: number
  progress_pct: number
  win_rate?: number
  expectancy_pct?: number
  profit_factor?: number
  avg_win_pct?: number
  avg_loss_pct?: number
  max_consecutive_losses?: number
  total_pnl_pct?: number
  signal_breakdown?: Record<string, {
    predictions: number
    win_rate: number
    avg_pnl_pct: number
    total_pnl_pct: number
  }>
  validation_criteria?: {
    min_predictions: number
    min_win_rate: number
    min_profit_factor: number
    max_consecutive_losses: number
  }
}

interface SignalStatus {
  total_signals_generated: number
  last_signals: Array<{
    name: string
    direction: string
    confidence: number
    reason: string
  }>
  edges_active: string[]
}

interface CollectorStatus {
  running: boolean
  ticks_collected: number
  errors: number
  has_futures_api: boolean
  hours_of_data: number
}

interface MarketDataPoint {
  timestamp: string
  price: number
  funding_rate: number | null
  open_interest: number | null
  volume_spike_ratio: number | null
  vwap_deviation_pct: number | null
  rsi_1m: number | null
  long_short_ratio: number | null
  bb_position: number | null
}

// ─── Status Badge ───
function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { bg: string; text: string; glow: string; label: string }> = {
    COLLECTING: { bg: 'rgba(59,130,246,0.15)', text: '#60A5FA', glow: '0 0 20px rgba(59,130,246,0.3)', label: '📊 COLLECTING DATA' },
    VALIDATED: { bg: 'rgba(34,197,94,0.15)', text: '#4ADE80', glow: '0 0 30px rgba(34,197,94,0.4)', label: '✅ EDGE VALIDATED — READY FOR LIVE' },
    NO_EDGE: { bg: 'rgba(239,68,68,0.15)', text: '#F87171', glow: '0 0 20px rgba(239,68,68,0.3)', label: '❌ NO EDGE — DO NOT TRADE' },
    WEAK: { bg: 'rgba(245,158,11,0.15)', text: '#FBBF24', glow: '0 0 20px rgba(245,158,11,0.3)', label: '⚠️ WEAK EDGE — NEEDS MORE DATA' },
  }
  const c = config[status] || config.COLLECTING

  return (
    <div style={{
      background: c.bg,
      border: `1px solid ${c.text}30`,
      borderRadius: '16px',
      padding: '20px 32px',
      textAlign: 'center',
      boxShadow: c.glow,
      animation: status === 'VALIDATED' ? 'pulse 2s ease-in-out infinite' : 'none'
    }}>
      <div style={{ fontSize: '24px', fontWeight: 700, color: c.text, letterSpacing: '0.05em' }}>
        {c.label}
      </div>
    </div>
  )
}

// ─── Progress Ring ───
function ProgressRing({ value, max, label, sublabel, color = '#06B6D4' }: {
  value: number; max: number; label: string; sublabel?: string; color?: string
}) {
  const pct = Math.min(value / Math.max(max, 1) * 100, 100)
  const r = 52, c = 2 * Math.PI * r
  const offset = c * (1 - pct / 100)

  return (
    <div style={{ textAlign: 'center' }}>
      <svg width="130" height="130" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="8"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}
          transform="rotate(-90 60 60)"
          style={{ transition: 'stroke-dashoffset 1s ease-out', filter: `drop-shadow(0 0 6px ${color}50)` }}
        />
        <text x="60" y="55" textAnchor="middle" fill="white" fontSize="22" fontWeight="700">
          {pct >= 100 ? '✓' : `${Math.round(pct)}%`}
        </text>
        <text x="60" y="72" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="10">
          {value}/{max}
        </text>
      </svg>
      <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: '13px', fontWeight: 600, marginTop: '4px' }}>{label}</div>
      {sublabel && <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>{sublabel}</div>}
    </div>
  )
}

// ─── Metric Card ───
function MetricCard({ label, value, unit, color, subtext }: {
  label: string; value: string | number; unit?: string; color?: string; subtext?: string
}) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: '12px',
      padding: '16px 20px',
      flex: 1,
      minWidth: '140px'
    }}>
      <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div style={{ color: color || 'white', fontSize: '24px', fontWeight: 700, marginTop: '4px' }}>
        {value}{unit && <span style={{ fontSize: '14px', opacity: 0.6 }}>{unit}</span>}
      </div>
      {subtext && <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', marginTop: '2px' }}>{subtext}</div>}
    </div>
  )
}

// ─── Signal List ───
function SignalList({ signals }: { signals: SignalStatus['last_signals'] }) {
  if (!signals || signals.length === 0) {
    return (
      <div style={{ color: 'rgba(255,255,255,0.3)', textAlign: 'center', padding: '32px', fontSize: '14px' }}>
        Waiting for market conditions to trigger signals...
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {signals.map((s, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          background: 'rgba(255,255,255,0.02)', borderRadius: '10px', padding: '12px 16px',
          border: `1px solid ${s.direction === 'LONG' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`
        }}>
          <div style={{
            width: '36px', height: '36px', borderRadius: '10px',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px',
            background: s.direction === 'LONG' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'
          }}>
            {s.direction === 'LONG' ? '📈' : '📉'}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: 'white', fontSize: '13px', fontWeight: 600 }}>{s.name.replace(/_/g, ' ').toUpperCase()}</div>
            <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', marginTop: '2px' }}>{s.reason}</div>
          </div>
          <div style={{
            padding: '4px 12px', borderRadius: '8px', fontSize: '12px', fontWeight: 700,
            background: s.direction === 'LONG' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)',
            color: s.direction === 'LONG' ? '#4ADE80' : '#F87171'
          }}>
            {s.direction}
          </div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', fontWeight: 600 }}>
            {(s.confidence * 100).toFixed(0)}%
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Edge Breakdown ───
function EdgeBreakdown({ breakdown }: { breakdown: EdgeReport['signal_breakdown'] }) {
  if (!breakdown || Object.keys(breakdown).length === 0) {
    return <div style={{ color: 'rgba(255,255,255,0.3)', textAlign: 'center', padding: '20px' }}>No data yet</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {Object.entries(breakdown).map(([name, data]) => {
        const isPositive = data.total_pnl_pct > 0
        const barWidth = Math.min(data.win_rate, 100)

        return (
          <div key={name} style={{
            background: 'rgba(255,255,255,0.02)', borderRadius: '10px', padding: '14px 16px',
            border: '1px solid rgba(255,255,255,0.05)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ color: 'white', fontSize: '13px', fontWeight: 600 }}>
                {name.replace(/_/g, ' ').toUpperCase()}
              </span>
              <span style={{ color: isPositive ? '#4ADE80' : '#F87171', fontSize: '13px', fontWeight: 700 }}>
                {data.total_pnl_pct > 0 ? '+' : ''}{data.total_pnl_pct.toFixed(3)}%
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{
                  width: `${barWidth}%`, height: '100%', borderRadius: '3px',
                  background: data.win_rate >= 55 ? 'linear-gradient(90deg, #06B6D4, #22C55E)' :
                    data.win_rate >= 50 ? 'linear-gradient(90deg, #FBBF24, #F59E0B)' :
                      'linear-gradient(90deg, #EF4444, #DC2626)',
                  transition: 'width 0.8s ease-out'
                }} />
              </div>
              <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px', fontWeight: 600, minWidth: '60px' }}>
                WR {data.win_rate}%
              </span>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>
                {data.predictions} trades
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Mini Sparkline ───
function Sparkline({ data, color = '#06B6D4', height = 40 }: { data: number[]; color?: string; height?: number }) {
  if (!data || data.length < 2) return null
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const w = 200

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = height - ((v - min) / range) * (height - 4)
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={w} height={height} style={{ display: 'block' }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 3px ${color}50)` }} />
    </svg>
  )
}

// ═══════════ MAIN VIEW ═══════════
export default function EdgeMonitorView() {
  const { token } = useAuth()
  const [edgeReport, setEdgeReport] = useState<EdgeReport | null>(null)
  const [signalStatus, setSignalStatus] = useState<SignalStatus | null>(null)
  const [collectorStatus, setCollectorStatus] = useState<CollectorStatus | null>(null)
  const [marketData, setMarketData] = useState<MarketDataPoint[]>([])
  const [loading, setLoading] = useState(true)

  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

  const fetchAll = useCallback(async () => {
    try {
      const [edge, signal, collector, market] = await Promise.all([
        fetch(`${API_URL}/api/v2/edge-report`, { headers }).then(r => r.json()),
        fetch(`${API_URL}/api/v2/signal-status`, { headers }).then(r => r.json()),
        fetch(`${API_URL}/api/v2/collector-status`, { headers }).then(r => r.json()),
        fetch(`${API_URL}/api/v2/market-data?limit=30`, { headers }).then(r => r.json()),
      ])
      setEdgeReport(edge)
      setSignalStatus(signal)
      setCollectorStatus(collector)
      setMarketData(market.data || [])
    } catch (e) {
      console.error('Edge monitor fetch error:', e)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') fetchAll()
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchAll])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
        <div style={{ width: '48px', height: '48px', border: '4px solid rgba(6,182,212,0.2)', borderTopColor: '#06B6D4', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  const report = edgeReport || { status: 'COLLECTING', total_predictions: 0, evaluated: 0, pending: 0, target: 200, progress_pct: 0, message: 'Initializing...' }
  const prices = marketData.map(d => d.price).reverse()
  const fundingRates = marketData.filter(d => d.funding_rate !== null).map(d => (d.funding_rate || 0) * 100).reverse()

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ color: 'white', fontSize: '28px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '12px' }}>
          🎯 Edge Monitor
          <span style={{ fontSize: '13px', fontWeight: 500, color: 'rgba(255,255,255,0.4)', background: 'rgba(255,255,255,0.05)', padding: '4px 12px', borderRadius: '8px' }}>
            v2 Edge-First System
          </span>
        </h1>
        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '14px', margin: '6px 0 0' }}>
          Signals are LOGGED only — no live trading until edge is proven
        </p>
      </div>

      {/* Status Badge */}
      <StatusBadge status={report.status} />

      {/* Progress + Key Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '24px', marginTop: '24px' }}>
        {/* Left: Progress Rings */}
        <div style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '16px', padding: '24px', display: 'flex', gap: '24px', alignItems: 'center'
        }}>
          <ProgressRing value={report.evaluated} max={report.target} label="Predictions" sublabel={`${report.pending} pending`} color="#06B6D4" />
          <ProgressRing value={report.win_rate || 0} max={100} label="Win Rate" sublabel={`Target: ≥55%`} color={(report.win_rate || 0) >= 55 ? '#22C55E' : '#FBBF24'} />
          <ProgressRing value={Math.min((report.profit_factor || 0) * 50, 100)} max={100} label="Profit Factor" sublabel={`${(report.profit_factor || 0).toFixed(2)} / 1.30`} color={(report.profit_factor || 0) >= 1.3 ? '#22C55E' : '#FBBF24'} />
        </div>

        {/* Right: Metric Cards */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
          <MetricCard label="Expectancy" value={(report.expectancy_pct || 0).toFixed(4)} unit="%" color={(report.expectancy_pct || 0) > 0 ? '#4ADE80' : '#F87171'} subtext="per trade average" />
          <MetricCard label="Avg Win" value={(report.avg_win_pct || 0).toFixed(3)} unit="%" color="#4ADE80" />
          <MetricCard label="Avg Loss" value={(report.avg_loss_pct || 0).toFixed(3)} unit="%" color="#F87171" />
          <MetricCard label="Total PnL" value={(report.total_pnl_pct || 0).toFixed(3)} unit="%" color={(report.total_pnl_pct || 0) > 0 ? '#4ADE80' : '#F87171'} />
          <MetricCard label="Max Loss Streak" value={report.max_consecutive_losses || 0} color={(report.max_consecutive_losses || 0) <= 6 ? '#4ADE80' : '#F87171'} subtext={`Limit: ≤6`} />
          <MetricCard label="Data Collected" value={collectorStatus?.hours_of_data?.toFixed(1) || '0'} unit=" hrs" color="#06B6D4" subtext={`${collectorStatus?.ticks_collected || 0} ticks`} />
        </div>
      </div>

      {/* Signal Breakdown + Active Signals */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginTop: '24px' }}>
        {/* Edge Breakdown */}
        <div style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '16px', padding: '20px'
        }}>
          <h3 style={{ color: 'white', fontSize: '15px', fontWeight: 600, margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            📊 Edge Performance Breakdown
          </h3>
          <EdgeBreakdown breakdown={report.signal_breakdown} />
        </div>

        {/* Live Signals */}
        <div style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '16px', padding: '20px'
        }}>
          <h3 style={{ color: 'white', fontSize: '15px', fontWeight: 600, margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🎯 Last Signals
            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', fontWeight: 400 }}>OBSERVE ONLY</span>
          </h3>
          <SignalList signals={signalStatus?.last_signals || []} />
        </div>
      </div>

      {/* Market Data Sparklines */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginTop: '24px'
      }}>
        <div style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '12px', padding: '16px'
        }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 600, marginBottom: '8px' }}>ETH PRICE (30 ticks)</div>
          <Sparkline data={prices} color="#06B6D4" />
          {prices.length > 0 && <div style={{ color: 'white', fontSize: '18px', fontWeight: 700, marginTop: '4px' }}>${prices[prices.length - 1]?.toFixed(2)}</div>}
        </div>
        <div style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '12px', padding: '16px'
        }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 600, marginBottom: '8px' }}>FUNDING RATE</div>
          <Sparkline data={fundingRates} color={fundingRates.length > 0 && fundingRates[fundingRates.length - 1] > 0.05 ? '#F87171' : '#4ADE80'} />
          {fundingRates.length > 0 && <div style={{ color: 'white', fontSize: '18px', fontWeight: 700, marginTop: '4px' }}>{fundingRates[fundingRates.length - 1]?.toFixed(4)}%</div>}
        </div>
        <div style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '12px', padding: '16px'
        }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 600, marginBottom: '8px' }}>SYSTEM STATUS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px' }}>Collector</span>
              <span style={{ color: collectorStatus?.running ? '#4ADE80' : '#F87171', fontSize: '12px', fontWeight: 600 }}>
                {collectorStatus?.running ? '● RUNNING' : '○ STOPPED'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px' }}>Futures API</span>
              <span style={{ color: collectorStatus?.has_futures_api ? '#4ADE80' : '#FBBF24', fontSize: '12px', fontWeight: 600 }}>
                {collectorStatus?.has_futures_api ? '● CONNECTED' : '○ N/A'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px' }}>Errors</span>
              <span style={{ color: (collectorStatus?.errors || 0) > 5 ? '#F87171' : '#4ADE80', fontSize: '12px', fontWeight: 600 }}>
                {collectorStatus?.errors || 0}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px' }}>Signals Generated</span>
              <span style={{ color: 'white', fontSize: '12px', fontWeight: 600 }}>
                {signalStatus?.total_signals_generated || 0}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Validation Criteria Footer */}
      <div style={{
        marginTop: '24px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
        borderRadius: '12px', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
      }}>
        <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
          GO/NO-GO CRITERIA: ≥200 predictions • WR ≥55% • PF ≥1.30 • Max streak ≤6
        </span>
        <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px' }}>
          Auto-refreshes every 15s • {report.message}
        </span>
      </div>
    </div>
  )
}

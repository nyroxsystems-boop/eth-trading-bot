import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Activity, Target, Zap } from 'lucide-react'
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'
import { LiveTradingToggle } from '../components/LiveTradingToggle'
import '../styles/premium.css'
import '../styles/components.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface DashboardViewProps {
    trades: any[]
    metrics: any
    status: any
    candlestickData: any[]
    tickerData: any[]
    timeframe: string
    setTimeframe: (tf: string) => void
}

interface TradingModeStatus {
    mode: 'paper' | 'live'
    can_enable_live: boolean
    requires_upgrade: boolean
}

interface PnLDataPoint {
    date: string
    daily_pnl: number
    cumulative_pnl: number
    trades: number
}

const DashboardView = ({ metrics, status }: DashboardViewProps) => {
    const dailyPnl = metrics?.daily_pnl || 0
    const totalPnl = metrics?.total_pnl || 0
    const winRate = metrics?.win_rate || 0
    const totalTrades = metrics?.total_trades || 0
    const todayTrades = status?.today_trades || 0

    const [tradingMode, setTradingMode] = useState<TradingModeStatus>({
        mode: 'paper',
        can_enable_live: false,
        requires_upgrade: true
    })

    const [pnlHistory, setPnlHistory] = useState<PnLDataPoint[]>([])
    const [chartDays, setChartDays] = useState(7)

    useEffect(() => {
        fetchTradingModeStatus()
        fetchPnlHistory()
    }, [chartDays])

    const fetchTradingModeStatus = async () => {
        try {
            const token = localStorage.getItem('auth_token') || localStorage.getItem('token')
            if (!token) return

            const res = await fetch(`${API_URL}/api/trading/mode/status`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setTradingMode({
                    mode: data.mode,
                    can_enable_live: data.can_enable_live,
                    requires_upgrade: data.requires_upgrade
                })
            }
        } catch (err) {
            console.error('Failed to fetch trading mode:', err)
        }
    }

    const fetchPnlHistory = async () => {
        try {
            const res = await fetch(`${API_URL}/api/performance/history?days=${chartDays}`)
            if (res.ok) {
                const data = await res.json()
                setPnlHistory(data)
            }
        } catch (err) {
            console.error('Failed to fetch P&L history:', err)
        }
    }

    const handleToggle = async () => {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token')
        const res = await fetch(`${API_URL}/api/trading/mode/toggle`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        })
        if (res.ok) {
            await fetchTradingModeStatus()
        } else {
            const error = await res.json()
            throw new Error(error.detail || 'Failed to toggle')
        }
    }

    const handleUpgrade = () => {
        window.location.href = '/subscription'
    }

    return (
        <div className="dashboard-container">
            {/* Stats Grid */}
            <div className="stats-grid">
                {/* Daily P&L Card */}
                <motion.div
                    className="glass-card stat-card"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                >
                    <div className="stat-header">
                        <div className="stat-icon" style={{ background: dailyPnl >= 0 ? 'var(--gradient-primary)' : 'var(--gradient-gold)' }}>
                            {dailyPnl >= 0 ? <TrendingUp size={24} /> : <TrendingDown size={24} />}
                        </div>
                        <span className="stat-label">Daily P&L</span>
                    </div>
                    <div className="stat-value">
                        <span className={`stat-number ${dailyPnl >= 0 ? 'positive' : 'negative'}`}>
                            {dailyPnl >= 0 ? '+' : ''}${Math.abs(dailyPnl).toFixed(2)}
                        </span>
                        <span className="stat-percentage">
                            {dailyPnl >= 0 ? '+' : ''}{((dailyPnl / 10000) * 100).toFixed(2)}%
                        </span>
                    </div>
                    <div className="stat-footer">
                        <span className="stat-trend">
                            {dailyPnl >= 0 ? '📈' : '📉'} Today
                        </span>
                    </div>
                </motion.div>

                {/* Win Rate Card */}
                <motion.div
                    className="glass-card stat-card"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                >
                    <div className="stat-header">
                        <div className="stat-icon" style={{ background: 'var(--gradient-secondary)' }}>
                            <Target size={24} />
                        </div>
                        <span className="stat-label">Win Rate</span>
                    </div>
                    <div className="stat-value">
                        <div className="circular-progress">
                            <svg width="120" height="120">
                                <circle
                                    cx="60"
                                    cy="60"
                                    r="50"
                                    fill="none"
                                    stroke="rgba(139, 92, 246, 0.2)"
                                    strokeWidth="10"
                                />
                                <circle
                                    cx="60"
                                    cy="60"
                                    r="50"
                                    fill="none"
                                    stroke="url(#gradient)"
                                    strokeWidth="10"
                                    strokeDasharray={`${(winRate / 100) * 314} 314`}
                                    strokeLinecap="round"
                                    transform="rotate(-90 60 60)"
                                />
                                <defs>
                                    <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" stopColor="#8B5CF6" />
                                        <stop offset="100%" stopColor="#EC4899" />
                                    </linearGradient>
                                </defs>
                            </svg>
                            <div className="progress-text">
                                <span className="progress-value">{winRate.toFixed(1)}%</span>
                            </div>
                        </div>
                    </div>
                    <div className="stat-footer">
                        <span className="stat-trend">
                            {metrics?.winning_trades || 0}W / {metrics?.losing_trades || 0}L
                        </span>
                    </div>
                </motion.div>

                {/* Total Trades Card */}
                <motion.div
                    className="glass-card stat-card"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                >
                    <div className="stat-header">
                        <div className="stat-icon" style={{ background: 'var(--gradient-gold)' }}>
                            <Activity size={24} />
                        </div>
                        <span className="stat-label">Total Trades</span>
                    </div>
                    <div className="stat-value">
                        <span className="stat-number">{totalTrades}</span>
                        <span className="stat-subtext">All time</span>
                    </div>
                    <div className="stat-footer">
                        <span className="stat-trend">
                            ⚡ {todayTrades} today
                        </span>
                    </div>
                </motion.div>

                {/* Bot Status Card */}
                <motion.div
                    className="glass-card stat-card"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 }}
                >
                    <div className="stat-header">
                        <div className="stat-icon" style={{ background: tradingMode.mode === 'live' ? 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)' : 'linear-gradient(135deg, #10B981 0%, #059669 100%)' }}>
                            <Zap size={24} />
                        </div>
                        <span className="stat-label">Bot Status</span>
                    </div>
                    <div className="stat-value">
                        <div className="status-indicator">
                            <div className={`status-dot ${tradingMode.mode === 'live' ? 'live' : 'active'}`} />
                            <span className="status-text">Running</span>
                        </div>
                        <span className="stat-subtext">
                            {tradingMode.mode === 'live' ? '💰 Live Trading' : '📄 Paper Trading'}
                        </span>
                    </div>
                    <div className="stat-footer">
                        <span className="stat-trend">
                            🎯 Target: 1.0% daily
                        </span>
                    </div>
                </motion.div>
            </div>

            {/* Live Trading Toggle */}
            <motion.div
                className="glass-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.45 }}
                style={{ marginTop: '24px', marginBottom: '24px' }}
            >
                <LiveTradingToggle
                    currentMode={tradingMode.mode}
                    canEnableLive={tradingMode.can_enable_live}
                    requiresUpgrade={tradingMode.requires_upgrade}
                    onToggle={handleToggle}
                    onUpgrade={handleUpgrade}
                />
            </motion.div>

            {/* Performance Chart */}
            <motion.div
                className="glass-card chart-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
            >
                <div className="chart-header">
                    <h3>Performance Overview</h3>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <div className="chart-stats">
                            <div className="chart-stat">
                                <span className="chart-stat-label">Total P&L</span>
                                <span className={`chart-stat-value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
                                    ${totalPnl.toFixed(2)}
                                </span>
                            </div>
                            <div className="chart-stat">
                                <span className="chart-stat-label">ROI</span>
                                <span className="chart-stat-value positive">
                                    {((totalPnl / 10000) * 100).toFixed(2)}%
                                </span>
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '4px' }}>
                            {[7, 14, 30].map(d => (
                                <button
                                    key={d}
                                    onClick={() => setChartDays(d)}
                                    style={{
                                        padding: '4px 12px',
                                        borderRadius: '8px',
                                        border: 'none',
                                        background: chartDays === d ? 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)' : 'rgba(139, 92, 246, 0.2)',
                                        color: 'white',
                                        fontSize: '12px',
                                        cursor: 'pointer',
                                        fontWeight: chartDays === d ? 600 : 400
                                    }}
                                >
                                    {d}D
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
                <div style={{ height: '300px', marginTop: '16px' }}>
                    {pnlHistory.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={pnlHistory} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.8} />
                                        <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(139, 92, 246, 0.1)" />
                                <XAxis
                                    dataKey="date"
                                    stroke="#64748B"
                                    fontSize={12}
                                    tickFormatter={(val) => val.slice(5)}
                                />
                                <YAxis
                                    stroke="#64748B"
                                    fontSize={12}
                                    tickFormatter={(val) => `$${val}`}
                                />
                                <Tooltip
                                    contentStyle={{
                                        background: 'rgba(15, 23, 42, 0.95)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '8px',
                                        color: '#fff'
                                    }}
                                    formatter={(value: number, name: string) => [
                                        `$${value.toFixed(2)}`,
                                        name === 'cumulative_pnl' ? 'Total P&L' : 'Daily P&L'
                                    ]}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="cumulative_pnl"
                                    stroke="#8B5CF6"
                                    strokeWidth={2}
                                    fillOpacity={1}
                                    fill="url(#colorPnl)"
                                />
                                <Line
                                    type="monotone"
                                    dataKey="daily_pnl"
                                    stroke="#10B981"
                                    strokeWidth={2}
                                    dot={{ fill: '#10B981', strokeWidth: 2 }}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="chart-placeholder">
                            <div className="chart-message">
                                <Activity size={48} opacity={0.3} />
                                <p>No trading data yet</p>
                                <span>Start trading to see your P&L chart</span>
                            </div>
                        </div>
                    )}
                </div>
            </motion.div>

        </div>
    )
}

export default DashboardView


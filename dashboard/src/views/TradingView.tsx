import { motion } from 'framer-motion'
import { Bot, Play, Pause, Brain, Target, BookOpen, Activity } from 'lucide-react'
import { useState, useEffect } from 'react'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TradingView = () => {
    const [botRunning, setBotRunning] = useState(false)
    const [loading, setLoading] = useState(false)
    const [status, setStatus] = useState<any>(null)
    const [trades, setTrades] = useState<any[]>([])
    const [capital, setCapital] = useState<number>(0)


    useEffect(() => {
        fetchAll()
        const interval = setInterval(fetchAll, 30000)
        return () => clearInterval(interval)
    }, [])

    const fetchAll = async () => {
        try {
            const token = localStorage.getItem('auth_token') || localStorage.getItem('token')
            const headers: any = token ? { 'Authorization': `Bearer ${token}` } : {}

            const [statusRes, tradesRes, capitalRes] = await Promise.allSettled([
                fetch(`${API_URL}/api/status`, { headers }),
                fetch(`${API_URL}/api/bot/journal`, { headers }),
                fetch(`${API_URL}/api/capital`, { headers })
            ])

            if (statusRes.status === 'fulfilled' && statusRes.value.ok) {
                const data = await statusRes.value.json()
                setBotRunning(data.is_running || false)
                setStatus(data)
            }
            if (tradesRes.status === 'fulfilled' && tradesRes.value.ok) {
                const data = await tradesRes.value.json()
                const allTrades = Array.isArray(data) ? data : []
                const todayStr = new Date().toISOString().slice(0, 10)
                setTrades(allTrades.filter((t: any) => t.timestamp?.slice(0, 10) === todayStr))
            }
            if (capitalRes.status === 'fulfilled' && capitalRes.value.ok) {
                const data = await capitalRes.value.json()
                setCapital(data.capital || 0)
            }
        } catch (e) {
            console.warn('Fetch error:', e)
        }

    }

    const handleToggleBot = async () => {
        setLoading(true)
        try {
            const token = localStorage.getItem('auth_token') || localStorage.getItem('token')
            const action = botRunning ? 'stop' : 'start'
            const res = await fetch(`${API_URL}/api/bot/${action}`, {
                method: 'POST',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            })
            const data = await res.json()
            setBotRunning(data.is_running ?? !botRunning)
        } catch (e) {
            console.error('Toggle bot error:', e)
        } finally {
            setLoading(false)
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '24px' }}
        >
            {/* Bot Status Header */}
            <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
                    <div>
                        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                            <Bot size={24} /> ETH Trading Bot
                        </h1>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <div style={{
                                    width: '10px', height: '10px', borderRadius: '50%',
                                    background: botRunning ? '#22c55e' : '#ef4444',
                                    animation: botRunning ? 'pulse 2s infinite' : 'none',
                                    boxShadow: botRunning ? '0 0 8px rgba(34,197,94,0.5)' : 'none'
                                }} />
                                <span style={{ fontSize: '14px', fontWeight: 600, color: botRunning ? '#22c55e' : '#ef4444' }}>
                                    {botRunning ? 'Running' : 'Stopped'}
                                </span>
                            </div>
                            <span style={{ color: '#475569' }}>|</span>
                            <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
                                Capital: <span style={{ color: '#06b6d4', fontWeight: 600 }}>{capital.toLocaleString()} USDT</span>
                            </span>
                            {status?.today_trades !== undefined && (
                                <>
                                    <span style={{ color: '#475569' }}>|</span>
                                    <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
                                        Today: <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{status.today_trades} trades</span>
                                    </span>
                                </>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={handleToggleBot}
                        disabled={loading}
                        style={{
                            padding: '12px 24px', borderRadius: '12px', fontWeight: 600,
                            display: 'flex', alignItems: 'center', gap: '8px',
                            cursor: loading ? 'wait' : 'pointer', fontSize: '14px',
                            border: `1px solid ${botRunning ? 'rgba(239,68,68,0.3)' : 'rgba(34,197,94,0.3)'}`,
                            background: botRunning ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                            color: botRunning ? '#ef4444' : '#22c55e',
                            opacity: loading ? 0.5 : 1,
                            transition: 'all 0.2s'
                        }}
                    >
                        {loading ? 'Processing...' : botRunning ? <><Pause size={18} /> Stop Bot</> : <><Play size={18} /> Start Bot</>}
                    </button>
                </div>
            </div>

            {/* Today's Trades */}
            <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                    <BookOpen size={20} style={{ color: '#06b6d4' }} />
                    <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>Today's Trades</h2>
                    <span style={{ marginLeft: 'auto', fontSize: '13px', color: 'var(--text-muted)' }}>{trades.length} trades</span>
                </div>

                {trades.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <p style={{ color: 'var(--text-muted)', fontSize: '16px', marginBottom: '4px' }}>No trades yet today</p>
                        <p style={{ color: '#64748b', fontSize: '13px' }}>Paper and live trades will appear here as the bot executes them</p>
                    </div>
                ) : (
                    <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.2)' }}>
                                    <th style={{ textAlign: 'left', padding: '8px 12px', color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>TIME</th>
                                    <th style={{ textAlign: 'left', padding: '8px 12px', color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>ACTION</th>
                                    <th style={{ textAlign: 'right', padding: '8px 12px', color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>QTY</th>
                                    <th style={{ textAlign: 'right', padding: '8px 12px', color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>PRICE</th>
                                    <th style={{ textAlign: 'right', padding: '8px 12px', color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>P&L</th>
                                    <th style={{ textAlign: 'center', padding: '8px 12px', color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>MODE</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trades.slice().reverse().map((trade: any, i: number) => (
                                    <tr key={i} style={{ borderBottom: '1px solid rgba(148,163,184,0.1)' }}>
                                        <td style={{ padding: '10px 12px', color: '#e2e8f0', fontSize: '13px' }}>
                                            {trade.timestamp ? new Date(trade.timestamp).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                                        </td>
                                        <td style={{ padding: '10px 12px' }}>
                                            <span style={{
                                                padding: '2px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 600,
                                                background: trade.action === 'BUY' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                                                color: trade.action === 'BUY' ? '#22c55e' : '#ef4444'
                                            }}>
                                                {trade.action}
                                            </span>
                                        </td>
                                        <td style={{ padding: '10px 12px', color: '#e2e8f0', fontSize: '13px', textAlign: 'right' }}>
                                            {parseFloat(trade.qty || 0).toFixed(5)}
                                        </td>
                                        <td style={{ padding: '10px 12px', color: '#e2e8f0', fontSize: '13px', textAlign: 'right' }}>
                                            ${parseFloat(trade.price || 0).toFixed(2)}
                                        </td>
                                        <td style={{
                                            padding: '10px 12px', fontSize: '13px', textAlign: 'right', fontWeight: 600,
                                            color: (trade.pnl || 0) >= 0 ? '#22c55e' : '#ef4444'
                                        }}>
                                            {trade.pnl ? `${parseFloat(trade.pnl) >= 0 ? '+' : '-'}$${Math.abs(parseFloat(trade.pnl)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '-'}
                                        </td>
                                        <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '2px 6px', borderRadius: '4px', fontSize: '11px',
                                                background: trade.mode === 'live' ? 'rgba(234,179,8,0.15)' : 'rgba(148,163,184,0.1)',
                                                color: trade.mode === 'live' ? '#eab308' : '#94a3b8'
                                            }}>
                                                {trade.mode || 'paper'}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* ML & Target Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
                {/* Auto-Learning Card */}
                <div className="glass-card" style={{
                    padding: '24px',
                    background: 'linear-gradient(135deg, rgba(139,92,246,0.08), rgba(6,182,212,0.08))',
                    border: '1px solid rgba(139,92,246,0.2)'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                        <Brain size={20} style={{ color: '#a78bfa' }} />
                        <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>Auto-Learning</h2>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#22c55e', animation: 'pulse 2s infinite' }} />
                        <span style={{ color: '#22c55e', fontSize: '14px' }}>Bot optimizes strategy automatically</span>
                    </div>
                    <p style={{ color: 'var(--text-muted)', fontSize: '13px', lineHeight: '1.6', marginBottom: '16px' }}>
                        GradientBoosting ML model with 11 features, trained on 2000+ bars. Auto-applies best strategies via continuous backtesting.
                    </p>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                        <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(30,41,59,0.5)' }}>
                            <div style={{ fontSize: '11px', color: '#94a3b8' }}>ML Confidence</div>
                            <div style={{ fontSize: '16px', fontWeight: 700, color: '#22c55e' }}>
                                {status?.ml_confidence ? `${(status.ml_confidence * 100).toFixed(0)}%` : '—'}
                            </div>
                        </div>
                        <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(30,41,59,0.5)' }}>
                            <div style={{ fontSize: '11px', color: '#94a3b8' }}>Regime</div>
                            <div style={{ fontSize: '16px', fontWeight: 700, color: '#e2e8f0' }}>
                                {status?.regime || '—'}
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'learning' } }))}
                        style={{
                            display: 'block', width: '100%', marginTop: '16px', padding: '10px',
                            borderRadius: '8px', border: '1px solid rgba(139,92,246,0.3)',
                            background: 'rgba(139,92,246,0.1)', color: '#a78bfa',
                            fontWeight: 600, cursor: 'pointer', fontSize: '13px', textAlign: 'center'
                        }}
                    >
                        View Learning Progress →
                    </button>
                </div>

                {/* Daily Target + Quick Stats */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div className="glass-card" style={{
                        padding: '24px',
                        background: 'linear-gradient(135deg, rgba(6,182,212,0.08), rgba(59,130,246,0.08))',
                        border: '1px solid rgba(6,182,212,0.2)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                            <Target size={20} style={{ color: '#06b6d4' }} />
                            <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>Daily Target</h2>
                        </div>
                        <div style={{ fontSize: '42px', fontWeight: 700, color: '#06b6d4', marginBottom: '4px' }}>1.0%</div>
                        <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Optimized for consistent gains</div>
                    </div>

                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                            <Activity size={20} style={{ color: '#10b981' }} />
                            <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>Bot Config</h2>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Pair</span>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>ETHUSDT</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Mode</span>
                                <span style={{ color: '#f59e0b', fontWeight: 600, fontSize: '13px' }}>
                                    {status?.paper_mode ? '📋 Paper' : '💰 Live'}
                                </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Scoring</span>
                                <span style={{ color: '#f59e0b', fontWeight: 600, fontSize: '13px' }}>v8 WR-Boost</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Position</span>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>
                                    {status?.in_position ? '📈 Long' : '💤 None'}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </motion.div>
    )
}

export default TradingView

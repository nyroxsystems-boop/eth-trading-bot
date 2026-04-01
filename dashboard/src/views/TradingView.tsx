import { motion } from 'framer-motion'
import { Bot, Activity, Zap, TrendingUp } from 'lucide-react'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
import { useState, useEffect } from 'react'

const TradingView = () => {
    const [botStatus, setBotStatus] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 30000)
        return () => clearInterval(interval)
    }, [])

    const fetchStatus = async () => {
        try {
            const token = localStorage.getItem('auth_token') || localStorage.getItem('token')
            const res = await fetch(`${API_URL}/api/status`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            })
            if (res.ok) setBotStatus(await res.json())
        } catch (e) { console.warn('Status fetch failed:', e) }
        setLoading(false)
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '24px' }}
        >
            <div style={{ marginBottom: '24px' }}>
                <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <Bot size={28} /> Trading
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '4px' }}>
                    Bot status and trading overview
                </p>
            </div>

            {loading ? (
                <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>Loading...</div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
                    {/* Bot Status */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                            <Activity size={20} style={{ color: '#10b981' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '16px' }}>Bot Status</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Mode</span>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>
                                    {botStatus?.mode || botStatus?.paper_mode ? '📋 Paper' : '💰 Live'}
                                </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Status</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>
                                    {botStatus?.status || 'Running'}
                                </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Pair</span>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>
                                    {botStatus?.symbol || 'ETHUSDT'}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Quick Stats */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                            <TrendingUp size={20} style={{ color: '#06b6d4' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '16px' }}>Quick Stats</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Total Trades</span>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>
                                    {botStatus?.total_trades ?? '—'}
                                </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Win Rate</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>
                                    {botStatus?.win_rate ? `${botStatus.win_rate}%` : '—'}
                                </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Current Position</span>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>
                                    {botStatus?.in_position ? '📈 Long' : '💤 None'}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Strategy */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                            <Zap size={20} style={{ color: '#f59e0b' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '16px' }}>Active Strategy</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Scoring</span>
                                <span style={{ color: '#f59e0b', fontWeight: 600, fontSize: '13px' }}>v8 WR-Boost</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Auto-Apply</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>✅ Active</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Learning</span>
                                <span style={{ color: '#8b5cf6', fontWeight: 600, fontSize: '13px' }}>🧠 Continuous</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Strategy Lab Link */}
            <div className="glass-card" style={{ padding: '20px', marginTop: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>🧪 Strategy Lab</div>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Test and optimize trading strategies with real Binance data</div>
                </div>
                <button
                    onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'strategy-lab' } }))}
                    style={{
                        padding: '10px 20px', borderRadius: '8px', border: 'none',
                        background: 'linear-gradient(135deg, #8b5cf6, #06b6d4)',
                        color: 'white', fontWeight: 600, cursor: 'pointer', fontSize: '13px'
                    }}
                >
                    Open Lab →
                </button>
            </div>
        </motion.div>
    )
}

export default TradingView

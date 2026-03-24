import { motion } from 'framer-motion'
import { useState, useEffect } from 'react'
import { Wallet, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Activity, DollarSign, BarChart3, Clock } from 'lucide-react'
import '../styles/premium.css'

const API = import.meta.env.VITE_API_URL || ''

interface TradeEntry {
    timestamp: string
    action: string
    qty: number
    price: number
    pnl: number | null
    mode: string
}

export default function PortfolioView() {
    const [capital, setCapital] = useState(0)
    const [mode, setMode] = useState('paper')
    const [status, setStatus] = useState<any>(null)
    const [trades, setTrades] = useState<TradeEntry[]>([])
    const [ethPrice, setEthPrice] = useState(0)

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 15000)
        return () => clearInterval(interval)
    }, [])

    const fetchData = async () => {
        try {
            const [capitalRes, statusRes, tradesRes] = await Promise.all([
                fetch(`${API}/api/capital`),
                fetch(`${API}/api/status`),
                fetch(`${API}/api/bot/journal`)
            ])
            const capitalData = await capitalRes.json()
            const statusData = await statusRes.json()
            const tradesData = await tradesRes.json()

            setCapital(capitalData.capital || 0)
            setMode(capitalData.mode || 'paper')
            setStatus(statusData)
            setEthPrice(statusData?.current_price || 0)

            // Filter today's trades
            const allTrades = Array.isArray(tradesData) ? tradesData : []
            const todayStr = new Date().toISOString().slice(0, 10)
            setTrades(allTrades.filter((t: any) => t.timestamp?.slice(0, 10) === todayStr))
        } catch (e) {
            console.error('Portfolio fetch error:', e)
        }
    }

    // Calculate today's P&L — only from SELL trades (BUYs have pnl=0 which skews stats)
    const sellTrades = trades.filter(t => t.action === 'SELL' && (t.pnl || 0) !== 0)
    const todayPnl = sellTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const todayPnlPct = capital > 0 ? (todayPnl / capital) * 100 : 0
    const wins = sellTrades.filter(t => (t.pnl || 0) > 0).length
    const losses = sellTrades.filter(t => (t.pnl || 0) < 0).length
    const winRate = sellTrades.length > 0 ? (wins / sellTrades.length * 100) : 0

    // ETH equivalent
    const ethEquivalent = ethPrice > 0 ? capital / ethPrice : 0

    return (
        <div style={{ padding: '32px', maxWidth: '1000px', margin: '0 auto' }}>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {/* Wallet Header */}
            <div style={{ marginBottom: '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                    <div style={{
                        width: '48px', height: '48px', borderRadius: '14px',
                        background: 'linear-gradient(135deg, #06b6d4, #8b5cf6)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 8px 32px rgba(6,182,212,0.3)'
                    }}>
                        <Wallet size={24} color="white" />
                    </div>
                    <div>
                        <h1 style={{
                            fontSize: '28px', fontWeight: 700,
                            color: 'var(--text-primary, #f1f5f9)'
                        }}>
                            My Wallet
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '13px' }}>
                            Trading Capital Overview
                        </p>
                    </div>
                    {/* Mode Badge */}
                    <div style={{
                        marginLeft: 'auto',
                        padding: '6px 14px',
                        borderRadius: '20px',
                        fontSize: '13px',
                        fontWeight: 600,
                        letterSpacing: '0.5px',
                        background: mode === 'live' ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)',
                        color: mode === 'live' ? '#22c55e' : '#eab308',
                        border: `1px solid ${mode === 'live' ? 'rgba(34,197,94,0.3)' : 'rgba(234,179,8,0.3)'}`
                    }}>
                        {mode === 'live' ? '🟢 LIVE' : '📝 PAPER'}
                    </div>
                </div>
            </div>

            {/* Main Balance Card */}
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                style={{
                    background: 'linear-gradient(135deg, rgba(6,182,212,0.12) 0%, rgba(139,92,246,0.12) 50%, rgba(236,72,153,0.08) 100%)',
                    border: '1px solid rgba(6,182,212,0.25)',
                    borderRadius: '24px',
                    padding: '36px',
                    marginBottom: '24px',
                    position: 'relative',
                    overflow: 'hidden'
                }}
            >
                {/* Background glow */}
                <div style={{
                    position: 'absolute', top: '-50%', right: '-20%',
                    width: '300px', height: '300px',
                    background: 'radial-gradient(circle, rgba(6,182,212,0.15) 0%, transparent 70%)',
                    pointerEvents: 'none'
                }} />

                <div style={{ position: 'relative', zIndex: 1 }}>
                    <p style={{ color: '#94a3b8', fontSize: '14px', fontWeight: 500, marginBottom: '8px', letterSpacing: '0.5px' }}>
                        TOTAL BALANCE
                    </p>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
                        <span style={{
                            fontSize: '48px', fontWeight: 800,
                            color: '#f1f5f9',
                            letterSpacing: '-2px'
                        }}>
                            ${capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                        <span style={{ color: '#94a3b8', fontSize: '18px', fontWeight: 500 }}>USDT</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ color: '#94a3b8', fontSize: '15px' }}>
                            ≈ {ethEquivalent.toFixed(4)} ETH
                        </span>
                        {ethPrice > 0 && (
                            <span style={{ color: '#64748b', fontSize: '13px' }}>
                                @ ${ethPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                            </span>
                        )}
                    </div>
                </div>
            </motion.div>

            {/* Stats Grid */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '16px',
                marginBottom: '24px'
            }}>
                {/* Today's P&L */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                    style={{
                        background: 'rgba(15,23,42,0.6)',
                        border: '1px solid rgba(148,163,184,0.1)',
                        borderRadius: '16px',
                        padding: '20px'
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        {todayPnl >= 0
                            ? <ArrowUpRight size={18} color="#22c55e" />
                            : <ArrowDownRight size={18} color="#ef4444" />
                        }
                        <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600, letterSpacing: '0.5px' }}>TODAY P&L</span>
                    </div>
                    <div style={{
                        fontSize: '24px', fontWeight: 700,
                        color: todayPnl >= 0 ? '#22c55e' : '#ef4444'
                    }}>
                        {todayPnl >= 0 ? '+' : ''}{todayPnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div style={{
                        fontSize: '13px', fontWeight: 600,
                        color: todayPnlPct >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)'
                    }}>
                        {todayPnlPct >= 0 ? '+' : ''}{todayPnlPct.toFixed(2)}%
                    </div>
                </motion.div>

                {/* Today's Trades */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15 }}
                    style={{
                        background: 'rgba(15,23,42,0.6)',
                        border: '1px solid rgba(148,163,184,0.1)',
                        borderRadius: '16px',
                        padding: '20px'
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <Activity size={18} color="#06b6d4" />
                        <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600, letterSpacing: '0.5px' }}>TODAY TRADES</span>
                    </div>
                    <div style={{ fontSize: '24px', fontWeight: 700, color: '#f1f5f9' }}>
                        {trades.length}
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>
                        {wins}W / {losses}L
                    </div>
                </motion.div>

                {/* Win Rate */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                    style={{
                        background: 'rgba(15,23,42,0.6)',
                        border: '1px solid rgba(148,163,184,0.1)',
                        borderRadius: '16px',
                        padding: '20px'
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <BarChart3 size={18} color="#8b5cf6" />
                        <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600, letterSpacing: '0.5px' }}>WIN RATE</span>
                    </div>
                    <div style={{
                        fontSize: '24px', fontWeight: 700,
                        color: winRate >= 60 ? '#22c55e' : winRate >= 40 ? '#eab308' : '#ef4444'
                    }}>
                        {winRate.toFixed(0)}%
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>
                        Today
                    </div>
                </motion.div>

                {/* ETH Price */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 }}
                    style={{
                        background: 'rgba(15,23,42,0.6)',
                        border: '1px solid rgba(148,163,184,0.1)',
                        borderRadius: '16px',
                        padding: '20px'
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <DollarSign size={18} color="#eab308" />
                        <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600, letterSpacing: '0.5px' }}>ETH PRICE</span>
                    </div>
                    <div style={{ fontSize: '24px', fontWeight: 700, color: '#f1f5f9' }}>
                        ${ethPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>
                        Live
                    </div>
                </motion.div>
            </div>

            {/* Today's Activity */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                style={{
                    background: 'rgba(15,23,42,0.6)',
                    border: '1px solid rgba(148,163,184,0.1)',
                    borderRadius: '20px',
                    padding: '24px'
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                    <Clock size={18} color="#06b6d4" />
                    <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#f1f5f9' }}>
                        Today's Activity
                    </h2>
                    <span style={{
                        marginLeft: 'auto', fontSize: '13px', color: '#64748b',
                        background: 'rgba(148,163,184,0.1)', padding: '4px 10px', borderRadius: '8px'
                    }}>
                        {new Date().toLocaleDateString('de-DE')}
                    </span>
                </div>

                {trades.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <Activity size={40} color="#334155" style={{ margin: '0 auto 12px' }} />
                        <p style={{ color: '#64748b', fontSize: '15px' }}>No trades today</p>
                        <p style={{ color: '#475569', fontSize: '13px' }}>The bot is analyzing the market...</p>
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {trades.slice().reverse().map((trade, i) => (
                            <div key={i} style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                padding: '14px 16px',
                                background: 'rgba(30,41,59,0.5)',
                                borderRadius: '12px',
                                border: '1px solid rgba(148,163,184,0.06)',
                                transition: 'all 0.2s',
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                    <div style={{
                                        width: '36px', height: '36px', borderRadius: '10px',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        background: trade.action === 'BUY'
                                            ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'
                                    }}>
                                        {trade.action === 'BUY'
                                            ? <TrendingUp size={18} color="#22c55e" />
                                            : <TrendingDown size={18} color="#ef4444" />
                                        }
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#f1f5f9' }}>
                                            {trade.action} ETH
                                        </div>
                                        <div style={{ fontSize: '12px', color: '#64748b' }}>
                                            {trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : '-'}
                                            {' · '}
                                            {parseFloat(String(trade.qty || 0)).toFixed(5)} ETH @ ${parseFloat(String(trade.price || 0)).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                        </div>
                                    </div>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                    {trade.pnl !== null && trade.pnl !== undefined ? (
                                        <>
                                            <div style={{
                                                fontSize: '15px', fontWeight: 700,
                                                color: trade.pnl >= 0 ? '#22c55e' : '#ef4444'
                                            }}>
                                                {trade.pnl >= 0 ? '+' : ''}{parseFloat(String(trade.pnl)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            </div>
                                            <div style={{ fontSize: '11px', color: '#64748b' }}>USDT</div>
                                        </>
                                    ) : (
                                        <div style={{ fontSize: '13px', color: '#475569' }}>pending</div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </motion.div>

            {/* Bot Status Footer */}
            {status && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4 }}
                    style={{
                        marginTop: '16px',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px',
                        padding: '12px',
                        color: '#64748b', fontSize: '13px'
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <div style={{
                            width: '8px', height: '8px', borderRadius: '50%',
                            background: status.is_running ? '#22c55e' : '#ef4444',
                            boxShadow: status.is_running ? '0 0 8px rgba(34,197,94,0.5)' : 'none',
                            animation: status.is_running ? 'pulse 2s infinite' : 'none'
                        }} />
                        Bot {status.is_running ? 'Active' : 'Stopped'}
                    </div>
                    <span>·</span>
                    <span>Mode: {mode === 'live' ? 'Live' : 'Paper'}</span>
                    <span>·</span>
                    <span>Strategy: Auto-Optimized</span>
                </motion.div>
            )}
        </motion.div>
        </div>
    )
}

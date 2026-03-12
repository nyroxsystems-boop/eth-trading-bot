import { motion } from 'framer-motion'
import { Play, Pause, Brain, Target, BookOpen } from 'lucide-react'
import { useState, useEffect } from 'react'

const API = import.meta.env.VITE_API_URL || ''

export default function BotsView() {
    const [botRunning, setBotRunning] = useState(false)
    const [loading, setLoading] = useState(false)
    const [status, setStatus] = useState<any>(null)
    const [trades, setTrades] = useState<any[]>([])
    const [capital, setCapital] = useState<number>(0)

    // Fetch bot status
    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const [statusRes, tradesRes, capitalRes] = await Promise.all([
                    fetch(`${API}/api/status`),
                    fetch(`${API}/api/bot/journal`),
                    fetch(`${API}/api/capital`)
                ])
                const statusData = await statusRes.json()
                const tradesData = await tradesRes.json()
                const capitalData = await capitalRes.json()

                setBotRunning(statusData.is_running || false)
                setStatus(statusData)
                // Filter to today's trades only
                const allTrades = Array.isArray(tradesData) ? tradesData : []
                const todayStr = new Date().toISOString().slice(0, 10)
                const todayTrades = allTrades.filter((t: any) => {
                    if (!t.timestamp) return false
                    return t.timestamp.slice(0, 10) === todayStr
                })
                setTrades(todayTrades)
                setCapital(capitalData.capital || 0)
            } catch (e) {
                console.error('Status fetch error:', e)
            }
        }
        fetchStatus()
        const interval = setInterval(fetchStatus, 15000)
        return () => clearInterval(interval)
    }, [])

    const handleToggleBot = async () => {
        setLoading(true)
        try {
            const action = botRunning ? 'stop' : 'start'
            const res = await fetch(`${API}/api/bot/${action}`, { method: 'POST' })
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
            exit={{ opacity: 0, y: -20 }}
            className="flex-1 p-8"
        >
            <div className="mb-6">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                    Bot Configuration
                </h1>
                <p className="text-slate-400 mt-2">Manage your trading bot and strategies</p>
            </div>

            {/* Bot Status + Capital */}
            <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6 mb-8"
            >
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold mb-2">ETH Trading Bot</h2>
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-2">
                                <div className={`w-3 h-3 rounded-full ${botRunning ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
                                <span className={`text-sm font-medium ${botRunning ? 'text-green-400' : 'text-red-400'}`}>
                                    {botRunning ? 'Running' : 'Stopped'}
                                </span>
                            </div>
                            <span className="text-slate-500">|</span>
                            <span className="text-sm text-slate-400">
                                Capital: <span className="text-cyan-400 font-semibold">{capital.toLocaleString()} USDT</span>
                            </span>
                            {status?.today_trades !== undefined && (
                                <>
                                    <span className="text-slate-500">|</span>
                                    <span className="text-sm text-slate-400">
                                        Today: <span className="text-white font-semibold">{status.today_trades} trades</span>
                                    </span>
                                </>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={handleToggleBot}
                        disabled={loading}
                        className={`px-6 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all duration-300 ${botRunning
                            ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
                            : 'bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30'
                            } ${loading ? 'opacity-50 cursor-wait' : ''}`}
                    >
                        {loading ? 'Processing...' : botRunning ? <><Pause className="w-5 h-5" /> Stop Bot</> : <><Play className="w-5 h-5" /> Start Bot</>}
                    </button>
                </div>
            </motion.div>

            {/* Trade Journal */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6 mb-8"
            >
                <div className="flex items-center gap-2 mb-4">
                    <BookOpen className="w-5 h-5 text-cyan-400" />
                    <h2 className="text-xl font-semibold">Today's Trades</h2>
                    <span className="text-sm text-slate-400 ml-auto">{trades.length} trades</span>
                </div>

                {trades.length === 0 ? (
                    <div className="text-center py-8">
                        <p className="text-slate-400 text-lg mb-2">No trades yet</p>
                        <p className="text-slate-500 text-sm">Paper and live trades will appear here as the bot makes them</p>
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
            </motion.div>

            {/* ML & Sentiment Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Auto-Learning Info Card */}
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 }}
                    className="bg-gradient-to-br from-purple-500/10 to-cyan-500/10 backdrop-blur-xl border border-purple-500/30 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Brain className="w-5 h-5 text-purple-400" />
                        <h2 className="text-xl font-semibold">Auto-Learning Active</h2>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center gap-3 text-emerald-400">
                            <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
                            <span>Bot optimizes strategy automatically</span>
                        </div>
                        <p className="text-slate-400 text-sm">
                            The bot uses reinforcement learning (DQN) to continuously improve trading decisions.
                            No manual tuning required!
                        </p>
                        <div className="grid grid-cols-2 gap-3 mt-4">
                            <div className="bg-slate-800/50 rounded-lg p-3">
                                <span className="text-slate-400 text-xs">Learning Rate</span>
                                <p className="text-white font-semibold">Adaptive</p>
                            </div>
                            <div className="bg-slate-800/50 rounded-lg p-3">
                                <span className="text-slate-400 text-xs">Status</span>
                                <p className="text-emerald-400 font-semibold">Active</p>
                            </div>
                        </div>
                        <button
                            onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'learning' } }))}
                            className="block w-full mt-4 text-center bg-purple-500/20 text-purple-400 border border-purple-500/30 py-2 rounded-lg hover:bg-purple-500/30 transition-colors cursor-pointer"
                        >
                            View Learning Progress →
                        </button>
                    </div>
                </motion.div>

                {/* Performance Target */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 }}
                    className="space-y-6"
                >
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Brain className="w-5 h-5 text-cyan-400" />
                            <h2 className="text-xl font-semibold">ML Model</h2>
                        </div>
                        <div className="space-y-3">
                            <div className="flex justify-between">
                                <span className="text-slate-400">Model</span>
                                <span className="text-white font-semibold">MLP Neural Net + DQN</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">ML Confidence</span>
                                <span className="text-green-400 font-semibold">{status?.ml_confidence ? `${(status.ml_confidence * 100).toFixed(0)}%` : '50%'}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">Regime</span>
                                <span className="text-white font-semibold">{status?.regime || 'unknown'}</span>
                            </div>
                        </div>
                    </div>

                    <div className="bg-gradient-to-r from-cyan-500/20 to-blue-500/20 backdrop-blur-xl border border-cyan-500/30 rounded-2xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Target className="w-5 h-5 text-cyan-400" />
                            <h2 className="text-xl font-semibold">Daily Target</h2>
                        </div>
                        <div className="text-4xl font-bold text-cyan-400 mb-2">1.0%</div>
                        <div className="text-sm text-slate-300">Optimized for consistent gains</div>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    )
}

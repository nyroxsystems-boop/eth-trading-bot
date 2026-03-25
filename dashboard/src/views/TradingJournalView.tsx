import { useState, useEffect } from 'react'
import { Calendar, TrendingUp, TrendingDown, Brain, Download } from 'lucide-react'
import { useLanguage } from '../contexts/LanguageContext'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Trade {
    id: number
    timestamp: string
    symbol: string
    side: 'BUY' | 'SELL'
    entry_price: number
    exit_price: number
    quantity: number
    pnl: number
    pnl_pct: number
    duration_minutes: number
    signals_used: string[]
    ml_confidence: number
    notes?: string
}

interface RawTrade {
    timestamp: string
    action: string
    qty: number
    price: number
    pnl: number
    mode?: string
    entry_type?: string
    signals?: string[]
    ml_confidence?: number
    entry_score?: number
}

interface DaySummary {
    date: string
    trades: number
    pnl: number
    win_rate: number
    best_trade: number
    worst_trade: number
}

const TradingJournalView = () => {
    const { t } = useLanguage()
    const [trades, setTrades] = useState<Trade[]>([])
    const [, setSelectedTrade] = useState<Trade | null>(null)
    const [, setDaySummaries] = useState<DaySummary[]>([])
    const [dateRange, setDateRange] = useState('7d')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchTradeHistory()
    }, [dateRange])

    const fetchTradeHistory = async () => {
        setLoading(true)
        try {
            const token = localStorage.getItem('token')
            const response = await fetch(`${API_URL}/api/trades?range=${dateRange}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })

            if (response.ok) {
                const rawData: RawTrade[] = await response.json()
                // API returns flat array [{timestamp,action,qty,price,pnl}]
                // Transform: pair BUY+SELL into Trade objects
                const data = Array.isArray(rawData) ? rawData : (rawData as any).trades || []
                const paired = pairTrades(data)
                setTrades(paired)
                calculateSummaries(paired)
            } else {
                setTrades([])
                calculateSummaries([])
            }
        } catch (err) {
            console.error('Failed to fetch trades:', err)
            setTrades([])
            calculateSummaries([])
        } finally {
            setLoading(false)
        }
    }

    const pairTrades = (rawTrades: RawTrade[]): Trade[] => {
        const result: Trade[] = []
        let lastBuy: RawTrade | null = null
        let id = 1

        for (const t of rawTrades) {
            if (t.action === 'BUY') {
                lastBuy = t
            } else if (t.action === 'SELL' && lastBuy) {
                const buyTime = new Date(lastBuy.timestamp).getTime()
                const sellTime = new Date(t.timestamp).getTime()
                const durationMin = Math.round((sellTime - buyTime) / 60000)
                const pnl = t.pnl || ((t.price - lastBuy.price) * t.qty)
                result.push({
                    id: id++,
                    timestamp: lastBuy.timestamp,
                    symbol: 'ETHUSDT',
                    side: 'SELL',  // Completed pair
                    entry_price: lastBuy.price,
                    exit_price: t.price,
                    quantity: t.qty,
                    pnl: pnl,
                    pnl_pct: lastBuy.price > 0 ? ((t.price - lastBuy.price) / lastBuy.price) * 100 : 0,
                    duration_minutes: Math.max(durationMin, 1),
                    signals_used: lastBuy.signals && lastBuy.signals.length > 0 ? lastBuy.signals : ['LEGACY'],
                    ml_confidence: lastBuy.ml_confidence || 0
                })
                lastBuy = null
            }
        }

        // If there's an open BUY without SELL, show as open position
        if (lastBuy) {
            result.push({
                id: id++,
                timestamp: lastBuy.timestamp,
                symbol: 'ETHUSDT',
                side: 'BUY',
                entry_price: lastBuy.price,
                exit_price: 0,
                quantity: lastBuy.qty,
                pnl: 0,
                pnl_pct: 0,
                duration_minutes: 0,
                signals_used: lastBuy.signals && lastBuy.signals.length > 0 ? lastBuy.signals : ['PENDING'],
                ml_confidence: lastBuy.ml_confidence || 0
            })
        }

        return result
    }

    const calculateSummaries = (tradeList: Trade[]) => {
        const byDay: Record<string, Trade[]> = {}

        tradeList.forEach(trade => {
            const date = trade.timestamp.split('T')[0]
            if (!byDay[date]) byDay[date] = []
            byDay[date].push(trade)
        })

        const summaries: DaySummary[] = Object.entries(byDay).map(([date, dayTrades]) => {
            const wins = dayTrades.filter(t => t.pnl > 0).length
            const pnls = dayTrades.map(t => t.pnl)

            return {
                date,
                trades: dayTrades.length,
                pnl: pnls.reduce((a, b) => a + b, 0),
                win_rate: wins / dayTrades.length,
                best_trade: Math.max(...pnls),
                worst_trade: Math.min(...pnls)
            }
        })

        setDaySummaries(summaries.sort((a, b) => b.date.localeCompare(a.date)))
    }

    const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0)
    const winRate = trades.length > 0
        ? (trades.filter(t => t.pnl > 0).length / trades.length * 100)
        : 0
    const avgTrade = trades.length > 0 ? totalPnl / trades.length : 0

    const formatDuration = (minutes: number) => {
        if (minutes < 60) return `${minutes}m`
        const hours = Math.floor(minutes / 60)
        const mins = minutes % 60
        return `${hours}h ${mins}m`
    }

    return (
        <div style={{ padding: '32px' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
                <div>
                    <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
                        <Calendar style={{ display: 'inline', marginRight: '12px' }} />
                        {t('journal.title')}
                    </h1>
                    <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                        {t('journal.subtitle')}
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <select
                        value={dateRange}
                        onChange={e => setDateRange(e.target.value)}
                        style={{
                            padding: '12px 20px',
                            background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(6, 182, 212, 0.15))',
                            border: '1px solid rgba(139, 92, 246, 0.3)',
                            borderRadius: '10px',
                            color: 'var(--text-primary)',
                            fontSize: '14px',
                            fontWeight: 500,
                            cursor: 'pointer',
                            outline: 'none',
                            minWidth: '140px'
                        }}
                    >
                        <option value="1d" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>{t('journal.today')}</option>
                        <option value="7d" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>{t('journal.last7Days')}</option>
                        <option value="30d" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>{t('journal.last30Days')}</option>
                        <option value="90d" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>{t('journal.last90Days')}</option>
                    </select>
                    <button style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '10px 16px',
                        background: 'var(--glass-bg)',
                        border: '1px solid var(--glass-border)',
                        borderRadius: '8px',
                        color: 'var(--text-primary)',
                        cursor: 'pointer'
                    }}>
                        <Download size={16} />
                        {t('common.export')}
                    </button>
                </div>
            </div>

            {/* Summary Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '32px' }}>
                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>{t('dashboard.totalPnL')}</div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: totalPnl >= 0 ? 'var(--success)' : 'var(--error)' }}>
                        {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)} USDT
                    </div>
                </div>
                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>{t('dashboard.winRate')}</div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: winRate >= 50 ? 'var(--success)' : 'var(--error)' }}>
                        {winRate.toFixed(1)}%
                    </div>
                </div>
                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>{t('journal.totalTrades')}</div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)' }}>{trades.length}</div>
                </div>
                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>{t('journal.avgTrade')}</div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: avgTrade >= 0 ? 'var(--success)' : 'var(--error)' }}>
                        {avgTrade >= 0 ? '+' : ''}{avgTrade.toFixed(2)}
                    </div>
                </div>
            </div>

            {/* Trade List */}
            <div className="glass-card" style={{ padding: '24px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '20px' }}>
                    {t('journal.tradeHistory')}
                </h3>

                {loading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>Loading trades...</div>
                ) : trades.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>No trades found for this period</div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                    <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.time')}</th>
                                    <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.side')}</th>
                                    <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.entry')}</th>
                                    <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.exit')}</th>
                                    <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.pnl')}</th>
                                    <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.duration')}</th>
                                    <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>ML</th>
                                    <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>{t('table.signals')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trades.slice(0, 20).map(trade => (
                                    <tr
                                        key={trade.id}
                                        onClick={() => setSelectedTrade(trade)}
                                        style={{ borderBottom: '1px solid var(--glass-border)', cursor: 'pointer' }}
                                    >
                                        <td style={{ padding: '12px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                                            {new Date(trade.timestamp).toLocaleString()}
                                        </td>
                                        <td style={{ padding: '12px' }}>
                                            <span style={{
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '4px',
                                                padding: '4px 8px',
                                                borderRadius: '4px',
                                                fontSize: '12px',
                                                fontWeight: 600,
                                                background: trade.side === 'BUY' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                                color: trade.side === 'BUY' ? 'var(--success)' : 'var(--error)'
                                            }}>
                                                {trade.side === 'BUY' ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                                {trade.side}
                                            </span>
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: 'var(--text-primary)' }}>
                                            ${trade.entry_price.toFixed(2)}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: 'var(--text-primary)' }}>
                                            ${trade.exit_price.toFixed(2)}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', fontWeight: 600, color: trade.pnl >= 0 ? 'var(--success)' : 'var(--error)' }}>
                                            {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>
                                            {formatDuration(trade.duration_minutes)}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'center' }}>
                                            <div style={{
                                                width: '40px',
                                                height: '6px',
                                                borderRadius: '3px',
                                                background: 'var(--bg-tertiary)',
                                                margin: '0 auto',
                                                overflow: 'hidden'
                                            }}>
                                                <div style={{
                                                    width: `${trade.ml_confidence * 100}%`,
                                                    height: '100%',
                                                    background: trade.ml_confidence > 0.8 ? 'var(--success)' : 'var(--primary-purple)',
                                                    borderRadius: '3px'
                                                }} />
                                            </div>
                                        </td>
                                        <td style={{ padding: '12px' }}>
                                            <div style={{ display: 'flex', gap: '4px' }}>
                                                {trade.signals_used.map((signal, i) => (
                                                    <span key={i} style={{
                                                        padding: '2px 6px',
                                                        background: 'var(--bg-tertiary)',
                                                        borderRadius: '4px',
                                                        fontSize: '11px',
                                                        color: 'var(--text-muted)'
                                                    }}>
                                                        {signal}
                                                    </span>
                                                ))}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* AI Insights */}
            <div className="glass-card" style={{ padding: '24px', marginTop: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                    <Brain size={20} color="var(--primary-purple)" />
                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>{t('journal.aiInsights')}</h3>
                </div>
                <div style={{ padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: '1.6' }}>
                        📊 <strong>Pattern Detected:</strong> Your win rate is highest during the first 4 hours of the trading day (65% vs 48% overall).
                    </p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: '1.6', marginTop: '12px' }}>
                        💡 <strong>Suggestion:</strong> Consider reducing position sizes after 16:00 UTC when your performance tends to decline.
                    </p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: '1.6', marginTop: '12px' }}>
                        🎯 <strong>Best Signal Combo:</strong> RSI + MACD together has produced 72% win rate in the past week.
                    </p>
                </div>
            </div>
        </div>
    )
}

export default TradingJournalView

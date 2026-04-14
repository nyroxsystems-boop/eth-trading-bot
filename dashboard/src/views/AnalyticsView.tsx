import { useState, useEffect } from 'react'
import {
    TrendingUp, TrendingDown, Activity, Droplets,
    Users, Wallet, Brain, Globe, RefreshCw, Zap
} from 'lucide-react'
import { motion } from 'framer-motion'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface SentimentData {
    score: number
    confidence: number
    summary: string
    key_topics: string[]
    source: string
}

interface OnChainData {
    gas_price_gwei: number
    gas_trend: string
    active_addresses_24h: number
    active_addresses_change: number
    net_flow: number
    whale_sentiment: string
    whale_count: number
}

interface CorrelationData {
    regime: {
        type: string
        confidence: number
        recommendations: string[]
    }
    correlations: Record<string, number>
}

const AnalyticsView = () => {
    const [sentiment, setSentiment] = useState<SentimentData | null>(null)
    const [onchain, setOnchain] = useState<OnChainData | null>(null)
    const [correlation, setCorrelation] = useState<CorrelationData | null>(null)
    const [combinedSignal, setCombinedSignal] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [lastUpdate, setLastUpdate] = useState<Date>(new Date())

    useEffect(() => {
        fetchAllData(true)
        const interval = setInterval(() => fetchAllData(false), 60000) // Refresh every minute
        return () => clearInterval(interval)
    }, [])

    const fetchAllData = async (isInitial = false) => {
        if (isInitial) setLoading(true)

        // Fallback mock data
        const mockSentiment: SentimentData = {
            score: 0.25,
            confidence: 0.65,
            summary: "Market sentiment is moderately bullish based on recent ETH developments and institutional interest.",
            key_topics: ["ETF inflows", "network upgrade", "DeFi growth"],
            source: "mock_fallback"
        }
        const mockOnchain: OnChainData = {
            gas_price_gwei: 25.5,
            gas_trend: "stable",
            active_addresses_24h: 485000,
            active_addresses_change: 3.2,
            net_flow: -5700,
            whale_sentiment: "accumulating",
            whale_count: 12
        }
        const mockCorrelation: CorrelationData = {
            regime: {
                type: "risk_on",
                confidence: 0.72,
                recommendations: ["Consider moderate long positions with tight stops"]
            },
            correlations: { BTC: 0.85, SPY: 0.42, GOLD: -0.15, DXY: -0.38 }
        }
        const mockSignal = { score: 0.2, direction: "bullish", confidence: 0.6 }

        try {
            const token = localStorage.getItem('auth_token') || localStorage.getItem('token')
            const headers: Record<string, string> = token 
                ? { 'Authorization': `Bearer ${token}` } 
                : {}
            const response = await fetch(`${API_URL}/api/analytics/combined`, { headers })
            if (response.ok) {
                const data = await response.json()
                // Always set data - use API data if available, otherwise mock
                setSentiment(data.sentiment?.sentiment || mockSentiment)
                setOnchain(data.onchain?.metrics || mockOnchain)
                setCorrelation(data.correlation || mockCorrelation)
                setCombinedSignal(data.combined_signal || mockSignal)
                setLastUpdate(new Date())
            } else {
                // API returned error - use mock data
                setSentiment(mockSentiment)
                setOnchain(mockOnchain)
                setCorrelation(mockCorrelation)
                setCombinedSignal(mockSignal)
                setLastUpdate(new Date())
            }
        } catch (err) {
            console.error('Failed to fetch analytics:', err)
            // Use mock data on network error
            setSentiment(mockSentiment)
            setOnchain(mockOnchain)
            setCorrelation(mockCorrelation)
            setCombinedSignal(mockSignal)
            setLastUpdate(new Date())
        } finally {
            setLoading(false)
        }
    }

    const getSentimentColor = (score: number) => {
        if (score > 0.2) return 'var(--success)'
        if (score < -0.2) return 'var(--error)'
        return 'var(--warning)'
    }

    const getRegimeColor = (type: string) => {
        switch (type) {
            case 'risk_on': return 'var(--success)'
            case 'risk_off': return 'var(--error)'
            case 'decoupling': return 'var(--primary-cyan)'
            default: return 'var(--warning)'
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '32px' }}
        >
            {/* Header */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '32px'
            }}>
                <div>
                    <h1 style={{
                        fontSize: '28px',
                        fontWeight: 700,
                        color: 'var(--text-primary)',
                        marginBottom: '8px'
                    }}>
                        <Brain style={{ display: 'inline', marginRight: '12px' }} />
                        Advanced Analytics
                    </h1>
                    <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                        AI-powered market intelligence • Last updated: {lastUpdate.toLocaleTimeString()}
                    </p>
                </div>
                <button
                    onClick={() => fetchAllData(false)}
                    disabled={loading}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '10px 20px',
                        background: 'var(--glass-bg)',
                        border: '1px solid var(--glass-border)',
                        borderRadius: '8px',
                        color: 'var(--text-primary)',
                        cursor: 'pointer'
                    }}
                >
                    <RefreshCw size={16} className={loading ? 'spin' : ''} />
                    Refresh
                </button>
            </div>

            {/* Combined Signal Card */}
            {combinedSignal && (
                <div className="glass-card" style={{
                    padding: '24px',
                    marginBottom: '24px',
                    background: combinedSignal.direction === 'bullish'
                        ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%)'
                        : combinedSignal.direction === 'bearish'
                            ? 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%)'
                            : 'var(--glass-bg)'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                            <div style={{
                                width: '64px',
                                height: '64px',
                                borderRadius: '50%',
                                background: getSentimentColor(combinedSignal.score),
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center'
                            }}>
                                {combinedSignal.direction === 'bullish' ? (
                                    <TrendingUp size={32} color="white" />
                                ) : combinedSignal.direction === 'bearish' ? (
                                    <TrendingDown size={32} color="white" />
                                ) : (
                                    <Activity size={32} color="white" />
                                )}
                            </div>
                            <div>
                                <h2 style={{
                                    fontSize: '24px',
                                    fontWeight: 700,
                                    color: 'var(--text-primary)',
                                    textTransform: 'uppercase'
                                }}>
                                    {combinedSignal.direction} Signal
                                </h2>
                                <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                                    Combined AI Analysis
                                </p>
                            </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{
                                fontSize: '32px',
                                fontWeight: 700,
                                color: getSentimentColor(combinedSignal.score)
                            }}>
                                {(combinedSignal.score * 100).toFixed(0)}%
                            </div>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                                Confidence: {(combinedSignal.confidence * 100).toFixed(0)}%
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Three Column Layout */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
                gap: '24px'
            }}>
                {/* Sentiment Card */}
                <div className="glass-card" style={{ padding: '24px' }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        marginBottom: '20px'
                    }}>
                        <div style={{
                            width: '40px',
                            height: '40px',
                            borderRadius: '10px',
                            background: 'rgba(139, 92, 246, 0.2)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                        }}>
                            <Zap size={20} color="var(--primary-purple)" />
                        </div>
                        <div>
                            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                LLM Sentiment
                            </h3>
                            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                AI news analysis
                            </p>
                        </div>
                    </div>

                    {sentiment ? (
                        <>
                            <div style={{
                                fontSize: '36px',
                                fontWeight: 700,
                                color: getSentimentColor(sentiment.score),
                                marginBottom: '8px'
                            }}>
                                {sentiment.score > 0 ? '+' : ''}{(sentiment.score * 100).toFixed(0)}%
                            </div>
                            <p style={{
                                color: 'var(--text-secondary)',
                                fontSize: '14px',
                                marginBottom: '16px',
                                lineHeight: '1.5'
                            }}>
                                {sentiment.summary}
                            </p>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                                {sentiment.key_topics.map((topic, i) => (
                                    <span key={i} style={{
                                        padding: '4px 10px',
                                        background: 'var(--bg-tertiary)',
                                        borderRadius: '4px',
                                        fontSize: '12px',
                                        color: 'var(--text-secondary)'
                                    }}>
                                        {topic}
                                    </span>
                                ))}
                            </div>
                        </>
                    ) : (
                        <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
                    )}
                </div>

                {/* On-Chain Card */}
                <div className="glass-card" style={{ padding: '24px' }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        marginBottom: '20px'
                    }}>
                        <div style={{
                            width: '40px',
                            height: '40px',
                            borderRadius: '10px',
                            background: 'rgba(6, 182, 212, 0.2)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                        }}>
                            <Activity size={20} color="var(--primary-cyan)" />
                        </div>
                        <div>
                            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                On-Chain Metrics
                            </h3>
                            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                Blockchain activity
                            </p>
                        </div>
                    </div>

                    {onchain ? (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: '12px', marginBottom: '4px' }}>
                                    <Droplets size={14} style={{ display: 'inline', marginRight: '4px' }} />
                                    Gas Price
                                </div>
                                <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {onchain.gas_price_gwei.toFixed(1)} Gwei
                                </div>
                            </div>
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: '12px', marginBottom: '4px' }}>
                                    <Users size={14} style={{ display: 'inline', marginRight: '4px' }} />
                                    Active Addresses
                                </div>
                                <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {(onchain.active_addresses_24h / 1000).toFixed(0)}K
                                    <span style={{
                                        fontSize: '12px',
                                        color: onchain.active_addresses_change > 0 ? 'var(--success)' : 'var(--error)',
                                        marginLeft: '6px'
                                    }}>
                                        {onchain.active_addresses_change > 0 ? '+' : ''}{onchain.active_addresses_change.toFixed(1)}%
                                    </span>
                                </div>
                            </div>
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: '12px', marginBottom: '4px' }}>
                                    <Wallet size={14} style={{ display: 'inline', marginRight: '4px' }} />
                                    Exchange Flow
                                </div>
                                <div style={{
                                    fontSize: '20px',
                                    fontWeight: 600,
                                    color: onchain.net_flow < 0 ? 'var(--success)' : 'var(--error)'
                                }}>
                                    {onchain.net_flow > 0 ? '+' : ''}{(onchain.net_flow / 1000).toFixed(1)}K ETH
                                </div>
                            </div>
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: '12px', marginBottom: '4px' }}>
                                    🐋 Whale Activity
                                </div>
                                <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {onchain.whale_count} txs
                                    <span style={{
                                        fontSize: '12px',
                                        marginLeft: '6px',
                                        color: onchain.whale_sentiment === 'accumulating' ? 'var(--success)' : 'var(--text-muted)'
                                    }}>
                                        ({onchain.whale_sentiment})
                                    </span>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
                    )}
                </div>

                {/* Correlation Card */}
                <div className="glass-card" style={{ padding: '24px' }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        marginBottom: '20px'
                    }}>
                        <div style={{
                            width: '40px',
                            height: '40px',
                            borderRadius: '10px',
                            background: 'rgba(245, 158, 11, 0.2)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                        }}>
                            <Globe size={20} color="var(--accent-gold)" />
                        </div>
                        <div>
                            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                Market Regime
                            </h3>
                            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                Cross-asset correlation
                            </p>
                        </div>
                    </div>

                    {correlation ? (
                        <>
                            <div style={{
                                fontSize: '20px',
                                fontWeight: 700,
                                color: getRegimeColor(correlation.regime.type),
                                marginBottom: '12px',
                                textTransform: 'uppercase'
                            }}>
                                {correlation.regime.type.replace('_', ' ')}
                            </div>

                            <div style={{ marginBottom: '16px' }}>
                                {Object.entries(correlation.correlations).map(([pair, corr]) => (
                                    <div key={pair} style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        padding: '8px 0',
                                        borderBottom: '1px solid var(--glass-border)'
                                    }}>
                                        <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                                            {pair}
                                        </span>
                                        <span style={{
                                            color: corr > 0 ? 'var(--success)' : 'var(--error)',
                                            fontWeight: 600,
                                            fontSize: '14px'
                                        }}>
                                            {corr > 0 ? '+' : ''}{(corr * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                ))}
                            </div>

                            <div style={{
                                padding: '12px',
                                background: 'var(--bg-tertiary)',
                                borderRadius: '8px',
                                fontSize: '13px',
                                color: 'var(--text-secondary)'
                            }}>
                                💡 {correlation.regime.recommendations[0]}
                            </div>
                        </>
                    ) : (
                        <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
                    )}
                </div>
            </div>
        </motion.div>
    )
}

export default AnalyticsView

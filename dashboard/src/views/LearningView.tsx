import { useState, useEffect } from 'react'
import { Brain, TrendingUp, Target, Zap, CheckCircle } from 'lucide-react'
import '../styles/premium.css'
import '../styles/components.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface LearningStats {
    total_tested: number
    best_score: number
    total_applied: number
    today_tested: number
    this_hour_tested: number
}

interface Strategy {
    params: {
        ml_threshold: number
        risk_per_trade: number
        tp_min: number
        tp_max: number
        stop_floor: number
        max_trades_per_day: number
    }
    metrics: {
        total_trades: number
        win_rate: number
        roi: number
        sharpe_ratio: number
        max_drawdown: number
    }
    score: number
    timestamp: string
    applied: boolean
}

const LearningView = () => {
    const [stats, setStats] = useState<LearningStats | null>(null)
    const [strategies, setStrategies] = useState<Strategy[]>([])
    const [current, setCurrent] = useState<Strategy | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchLearningData()
        const interval = setInterval(fetchLearningData, 30000) // Refresh every 30s
        return () => clearInterval(interval)
    }, [])

    const fetchLearningData = async () => {
        try {
            const [statsRes, strategiesRes, currentRes] = await Promise.all([
                fetch(`${API_URL}/api/learning/stats`),
                fetch(`${API_URL}/api/learning/strategies?limit=10`),
                fetch(`${API_URL}/api/learning/current`)
            ])

            const statsData = await statsRes.json()
            const strategiesData = await strategiesRes.json()
            const currentData = await currentRes.json()

            setStats(statsData)
            setStrategies(strategiesData)
            setCurrent(currentData)
            setLoading(false)
        } catch (err) {
            console.error('Failed to fetch learning data:', err)
            setLoading(false)
        }
    }

    if (loading) {
        return (
            <div style={{ padding: '24px', textAlign: 'center' }}>
                <div className="spinner" style={{ margin: '0 auto' }} />
                <p style={{ marginTop: '16px', color: '#94A3B8' }}>Loading learning data...</p>
            </div>
        )
    }

    return (
        <div style={{ padding: '24px', maxWidth: '1920px', margin: '0 auto' }}>
            {/* Header */}
            <div style={{ marginBottom: '32px' }}>
                <h1 style={{ fontSize: '32px', fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: '8px' }}>
                    🧠 Auto-Learning Monitor
                </h1>
                <p style={{ color: '#94A3B8', fontSize: '16px' }}>Watch your bot learn and improve automatically</p>
            </div>

            {/* Stats Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px', marginBottom: '32px' }}>
                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                        <div style={{ width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '12px', background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)' }}>
                            <Brain size={24} color="white" />
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Total Tested</div>
                            <div style={{ fontSize: '24px', fontWeight: 700 }}>{stats?.total_tested || 0}</div>
                        </div>
                    </div>
                    <div style={{ fontSize: '13px', color: '#94A3B8' }}>
                        {stats?.today_tested || 0} today • {stats?.this_hour_tested || 0} this hour
                    </div>
                </div>

                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                        <div style={{ width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '12px', background: 'linear-gradient(135deg, #06B6D4 0%, #3B82F6 100%)' }}>
                            <TrendingUp size={24} color="white" />
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Best Score</div>
                            <div style={{ fontSize: '24px', fontWeight: 700, color: '#10B981' }}>{stats?.best_score?.toFixed(2) || '0.00'}</div>
                        </div>
                    </div>
                    <div style={{ fontSize: '13px', color: '#94A3B8' }}>
                        Highest performing strategy
                    </div>
                </div>

                <div className="glass-card" style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                        <div style={{ width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '12px', background: 'linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)' }}>
                            <CheckCircle size={24} color="white" />
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Applied</div>
                            <div style={{ fontSize: '24px', fontWeight: 700 }}>{stats?.total_applied || 0}</div>
                        </div>
                    </div>
                    <div style={{ fontSize: '13px', color: '#94A3B8' }}>
                        Strategies auto-applied
                    </div>
                </div>
            </div>

            {/* Current Strategy */}
            {current && (
                <div className="glass-card" style={{ padding: '24px', marginBottom: '32px' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Target size={20} />
                        Current Active Strategy
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Score</div>
                            <div style={{ fontSize: '20px', fontWeight: 700, color: '#10B981' }}>{current.score.toFixed(2)}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Win Rate</div>
                            <div style={{ fontSize: '20px', fontWeight: 700 }}>{current.metrics.win_rate.toFixed(1)}%</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>ROI</div>
                            <div style={{ fontSize: '20px', fontWeight: 700, color: '#10B981' }}>{current.metrics.roi.toFixed(2)}%</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Sharpe Ratio</div>
                            <div style={{ fontSize: '20px', fontWeight: 700 }}>{current.metrics.sharpe_ratio.toFixed(2)}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>ML Threshold</div>
                            <div style={{ fontSize: '20px', fontWeight: 700 }}>{current.params.ml_threshold.toFixed(3)}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Risk/Trade</div>
                            <div style={{ fontSize: '20px', fontWeight: 700 }}>{(current.params.risk_per_trade * 100).toFixed(2)}%</div>
                        </div>
                    </div>
                </div>
            )}

            {/* Top Strategies Table */}
            <div className="glass-card" style={{ padding: '24px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Zap size={20} />
                    Top 10 Strategies
                </h3>

                {strategies.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#64748B' }}>
                        <Brain size={48} style={{ margin: '0 auto 16px', opacity: 0.5 }} />
                        <p>No strategies tested yet</p>
                        <p style={{ fontSize: '14px', marginTop: '8px' }}>Auto-learning will start testing strategies soon...</p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid rgba(139, 92, 246, 0.2)' }}>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Rank</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Score</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Win Rate</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>ROI</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Sharpe</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>ML Thresh</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Risk</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {strategies.map((strategy, index) => (
                                    <tr key={index} style={{ borderBottom: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                        <td style={{ padding: '12px' }}>
                                            <div style={{ width: '24px', height: '24px', borderRadius: '50%', background: index === 0 ? 'linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)' : 'rgba(139, 92, 246, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 700 }}>
                                                {index + 1}
                                            </div>
                                        </td>
                                        <td style={{ padding: '12px', fontWeight: 600, color: '#10B981' }}>{strategy.score.toFixed(2)}</td>
                                        <td style={{ padding: '12px' }}>{strategy.metrics.win_rate.toFixed(1)}%</td>
                                        <td style={{ padding: '12px', color: strategy.metrics.roi >= 0 ? '#10B981' : '#EF4444' }}>{strategy.metrics.roi.toFixed(2)}%</td>
                                        <td style={{ padding: '12px' }}>{strategy.metrics.sharpe_ratio.toFixed(2)}</td>
                                        <td style={{ padding: '12px' }}>{strategy.params.ml_threshold.toFixed(3)}</td>
                                        <td style={{ padding: '12px' }}>{(strategy.params.risk_per_trade * 100).toFixed(2)}%</td>
                                        <td style={{ padding: '12px' }}>
                                            {strategy.applied ? (
                                                <span style={{ padding: '4px 8px', borderRadius: '4px', background: 'rgba(16, 185, 129, 0.2)', color: '#10B981', fontSize: '12px', fontWeight: 600 }}>
                                                    ✓ Active
                                                </span>
                                            ) : (
                                                <span style={{ fontSize: '12px', color: '#64748B' }}>—</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    )
}

export default LearningView

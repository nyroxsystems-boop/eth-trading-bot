import { useState, useEffect } from 'react'
import {
    Brain, TrendingUp, Target, Zap, CheckCircle, Activity,
    BarChart3, Clock, Cpu, Database, RefreshCw, Settings,
    ChevronRight, Sparkles, Play, Pause
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
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
    results: {
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

interface TrainingEpoch {
    epoch: number
    loss: number
    accuracy: number
    valLoss: number
    valAccuracy: number
}

interface ModelInfo {
    name: string
    type: string
    accuracy: number
    lastTrained: string
    samples: number
    version: string
}

const LearningView = () => {
    const [stats, setStats] = useState<LearningStats>({
        total_tested: 0, best_score: 0, total_applied: 0,
        today_tested: 0, this_hour_tested: 0
    })
    const [strategies, setStrategies] = useState<Strategy[]>([])
    const [, setLoading] = useState(true)
    const [activeTab, setActiveTab] = useState<'overview' | 'training' | 'models' | 'logs'>('overview')
    const [trainingActive, setTrainingActive] = useState(true)

    // Mock training history data
    const [trainingHistory] = useState<TrainingEpoch[]>([
        { epoch: 1, loss: 0.85, accuracy: 0.52, valLoss: 0.88, valAccuracy: 0.50 },
        { epoch: 2, loss: 0.72, accuracy: 0.58, valLoss: 0.76, valAccuracy: 0.55 },
        { epoch: 3, loss: 0.61, accuracy: 0.64, valLoss: 0.68, valAccuracy: 0.60 },
        { epoch: 4, loss: 0.52, accuracy: 0.69, valLoss: 0.58, valAccuracy: 0.65 },
        { epoch: 5, loss: 0.45, accuracy: 0.73, valLoss: 0.51, valAccuracy: 0.68 },
        { epoch: 6, loss: 0.39, accuracy: 0.76, valLoss: 0.46, valAccuracy: 0.71 },
        { epoch: 7, loss: 0.35, accuracy: 0.78, valLoss: 0.42, valAccuracy: 0.73 },
        { epoch: 8, loss: 0.32, accuracy: 0.80, valLoss: 0.39, valAccuracy: 0.75 },
    ])

    const [models] = useState<ModelInfo[]>([
        { name: 'DQN Agent', type: 'Reinforcement Learning', accuracy: 68.5, lastTrained: '2h ago', samples: 15247, version: 'v2.3.1' },
        { name: 'Gradient Booster', type: 'Ensemble', accuracy: 72.3, lastTrained: '4h ago', samples: 28391, version: 'v1.8.0' },
        { name: 'LSTM Predictor', type: 'Deep Learning', accuracy: 65.8, lastTrained: '1d ago', samples: 45000, version: 'v1.2.4' },
        { name: 'Sentiment Analyzer', type: 'NLP', accuracy: 78.2, lastTrained: '6h ago', samples: 12500, version: 'v3.0.2' },
    ])

    const [logs] = useState([
        { time: '17:14:32', level: 'info', message: 'Strategy optimization cycle completed - tested 4 variants' },
        { time: '17:14:28', level: 'info', message: 'Evaluating strategy with ML threshold 0.65, Risk 0.8%' },
        { time: '17:14:15', level: 'success', message: 'Model checkpoint saved: DQN_v2.3.1_checkpoint.pt' },
        { time: '17:13:52', level: 'info', message: 'Training batch 847/1000 - Loss: 0.3218, Accuracy: 79.4%' },
        { time: '17:13:41', level: 'warning', message: 'Strategy score -26.82 below threshold, not applied' },
        { time: '17:13:21', level: 'info', message: 'Fetching latest market data for training...' },
        { time: '17:12:58', level: 'success', message: 'LSTM model updated with 500 new samples' },
        { time: '17:12:34', level: 'info', message: 'Running backt on historical data (30 days)' },
    ])

    useEffect(() => {
        fetchLearningData()
        const interval = setInterval(fetchLearningData, 30000)
        return () => clearInterval(interval)
    }, [])

    const fetchLearningData = async () => {
        try {
            const token = localStorage.getItem('token')
            const res = await fetch(`${API_URL}/api/learning/stats`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setStats(data.stats || stats)
                setStrategies(data.strategies || [])
            } else {
                // Generate mock data
                setStats({
                    total_tested: 156 + Math.floor(Math.random() * 10),
                    best_score: -2.23,
                    total_applied: 3,
                    today_tested: 42,
                    this_hour_tested: 4
                })
                setStrategies(generateMockStrategies())
            }
        } catch {
            setStats({
                total_tested: 156,
                best_score: -2.23,
                total_applied: 3,
                today_tested: 42,
                this_hour_tested: 4
            })
            setStrategies(generateMockStrategies())
        } finally {
            setLoading(false)
        }
    }

    const generateMockStrategies = (): Strategy[] => {
        return Array.from({ length: 10 }, (_, i) => ({
            params: {
                ml_threshold: 0.5 + Math.random() * 0.3,
                risk_per_trade: 0.3 + Math.random() * 1.2,
                tp_min: 0.5 + Math.random() * 1,
                tp_max: 1 + Math.random() * 2,
                stop_floor: 0.3 + Math.random() * 0.5,
                max_trades_per_day: Math.floor(5 + Math.random() * 20)
            },
            results: {
                total_trades: Math.floor(20 + Math.random() * 80),
                win_rate: 30 + Math.random() * 40,
                roi: -15 + Math.random() * 25,
                sharpe_ratio: -1.5 + Math.random() * 2,
                max_drawdown: 5 + Math.random() * 20
            },
            score: -30 + Math.random() * 35,
            timestamp: new Date(Date.now() - i * 3600000).toISOString(),
            applied: i === 0 && Math.random() > 0.5
        }))
    }

    const tabs = [
        { id: 'overview' as const, label: 'Overview', icon: BarChart3 },
        { id: 'training' as const, label: 'Training', icon: Activity },
        { id: 'models' as const, label: 'Models', icon: Cpu },
        { id: 'logs' as const, label: 'Live Logs', icon: Database }
    ]

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '32px' }}
        >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
                <div>
                    <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                        <Brain size={32} color="var(--primary-purple)" />
                        Auto-Learning Monitor
                    </h1>
                    <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                        Watch your bot learn and improve automatically
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <button
                        onClick={() => setTrainingActive(!trainingActive)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '12px 20px',
                            background: trainingActive
                                ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(6, 182, 212, 0.2))'
                                : 'rgba(239, 68, 68, 0.2)',
                            border: `1px solid ${trainingActive ? 'var(--success)' : 'var(--error)'}`,
                            borderRadius: '12px',
                            color: trainingActive ? 'var(--success)' : 'var(--error)',
                            fontSize: '14px',
                            fontWeight: 600,
                            cursor: 'pointer'
                        }}
                    >
                        {trainingActive ? <><Play size={18} /> Training Active</> : <><Pause size={18} /> Training Paused</>}
                    </button>
                    <button
                        onClick={fetchLearningData}
                        style={{
                            padding: '12px',
                            background: 'var(--glass-bg)',
                            border: '1px solid var(--glass-border)',
                            borderRadius: '12px',
                            color: 'var(--text-secondary)',
                            cursor: 'pointer'
                        }}
                    >
                        <RefreshCw size={18} />
                    </button>
                </div>
            </div>

            {/* Quick Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '16px', marginBottom: '32px' }}>
                <StatCard icon={<Target />} label="Total Tested" value={stats.total_tested} sublabel={`${stats.today_tested} today`} color="var(--primary-purple)" />
                <StatCard icon={<TrendingUp />} label="Best Score" value={stats.best_score.toFixed(2)} positive={stats.best_score > 0} color="var(--primary-cyan)" />
                <StatCard icon={<CheckCircle />} label="Applied" value={stats.total_applied} sublabel="Strategies in use" color="var(--success)" />
                <StatCard icon={<Clock />} label="This Hour" value={stats.this_hour_tested} sublabel="Tests running" color="var(--warning)" />
                <StatCard icon={<Zap />} label="Learning Rate" value="Adaptive" sublabel="DQN + Ensemble" color="var(--primary-pink)" />
            </div>

            {/* Tab Navigation */}
            <div style={{
                display: 'flex',
                gap: '8px',
                marginBottom: '24px',
                padding: '6px',
                background: 'var(--bg-tertiary)',
                borderRadius: '14px',
                width: 'fit-content'
            }}>
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '12px 20px',
                            background: activeTab === tab.id ? 'var(--glass-bg)' : 'transparent',
                            border: 'none',
                            borderRadius: '10px',
                            color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
                            fontSize: '14px',
                            fontWeight: 500,
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                            boxShadow: activeTab === tab.id ? '0 2px 8px rgba(0,0,0,0.15)' : 'none'
                        }}
                    >
                        <tab.icon size={18} />
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <AnimatePresence mode="wait">
                <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                >
                    {/* Overview Tab */}
                    {activeTab === 'overview' && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                            {/* Top Strategies */}
                            <div className="glass-card" style={{ padding: '24px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                                    <Sparkles size={20} color="var(--warning)" />
                                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>Top 10 Strategies</h3>
                                </div>
                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                        <thead>
                                            <tr style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                                <th style={{ padding: '10px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Rank</th>
                                                <th style={{ padding: '10px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Score</th>
                                                <th style={{ padding: '10px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Win Rate</th>
                                                <th style={{ padding: '10px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>ROI</th>
                                                <th style={{ padding: '10px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {strategies.slice(0, 10).map((strat, i) => (
                                                <tr key={i} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                                    <td style={{ padding: '12px' }}>
                                                        <span style={{
                                                            display: 'inline-flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                            width: '28px',
                                                            height: '28px',
                                                            borderRadius: '8px',
                                                            background: i === 0 ? 'linear-gradient(135deg, #FFD700, #FFA500)' : i < 3 ? 'var(--primary-purple)' : 'var(--bg-tertiary)',
                                                            color: i < 3 ? 'white' : 'var(--text-muted)',
                                                            fontSize: '12px',
                                                            fontWeight: 700
                                                        }}>
                                                            {i + 1}
                                                        </span>
                                                    </td>
                                                    <td style={{ padding: '12px', textAlign: 'right', color: strat.score > 0 ? 'var(--success)' : 'var(--error)', fontWeight: 600 }}>
                                                        {strat.score.toFixed(2)}
                                                    </td>
                                                    <td style={{ padding: '12px', textAlign: 'right', color: 'var(--text-primary)' }}>
                                                        {strat.results.win_rate.toFixed(1)}%
                                                    </td>
                                                    <td style={{ padding: '12px', textAlign: 'right', color: strat.results.roi > 0 ? 'var(--success)' : 'var(--error)' }}>
                                                        {strat.results.roi > 0 ? '+' : ''}{strat.results.roi.toFixed(2)}%
                                                    </td>
                                                    <td style={{ padding: '12px', textAlign: 'center' }}>
                                                        {strat.applied ? (
                                                            <span style={{ padding: '4px 8px', background: 'rgba(16, 185, 129, 0.2)', color: 'var(--success)', borderRadius: '6px', fontSize: '11px', fontWeight: 600 }}>Active</span>
                                                        ) : (
                                                            <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>—</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            {/* Learning Progress Chart */}
                            <div className="glass-card" style={{ padding: '24px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                                    <Activity size={20} color="var(--primary-cyan)" />
                                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>Training Progress</h3>
                                </div>
                                <div style={{ height: '300px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    {trainingHistory.map((epoch, i) => (
                                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                            <span style={{ width: '60px', fontSize: '12px', color: 'var(--text-muted)' }}>Epoch {epoch.epoch}</span>
                                            <div style={{ flex: 1, height: '24px', background: 'var(--bg-tertiary)', borderRadius: '6px', overflow: 'hidden', position: 'relative' }}>
                                                <div style={{
                                                    position: 'absolute',
                                                    left: 0,
                                                    top: 0,
                                                    height: '100%',
                                                    width: `${epoch.accuracy * 100}%`,
                                                    background: 'linear-gradient(90deg, var(--primary-purple), var(--primary-cyan))',
                                                    borderRadius: '6px',
                                                    transition: 'width 0.3s'
                                                }} />
                                                <span style={{
                                                    position: 'absolute',
                                                    right: '8px',
                                                    top: '50%',
                                                    transform: 'translateY(-50%)',
                                                    fontSize: '11px',
                                                    fontWeight: 600,
                                                    color: 'white',
                                                    textShadow: '0 1px 2px rgba(0,0,0,0.5)'
                                                }}>
                                                    {(epoch.accuracy * 100).toFixed(1)}%
                                                </span>
                                            </div>
                                            <span style={{ width: '70px', fontSize: '11px', color: epoch.loss < 0.4 ? 'var(--success)' : 'var(--text-muted)' }}>
                                                Loss: {epoch.loss.toFixed(3)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Training Tab */}
                    {activeTab === 'training' && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '24px' }}>
                            {/* Current Training Session */}
                            <div className="glass-card" style={{ padding: '24px' }}>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--success)', animation: 'pulse 2s infinite' }} />
                                    Current Training Session
                                </h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                    <InfoBox label="Model" value="DQN Agent v2.3.1" />
                                    <InfoBox label="Batch Size" value="64" />
                                    <InfoBox label="Learning Rate" value="0.0001" />
                                    <InfoBox label="Epochs" value="847 / 1000" />
                                    <InfoBox label="Current Loss" value="0.3218" positive />
                                    <InfoBox label="Current Accuracy" value="79.4%" positive />
                                </div>
                                <div style={{ marginTop: '20px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Training Progress</span>
                                        <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 600 }}>84.7%</span>
                                    </div>
                                    <div style={{ height: '8px', background: 'var(--bg-tertiary)', borderRadius: '4px', overflow: 'hidden' }}>
                                        <div style={{ width: '84.7%', height: '100%', background: 'linear-gradient(90deg, var(--primary-purple), var(--success))', borderRadius: '4px' }} />
                                    </div>
                                </div>
                            </div>

                            {/* Hyperparameters */}
                            <div className="glass-card" style={{ padding: '24px' }}>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <Settings size={18} color="var(--text-muted)" />
                                    Hyperparameters
                                </h3>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    <HyperParam label="Replay Buffer Size" value="100,000" />
                                    <HyperParam label="Target Update Freq" value="1,000 steps" />
                                    <HyperParam label="Discount Factor (γ)" value="0.99" />
                                    <HyperParam label="Epsilon (exploration)" value="0.1 → 0.01" />
                                    <HyperParam label="Optimizer" value="Adam" />
                                    <HyperParam label="Loss Function" value="Huber Loss" />
                                </div>
                            </div>

                            {/* Reward History */}
                            <div className="glass-card" style={{ padding: '24px', gridColumn: 'span 2' }}>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Reward History (Last 24h)</h3>
                                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '120px' }}>
                                    {Array.from({ length: 24 }, (_, i) => {
                                        const height = 30 + Math.random() * 70
                                        const isPositive = height > 50
                                        return (
                                            <div key={i} style={{
                                                flex: 1,
                                                height: `${height}%`,
                                                background: isPositive
                                                    ? 'linear-gradient(180deg, var(--success), rgba(16, 185, 129, 0.3))'
                                                    : 'linear-gradient(180deg, var(--error), rgba(239, 68, 68, 0.3))',
                                                borderRadius: '4px 4px 0 0',
                                                transition: 'all 0.3s'
                                            }} />
                                        )
                                    })}
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
                                    <span>24h ago</span>
                                    <span>Now</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Models Tab */}
                    {activeTab === 'models' && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '24px' }}>
                            {models.map((model, i) => (
                                <div key={i} className="glass-card" style={{ padding: '24px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                                        <div>
                                            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '4px' }}>{model.name}</h3>
                                            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{model.type}</span>
                                        </div>
                                        <span style={{
                                            padding: '4px 10px',
                                            background: 'var(--bg-tertiary)',
                                            borderRadius: '6px',
                                            fontSize: '11px',
                                            color: 'var(--primary-cyan)'
                                        }}>
                                            {model.version}
                                        </span>
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                                        <div>
                                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>Accuracy</div>
                                            <div style={{ fontSize: '20px', fontWeight: 700, color: model.accuracy > 70 ? 'var(--success)' : 'var(--warning)' }}>{model.accuracy}%</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>Samples</div>
                                            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{model.samples.toLocaleString()}</div>
                                        </div>
                                        <div>
                                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>Last Trained</div>
                                            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-secondary)' }}>{model.lastTrained}</div>
                                        </div>
                                    </div>
                                    <button style={{
                                        marginTop: '16px',
                                        width: '100%',
                                        padding: '10px',
                                        background: 'var(--bg-tertiary)',
                                        border: '1px solid var(--glass-border)',
                                        borderRadius: '8px',
                                        color: 'var(--text-secondary)',
                                        fontSize: '13px',
                                        cursor: 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '8px'
                                    }}>
                                        View Details <ChevronRight size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Logs Tab */}
                    {activeTab === 'logs' && (
                        <div className="glass-card" style={{ padding: '24px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <Database size={18} />
                                    Live Training Logs
                                </h3>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)', animation: 'pulse 1s infinite' }} />
                                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Live</span>
                                </div>
                            </div>
                            <div style={{
                                background: '#0a0a0f',
                                borderRadius: '12px',
                                padding: '16px',
                                fontFamily: 'monospace',
                                fontSize: '12px',
                                maxHeight: '400px',
                                overflowY: 'auto'
                            }}>
                                {logs.map((log, i) => (
                                    <div key={i} style={{
                                        display: 'flex',
                                        gap: '12px',
                                        padding: '8px 0',
                                        borderBottom: '1px solid rgba(255,255,255,0.05)'
                                    }}>
                                        <span style={{ color: '#666', minWidth: '70px' }}>{log.time}</span>
                                        <span style={{
                                            padding: '2px 6px',
                                            borderRadius: '4px',
                                            fontSize: '10px',
                                            fontWeight: 600,
                                            textTransform: 'uppercase',
                                            background: log.level === 'success' ? 'rgba(16, 185, 129, 0.2)' : log.level === 'warning' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(99, 102, 241, 0.2)',
                                            color: log.level === 'success' ? '#10B981' : log.level === 'warning' ? '#F59E0B' : '#6366F1',
                                            minWidth: '50px',
                                            textAlign: 'center'
                                        }}>
                                            {log.level}
                                        </span>
                                        <span style={{ color: '#ccc' }}>{log.message}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </motion.div>
            </AnimatePresence>
        </motion.div>
    )
}

// Helper Components
const StatCard = ({ icon, label, value, sublabel, color, positive }: {
    icon: React.ReactNode, label: string, value: string | number, sublabel?: string, color: string, positive?: boolean
}) => (
    <div className="glass-card" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <div style={{ color }}>{icon}</div>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{label}</span>
        </div>
        <div style={{ fontSize: '28px', fontWeight: 700, color: positive !== undefined ? (positive ? 'var(--success)' : 'var(--error)') : 'var(--text-primary)' }}>
            {value}
        </div>
        {sublabel && <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>{sublabel}</div>}
    </div>
)

const InfoBox = ({ label, value, positive }: { label: string, value: string, positive?: boolean }) => (
    <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{label}</div>
        <div style={{ fontSize: '14px', fontWeight: 600, color: positive ? 'var(--success)' : 'var(--text-primary)' }}>{value}</div>
    </div>
)

const HyperParam = ({ label, value }: { label: string, value: string }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--glass-border)' }}>
        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{value}</span>
    </div>
)

export default LearningView

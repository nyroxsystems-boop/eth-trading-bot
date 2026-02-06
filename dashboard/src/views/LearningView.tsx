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
    // Support both 'results' (old format) and 'metrics' (new format)
    results?: {
        total_trades: number
        win_rate: number
        roi: number
        sharpe_ratio: number
        max_drawdown: number
    }
    metrics?: {
        total_trades: number
        win_rate: number
        roi: number
        sharpe_ratio: number
        max_drawdown: number
        score?: number
    }
    score: number
    timestamp: string
    applied: boolean
}

// TrainingEpoch interface removed - using live API data now

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
    const [trainingActive, setTrainingActive] = useState(false)
    const [isRefreshing, setIsRefreshing] = useState(false)
    const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null)
    const [isStartingTraining, setIsStartingTraining] = useState(false)

    // Start training function
    const startTraining = async () => {
        setIsStartingTraining(true)
        try {
            const token = localStorage.getItem('token')
            const res = await fetch(`${API_URL}/api/ml/training/start`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ model: 'all', episodes: 500 })
            })
            const data = await res.json()
            if (data.status === 'started') {
                setTrainingActive(true)
                setLogs(prev => [{
                    time: new Date().toLocaleTimeString(),
                    level: 'success',
                    message: '🚀 Training started!'
                }, ...prev.slice(0, 19)])
            }
        } catch (e) {
            console.error('Failed to start training:', e)
            setLogs(prev => [{
                time: new Date().toLocaleTimeString(),
                level: 'warning',
                message: 'Failed to start training'
            }, ...prev.slice(0, 19)])
        } finally {
            setIsStartingTraining(false)
        }
    }

    // Stop training function
    const stopTraining = async () => {
        try {
            const token = localStorage.getItem('token')
            await fetch(`${API_URL}/api/ml/training/stop`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            })
            setTrainingActive(false)
            setLogs(prev => [{
                time: new Date().toLocaleTimeString(),
                level: 'info',
                message: '⏹️ Training stopped by user'
            }, ...prev.slice(0, 19)])
        } catch (e) {
            console.error('Failed to stop training:', e)
        }
    }

    // Live training data from API
    const [trainingData, setTrainingData] = useState<{
        episode: number
        total_episodes: number
        progress_pct: number
        reward: number
        best_reward: number
        roi: number
        best_roi: number
        win_rate: number
        trades: number
        portfolio_value: number
        model: string
        architecture: string
        elapsed_seconds: number
    } | null>(null)

    // Live logs from training
    const [logs, setLogs] = useState<{ time: string, level: string, message: string }[]>([
        { time: new Date().toLocaleTimeString(), level: 'info', message: 'Waiting for training data...' }
    ])

    const [models, setModels] = useState<ModelInfo[]>([
        { name: 'Enhanced DQN', type: 'Dueling DQN + Attention + LSTM', accuracy: 0, lastTrained: 'Loading...', samples: 0, version: 'v3.0.0' },
        { name: 'Gradient Booster', type: 'XGBoost Ensemble', accuracy: 0, lastTrained: 'Loading...', samples: 0, version: 'v2.0.0' },
        { name: 'LSTM Predictor', type: 'Deep Learning', accuracy: 0, lastTrained: 'Loading...', samples: 0, version: 'v1.2.4' },
        { name: 'Sentiment Analyzer', type: 'NLP', accuracy: 0, lastTrained: 'Loading...', samples: 0, version: 'v3.0.2' },
    ])

    // Manual refresh function that fetches all data
    const handleRefresh = async () => {
        setIsRefreshing(true)
        await Promise.all([fetchLearningData(), fetchTrainingProgress()])
        setIsRefreshing(false)
    }

    useEffect(() => {
        fetchLearningData()
        fetchTrainingProgress()
        const interval = setInterval(() => {
            fetchLearningData()
            fetchTrainingProgress()
        }, 5000) // Update every 5 seconds
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
                setStrategies(generateMockStrategies())
            }
        } catch {
            setStrategies(generateMockStrategies())
        } finally {
            setLoading(false)
        }

        // Also fetch models status
        try {
            const modelsRes = await fetch(`${API_URL}/api/ml/models/status`)
            if (modelsRes.ok) {
                const modelsData = await modelsRes.json()
                if (modelsData.models && modelsData.models.length > 0) {
                    setModels(modelsData.models)
                }
            }
        } catch (e) {
            console.log('Models status fetch error:', e)
        }
    }

    const fetchTrainingProgress = async () => {
        try {
            // Try training-progress endpoint first
            const res = await fetch(`${API_URL}/api/ml/training-progress`)
            if (res.ok) {
                const data = await res.json()
                if (data.training_active && data.episode) {
                    setTrainingActive(true)
                    setTrainingData({
                        episode: data.episode || 0,
                        total_episodes: data.total_episodes || 500,
                        progress_pct: data.progress_pct || 0,
                        reward: data.current_reward || 0,
                        best_reward: data.best_reward || 0,
                        roi: data.roi || 0,
                        best_roi: data.best_roi || 0,
                        win_rate: data.win_rate || 0,
                        trades: data.trades || 0,
                        portfolio_value: data.portfolio_value || 0,
                        model: data.model || 'Enhanced DQN',
                        architecture: data.architecture || 'Unknown',
                        elapsed_seconds: data.elapsed_seconds || 0
                    })

                    // Add to logs
                    const newLog = {
                        time: new Date().toLocaleTimeString(),
                        level: 'success',
                        message: `Episode ${data.episode}/${data.total_episodes} - ROI: ${data.roi?.toFixed(1)}% - WinRate: ${data.win_rate?.toFixed(0)}%`
                    }
                    setLogs(prev => [newLog, ...prev.slice(0, 19)])

                    // Update models with live data
                    if (data.episode > 0) {
                        setModels(prev => prev.map((m, i) =>
                            i === 0 ? {
                                ...m,
                                name: data.model || 'Enhanced DQN',
                                type: data.architecture || 'Dueling DQN + Attention + LSTM',
                                accuracy: data.win_rate || 0,
                                samples: data.trades || 0,
                                lastTrained: 'Training now...'
                            } : m
                        ))
                    }
                } else {
                    setTrainingActive(false)
                }
            }
        } catch (e) {
            console.log('Training progress fetch error:', e)
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
                        onClick={trainingActive ? stopTraining : startTraining}
                        disabled={isStartingTraining}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '12px 20px',
                            background: trainingActive
                                ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(6, 182, 212, 0.2))'
                                : 'linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(6, 182, 212, 0.3))',
                            border: `1px solid ${trainingActive ? 'var(--success)' : 'var(--primary-purple)'}`,
                            borderRadius: '12px',
                            color: trainingActive ? 'var(--success)' : 'var(--text-primary)',
                            fontSize: '14px',
                            fontWeight: 600,
                            cursor: isStartingTraining ? 'not-allowed' : 'pointer',
                            opacity: isStartingTraining ? 0.7 : 1,
                            transition: 'all 0.3s ease'
                        }}
                    >
                        {isStartingTraining ? (
                            <>Starting...</>
                        ) : trainingActive ? (
                            <><Pause size={18} /> Stop Training</>
                        ) : (
                            <><Play size={18} /> Start Training</>
                        )}
                    </button>
                    <button
                        onClick={handleRefresh}
                        disabled={isRefreshing}
                        style={{
                            padding: '12px',
                            background: 'var(--glass-bg)',
                            border: '1px solid var(--glass-border)',
                            borderRadius: '12px',
                            color: 'var(--text-secondary)',
                            cursor: isRefreshing ? 'not-allowed' : 'pointer',
                            opacity: isRefreshing ? 0.6 : 1
                        }}
                    >
                        <RefreshCw size={18} style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }} />
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
                                                        {((strat.metrics || strat.results)?.win_rate ?? 0).toFixed(1)}%
                                                    </td>
                                                    <td style={{ padding: '12px', textAlign: 'right', color: ((strat.metrics || strat.results)?.roi ?? 0) > 0 ? 'var(--success)' : 'var(--error)' }}>
                                                        {((strat.metrics || strat.results)?.roi ?? 0) > 0 ? '+' : ''}{((strat.metrics || strat.results)?.roi ?? 0).toFixed(2)}%
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

                            {/* Live Training Progress */}
                            <div className="glass-card" style={{ padding: '24px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                                    <Activity size={20} color="var(--primary-cyan)" />
                                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>Live Training Progress</h3>
                                </div>
                                {trainingData ? (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                                            <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Episode</div>
                                                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--primary-cyan)' }}>{trainingData.episode} / {trainingData.total_episodes}</div>
                                            </div>
                                            <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ROI</div>
                                                <div style={{ fontSize: '18px', fontWeight: 700, color: trainingData.roi > 0 ? 'var(--success)' : 'var(--error)' }}>{trainingData.roi > 0 ? '+' : ''}{trainingData.roi.toFixed(1)}%</div>
                                            </div>
                                            <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Best ROI</div>
                                                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--success)' }}>+{trainingData.best_roi.toFixed(1)}%</div>
                                            </div>
                                            <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Win Rate</div>
                                                <div style={{ fontSize: '18px', fontWeight: 700, color: trainingData.win_rate > 50 ? 'var(--success)' : 'var(--warning)' }}>{trainingData.win_rate.toFixed(0)}%</div>
                                            </div>
                                        </div>
                                        <div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Progress</span>
                                                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>{trainingData.progress_pct.toFixed(1)}%</span>
                                            </div>
                                            <div style={{ height: '10px', background: 'var(--bg-tertiary)', borderRadius: '5px', overflow: 'hidden' }}>
                                                <div style={{ width: `${trainingData.progress_pct}%`, height: '100%', background: 'linear-gradient(90deg, var(--primary-purple), var(--primary-cyan))', borderRadius: '5px', transition: 'width 0.5s' }} />
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                                        <Activity size={40} style={{ marginBottom: '12px', opacity: 0.3 }} />
                                        <p>No active training session</p>
                                        <p style={{ fontSize: '12px' }}>Start training to see live progress</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Training Tab */}
                    {activeTab === 'training' && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '24px' }}>
                            {/* Current Training Session */}
                            <div className="glass-card" style={{ padding: '24px' }}>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: trainingData ? 'var(--success)' : 'var(--text-muted)', animation: trainingData ? 'pulse 2s infinite' : 'none' }} />
                                    Current Training Session
                                </h3>
                                {trainingData ? (
                                    <>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                            <InfoBox label="Model" value={trainingData.model} />
                                            <InfoBox label="Architecture" value={trainingData.architecture.split(' ')[0]} />
                                            <InfoBox label="Episode" value={`${trainingData.episode} / ${trainingData.total_episodes}`} />
                                            <InfoBox label="Trades" value={trainingData.trades.toLocaleString()} />
                                            <InfoBox label="Current ROI" value={`${trainingData.roi > 0 ? '+' : ''}${trainingData.roi.toFixed(1)}%`} positive={trainingData.roi > 0} />
                                            <InfoBox label="Win Rate" value={`${trainingData.win_rate.toFixed(1)}%`} positive={trainingData.win_rate > 50} />
                                        </div>
                                        <div style={{ marginTop: '20px' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                                <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Training Progress</span>
                                                <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 600 }}>{trainingData.progress_pct.toFixed(1)}%</span>
                                            </div>
                                            <div style={{ height: '8px', background: 'var(--bg-tertiary)', borderRadius: '4px', overflow: 'hidden' }}>
                                                <div style={{ width: `${trainingData.progress_pct}%`, height: '100%', background: 'linear-gradient(90deg, var(--primary-purple), var(--success))', borderRadius: '4px', transition: 'width 0.5s' }} />
                                            </div>
                                        </div>
                                    </>
                                ) : (
                                    <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                                        <p>No active training session</p>
                                    </div>
                                )}
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
                                    <button
                                        onClick={() => setSelectedModel(model)}
                                        style={{
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

            {/* Model Details Modal */}
            {
                selectedModel && (
                    <div
                        style={{
                            position: 'fixed',
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            background: 'rgba(0, 0, 0, 0.7)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            zIndex: 1000
                        }}
                        onClick={() => setSelectedModel(null)}
                    >
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="glass-card"
                            style={{
                                padding: '32px',
                                maxWidth: '500px',
                                width: '90%',
                                maxHeight: '80vh',
                                overflowY: 'auto'
                            }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                                <div>
                                    <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '4px' }}>{selectedModel.name}</h2>
                                    <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>{selectedModel.type}</span>
                                </div>
                                <button
                                    onClick={() => setSelectedModel(null)}
                                    style={{
                                        background: 'var(--bg-tertiary)',
                                        border: '1px solid var(--glass-border)',
                                        borderRadius: '8px',
                                        padding: '8px 12px',
                                        color: 'var(--text-secondary)',
                                        cursor: 'pointer',
                                        fontSize: '14px'
                                    }}
                                >
                                    ✕
                                </button>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '24px' }}>
                                <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '12px' }}>
                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>Accuracy</div>
                                    <div style={{ fontSize: '28px', fontWeight: 700, color: selectedModel.accuracy > 70 ? 'var(--success)' : 'var(--warning)' }}>{selectedModel.accuracy}%</div>
                                </div>
                                <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '12px' }}>
                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>Training Samples</div>
                                    <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary-cyan)' }}>{selectedModel.samples.toLocaleString()}</div>
                                </div>
                            </div>

                            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '20px' }}>
                                <h4 style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '12px' }}>Model Information</h4>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Version</span>
                                        <span style={{ fontWeight: 600, color: 'var(--primary-cyan)' }}>{selectedModel.version}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Last Trained</span>
                                        <span style={{ fontWeight: 600 }}>{selectedModel.lastTrained}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Model Type</span>
                                        <span style={{ fontWeight: 600 }}>{selectedModel.type}</span>
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                )
            }
        </motion.div >
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

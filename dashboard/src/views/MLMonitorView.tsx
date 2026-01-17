import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Brain, Cpu, Activity, TrendingUp, Zap, BarChart3, AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface MLModel {
    status: 'trained' | 'not_trained'
    file_size?: string
    last_updated?: string
    model_type: string
}

interface TrainingProcess {
    type: string
    pid: string
    cpu: string
    memory: string
    time: string
}

interface DQNInfo {
    status: string
    epsilon?: number
    episodes_trained?: number
    last_updated?: string
    avg_reward_last_20?: number
}

interface DQNPrediction {
    status: string
    recommendation?: string
    confidence?: number
    probabilities?: Record<string, number>
}

interface FeatureImportance {
    name: string
    importance: number
}

export default function MLMonitorView() {
    const [models, setModels] = useState<Record<string, MLModel>>({})
    const [trainingActive, setTrainingActive] = useState(false)
    const [trainingProcesses, setTrainingProcesses] = useState<TrainingProcess[]>([])
    const [dqnInfo, setDqnInfo] = useState<DQNInfo | null>(null)
    const [dqnPrediction, setDqnPrediction] = useState<DQNPrediction | null>(null)
    const [features, setFeatures] = useState<FeatureImportance[]>([])
    const [loading, setLoading] = useState(true)
    const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

    const fetchData = async () => {
        try {
            // Fetch ML status
            const statusRes = await fetch(`${API_URL}/api/ml/status`)
            const statusData = await statusRes.json()
            setModels(statusData.models || {})

            // Fetch training progress
            const progressRes = await fetch(`${API_URL}/api/ml/training-progress`)
            const progressData = await progressRes.json()
            setTrainingActive(progressData.training_active)
            setTrainingProcesses(progressData.processes || [])

            // Fetch DQN info
            const dqnRes = await fetch(`${API_URL}/api/ml/dqn/info`)
            const dqnData = await dqnRes.json()
            setDqnInfo(dqnData)

            // Fetch DQN prediction
            const predRes = await fetch(`${API_URL}/api/ml/dqn/predict`)
            const predData = await predRes.json()
            setDqnPrediction(predData)

            // Fetch feature importance
            const featRes = await fetch(`${API_URL}/api/ml/feature-importance`)
            const featData = await featRes.json()
            if (featData.status === 'success') {
                setFeatures(featData.features || [])
            }

            setLastRefresh(new Date())
        } catch (err) {
            console.error('Failed to fetch ML data:', err)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 10000)
        return () => clearInterval(interval)
    }, [])

    const getStatusColor = (status: string) => {
        if (status === 'trained') return 'text-emerald-400'
        if (status === 'not_trained') return 'text-amber-400'
        return 'text-red-400'
    }

    const getStatusIcon = (status: string) => {
        if (status === 'trained') return <CheckCircle2 className="w-5 h-5 text-emerald-400" />
        if (status === 'not_trained') return <AlertCircle className="w-5 h-5 text-amber-400" />
        return <AlertCircle className="w-5 h-5 text-red-400" />
    }

    const getRecommendationColor = (rec: string) => {
        if (rec === 'BUY') return 'text-emerald-400 bg-emerald-400/10'
        if (rec === 'SELL') return 'text-red-400 bg-red-400/10'
        return 'text-gray-400 bg-gray-400/10'
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-cyan-400"></div>
            </div>
        )
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-6 space-y-6"
        >
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Brain className="w-8 h-8 text-purple-400" />
                    <div>
                        <h1 className="text-2xl font-bold text-white">ML / AI Monitor</h1>
                        <p className="text-gray-400 text-sm">Real-time machine learning model status</p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-gray-500 text-sm">
                        Last updated: {lastRefresh.toLocaleTimeString()}
                    </span>
                    <button
                        onClick={fetchData}
                        className="flex items-center gap-2 px-4 py-2 bg-cyan-500/20 text-cyan-400 rounded-lg hover:bg-cyan-500/30 transition-colors"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Training Status Alert */}
            {trainingActive && (
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-purple-500/20 border border-purple-500/50 rounded-xl p-4"
                >
                    <div className="flex items-center gap-3">
                        <div className="animate-pulse">
                            <Zap className="w-6 h-6 text-purple-400" />
                        </div>
                        <div>
                            <h3 className="text-purple-400 font-semibold">Training in Progress</h3>
                            <p className="text-gray-400 text-sm">
                                {trainingProcesses.map(p => `${p.type} (PID: ${p.pid}, CPU: ${p.cpu}%)`).join(', ')}
                            </p>
                        </div>
                    </div>
                </motion.div>
            )}

            {/* Model Status Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(models).map(([key, model]) => (
                    <motion.div
                        key={key}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="bg-gray-800/50 backdrop-blur rounded-xl p-5 border border-gray-700/50"
                    >
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                                {key === 'dqn' && <Activity className="w-5 h-5 text-cyan-400" />}
                                {key === 'gradient_boosting' && <TrendingUp className="w-5 h-5 text-emerald-400" />}
                                {key === 'lstm' && <Cpu className="w-5 h-5 text-purple-400" />}
                                <span className="text-white font-medium capitalize">{key.replace('_', ' ')}</span>
                            </div>
                            {getStatusIcon(model.status)}
                        </div>
                        <p className="text-gray-500 text-sm mb-2">{model.model_type}</p>
                        <div className={`text-sm ${getStatusColor(model.status)}`}>
                            {model.status === 'trained' ? (
                                <>
                                    <span>Size: {model.file_size}</span>
                                    <br />
                                    <span className="text-gray-500">
                                        Updated: {model.last_updated ? new Date(model.last_updated).toLocaleString() : 'Unknown'}
                                    </span>
                                </>
                            ) : (
                                <span>Not trained yet</span>
                            )}
                        </div>
                    </motion.div>
                ))}
            </div>

            {/* DQN Details & Prediction */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* DQN Stats */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-700/50">
                    <div className="flex items-center gap-2 mb-4">
                        <Activity className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-lg font-semibold text-white">DQN Agent Stats</h2>
                    </div>
                    {dqnInfo && dqnInfo.status === 'trained' ? (
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-gray-900/50 rounded-lg p-4">
                                <span className="text-gray-500 text-sm">Episodes Trained</span>
                                <p className="text-2xl font-bold text-white">{dqnInfo.episodes_trained || 0}</p>
                            </div>
                            <div className="bg-gray-900/50 rounded-lg p-4">
                                <span className="text-gray-500 text-sm">Epsilon (Exploration)</span>
                                <p className="text-2xl font-bold text-cyan-400">{dqnInfo.epsilon?.toFixed(4)}</p>
                            </div>
                            <div className="bg-gray-900/50 rounded-lg p-4">
                                <span className="text-gray-500 text-sm">Avg Reward (Last 20)</span>
                                <p className="text-2xl font-bold text-emerald-400">{dqnInfo.avg_reward_last_20?.toFixed(2)}</p>
                            </div>
                            <div className="bg-gray-900/50 rounded-lg p-4">
                                <span className="text-gray-500 text-sm">Last Updated</span>
                                <p className="text-sm text-gray-400">
                                    {dqnInfo.last_updated ? new Date(dqnInfo.last_updated).toLocaleString() : 'Unknown'}
                                </p>
                            </div>
                        </div>
                    ) : (
                        <div className="text-center py-8 text-gray-500">
                            <AlertCircle className="w-12 h-12 mx-auto mb-2 text-amber-400" />
                            <p>DQN Agent not trained yet</p>
                            <p className="text-sm">Run: python rl_trading_agent.py --train</p>
                        </div>
                    )}
                </div>

                {/* DQN Prediction */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-700/50">
                    <div className="flex items-center gap-2 mb-4">
                        <Zap className="w-5 h-5 text-yellow-400" />
                        <h2 className="text-lg font-semibold text-white">AI Recommendation</h2>
                    </div>
                    {dqnPrediction && dqnPrediction.status === 'success' ? (
                        <div className="text-center">
                            <div className={`inline-block px-8 py-4 rounded-xl text-3xl font-bold ${getRecommendationColor(dqnPrediction.recommendation || 'HOLD')}`}>
                                {dqnPrediction.recommendation}
                            </div>
                            <p className="mt-3 text-gray-400">
                                Confidence: <span className="text-white font-semibold">{dqnPrediction.confidence}%</span>
                            </p>
                            <div className="mt-4 grid grid-cols-3 gap-2">
                                {dqnPrediction.probabilities && Object.entries(dqnPrediction.probabilities).map(([action, prob]) => (
                                    <div key={action} className="bg-gray-900/50 rounded-lg p-2">
                                        <span className="text-gray-500 text-xs">{action}</span>
                                        <p className="text-white font-semibold">{prob}%</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="text-center py-8 text-gray-500">
                            <Brain className="w-12 h-12 mx-auto mb-2 text-gray-600" />
                            <p>No prediction available</p>
                            <p className="text-sm">Train the DQN agent first</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Feature Importance */}
            {features.length > 0 && (
                <div className="bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-700/50">
                    <div className="flex items-center gap-2 mb-4">
                        <BarChart3 className="w-5 h-5 text-emerald-400" />
                        <h2 className="text-lg font-semibold text-white">Feature Importance (Gradient Boosting)</h2>
                    </div>
                    <div className="space-y-3">
                        {features.slice(0, 8).map((feature, idx) => (
                            <div key={feature.name} className="flex items-center gap-4">
                                <span className="text-gray-400 w-32 text-sm truncate">{feature.name}</span>
                                <div className="flex-1 bg-gray-700/30 rounded-full h-4 overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${feature.importance}%` }}
                                        transition={{ duration: 0.5, delay: idx * 0.1 }}
                                        className="h-full bg-gradient-to-r from-cyan-500 to-emerald-500 rounded-full"
                                    />
                                </div>
                                <span className="text-white font-medium w-16 text-right">{feature.importance}%</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </motion.div>
    )
}

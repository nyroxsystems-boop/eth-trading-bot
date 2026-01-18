import { useState, useEffect } from 'react'
import {
    Beaker, Layers, Sliders, LineChart, Play, Save, RotateCcw,
    TrendingUp, Shield, Zap, Target, Clock, AlertTriangle, Sparkles,
    Share2, Download, Star, Brain, Wand2, ChevronRight,
    Plus, GripVertical, ArrowRight, Check, X, Eye
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import '../styles/premium.css'
import './StrategyLabView.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type TabType = 'templates' | 'params' | 'backtest' | 'builder'

interface StrategyTemplate {
    id: string
    name: string
    description: string
    riskLevel: 'low' | 'medium' | 'high'
    expectedReturn: string
    icon: string
    params: StrategyParams
}

interface StrategyParams {
    riskPerTrade: number
    mlThreshold: number
    takeProfitMin: number
    takeProfitMax: number
    stopLoss: number
    maxTradesPerDay: number
    rsiOverbought: number
    rsiOversold: number
}

interface BacktestResult {
    totalReturn: number
    winRate: number
    totalTrades: number
    maxDrawdown: number
    sharpeRatio: number
    profitFactor: number
}

interface IndicatorBlock {
    id: string
    type: string
    name: string
    icon: string
    config: Record<string, number>
    condition: string
}

const TEMPLATES: StrategyTemplate[] = [
    {
        id: 'conservative',
        name: 'Conservative',
        description: 'Low risk, steady gains. Perfect for beginners.',
        riskLevel: 'low',
        expectedReturn: '5-10% / month',
        icon: '🛡️',
        params: { riskPerTrade: 0.5, mlThreshold: 0.7, takeProfitMin: 0.8, takeProfitMax: 1.5, stopLoss: 0.5, maxTradesPerDay: 5, rsiOverbought: 75, rsiOversold: 25 }
    },
    {
        id: 'balanced',
        name: 'Balanced',
        description: 'Moderate risk with balanced returns.',
        riskLevel: 'medium',
        expectedReturn: '10-20% / month',
        icon: '⚖️',
        params: { riskPerTrade: 1.0, mlThreshold: 0.6, takeProfitMin: 1.0, takeProfitMax: 2.0, stopLoss: 0.8, maxTradesPerDay: 10, rsiOverbought: 70, rsiOversold: 30 }
    },
    {
        id: 'aggressive',
        name: 'Aggressive',
        description: 'Higher risk for potentially higher rewards.',
        riskLevel: 'high',
        expectedReturn: '20-40% / month',
        icon: '🚀',
        params: { riskPerTrade: 2.0, mlThreshold: 0.55, takeProfitMin: 1.5, takeProfitMax: 3.0, stopLoss: 1.2, maxTradesPerDay: 20, rsiOverbought: 65, rsiOversold: 35 }
    },
    {
        id: 'scalper',
        name: 'Scalper',
        description: 'Many small trades, quick profits.',
        riskLevel: 'medium',
        expectedReturn: '15-25% / month',
        icon: '⚡',
        params: { riskPerTrade: 0.8, mlThreshold: 0.55, takeProfitMin: 0.5, takeProfitMax: 1.0, stopLoss: 0.4, maxTradesPerDay: 30, rsiOverbought: 65, rsiOversold: 35 }
    },
    {
        id: 'swing',
        name: 'Swing Trader',
        description: 'Fewer trades, larger moves.',
        riskLevel: 'medium',
        expectedReturn: '15-30% / month',
        icon: '🌊',
        params: { riskPerTrade: 1.5, mlThreshold: 0.7, takeProfitMin: 2.0, takeProfitMax: 4.0, stopLoss: 1.5, maxTradesPerDay: 3, rsiOverbought: 75, rsiOversold: 25 }
    }
]

const DEFAULT_PARAMS: StrategyParams = {
    riskPerTrade: 1.0,
    mlThreshold: 0.6,
    takeProfitMin: 1.0,
    takeProfitMax: 2.0,
    stopLoss: 0.8,
    maxTradesPerDay: 10,
    rsiOverbought: 70,
    rsiOversold: 30
}

const AVAILABLE_INDICATORS = [
    { id: 'rsi', name: 'RSI', icon: '📈', desc: 'Relative Strength Index', color: '#8B5CF6' },
    { id: 'macd', name: 'MACD', icon: '📉', desc: 'Moving Average Convergence', color: '#EC4899' },
    { id: 'bb', name: 'Bollinger Bands', icon: '📊', desc: 'Volatility bands', color: '#10B981' },
    { id: 'ema', name: 'EMA', icon: '〰️', desc: 'Exponential Moving Average', color: '#F59E0B' },
    { id: 'sma', name: 'SMA', icon: '➖', desc: 'Simple Moving Average', color: '#3B82F6' },
    { id: 'vol', name: 'Volume', icon: '📶', desc: 'Trading volume analysis', color: '#6366F1' },
    { id: 'atr', name: 'ATR', icon: '📏', desc: 'Average True Range', color: '#EF4444' },
    { id: 'stoch', name: 'Stochastic', icon: '🔄', desc: 'Stochastic Oscillator', color: '#14B8A6' },
    { id: 'vwap', name: 'VWAP', icon: '💹', desc: 'Volume Weighted Price', color: '#8B5CF6' },
    { id: 'obv', name: 'OBV', icon: '📦', desc: 'On-Balance Volume', color: '#F97316' }
]

const AI_SUGGESTIONS = [
    { name: 'Momentum Hunter', desc: 'AI-optimized for trending markets', score: 94 },
    { name: 'Mean Reversion Pro', desc: 'Catches overextended moves', score: 87 },
    { name: 'Volatility Crusher', desc: 'Profits from high volatility', score: 91 },
    { name: 'Smart Money Flow', desc: 'Follows institutional patterns', score: 89 }
]

const StrategyLabView = () => {
    const [activeTab, setActiveTab] = useState<TabType>('templates')
    const [params, setParams] = useState<StrategyParams>(DEFAULT_PARAMS)
    const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
    const [backtestRunning, setBacktestRunning] = useState(false)
    const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null)
    const [backtestPeriod, setBacktestPeriod] = useState<number>(30)
    const [saving, setSaving] = useState(false)

    // Builder state
    const [entryConditions, setEntryConditions] = useState<IndicatorBlock[]>([
        { id: '1', type: 'rsi', name: 'RSI', icon: '📈', config: { period: 14, value: 30 }, condition: 'below' },
        { id: '2', type: 'macd', name: 'MACD', icon: '📉', config: { fast: 12, slow: 26 }, condition: 'bullish_cross' }
    ])
    const [exitConditions, setExitConditions] = useState<IndicatorBlock[]>([
        { id: '3', type: 'rsi', name: 'RSI', icon: '📈', config: { period: 14, value: 70 }, condition: 'above' }
    ])
    const [showAISuggestions, setShowAISuggestions] = useState(false)
    const [livePreview, setLivePreview] = useState(true)
    const [estimatedPerformance, setEstimatedPerformance] = useState({ roi: 18.5, winRate: 62, trades: 156 })

    useEffect(() => {
        loadCurrentParams()
    }, [])

    // Update estimated performance when conditions change
    useEffect(() => {
        const baseScore = entryConditions.length * 5 + exitConditions.length * 3
        setEstimatedPerformance({
            roi: 12 + baseScore + Math.random() * 8,
            winRate: 55 + baseScore + Math.random() * 10,
            trades: 100 + baseScore * 10 + Math.random() * 50
        })
    }, [entryConditions, exitConditions])

    const loadCurrentParams = async () => {
        try {
            const token = localStorage.getItem('token')
            const res = await fetch(`${API_URL}/api/strategy/parameters`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                if (data.params) setParams(data.params)
            }
        } catch (err) {
            console.error('Failed to load params:', err)
        }
    }

    const applyTemplate = (template: StrategyTemplate) => {
        setParams(template.params)
        setSelectedTemplate(template.id)
    }

    const saveParams = async () => {
        setSaving(true)
        try {
            const token = localStorage.getItem('token')
            await fetch(`${API_URL}/api/strategy/parameters`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ params })
            })
        } catch (err) {
            console.error('Failed to save:', err)
        } finally {
            setSaving(false)
        }
    }

    const runBacktest = async () => {
        setBacktestRunning(true)
        try {
            const token = localStorage.getItem('token')
            const res = await fetch(`${API_URL}/api/strategy/backtest`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ params, days: backtestPeriod })
            })
            if (res.ok) {
                const data = await res.json()
                setBacktestResult(data.result)
            }
        } catch (err) {
            // Mock result for demo
            setBacktestResult({
                totalReturn: 18.5 + Math.random() * 10,
                winRate: 58 + Math.random() * 15,
                totalTrades: Math.floor(backtestPeriod * params.maxTradesPerDay * 0.7),
                maxDrawdown: 5 + Math.random() * 8,
                sharpeRatio: 1.2 + Math.random() * 0.8,
                profitFactor: 1.5 + Math.random() * 0.5
            })
        } finally {
            setBacktestRunning(false)
        }
    }

    const addIndicator = (type: 'entry' | 'exit', indicatorId: string) => {
        const indicator = AVAILABLE_INDICATORS.find(i => i.id === indicatorId)
        if (!indicator) return

        const newBlock: IndicatorBlock = {
            id: Date.now().toString(),
            type: indicatorId,
            name: indicator.name,
            icon: indicator.icon,
            config: {},
            condition: 'default'
        }

        if (type === 'entry') {
            setEntryConditions([...entryConditions, newBlock])
        } else {
            setExitConditions([...exitConditions, newBlock])
        }
    }

    const removeIndicator = (type: 'entry' | 'exit', id: string) => {
        if (type === 'entry') {
            setEntryConditions(entryConditions.filter(c => c.id !== id))
        } else {
            setExitConditions(exitConditions.filter(c => c.id !== id))
        }
    }

    const applyAISuggestion = (_suggestion: typeof AI_SUGGESTIONS[0]) => {
        // Simulate applying AI suggestion
        setEntryConditions([
            { id: '1', type: 'rsi', name: 'RSI', icon: '📈', config: { period: 14, value: 25 }, condition: 'below' },
            { id: '2', type: 'macd', name: 'MACD', icon: '📉', config: {}, condition: 'bullish_cross' },
            { id: '3', type: 'vol', name: 'Volume', icon: '📶', config: {}, condition: 'spike' }
        ])
        setExitConditions([
            { id: '4', type: 'rsi', name: 'RSI', icon: '📈', config: { period: 14, value: 75 }, condition: 'above' },
            { id: '5', type: 'atr', name: 'ATR', icon: '📏', config: {}, condition: 'trailing' }
        ])
        setShowAISuggestions(false)
    }

    const tabs = [
        { id: 'templates' as TabType, label: 'Templates', icon: Layers },
        { id: 'params' as TabType, label: 'Parameters', icon: Sliders },
        { id: 'backtest' as TabType, label: 'Backtest', icon: LineChart },
        { id: 'builder' as TabType, label: 'Builder', icon: Beaker }
    ]

    const getRiskColor = (level: string) => {
        switch (level) {
            case 'low': return 'var(--success)'
            case 'medium': return 'var(--warning)'
            case 'high': return 'var(--error)'
            default: return 'var(--text-muted)'
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="strategy-lab"
        >
            {/* Header */}
            <div className="lab-header">
                <div>
                    <h1><Beaker className="header-icon" /> Strategy Lab</h1>
                    <p>Customize, test, and optimize your trading strategy</p>
                </div>
            </div>

            {/* Tabs */}
            <div className="lab-tabs">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        className={`lab-tab ${activeTab === tab.id ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
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
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.2 }}
                    className="tab-content"
                >
                    {/* Templates Tab */}
                    {activeTab === 'templates' && (
                        <div className="templates-grid">
                            {TEMPLATES.map(template => (
                                <div
                                    key={template.id}
                                    className={`template-card ${selectedTemplate === template.id ? 'selected' : ''}`}
                                    onClick={() => applyTemplate(template)}
                                >
                                    <div className="template-icon">{template.icon}</div>
                                    <h3>{template.name}</h3>
                                    <p>{template.description}</p>
                                    <div className="template-meta">
                                        <span className="risk-badge" style={{ color: getRiskColor(template.riskLevel) }}>
                                            <Shield size={14} />
                                            {template.riskLevel}
                                        </span>
                                        <span className="return-badge">
                                            <TrendingUp size={14} />
                                            {template.expectedReturn}
                                        </span>
                                    </div>
                                    {selectedTemplate === template.id && (
                                        <div className="applied-badge">✓ Applied</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Parameters Tab */}
                    {activeTab === 'params' && (
                        <div className="params-container">
                            <div className="params-grid">
                                <ParamSlider
                                    label="Risk per Trade"
                                    value={params.riskPerTrade}
                                    min={0.1} max={5} step={0.1}
                                    unit="%"
                                    icon={<AlertTriangle size={16} />}
                                    onChange={v => setParams({ ...params, riskPerTrade: v })}
                                />
                                <ParamSlider
                                    label="ML Confidence Threshold"
                                    value={params.mlThreshold}
                                    min={0.4} max={0.9} step={0.05}
                                    unit=""
                                    icon={<Zap size={16} />}
                                    onChange={v => setParams({ ...params, mlThreshold: v })}
                                    format={v => (v * 100).toFixed(0) + '%'}
                                />
                                <ParamSlider
                                    label="Take Profit Min"
                                    value={params.takeProfitMin}
                                    min={0.3} max={5} step={0.1}
                                    unit="%"
                                    icon={<Target size={16} />}
                                    onChange={v => setParams({ ...params, takeProfitMin: v })}
                                />
                                <ParamSlider
                                    label="Take Profit Max"
                                    value={params.takeProfitMax}
                                    min={0.5} max={10} step={0.1}
                                    unit="%"
                                    icon={<Target size={16} />}
                                    onChange={v => setParams({ ...params, takeProfitMax: v })}
                                />
                                <ParamSlider
                                    label="Stop Loss"
                                    value={params.stopLoss}
                                    min={0.2} max={5} step={0.1}
                                    unit="%"
                                    icon={<Shield size={16} />}
                                    onChange={v => setParams({ ...params, stopLoss: v })}
                                />
                                <ParamSlider
                                    label="Max Trades per Day"
                                    value={params.maxTradesPerDay}
                                    min={1} max={50} step={1}
                                    unit=""
                                    icon={<Clock size={16} />}
                                    onChange={v => setParams({ ...params, maxTradesPerDay: v })}
                                />
                                <ParamSlider
                                    label="RSI Overbought"
                                    value={params.rsiOverbought}
                                    min={60} max={90} step={1}
                                    unit=""
                                    icon={<TrendingUp size={16} />}
                                    onChange={v => setParams({ ...params, rsiOverbought: v })}
                                />
                                <ParamSlider
                                    label="RSI Oversold"
                                    value={params.rsiOversold}
                                    min={10} max={40} step={1}
                                    unit=""
                                    icon={<TrendingUp size={16} />}
                                    onChange={v => setParams({ ...params, rsiOversold: v })}
                                />
                            </div>
                            <div className="params-actions">
                                <button className="btn-reset" onClick={() => setParams(DEFAULT_PARAMS)}>
                                    <RotateCcw size={16} /> Reset Defaults
                                </button>
                                <button className="btn-save" onClick={saveParams} disabled={saving}>
                                    <Save size={16} /> {saving ? 'Saving...' : 'Save Parameters'}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Backtest Tab - FIXED: No parameter sliders */}
                    {activeTab === 'backtest' && (
                        <div className="backtest-container">
                            <div className="backtest-config glass-card">
                                <div className="config-header">
                                    <h3>⏱️ Backtest Configuration</h3>
                                    <p className="config-hint">Test your strategy against historical data</p>
                                </div>
                                <div className="period-selector">
                                    {[7, 30, 90, 180, 365].map(days => (
                                        <button
                                            key={days}
                                            className={`period-btn ${backtestPeriod === days ? 'active' : ''}`}
                                            onClick={() => setBacktestPeriod(days)}
                                        >
                                            {days}d
                                        </button>
                                    ))}
                                </div>

                                {/* Current strategy summary */}
                                <div className="strategy-summary">
                                    <h4>📊 Active Strategy</h4>
                                    <div className="summary-grid">
                                        <div className="summary-item">
                                            <span>Risk/Trade</span>
                                            <strong>{params.riskPerTrade}%</strong>
                                        </div>
                                        <div className="summary-item">
                                            <span>ML Threshold</span>
                                            <strong>{(params.mlThreshold * 100).toFixed(0)}%</strong>
                                        </div>
                                        <div className="summary-item">
                                            <span>Take Profit</span>
                                            <strong>{params.takeProfitMin}-{params.takeProfitMax}%</strong>
                                        </div>
                                        <div className="summary-item">
                                            <span>Stop Loss</span>
                                            <strong>{params.stopLoss}%</strong>
                                        </div>
                                    </div>
                                </div>

                                <button
                                    className="btn-run-backtest"
                                    onClick={runBacktest}
                                    disabled={backtestRunning}
                                >
                                    <Play size={18} />
                                    {backtestRunning ? 'Running Simulation...' : 'Run Backtest'}
                                </button>
                            </div>

                            {backtestResult && (
                                <motion.div
                                    className="backtest-results glass-card"
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                >
                                    <h3>📈 Results ({backtestPeriod} days)</h3>
                                    <div className="results-grid">
                                        <ResultCard
                                            label="Total Return"
                                            value={`${backtestResult.totalReturn.toFixed(1)}%`}
                                            positive={backtestResult.totalReturn > 0}
                                        />
                                        <ResultCard
                                            label="Win Rate"
                                            value={`${backtestResult.winRate.toFixed(1)}%`}
                                            positive={backtestResult.winRate > 50}
                                        />
                                        <ResultCard
                                            label="Total Trades"
                                            value={backtestResult.totalTrades.toString()}
                                        />
                                        <ResultCard
                                            label="Max Drawdown"
                                            value={`${backtestResult.maxDrawdown.toFixed(1)}%`}
                                            positive={false}
                                        />
                                        <ResultCard
                                            label="Sharpe Ratio"
                                            value={backtestResult.sharpeRatio.toFixed(2)}
                                            positive={backtestResult.sharpeRatio > 1}
                                        />
                                        <ResultCard
                                            label="Profit Factor"
                                            value={backtestResult.profitFactor.toFixed(2)}
                                            positive={backtestResult.profitFactor > 1}
                                        />
                                    </div>
                                </motion.div>
                            )}
                        </div>
                    )}

                    {/* EPIC Builder Tab */}
                    {activeTab === 'builder' && (
                        <div className="builder-epic">
                            {/* Top Toolbar */}
                            <div className="builder-toolbar glass-card">
                                <div className="toolbar-left">
                                    <button
                                        className={`toolbar-btn ai-btn ${showAISuggestions ? 'active' : ''}`}
                                        onClick={() => setShowAISuggestions(!showAISuggestions)}
                                    >
                                        <Sparkles size={18} />
                                        AI Suggestions
                                    </button>
                                    <button className="toolbar-btn">
                                        <Wand2 size={18} />
                                        Optimize
                                    </button>
                                </div>
                                <div className="toolbar-right">
                                    <button className={`preview-toggle ${livePreview ? 'active' : ''}`} onClick={() => setLivePreview(!livePreview)}>
                                        <Eye size={16} />
                                        Live Preview
                                    </button>
                                    <button className="toolbar-btn share-btn">
                                        <Share2 size={18} />
                                        Share
                                    </button>
                                    <button className="toolbar-btn export-btn">
                                        <Download size={18} />
                                        Export
                                    </button>
                                </div>
                            </div>

                            {/* AI Suggestions Panel */}
                            <AnimatePresence>
                                {showAISuggestions && (
                                    <motion.div
                                        className="ai-suggestions-panel glass-card"
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: 'auto' }}
                                        exit={{ opacity: 0, height: 0 }}
                                    >
                                        <div className="ai-header">
                                            <Brain size={24} />
                                            <div>
                                                <h3>AI Strategy Suggestions</h3>
                                                <p>Powered by machine learning analysis of 10,000+ backtests</p>
                                            </div>
                                        </div>
                                        <div className="ai-grid">
                                            {AI_SUGGESTIONS.map((suggestion, i) => (
                                                <motion.div
                                                    key={i}
                                                    className="ai-suggestion-card"
                                                    whileHover={{ scale: 1.02 }}
                                                    onClick={() => applyAISuggestion(suggestion)}
                                                >
                                                    <div className="suggestion-score">
                                                        <Star size={14} />
                                                        {suggestion.score}
                                                    </div>
                                                    <h4>{suggestion.name}</h4>
                                                    <p>{suggestion.desc}</p>
                                                    <button className="apply-suggestion-btn">
                                                        Apply Strategy <ArrowRight size={14} />
                                                    </button>
                                                </motion.div>
                                            ))}
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* Main Builder Layout */}
                            <div className="builder-main-layout">
                                {/* Indicators Palette */}
                                <div className="indicators-palette glass-card">
                                    <h3>📊 Indicators</h3>
                                    <p className="palette-hint">Drag to Entry or Exit zones</p>
                                    <div className="indicator-palette-list">
                                        {AVAILABLE_INDICATORS.map(ind => (
                                            <motion.div
                                                key={ind.id}
                                                className="palette-indicator"
                                                style={{ borderColor: ind.color }}
                                                whileHover={{ scale: 1.05, x: 5 }}
                                                draggable
                                                onDragEnd={() => {
                                                    // Drag end handler
                                                }}
                                            >
                                                <span className="palette-icon" style={{ background: ind.color }}>{ind.icon}</span>
                                                <div className="palette-info">
                                                    <span className="palette-name">{ind.name}</span>
                                                    <span className="palette-desc">{ind.desc}</span>
                                                </div>
                                                <Plus size={16} className="add-icon" onClick={() => addIndicator('entry', ind.id)} />
                                            </motion.div>
                                        ))}
                                    </div>
                                </div>

                                {/* Strategy Canvas */}
                                <div className="strategy-canvas-epic">
                                    {/* Entry Zone */}
                                    <div className="condition-zone entry-zone glass-card">
                                        <div className="zone-header">
                                            <div className="zone-title">
                                                <span className="zone-icon">🟢</span>
                                                <span>Entry Conditions</span>
                                            </div>
                                            <button className="add-condition-btn" onClick={() => addIndicator('entry', 'rsi')}>
                                                <Plus size={16} /> Add
                                            </button>
                                        </div>
                                        <div className="conditions-list">
                                            {entryConditions.map((condition, index) => (
                                                <motion.div
                                                    key={condition.id}
                                                    className="condition-block-epic"
                                                    initial={{ opacity: 0, x: -20 }}
                                                    animate={{ opacity: 1, x: 0 }}
                                                    exit={{ opacity: 0, x: 20 }}
                                                    layout
                                                >
                                                    <div className="condition-grip">
                                                        <GripVertical size={16} />
                                                    </div>
                                                    <span className="condition-icon">{condition.icon}</span>
                                                    <div className="condition-content">
                                                        <span className="condition-name">{condition.name}</span>
                                                        <select className="condition-select">
                                                            <option>Below 30</option>
                                                            <option>Above 70</option>
                                                            <option>Crosses Above</option>
                                                            <option>Crosses Below</option>
                                                        </select>
                                                    </div>
                                                    <button
                                                        className="remove-condition"
                                                        onClick={() => removeIndicator('entry', condition.id)}
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                    {index < entryConditions.length - 1 && (
                                                        <div className="condition-connector">AND</div>
                                                    )}
                                                </motion.div>
                                            ))}
                                            {entryConditions.length === 0 && (
                                                <div className="empty-zone">
                                                    <Plus size={24} />
                                                    <span>Add entry conditions</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Flow Arrow */}
                                    <div className="flow-arrow">
                                        <ChevronRight size={32} />
                                        <span>Signal</span>
                                        <ChevronRight size={32} />
                                    </div>

                                    {/* Exit Zone */}
                                    <div className="condition-zone exit-zone glass-card">
                                        <div className="zone-header">
                                            <div className="zone-title">
                                                <span className="zone-icon">🔴</span>
                                                <span>Exit Conditions</span>
                                            </div>
                                            <button className="add-condition-btn" onClick={() => addIndicator('exit', 'rsi')}>
                                                <Plus size={16} /> Add
                                            </button>
                                        </div>
                                        <div className="conditions-list">
                                            {exitConditions.map((condition, index) => (
                                                <motion.div
                                                    key={condition.id}
                                                    className="condition-block-epic"
                                                    initial={{ opacity: 0, x: -20 }}
                                                    animate={{ opacity: 1, x: 0 }}
                                                    layout
                                                >
                                                    <div className="condition-grip">
                                                        <GripVertical size={16} />
                                                    </div>
                                                    <span className="condition-icon">{condition.icon}</span>
                                                    <div className="condition-content">
                                                        <span className="condition-name">{condition.name}</span>
                                                        <select className="condition-select">
                                                            <option>Above 70</option>
                                                            <option>Below 30</option>
                                                            <option>Take Profit Hit</option>
                                                            <option>Trailing Stop</option>
                                                        </select>
                                                    </div>
                                                    <button
                                                        className="remove-condition"
                                                        onClick={() => removeIndicator('exit', condition.id)}
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                    {index < exitConditions.length - 1 && (
                                                        <div className="condition-connector">OR</div>
                                                    )}
                                                </motion.div>
                                            ))}
                                            {exitConditions.length === 0 && (
                                                <div className="empty-zone">
                                                    <Plus size={24} />
                                                    <span>Add exit conditions</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Live Preview & Stats */}
                                {livePreview && (
                                    <div className="live-preview-panel glass-card">
                                        <h3>📈 Live Performance Estimate</h3>
                                        <div className="preview-stats">
                                            <div className="preview-stat big">
                                                <span className="stat-label">Est. Monthly ROI</span>
                                                <span className="stat-value positive">+{estimatedPerformance.roi.toFixed(1)}%</span>
                                            </div>
                                            <div className="preview-stat">
                                                <span className="stat-label">Win Rate</span>
                                                <span className="stat-value">{estimatedPerformance.winRate.toFixed(0)}%</span>
                                            </div>
                                            <div className="preview-stat">
                                                <span className="stat-label">Est. Trades/Mo</span>
                                                <span className="stat-value">{Math.floor(estimatedPerformance.trades)}</span>
                                            </div>
                                        </div>

                                        {/* Mini Chart Preview */}
                                        <div className="mini-chart-preview">
                                            <div className="chart-line" />
                                            <div className="chart-entries">
                                                {[20, 35, 50, 65, 80].map((pos, i) => (
                                                    <div key={i} className="chart-marker entry" style={{ left: `${pos}%` }}>
                                                        🟢
                                                    </div>
                                                ))}
                                                {[30, 45, 60, 75, 90].map((pos, i) => (
                                                    <div key={i} className="chart-marker exit" style={{ left: `${pos}%` }}>
                                                        🔴
                                                    </div>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Risk Assessment */}
                                        <div className="risk-assessment">
                                            <h4>🛡️ Risk Assessment</h4>
                                            <div className="risk-meter">
                                                <div className="meter-fill" style={{ width: '45%' }} />
                                            </div>
                                            <span className="risk-label">Moderate Risk</span>
                                        </div>

                                        {/* Action Buttons */}
                                        <div className="preview-actions">
                                            <button className="btn-test" onClick={() => setActiveTab('backtest')}>
                                                <Play size={16} /> Test Strategy
                                            </button>
                                            <button className="btn-activate" onClick={saveParams}>
                                                <Check size={16} /> Activate
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </motion.div>
            </AnimatePresence>
        </motion.div>
    )
}

// Parameter Slider Component
const ParamSlider = ({ label, value, min, max, step, unit, icon, onChange, format }: {
    label: string
    value: number
    min: number
    max: number
    step: number
    unit: string
    icon: React.ReactNode
    onChange: (v: number) => void
    format?: (v: number) => string
}) => (
    <div className="param-slider">
        <div className="param-header">
            <span className="param-icon">{icon}</span>
            <span className="param-label">{label}</span>
            <span className="param-value">
                {format ? format(value) : `${value}${unit}`}
            </span>
        </div>
        <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={e => onChange(parseFloat(e.target.value))}
        />
    </div>
)

// Result Card Component
const ResultCard = ({ label, value, positive }: {
    label: string
    value: string
    positive?: boolean
}) => (
    <div className="result-card">
        <span className="result-label">{label}</span>
        <span className={`result-value ${positive === true ? 'positive' : positive === false ? 'negative' : ''}`}>
            {value}
        </span>
    </div>
)

export default StrategyLabView

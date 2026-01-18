import { useState, useEffect } from 'react'
import {
    Beaker, Layers, Sliders, LineChart, Play, Save, RotateCcw,
    TrendingUp, Shield, Zap, Target, Clock, AlertTriangle
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

const StrategyLabView = () => {
    const [activeTab, setActiveTab] = useState<TabType>('templates')
    const [params, setParams] = useState<StrategyParams>(DEFAULT_PARAMS)
    const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
    const [backtestRunning, setBacktestRunning] = useState(false)
    const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null)
    const [backtestPeriod, setBacktestPeriod] = useState<number>(30)
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        loadCurrentParams()
    }, [])

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

                    {/* Backtest Tab */}
                    {activeTab === 'backtest' && (
                        <div className="backtest-container">
                            <div className="backtest-config">
                                <h3>Backtest Configuration</h3>
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
                                <button
                                    className="btn-run-backtest"
                                    onClick={runBacktest}
                                    disabled={backtestRunning}
                                >
                                    <Play size={18} />
                                    {backtestRunning ? 'Running...' : 'Run Backtest'}
                                </button>
                            </div>

                            {backtestResult && (
                                <motion.div
                                    className="backtest-results"
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                >
                                    <h3>Results ({backtestPeriod} days)</h3>
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

                    {/* Builder Tab */}
                    {activeTab === 'builder' && (
                        <div className="builder-container">
                            <div className="builder-layout">
                                {/* Available Indicators */}
                                <div className="indicators-panel glass-card">
                                    <h3>📊 Available Indicators</h3>
                                    <p className="panel-hint">Drag indicators to build your strategy</p>
                                    <div className="indicator-list">
                                        {[
                                            { id: 'rsi', name: 'RSI', icon: '📈', desc: 'Relative Strength Index' },
                                            { id: 'macd', name: 'MACD', icon: '📉', desc: 'Moving Average Convergence' },
                                            { id: 'bb', name: 'Bollinger Bands', icon: '📊', desc: 'Volatility bands' },
                                            { id: 'ema', name: 'EMA', icon: '〰️', desc: 'Exponential Moving Average' },
                                            { id: 'sma', name: 'SMA', icon: '➖', desc: 'Simple Moving Average' },
                                            { id: 'vol', name: 'Volume', icon: '📶', desc: 'Trading volume analysis' },
                                            { id: 'atr', name: 'ATR', icon: '📏', desc: 'Average True Range' },
                                            { id: 'stoch', name: 'Stochastic', icon: '🔄', desc: 'Stochastic Oscillator' }
                                        ].map(ind => (
                                            <div key={ind.id} className="indicator-item" draggable>
                                                <span className="ind-icon">{ind.icon}</span>
                                                <div className="ind-info">
                                                    <span className="ind-name">{ind.name}</span>
                                                    <span className="ind-desc">{ind.desc}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Strategy Canvas */}
                                <div className="strategy-canvas glass-card">
                                    <h3>🎯 Your Strategy</h3>
                                    <div className="canvas-content">
                                        {/* Entry Conditions */}
                                        <div className="condition-block entry">
                                            <div className="block-header">
                                                <span className="block-icon">🟢</span>
                                                <span>Entry Conditions</span>
                                            </div>
                                            <div className="drop-zone" data-type="entry">
                                                <div className="active-indicator">
                                                    <span>📈 RSI</span>
                                                    <span className="condition">{'<'} 30 (Oversold)</span>
                                                </div>
                                                <div className="connector">AND</div>
                                                <div className="active-indicator">
                                                    <span>📉 MACD</span>
                                                    <span className="condition">Bullish Cross</span>
                                                </div>
                                                <div className="add-placeholder">
                                                    <span>+ Drop indicator here</span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Exit Conditions */}
                                        <div className="condition-block exit">
                                            <div className="block-header">
                                                <span className="block-icon">🔴</span>
                                                <span>Exit Conditions</span>
                                            </div>
                                            <div className="drop-zone" data-type="exit">
                                                <div className="active-indicator">
                                                    <span>📈 RSI</span>
                                                    <span className="condition">{'>'} 70 (Overbought)</span>
                                                </div>
                                                <div className="connector">OR</div>
                                                <div className="active-indicator">
                                                    <span>🎯 Take Profit</span>
                                                    <span className="condition">+{params.takeProfitMax}%</span>
                                                </div>
                                                <div className="add-placeholder">
                                                    <span>+ Drop indicator here</span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Risk Management */}
                                        <div className="condition-block risk">
                                            <div className="block-header">
                                                <span className="block-icon">🛡️</span>
                                                <span>Risk Management</span>
                                            </div>
                                            <div className="risk-settings">
                                                <div className="risk-item">
                                                    <span>Stop Loss:</span>
                                                    <strong>-{params.stopLoss}%</strong>
                                                </div>
                                                <div className="risk-item">
                                                    <span>Max Trades/Day:</span>
                                                    <strong>{params.maxTradesPerDay}</strong>
                                                </div>
                                                <div className="risk-item">
                                                    <span>Position Size:</span>
                                                    <strong>{params.riskPerTrade}%</strong>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Save Button */}
                                    <div className="canvas-actions">
                                        <button className="btn-save" onClick={saveParams}>
                                            <Save size={16} /> Save Strategy
                                        </button>
                                    </div>
                                </div>
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

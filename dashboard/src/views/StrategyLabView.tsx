import { useState, useEffect, useRef } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import { Play, RotateCcw, TrendingUp, Target, Zap } from 'lucide-react'
import '../styles/premium.css'
import '../styles/components.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface BacktestResult {
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number
    total_pnl: number
    roi: number
    sharpe_ratio: number
    max_drawdown: number
}

const StrategyLabView = () => {
    const chartContainerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<any>(null)
    const candlestickSeriesRef = useRef<any>(null)

    // Strategy Parameters
    const [params, setParams] = useState({
        ml_threshold: 0.52,
        risk_per_trade: 0.006,
        tp_min: 0.010,
        tp_max: 0.015,
        stop_floor: 0.005,
        max_trades_per_day: 15,
    })

    const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null)
    const [loading, setLoading] = useState(false)

    // Initialize Chart
    useEffect(() => {
        if (!chartContainerRef.current) return

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#CBD5E1',
            },
            grid: {
                vertLines: { color: 'rgba(139, 92, 246, 0.1)' },
                horzLines: { color: 'rgba(139, 92, 246, 0.1)' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 500,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
        })

        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#10B981',
            downColor: '#EF4444',
            borderVisible: false,
            wickUpColor: '#10B981',
            wickDownColor: '#EF4444',
        })

        chartRef.current = chart
        candlestickSeriesRef.current = candlestickSeries

        // Load initial data
        loadChartData()

        // Handle resize
        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                })
            }
        }

        window.addEventListener('resize', handleResize)

        return () => {
            window.removeEventListener('resize', handleResize)
            chart.remove()
        }
    }, [])

    const loadChartData = async () => {
        try {
            const data = generateCandlestickData(100)
            if (candlestickSeriesRef.current) {
                candlestickSeriesRef.current.setData(data)
            }
        } catch (err) {
            console.error('Failed to load chart data:', err)
        }
    }

    const generateCandlestickData = (count: number) => {
        const data = []
        let basePrice = 3200
        const now = Math.floor(Date.now() / 1000)

        for (let i = count - 1; i >= 0; i--) {
            const time = now - (i * 900) as any
            const volatility = 15
            const open = basePrice + (Math.random() - 0.5) * volatility
            const close = open + (Math.random() - 0.5) * volatility * 1.5
            const high = Math.max(open, close) + Math.random() * (volatility * 0.5)
            const low = Math.min(open, close) - Math.random() * (volatility * 0.5)

            data.push({ time, open, high, low, close })
            basePrice = close
        }

        return data
    }

    const runBacktest = async () => {
        setLoading(true)
        try {
            const res = await fetch(`${API_URL}/api/backtest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params),
            })
            const result = await res.json()
            setBacktestResult(result)
        } catch (err) {
            console.error('Backtest failed:', err)
        } finally {
            setLoading(false)
        }
    }

    const resetParams = () => {
        setParams({
            ml_threshold: 0.52,
            risk_per_trade: 0.006,
            tp_min: 0.010,
            tp_max: 0.015,
            stop_floor: 0.005,
            max_trades_per_day: 15,
        })
        setBacktestResult(null)
    }

    return (
        <div style={{ padding: '24px', maxWidth: '1920px', margin: '0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px' }}>
                <div>
                    <h1 style={{ fontSize: '32px', fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: '8px' }}>
                        Strategy Testing Lab
                    </h1>
                    <p style={{ color: '#94A3B8', fontSize: '16px' }}>Test different parameters and see results in real-time</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button className="btn-primary" onClick={resetParams}>
                        <RotateCcw size={18} />
                        Reset
                    </button>
                    <button className="btn-primary" onClick={runBacktest} disabled={loading}>
                        {loading ? 'Running...' : <><Play size={18} /> Run Backtest</>}
                    </button>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
                {/* Chart */}
                <div className="glass-card" style={{ gridColumn: '1 / 2', gridRow: '1 / 3', padding: '24px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 600 }}>ETH/USDT - 15M</h3>
                    </div>
                    <div ref={chartContainerRef} style={{ borderRadius: '12px', overflow: 'hidden' }} />
                </div>

                {/* Parameters */}
                <div className="glass-card" style={{ padding: '24px' }}>
                    <h3 style={{ marginBottom: '24px' }}>Strategy Parameters</h3>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                            ML Threshold
                            <span style={{ fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                {params.ml_threshold.toFixed(2)}
                            </span>
                        </label>
                        <input type="range" className="slider" min="0.30" max="0.70" step="0.01" value={params.ml_threshold}
                            onChange={(e) => setParams({ ...params, ml_threshold: parseFloat(e.target.value) })} />
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                            Risk per Trade
                            <span style={{ fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                {(params.risk_per_trade * 100).toFixed(2)}%
                            </span>
                        </label>
                        <input type="range" className="slider" min="0.003" max="0.020" step="0.001" value={params.risk_per_trade}
                            onChange={(e) => setParams({ ...params, risk_per_trade: parseFloat(e.target.value) })} />
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                            Take Profit Min
                            <span style={{ fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                {(params.tp_min * 100).toFixed(2)}%
                            </span>
                        </label>
                        <input type="range" className="slider" min="0.005" max="0.020" step="0.001" value={params.tp_min}
                            onChange={(e) => setParams({ ...params, tp_min: parseFloat(e.target.value) })} />
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                            Take Profit Max
                            <span style={{ fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                {(params.tp_max * 100).toFixed(2)}%
                            </span>
                        </label>
                        <input type="range" className="slider" min="0.010" max="0.030" step="0.001" value={params.tp_max}
                            onChange={(e) => setParams({ ...params, tp_max: parseFloat(e.target.value) })} />
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                            Stop Loss
                            <span style={{ fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                {(params.stop_floor * 100).toFixed(2)}%
                            </span>
                        </label>
                        <input type="range" className="slider" min="0.003" max="0.015" step="0.001" value={params.stop_floor}
                            onChange={(e) => setParams({ ...params, stop_floor: parseFloat(e.target.value) })} />
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                            Max Trades/Day
                            <span style={{ fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                                {params.max_trades_per_day}
                            </span>
                        </label>
                        <input type="range" className="slider" min="5" max="30" step="1" value={params.max_trades_per_day}
                            onChange={(e) => setParams({ ...params, max_trades_per_day: parseInt(e.target.value) })} />
                    </div>
                </div>

                {/* Results */}
                {backtestResult && (
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <h3 style={{ marginBottom: '24px' }}>Backtest Results</h3>

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                <div style={{ width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '12px', background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', color: 'white' }}>
                                    <TrendingUp size={24} />
                                </div>
                                <div>
                                    <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Total P&L</div>
                                    <div style={{ fontSize: '20px', fontWeight: 700, color: backtestResult.total_pnl >= 0 ? '#10B981' : '#EF4444' }}>
                                        ${backtestResult.total_pnl.toFixed(2)}
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                <div style={{ width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '12px', background: 'linear-gradient(135deg, #06B6D4 0%, #3B82F6 100%)', color: 'white' }}>
                                    <Target size={24} />
                                </div>
                                <div>
                                    <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Win Rate</div>
                                    <div style={{ fontSize: '20px', fontWeight: 700 }}>{backtestResult.win_rate.toFixed(1)}%</div>
                                </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                <div style={{ width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '12px', background: 'linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)', color: 'white' }}>
                                    <Zap size={24} />
                                </div>
                                <div>
                                    <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Total Trades</div>
                                    <div style={{ fontSize: '20px', fontWeight: 700 }}>{backtestResult.total_trades}</div>
                                </div>
                            </div>

                            <div style={{ padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>ROI</div>
                                <div style={{ fontSize: '20px', fontWeight: 700, color: '#10B981' }}>{backtestResult.roi.toFixed(2)}%</div>
                            </div>

                            <div style={{ padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Sharpe Ratio</div>
                                <div style={{ fontSize: '20px', fontWeight: 700 }}>{backtestResult.sharpe_ratio.toFixed(2)}</div>
                            </div>

                            <div style={{ padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                                <div style={{ fontSize: '12px', color: '#64748B', textTransform: 'uppercase' }}>Max Drawdown</div>
                                <div style={{ fontSize: '20px', fontWeight: 700, color: '#EF4444' }}>{backtestResult.max_drawdown.toFixed(2)}%</div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

export default StrategyLabView

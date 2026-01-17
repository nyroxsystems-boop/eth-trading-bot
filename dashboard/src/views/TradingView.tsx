import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import CandlestickChart from '../components/CandlestickChart'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface CandleData {
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

export default function TradingView() {
    const [candleData, setCandleData] = useState<CandleData[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [currentPrice, setCurrentPrice] = useState<number>(0)
    const [priceChange, setPriceChange] = useState<number>(0)

    useEffect(() => {
        fetchChartData()
        // Refresh every 30 seconds
        const interval = setInterval(fetchChartData, 30000)
        return () => clearInterval(interval)
    }, [])

    const fetchChartData = async () => {
        try {
            const res = await fetch(`${API_URL}/api/chart/data?symbol=ETHUSDT&interval=5m&limit=50`)
            if (!res.ok) throw new Error('Failed to fetch chart data')

            const data = await res.json()
            if (data.data && data.data.length > 0) {
                setCandleData(data.data)
                const lastCandle = data.data[data.data.length - 1]
                const firstCandle = data.data[0]
                setCurrentPrice(lastCandle.close)
                setPriceChange(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100)
            }
            setError(null)
        } catch (err) {
            console.error('Chart data error:', err)
            setError('Failed to load chart data')
        } finally {
            setLoading(false)
        }
    }

    const orderBook = {
        bids: [
            { price: currentPrice - 0.50, amount: 1.234, total: (currentPrice - 0.50) * 1.234 },
            { price: currentPrice - 1.00, amount: 0.567, total: (currentPrice - 1.00) * 0.567 },
            { price: currentPrice - 1.50, amount: 2.345, total: (currentPrice - 1.50) * 2.345 },
        ],
        asks: [
            { price: currentPrice + 0.50, amount: 0.789, total: (currentPrice + 0.50) * 0.789 },
            { price: currentPrice + 1.00, amount: 1.456, total: (currentPrice + 1.00) * 1.456 },
            { price: currentPrice + 1.50, amount: 0.234, total: (currentPrice + 1.50) * 0.234 },
        ]
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
                    Trading
                </h1>
                <p className="text-slate-400 mt-2">Live ETH/USDT chart from Binance</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                {/* Main Chart - Takes 3 columns */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                    className="lg:col-span-3 bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="mb-4">
                        <h2 className="text-2xl font-bold mb-1">ETH/USDT</h2>
                        <div className="flex items-center gap-4 text-sm">
                            {loading ? (
                                <span className="text-slate-400">Loading...</span>
                            ) : error ? (
                                <span className="text-red-400">{error}</span>
                            ) : (
                                <>
                                    <span className={priceChange >= 0 ? "text-green-400 font-semibold" : "text-red-400 font-semibold"}>
                                        ${currentPrice.toFixed(2)}
                                    </span>
                                    <span className={priceChange >= 0 ? "text-green-400" : "text-red-400"}>
                                        {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                                    </span>
                                </>
                            )}
                        </div>
                    </div>
                    {loading ? (
                        <div className="flex items-center justify-center h-[500px]">
                            <div className="text-slate-400">Loading chart data...</div>
                        </div>
                    ) : candleData.length > 0 ? (
                        <CandlestickChart data={candleData} height={500} />
                    ) : (
                        <div className="flex items-center justify-center h-[500px]">
                            <div className="text-slate-400">No chart data available</div>
                        </div>
                    )}
                </motion.div>

                {/* Order Book & Trade Panel - Takes 1 column */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 }}
                    className="lg:col-span-1 space-y-6"
                >
                    {/* Order Book */}
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-4">
                        <h3 className="text-lg font-semibold mb-4">Order Book</h3>

                        {/* Asks */}
                        <div className="mb-4">
                            <div className="text-xs text-slate-400 mb-2 grid grid-cols-3">
                                <span>Price</span>
                                <span className="text-right">Amount</span>
                                <span className="text-right">Total</span>
                            </div>
                            {orderBook.asks.reverse().map((ask, i) => (
                                <div key={i} className="text-xs grid grid-cols-3 py-1 hover:bg-red-500/10 transition-colors">
                                    <span className="text-red-400 font-mono">{ask.price.toFixed(2)}</span>
                                    <span className="text-right font-mono">{ask.amount.toFixed(3)}</span>
                                    <span className="text-right text-slate-400 font-mono">{ask.total.toFixed(2)}</span>
                                </div>
                            ))}
                        </div>

                        {/* Current Price */}
                        <div className="text-center py-2 bg-green-500/10 rounded-lg mb-4">
                            <span className={`font-bold font-mono ${priceChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${currentPrice.toFixed(2)}
                            </span>
                        </div>

                        {/* Bids */}
                        <div>
                            {orderBook.bids.map((bid, i) => (
                                <div key={i} className="text-xs grid grid-cols-3 py-1 hover:bg-green-500/10 transition-colors">
                                    <span className="text-green-400 font-mono">{bid.price.toFixed(2)}</span>
                                    <span className="text-right font-mono">{bid.amount.toFixed(3)}</span>
                                    <span className="text-right text-slate-400 font-mono">{bid.total.toFixed(2)}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Quick Trade */}
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-4">
                        <h3 className="text-lg font-semibold mb-4">Quick Trade</h3>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs text-slate-400 mb-1 block">Amount (ETH)</label>
                                <input
                                    type="number"
                                    placeholder="0.00"
                                    className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <button className="bg-green-500/20 hover:bg-green-500/30 text-green-400 font-semibold py-2 rounded-lg transition-colors text-sm">
                                    BUY
                                </button>
                                <button className="bg-red-500/20 hover:bg-red-500/30 text-red-400 font-semibold py-2 rounded-lg transition-colors text-sm">
                                    SELL
                                </button>
                            </div>
                        </div>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    )
}

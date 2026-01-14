import { motion } from 'framer-motion'
import CandlestickChart from '../components/CandlestickChart'

export default function TradingView() {
    // Mock candlestick data with volume
    const candleData = Array.from({ length: 50 }, (_, i) => {
        const basePrice = 3200 + Math.random() * 100
        const open = basePrice + (Math.random() - 0.5) * 20
        const close = open + (Math.random() - 0.5) * 30
        const high = Math.max(open, close) + Math.random() * 15
        const low = Math.min(open, close) - Math.random() * 15
        const volume = Math.random() * 1000 + 500

        return {
            time: `${i}:00`,
            open,
            high,
            low,
            close,
            volume
        }
    })

    const orderBook = {
        bids: [
            { price: 3229.50, amount: 1.234, total: 3985.47 },
            { price: 3229.00, amount: 0.567, total: 1830.84 },
            { price: 3228.50, amount: 2.345, total: 7570.83 },
        ],
        asks: [
            { price: 3230.50, amount: 0.789, total: 2548.88 },
            { price: 3231.00, amount: 1.456, total: 4704.38 },
            { price: 3231.50, amount: 0.234, total: 756.17 },
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
                <p className="text-slate-400 mt-2">Advanced trading view with order book</p>
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
                            <span className="text-green-400 font-semibold">$3,230.12</span>
                            <span className="text-green-400">+0.26%</span>
                            <span className="text-slate-400">24h High: $3,245.00</span>
                            <span className="text-slate-400">24h Low: $3,180.00</span>
                        </div>
                    </div>
                    <CandlestickChart data={candleData} height={500} />
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
                            <span className="text-green-400 font-bold font-mono">$3,230.12</span>
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

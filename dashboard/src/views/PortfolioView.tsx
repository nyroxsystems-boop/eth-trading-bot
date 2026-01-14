import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, DollarSign, PieChart } from 'lucide-react'
import { PieChart as RePieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'

export default function PortfolioView() {
    const holdings = [
        { asset: 'ETH', amount: 2.5, value: 8075.30, allocation: 84 },
        { asset: 'USDT', amount: 1500.00, value: 1500.00, allocation: 16 },
    ]

    const positions = [
        { id: 1, pair: 'ETH/USDT', type: 'LONG', entry: 3200.50, current: 3230.12, qty: 0.5, pnl: 14.81, pnlPercent: 0.92 },
        { id: 2, pair: 'ETH/USDT', type: 'LONG', entry: 3180.00, current: 3230.12, qty: 0.3, pnl: 15.04, pnlPercent: 1.58 },
    ]

    const pieData = holdings.map(h => ({ name: h.asset, value: h.allocation }))
    const COLORS = ['#00d4ff', '#00ff88', '#ff3366']

    const totalValue = holdings.reduce((sum, h) => sum + h.value, 0)
    const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0)

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex-1 p-8"
        >
            <div className="mb-6">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                    Portfolio
                </h1>
                <p className="text-slate-400 mt-2">Your holdings and active positions</p>
            </div>

            {/* Portfolio Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <DollarSign className="w-5 h-5 text-cyan-400" />
                        <span className="text-slate-400 text-sm">Total Value</span>
                    </div>
                    <div className="text-3xl font-bold text-white">${totalValue.toFixed(2)}</div>
                    <div className="text-sm text-green-400 mt-1">+2.4% (24h)</div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.2 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <TrendingUp className="w-5 h-5 text-green-400" />
                        <span className="text-slate-400 text-sm">Unrealized P&L</span>
                    </div>
                    <div className="text-3xl font-bold text-green-400">+${totalPnl.toFixed(2)}</div>
                    <div className="text-sm text-slate-400 mt-1">From {positions.length} positions</div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.3 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <PieChart className="w-5 h-5 text-cyan-400" />
                        <span className="text-slate-400 text-sm">Assets</span>
                    </div>
                    <div className="text-3xl font-bold text-white">{holdings.length}</div>
                    <div className="text-sm text-slate-400 mt-1">Diversified portfolio</div>
                </motion.div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Holdings */}
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.4 }}
                >
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6">
                        <h2 className="text-xl font-semibold mb-4">Holdings</h2>
                        <div className="space-y-3">
                            {holdings.map((holding, idx) => (
                                <div key={idx} className="flex items-center justify-between p-4 bg-slate-800/30 rounded-xl hover:bg-slate-800/50 transition-colors">
                                    <div>
                                        <div className="font-semibold text-white">{holding.asset}</div>
                                        <div className="text-sm text-slate-400">{holding.amount.toFixed(4)} {holding.asset}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="font-semibold text-white">${holding.value.toFixed(2)}</div>
                                        <div className="text-sm text-slate-400">{holding.allocation}%</div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Pie Chart */}
                        <div className="mt-6">
                            <ResponsiveContainer width="100%" height={200}>
                                <RePieChart>
                                    <Pie
                                        data={pieData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={80}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {pieData.map((_, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip />
                                </RePieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </motion.div>

                {/* Open Positions */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 }}
                >
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6">
                        <h2 className="text-xl font-semibold mb-4">Open Positions</h2>
                        <div className="space-y-3">
                            {positions.map((pos) => (
                                <div key={pos.id} className="p-4 bg-slate-800/30 rounded-xl border border-slate-700/50 hover:border-cyan-500/30 transition-colors">
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-2">
                                            <span className="font-semibold text-white">{pos.pair}</span>
                                            <span className="text-xs px-2 py-1 bg-green-500/20 text-green-400 rounded">
                                                {pos.type}
                                            </span>
                                        </div>
                                        <div className={`text-sm font-semibold ${pos.pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {pos.pnl > 0 ? '+' : ''}{pos.pnl.toFixed(2)} USDT
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 text-sm">
                                        <div>
                                            <div className="text-slate-400">Entry</div>
                                            <div className="text-white font-mono">${pos.entry.toFixed(2)}</div>
                                        </div>
                                        <div>
                                            <div className="text-slate-400">Current</div>
                                            <div className="text-white font-mono">${pos.current.toFixed(2)}</div>
                                        </div>
                                        <div>
                                            <div className="text-slate-400">Qty</div>
                                            <div className="text-white font-mono">{pos.qty}</div>
                                        </div>
                                    </div>
                                    <div className="mt-2 flex items-center gap-2">
                                        {pos.pnl > 0 ? <TrendingUp className="w-4 h-4 text-green-400" /> : <TrendingDown className="w-4 h-4 text-red-400" />}
                                        <span className={`text-sm font-medium ${pos.pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {pos.pnlPercent > 0 ? '+' : ''}{pos.pnlPercent.toFixed(2)}%
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    )
}

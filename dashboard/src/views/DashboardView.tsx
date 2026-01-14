import { motion } from 'framer-motion'
import { Bell, User } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import CandlestickChart from '../components/CandlestickChart'
import TickerBar from '../components/TickerBar'
import MetricCard from '../components/MetricCard'
import { Trade, Metrics, BotStatus } from '../types'

interface DashboardViewProps {
    trades: Trade[]
    metrics: Metrics | null
    status: BotStatus | null
    candlestickData: any[]
    tickerData: any[]
    timeframe: string
    setTimeframe: (tf: string) => void
}

const timeframes = ['1M', '5M', '15M', '1H', '4H', '1D']

export default function DashboardView({
    trades,
    metrics,
    status,
    candlestickData,
    tickerData,
    timeframe,
    setTimeframe
}: DashboardViewProps) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="flex-1"
        >
            {/* Header */}
            <header className="border-b border-slate-800/50 bg-slate-900/30 backdrop-blur-xl">
                <div className="px-8 py-4 flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                            Dashboard
                        </h1>
                        <p className="text-sm text-slate-400 mt-1">Trading Overview & Performance</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <button className="w-10 h-10 rounded-xl bg-slate-800/50 flex items-center justify-center hover:bg-slate-800 transition-all duration-300 hover:scale-110 hover:shadow-lg hover:shadow-cyan-500/20">
                            <Bell className="w-5 h-5 text-slate-400 hover:text-cyan-400 transition-colors" />
                        </button>
                        <button className="w-10 h-10 rounded-xl bg-slate-800/50 flex items-center justify-center hover:bg-slate-800 transition-all duration-300 hover:scale-110 hover:shadow-lg hover:shadow-cyan-500/20">
                            <User className="w-5 h-5 text-slate-400 hover:text-cyan-400 transition-colors" />
                        </button>
                    </div>
                </div>
            </header>

            {/* Candlestick Chart Section */}
            <div className="px-8 py-6">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6 shadow-2xl hover:shadow-cyan-500/10 transition-shadow duration-300"
                >
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <h2 className="text-lg font-semibold">ETH/USD</h2>
                            <span className="text-cyan-400 text-sm px-3 py-1 bg-cyan-500/10 rounded-full border border-cyan-500/20">
                                Live Market Data
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            {timeframes.map((tf) => (
                                <button
                                    key={tf}
                                    onClick={() => setTimeframe(tf)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-300 ${timeframe === tf
                                            ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30'
                                            : 'bg-slate-800/50 text-slate-400 hover:text-white hover:bg-slate-800 hover:scale-105'
                                        }`}
                                >
                                    {tf}
                                </button>
                            ))}
                        </div>
                    </div>
                    <CandlestickChart data={candlestickData} height={350} />
                </motion.div>
            </div>

            {/* Ticker Bar */}
            <TickerBar tickers={tickerData} />

            {/* Metrics Grid & Trade Feed */}
            <div className="px-8 py-6">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left: Metrics Grid (2x2) */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.2 }}
                        className="lg:col-span-2 grid grid-cols-2 gap-6"
                    >
                        <MetricCard
                            title="Daily P&L"
                            value={`$${metrics?.daily_pnl.toFixed(2) || '0.00'}`}
                            subtitle={`${((metrics?.daily_pnl || 0) / 10000 * 100).toFixed(2)}%`}
                            type="pnl"
                            trend={metrics?.daily_pnl && metrics.daily_pnl > 0 ? 'up' : 'down'}
                        />
                        <MetricCard
                            title="Win Rate"
                            value={`${metrics?.win_rate.toFixed(1) || '0'}%`}
                            type="winrate"
                            percentage={metrics?.win_rate || 0}
                        />
                        <MetricCard
                            title="ML Confidence"
                            value={(status?.ml_confidence || 0.5).toFixed(2)}
                            subtitle={status?.ml_confidence && status.ml_confidence > 0.6 ? 'High' : 'Medium'}
                            type="confidence"
                            percentage={(status?.ml_confidence || 0.5)}
                        />
                        <MetricCard
                            title="Total Trades"
                            value={metrics?.total_trades || 0}
                            subtitle={`${status?.today_trades || 0} today`}
                            type="trades"
                        />
                    </motion.div>

                    {/* Right: Live Trade Feed */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.3 }}
                        className="lg:col-span-1"
                    >
                        <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6 h-full shadow-2xl">
                            <div className="bg-gradient-to-r from-cyan-500 to-blue-500 text-white px-4 py-2 rounded-lg mb-4 text-center font-semibold shadow-lg shadow-cyan-500/30">
                                Live Trades - ETH/USD
                            </div>
                            <TradeFeed trades={trades.slice(-10).reverse()} />
                        </div>
                    </motion.div>
                </div>
            </div>

            {/* Performance Analysis */}
            <div className="px-8 pb-6">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6 shadow-2xl"
                >
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-semibold">Performance Analysis</h2>
                        <select className="bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-2 text-sm hover:bg-slate-800 transition-colors cursor-pointer">
                            <option>Last 30 days</option>
                            <option>Last 7 days</option>
                            <option>Last 24 hours</option>
                        </select>
                    </div>
                    <PerformanceChart trades={trades} />

                    {/* Additional Metrics */}
                    <div className="grid grid-cols-3 gap-6 mt-6">
                        <div className="p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
                            <div className="text-slate-400 text-sm mb-2">Max Drawdown</div>
                            <div className="text-2xl font-bold text-red-400">-{metrics?.max_drawdown.toFixed(2) || '0'}%</div>
                        </div>
                        <div className="p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
                            <div className="text-slate-400 text-sm mb-2">Sharpe Ratio</div>
                            <div className="text-2xl font-bold text-cyan-400">{(metrics?.sharpe_ratio || 0).toFixed(2)}</div>
                        </div>
                        <div className="p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
                            <div className="text-slate-400 text-sm mb-2">Avg. Trade Duration</div>
                            <div className="text-2xl font-bold text-cyan-400">2h min</div>
                        </div>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    )
}

// Performance Chart Component
function PerformanceChart({ trades }: { trades: Trade[] }) {
    const data = trades.reduce((acc: any[], trade, idx) => {
        const prevPnl = idx > 0 ? acc[idx - 1].pnl : 0
        const currentPnl = prevPnl + (trade.pnl || 0)
        acc.push({
            index: idx,
            pnl: currentPnl,
            timestamp: new Date(trade.timestamp).toLocaleTimeString()
        })
        return acc
    }, [])

    return (
        <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={data}>
                <defs>
                    <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#00ff88" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
                    </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="index" stroke="#64748b" />
                <YAxis stroke="#64748b" />
                <Tooltip
                    contentStyle={{
                        backgroundColor: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: '8px'
                    }}
                />
                <Area
                    type="monotone"
                    dataKey="pnl"
                    stroke="#00ff88"
                    fillOpacity={1}
                    fill="url(#colorPnl)"
                />
            </AreaChart>
        </ResponsiveContainer>
    )
}

// Trade Feed Component
function TradeFeed({ trades }: { trades: Trade[] }) {
    return (
        <div className="space-y-3 max-h-[400px] overflow-y-auto custom-scrollbar">
            {trades.map((trade, idx) => (
                <motion.div
                    key={`${trade.timestamp}-${idx}`}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className={`p-3 rounded-xl border text-sm transition-all duration-300 hover:scale-105 ${trade.action === 'BUY'
                            ? 'bg-green-500/10 border-green-500/30 hover:bg-green-500/20'
                            : 'bg-red-500/10 border-red-500/30 hover:bg-red-500/20'
                        }`}
                >
                    <div className="flex items-center justify-between mb-1">
                        <span className={`font-semibold ${trade.action === 'BUY' ? 'text-green-400' : 'text-red-400'
                            }`}>
                            {trade.action} ↗
                        </span>
                        <span className="text-xs text-slate-400">
                            {new Date(trade.timestamp).toLocaleTimeString()}
                        </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-300 font-mono">${trade.price.toFixed(2)}</span>
                        <span className="text-slate-400">{trade.qty.toFixed(4)} BTC</span>
                    </div>
                    {trade.pnl !== undefined && (
                        <div className={`text-xs mt-1 font-medium font-mono ${trade.pnl > 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                            {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)} USDT
                        </div>
                    )}
                </motion.div>
            ))}
        </div>
    )
}

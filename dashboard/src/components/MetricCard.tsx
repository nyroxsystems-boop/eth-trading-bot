import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, CheckCircle, Brain, Activity } from 'lucide-react'

interface MetricCardProps {
    title: string
    value: string | number
    subtitle?: string
    type?: 'pnl' | 'winrate' | 'confidence' | 'trades'
    trend?: 'up' | 'down'
    percentage?: number
    icon?: React.ReactNode
}

export default function MetricCard({
    title,
    value,
    subtitle,
    type = 'trades',
    trend,
    percentage
}: MetricCardProps) {
    const getIcon = () => {
        switch (type) {
            case 'pnl':
                return trend === 'up' ? <TrendingUp className="w-6 h-6" /> : <TrendingDown className="w-6 h-6" />
            case 'winrate':
                return <CheckCircle className="w-6 h-6" />
            case 'confidence':
                return <Brain className="w-6 h-6" />
            case 'trades':
                return <Activity className="w-6 h-6" />
            default:
                return null
        }
    }

    const getColor = () => {
        switch (type) {
            case 'pnl':
                return trend === 'up' ? 'text-green-400' : 'text-red-400'
            case 'winrate':
                return 'text-green-400'
            case 'confidence':
                return 'text-cyan-400'
            case 'trades':
                return 'text-cyan-400'
            default:
                return 'text-slate-400'
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 hover:border-cyan-500/30 transition-all"
        >
            <div className="flex items-start justify-between mb-4">
                <div className="text-slate-400 text-sm font-medium">{title}</div>
                <div className={getColor()}>
                    {getIcon()}
                </div>
            </div>

            {/* Win Rate - Circular Progress */}
            {type === 'winrate' && percentage !== undefined && (
                <div className="flex items-center gap-4">
                    <div className="relative w-20 h-20">
                        <svg className="w-20 h-20 transform -rotate-90">
                            <circle
                                cx="40"
                                cy="40"
                                r="32"
                                stroke="#1e293b"
                                strokeWidth="6"
                                fill="none"
                            />
                            <circle
                                cx="40"
                                cy="40"
                                r="32"
                                stroke="#00ff88"
                                strokeWidth="6"
                                fill="none"
                                strokeDasharray={`${2 * Math.PI * 32}`}
                                strokeDashoffset={`${2 * Math.PI * 32 * (1 - percentage / 100)}`}
                                strokeLinecap="round"
                                className="transition-all duration-1000"
                            />
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center">
                            <CheckCircle className="w-6 h-6 text-green-400" />
                        </div>
                    </div>
                    <div className="text-4xl font-bold text-green-400">{value}</div>
                </div>
            )}

            {/* ML Confidence - Gauge */}
            {type === 'confidence' && percentage !== undefined && (
                <div className="flex items-center gap-4">
                    <div className="relative w-20 h-20">
                        <svg className="w-20 h-20 transform -rotate-90">
                            <circle
                                cx="40"
                                cy="40"
                                r="32"
                                stroke="#1e293b"
                                strokeWidth="6"
                                fill="none"
                                strokeDasharray={`${Math.PI * 32} ${Math.PI * 32}`}
                            />
                            <circle
                                cx="40"
                                cy="40"
                                r="32"
                                stroke="#00d4ff"
                                strokeWidth="6"
                                fill="none"
                                strokeDasharray={`${Math.PI * 32 * percentage} ${Math.PI * 32}`}
                                strokeLinecap="round"
                                className="transition-all duration-1000"
                            />
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center flex-col">
                            <div className="text-xs text-slate-400">Index</div>
                            <div className="text-sm font-bold text-cyan-400">{value}</div>
                        </div>
                    </div>
                    <div className="text-sm text-slate-400">{subtitle}</div>
                </div>
            )}

            {/* P&L - Simple with trend */}
            {type === 'pnl' && (
                <div>
                    <div className={`text-4xl font-bold mb-2 ${getColor()}`}>
                        {value}
                    </div>
                    {subtitle && (
                        <div className={`text-sm flex items-center gap-1 ${getColor()}`}>
                            {trend === 'up' ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                            {subtitle}
                        </div>
                    )}
                </div>
            )}

            {/* Total Trades - Simple number */}
            {type === 'trades' && (
                <div>
                    <div className="text-5xl font-bold text-cyan-400 mb-2">{value}</div>
                    {subtitle && <div className="text-sm text-slate-400">{subtitle}</div>}
                </div>
            )}
        </motion.div>
    )
}

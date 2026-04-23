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
                return trend === 'up' ? <TrendingUp size={20} /> : <TrendingDown size={20} />
            case 'winrate':
                return <CheckCircle size={20} />
            case 'confidence':
                return <Brain size={20} />
            case 'trades':
                return <Activity size={20} />
            default:
                return null
        }
    }

    const getValueColor = () => {
        switch (type) {
            case 'pnl':
                return trend === 'up' ? 'var(--green)' : 'var(--red)'
            case 'winrate':
                return 'var(--green)'
            case 'confidence':
                return 'var(--cyan)'
            case 'trades':
                return 'var(--cyan)'
            default:
                return 'var(--text-secondary)'
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="card"
            style={{ padding: '20px' }}
        >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
                    {title}
                </div>
                <div style={{ color: getValueColor(), opacity: 0.7 }}>
                    {getIcon()}
                </div>
            </div>

            {/* Win Rate - Circular Progress */}
            {type === 'winrate' && percentage !== undefined && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ position: 'relative', width: '64px', height: '64px' }}>
                        <svg width="64" height="64" style={{ transform: 'rotate(-90deg)' }}>
                            <circle
                                cx="32"
                                cy="32"
                                r="26"
                                stroke="rgba(255,255,255,0.06)"
                                strokeWidth="5"
                                fill="none"
                            />
                            <circle
                                cx="32"
                                cy="32"
                                r="26"
                                stroke="var(--green)"
                                strokeWidth="5"
                                fill="none"
                                strokeDasharray={`${2 * Math.PI * 26}`}
                                strokeDashoffset={`${2 * Math.PI * 26 * (1 - percentage / 100)}`}
                                strokeLinecap="round"
                                style={{ transition: 'all 1s ease' }}
                            />
                        </svg>
                        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <CheckCircle size={16} style={{ color: 'var(--green)' }} />
                        </div>
                    </div>
                    <div style={{ fontSize: '32px', fontWeight: 700, color: 'var(--green)', fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
                </div>
            )}

            {/* ML Confidence - Gauge */}
            {type === 'confidence' && percentage !== undefined && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ position: 'relative', width: '64px', height: '64px' }}>
                        <svg width="64" height="64" style={{ transform: 'rotate(-90deg)' }}>
                            <circle
                                cx="32"
                                cy="32"
                                r="26"
                                stroke="rgba(255,255,255,0.06)"
                                strokeWidth="5"
                                fill="none"
                                strokeDasharray={`${Math.PI * 26} ${Math.PI * 26}`}
                            />
                            <circle
                                cx="32"
                                cy="32"
                                r="26"
                                stroke="var(--cyan)"
                                strokeWidth="5"
                                fill="none"
                                strokeDasharray={`${Math.PI * 26 * percentage} ${Math.PI * 26}`}
                                strokeLinecap="round"
                                style={{ transition: 'all 1s ease' }}
                            />
                        </svg>
                        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                            <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>Index</div>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--cyan)' }}>{value}</div>
                        </div>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{subtitle}</div>
                </div>
            )}

            {/* P&L - Simple with trend */}
            {type === 'pnl' && (
                <div>
                    <div style={{ fontSize: '32px', fontWeight: 700, marginBottom: '6px', color: getValueColor(), fontFamily: "'JetBrains Mono', monospace" }}>
                        {value}
                    </div>
                    {subtitle && (
                        <div style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px', color: getValueColor() }}>
                            {trend === 'up' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                            {subtitle}
                        </div>
                    )}
                </div>
            )}

            {/* Total Trades - Simple number */}
            {type === 'trades' && (
                <div>
                    <div style={{ fontSize: '36px', fontWeight: 700, color: 'var(--cyan)', marginBottom: '6px', fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
                    {subtitle && <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{subtitle}</div>}
                </div>
            )}
        </motion.div>
    )
}

import { TrendingUp, TrendingDown } from 'lucide-react'

interface TickerItem {
    symbol: string
    name: string
    price: number
    change: number
    changePercent: number
}

interface TickerBarProps {
    tickers: TickerItem[]
}

export default function TickerBar({ tickers }: TickerBarProps) {
    return (
        <div className="ticker-bar">
            {tickers.map((ticker) => {
                const isPositive = ticker.change >= 0

                return (
                    <div key={ticker.symbol} style={{ display: 'flex', alignItems: 'center', gap: '8px', whiteSpace: 'nowrap' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '13px', fontWeight: 500 }}>{ticker.symbol}</span>
                        <span className="ticker-price">${ticker.price.toFixed(2)}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '13px', color: isPositive ? 'var(--green)' : 'var(--red)' }}>
                            {isPositive ? (
                                <TrendingUp size={12} />
                            ) : (
                                <TrendingDown size={12} />
                            )}
                            <span>{isPositive ? '+' : ''}{ticker.changePercent.toFixed(2)}%</span>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

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
        <div className="flex items-center gap-6 px-4 py-3 bg-slate-900/30 border-y border-slate-800 overflow-x-auto">
            {tickers.map((ticker) => {
                const isPositive = ticker.change >= 0

                return (
                    <div key={ticker.symbol} className="flex items-center gap-2 min-w-fit">
                        <span className="text-slate-400 text-sm font-medium">{ticker.symbol}</span>
                        <span className="text-white font-semibold">${ticker.price.toFixed(2)}</span>
                        <div className={`flex items-center gap-1 text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                            {isPositive ? (
                                <TrendingUp className="w-3 h-3" />
                            ) : (
                                <TrendingDown className="w-3 h-3" />
                            )}
                            <span>{isPositive ? '+' : ''}{ticker.changePercent.toFixed(2)}%</span>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

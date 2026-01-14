import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'

interface CandlestickData {
    time: any
    open: number
    high: number
    low: number
    close: number
}

interface CandlestickChartProps {
    data: CandlestickData[]
}

export default function CandlestickChart({ data }: CandlestickChartProps) {
    // Convert candlestick data to line chart data for simplicity
    const lineData = data.map((item, index) => ({
        index,
        price: item.close,
        high: item.high,
        low: item.low,
    }))

    return (
        <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={lineData}>
                <defs>
                    <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#00ff88" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
                    </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                    dataKey="index"
                    stroke="#64748b"
                    tick={{ fill: '#64748b' }}
                />
                <YAxis
                    stroke="#64748b"
                    tick={{ fill: '#64748b' }}
                    domain={['dataMin - 50', 'dataMax + 50']}
                />
                <Tooltip
                    contentStyle={{
                        backgroundColor: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: '8px',
                        color: '#fff'
                    }}
                />
                <Area
                    type="monotone"
                    dataKey="price"
                    stroke="#00ff88"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorPrice)"
                />
            </AreaChart>
        </ResponsiveContainer>
    )
}

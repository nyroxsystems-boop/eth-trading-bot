import { ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface CandleData {
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

interface CandlestickChartProps {
    data: CandleData[]
    height?: number
}

// Custom Candlestick Shape
const Candlestick = (props: any) => {
    const { x, y, width, height, payload } = props

    if (!payload) return null

    const { open, high, low, close } = payload
    const isGreen = close > open
    const color = isGreen ? '#00ff88' : '#ff3366'



    // Scale factors
    const priceRange = high - low
    const scale = height / priceRange

    const wickX = x + width / 2
    const bodyWidth = Math.max(width * 0.9, 3)  // Increased from 0.6 to 0.9 for thicker candles
    const bodyX = x + (width - bodyWidth) / 2

    const highY = y + (high - payload.high) * scale
    const lowY = y + (high - low) * scale
    const openY = y + (high - open) * scale
    const closeY = y + (high - close) * scale

    return (
        <g>
            {/* Wick (high-low line) */}
            <line
                x1={wickX}
                y1={highY}
                x2={wickX}
                y2={lowY}
                stroke={color}
                strokeWidth={2}  // Increased from 1 to 2 for thicker wicks
            />
            {/* Body (open-close rectangle) */}
            <rect
                x={bodyX}
                y={Math.min(openY, closeY)}
                width={bodyWidth}
                height={Math.max(Math.abs(closeY - openY), 2)}  // Minimum height 2 instead of 1
                fill={color}
                stroke={color}
                strokeWidth={1}
            />
        </g>
    )
}

export default function CandlestickChart({ data, height = 400 }: CandlestickChartProps) {
    // Transform data for chart
    const chartData = data.map(item => ({
        ...item,
        candle: [item.low, item.open, item.close, item.high],
    }))

    return (
        <div className="w-full">
            {/* Main Candlestick Chart */}
            <ResponsiveContainer width="100%" height={height}>
                <ComposedChart
                    data={chartData}
                    margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                    barCategoryGap="5%"  // Reduced gap between candles (default is 10%)
                >
                    <defs>
                        <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#334155" stopOpacity={0.8} />
                            <stop offset="95%" stopColor="#334155" stopOpacity={0.1} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis
                        dataKey="time"
                        stroke="#64748b"
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                    />
                    <YAxis
                        yAxisId="price"
                        orientation="right"
                        stroke="#64748b"
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        domain={['dataMin - 10', 'dataMax + 10']}
                    />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: '#0f172a',
                            border: '1px solid #334155',
                            borderRadius: '8px',
                            color: '#fff',
                            fontSize: '12px'
                        }}
                        formatter={(value: any, name: string) => {
                            if (name === 'candle') {
                                const [low, open, close, high] = value
                                return [
                                    <div key="candle-info" className="space-y-1">
                                        <div className="flex justify-between gap-4">
                                            <span className="text-slate-400">O:</span>
                                            <span className="text-white font-mono">${open.toFixed(2)}</span>
                                        </div>
                                        <div className="flex justify-between gap-4">
                                            <span className="text-slate-400">H:</span>
                                            <span className="text-green-400 font-mono">${high.toFixed(2)}</span>
                                        </div>
                                        <div className="flex justify-between gap-4">
                                            <span className="text-slate-400">L:</span>
                                            <span className="text-red-400 font-mono">${low.toFixed(2)}</span>
                                        </div>
                                        <div className="flex justify-between gap-4">
                                            <span className="text-slate-400">C:</span>
                                            <span className="text-white font-mono">${close.toFixed(2)}</span>
                                        </div>
                                    </div>,
                                    ''
                                ]
                            }
                            return [value, name]
                        }}
                    />
                    <Bar
                        yAxisId="price"
                        dataKey="candle"
                        shape={<Candlestick />}
                    >
                        {chartData.map((_, index) => (
                            <Cell key={`cell-${index}`} />
                        ))}
                    </Bar>
                </ComposedChart>
            </ResponsiveContainer>

            {/* Volume Chart */}
            <ResponsiveContainer width="100%" height={80}>
                <ComposedChart
                    data={chartData}
                    margin={{ top: 0, right: 10, left: 0, bottom: 5 }}
                    barCategoryGap="5%"  // Match main chart spacing
                >
                    <XAxis
                        dataKey="time"
                        hide
                    />
                    <YAxis
                        orientation="right"
                        stroke="#64748b"
                        tick={{ fill: '#64748b', fontSize: 10 }}
                        tickLine={false}
                        width={50}
                    />
                    <Bar dataKey="volume" fill="url(#volumeGradient)">
                        {chartData.map((entry, index) => (
                            <Cell
                                key={`vol-${index}`}
                                fill={entry.close > entry.open ? 'rgba(0, 255, 136, 0.3)' : 'rgba(255, 51, 102, 0.3)'}
                            />
                        ))}
                    </Bar>
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    )
}

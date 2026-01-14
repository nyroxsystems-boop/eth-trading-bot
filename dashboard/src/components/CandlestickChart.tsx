import { useEffect, useRef } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'

interface CandlestickData {
    time: Time
    open: number
    high: number
    low: number
    close: number
}

interface CandlestickChartProps {
    data: CandlestickData[]
}

export default function CandlestickChart({ data }: CandlestickChartProps) {
    const chartContainerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

    useEffect(() => {
        if (!chartContainerRef.current) return

        // Create chart
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#64748b',
            },
            grid: {
                vertLines: { color: '#1e293b' },
                horzLines: { color: '#1e293b' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 300,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                borderColor: '#1e293b',
            },
            rightPriceScale: {
                borderColor: '#1e293b',
            },
        })

        // Add candlestick series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#00ff88',
            downColor: '#ff3366',
            borderUpColor: '#00ff88',
            borderDownColor: '#ff3366',
            wickUpColor: '#00ff88',
            wickDownColor: '#ff3366',
        })

        chartRef.current = chart
        candlestickSeriesRef.current = candlestickSeries

        // Handle resize
        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                })
            }
        }

        window.addEventListener('resize', handleResize)

        return () => {
            window.removeEventListener('resize', handleResize)
            chart.remove()
        }
    }, [])

    useEffect(() => {
        if (candlestickSeriesRef.current && data.length > 0) {
            candlestickSeriesRef.current.setData(data as any)
        }
    }, [data])

    return (
        <div className="relative">
            <div ref={chartContainerRef} className="w-full" />
        </div>
    )
}

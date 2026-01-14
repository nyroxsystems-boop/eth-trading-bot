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
    const resizeObserverRef = useRef<ResizeObserver | null>(null)

    useEffect(() => {
        if (!chartContainerRef.current) return

        try {
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

            // Handle resize with ResizeObserver
            if (chartContainerRef.current) {
                resizeObserverRef.current = new ResizeObserver(entries => {
                    if (entries.length === 0 || entries[0].target !== chartContainerRef.current) return
                    if (chartRef.current) {
                        const { width } = entries[0].contentRect
                        chartRef.current.applyOptions({ width })
                    }
                })

                resizeObserverRef.current.observe(chartContainerRef.current)
            }
        } catch (err) {
            console.error('Failed to create chart:', err)
        }

        return () => {
            try {
                if (resizeObserverRef.current && chartContainerRef.current) {
                    resizeObserverRef.current.unobserve(chartContainerRef.current)
                }
                if (chartRef.current) {
                    chartRef.current.remove()
                    chartRef.current = null
                }
            } catch (err) {
                console.error('Error cleaning up chart:', err)
            }
        }
    }, [])

    useEffect(() => {
        if (candlestickSeriesRef.current && data.length > 0) {
            try {
                candlestickSeriesRef.current.setData(data as any)
            } catch (err) {
                console.error('Failed to set chart data:', err)
            }
        }
    }, [data])

    return (
        <div className="relative w-full">
            <div ref={chartContainerRef} className="w-full" style={{ minHeight: '300px' }} />
        </div>
    )
}

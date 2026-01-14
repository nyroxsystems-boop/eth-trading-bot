import { useState, useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import './App.css'

// Components
import Sidebar from './components/Sidebar'

// Views
import DashboardView from './views/DashboardView'
import PortfolioView from './views/PortfolioView'
import TradingView from './views/TradingView'
import BotsView from './views/BotsView'
import SettingsView from './views/SettingsView'

// Types
import { Trade, Metrics, BotStatus, CandleData } from './types'

// API Configuration
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

// Generate mock candlestick data with volume
const generateCandlestickData = (): CandleData[] => {
  const data: CandleData[] = []
  let basePrice = 3200

  for (let i = 100; i >= 0; i--) {
    const open = basePrice + (Math.random() - 0.5) * 20
    const close = open + (Math.random() - 0.5) * 30
    const high = Math.max(open, close) + Math.random() * 15
    const low = Math.min(open, close) - Math.random() * 15
    const volume = Math.random() * 1000 + 500

    data.push({
      time: `${100 - i}:00`,
      open,
      high,
      low,
      close,
      volume
    })
    basePrice = close
  }

  return data
}

// Generate mock ticker data
const generateTickerData = () => [
  { symbol: 'ETH', name: 'Ethereum', price: 3230.12, change: 8.24, changePercent: 0.26 },
  { symbol: 'XRP', name: 'Ripple', price: 0.6039, change: 0.0524, changePercent: 8.78 },
  { symbol: 'BTC', name: 'Bitcoin', price: 55218.50, change: -621.30, changePercent: -11.38 },
  { symbol: 'ADA', name: 'Cardano', price: 0.066415, change: 0.0078, changePercent: 18.5 },
]

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [trades, setTrades] = useState<Trade[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [, setConnected] = useState(false)
  const [candlestickData] = useState(generateCandlestickData())
  const [tickerData] = useState(generateTickerData())
  const [timeframe, setTimeframe] = useState('15M')

  // Fetch initial data
  useEffect(() => {
    fetchTrades()
    fetchMetrics()
    fetchStatus()
  }, [])

  // WebSocket connection
  useEffect(() => {
    if (!WS_URL || WS_URL === 'ws://localhost:8000/ws') {
      console.warn('WebSocket URL not configured for production')
      return
    }

    try {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        console.log('WebSocket connected')
        setConnected(true)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'update') {
            setStatus(data.status)
            setMetrics(data.metrics)
          } else if (data.type === 'new_trade') {
            setTrades(prev => [...prev, data.trade])
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setConnected(false)
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        setConnected(false)
      }

      return () => {
        try {
          ws.close()
        } catch (err) {
          console.error('Error closing WebSocket:', err)
        }
      }
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      setConnected(false)
    }
  }, [])

  const fetchTrades = async () => {
    try {
      const res = await fetch(`${API_URL}/api/trades?limit=50`)
      const data = await res.json()
      setTrades(data)
    } catch (err) {
      console.error('Failed to fetch trades:', err)
    }
  }

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_URL}/api/performance`)
      const data = await res.json()
      setMetrics(data)
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    }
  }

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/status`)
      const data = await res.json()
      setStatus(data)
    } catch (err) {
      console.error('Failed to fetch status:', err)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Sidebar */}
      <Sidebar activePage={activePage} onPageChange={setActivePage} />

      {/* Main Content */}
      <div className="ml-20">
        <AnimatePresence mode="wait">
          {activePage === 'dashboard' && (
            <DashboardView
              key="dashboard"
              trades={trades}
              metrics={metrics}
              status={status}
              candlestickData={candlestickData}
              tickerData={tickerData}
              timeframe={timeframe}
              setTimeframe={setTimeframe}
            />
          )}
          {activePage === 'portfolio' && <PortfolioView key="portfolio" />}
          {activePage === 'trading' && <TradingView key="trading" />}
          {activePage === 'bots' && <BotsView key="bots" />}
          {activePage === 'settings' && <SettingsView key="settings" />}
        </AnimatePresence>
      </div>
    </div>
  )
}

export default App

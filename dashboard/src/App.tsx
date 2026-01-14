import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Bell, User } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import './App.css'

// Components
import Sidebar from './components/Sidebar'
import CandlestickChart from './components/CandlestickChart'
import TickerBar from './components/TickerBar'
import MetricCard from './components/MetricCard'

// Types
interface Trade {
  timestamp: string
  action: string
  qty: number
  price: number
  pnl?: number
}

interface Metrics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  daily_pnl: number
  avg_win: number
  avg_loss: number
  sharpe_ratio: number
  max_drawdown: number
  roi: number
}

interface BotStatus {
  is_running: boolean
  today_trades: number
  ml_confidence: number
  sentiment_score: number
  regime: string
  last_update: string
}

// API Configuration
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

// Generate mock candlestick data
const generateCandlestickData = () => {
  const data = []
  let basePrice = 3200
  const now = Math.floor(Date.now() / 1000)

  for (let i = 100; i >= 0; i--) {
    const time = (now - (i * 900)) as any // 15-minute intervals
    const open = basePrice + (Math.random() - 0.5) * 20
    const close = open + (Math.random() - 0.5) * 30
    const high = Math.max(open, close) + Math.random() * 15
    const low = Math.min(open, close) - Math.random() * 15

    data.push({ time, open, high, low, close })
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
  const [trades, setTrades] = useState<Trade[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [, setConnected] = useState(false)
  const [candlestickData] = useState(generateCandlestickData())
  const [tickerData] = useState(generateTickerData())
  const [timeframe, setTimeframe] = useState('15M')

  const timeframes = ['1M', '5M', '15M', '1H', '4H', '1D']

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
      <Sidebar activePage="dashboard" />

      {/* Main Content */}
      <div className="ml-20">
        {/* Header */}
        <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-xl">
          <div className="px-8 py-4 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Dashboard</h1>
            </div>
            <div className="flex items-center gap-4">
              <button className="w-10 h-10 rounded-xl bg-slate-800/50 flex items-center justify-center hover:bg-slate-800 transition-colors">
                <Bell className="w-5 h-5 text-slate-400" />
              </button>
              <button className="w-10 h-10 rounded-xl bg-slate-800/50 flex items-center justify-center hover:bg-slate-800 transition-colors">
                <User className="w-5 h-5 text-slate-400" />
              </button>
            </div>
          </div>
        </header>

        {/* Candlestick Chart Section */}
        <div className="px-8 py-6">
          <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">ETH/USD</h2>
                <span className="text-cyan-400 text-sm">Live Market Data</span>
              </div>
              <div className="flex items-center gap-2">
                {timeframes.map((tf) => (
                  <button
                    key={tf}
                    onClick={() => setTimeframe(tf)}
                    className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${timeframe === tf
                      ? 'bg-cyan-500 text-white'
                      : 'bg-slate-800/50 text-slate-400 hover:text-white'
                      }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
            <CandlestickChart data={candlestickData} />
          </div>
        </div>

        {/* Ticker Bar */}
        <TickerBar tickers={tickerData} />

        {/* Metrics Grid & Trade Feed */}
        <div className="px-8 py-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Metrics Grid (2x2) */}
            <div className="lg:col-span-2 grid grid-cols-2 gap-6">
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
            </div>

            {/* Right: Live Trade Feed */}
            <div className="lg:col-span-1">
              <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 h-full">
                <div className="bg-cyan-500 text-white px-4 py-2 rounded-lg mb-4 text-center font-semibold">
                  Live Trades - ETH/USD
                </div>
                <TradeFeed trades={trades.slice(-10).reverse()} />
              </div>
            </div>
          </div>
        </div>

        {/* Performance Analysis */}
        <div className="px-8 pb-6">
          <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">Performance Analysis</h2>
              <select className="bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-2 text-sm">
                <option>Last 30 days</option>
                <option>Last 7 days</option>
                <option>Last 24 hours</option>
              </select>
            </div>
            <PerformanceChart trades={trades} />

            {/* Additional Metrics */}
            <div className="grid grid-cols-3 gap-6 mt-6">
              <div>
                <div className="text-slate-400 text-sm mb-2">Max Drawdown</div>
                <div className="text-2xl font-bold text-red-400">-{metrics?.max_drawdown.toFixed(2) || '0'}%</div>
              </div>
              <div>
                <div className="text-slate-400 text-sm mb-2">Sharpe Ratio</div>
                <div className="text-2xl font-bold text-cyan-400">{(metrics?.sharpe_ratio || 0).toFixed(2)}</div>
              </div>
              <div>
                <div className="text-slate-400 text-sm mb-2">Avg. Trade Duration</div>
                <div className="text-2xl font-bold text-cyan-400">2h min</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
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
      <AnimatePresence>
        {trades.map((trade, idx) => (
          <motion.div
            key={`${trade.timestamp}-${idx}`}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className={`p-3 rounded-xl border text-sm ${trade.action === 'BUY'
              ? 'bg-green-500/10 border-green-500/30'
              : 'bg-red-500/10 border-red-500/30'
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
              <span className="text-slate-300">${trade.price.toFixed(2)}</span>
              <span className="text-slate-400">{trade.qty.toFixed(4)} BTC</span>
            </div>
            {trade.pnl !== undefined && (
              <div className={`text-xs mt-1 font-medium ${trade.pnl > 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)} USDT
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

export default App

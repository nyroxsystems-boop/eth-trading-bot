import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  TrendingUp, TrendingDown, Activity, Target, 
  Brain, DollarSign, BarChart3, Zap 
} from 'lucide-react'
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import './App.css'

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

function App() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [connected, setConnected] = useState(false)

  // Fetch initial data
  useEffect(() => {
    fetchTrades()
    fetchMetrics()
    fetchStatus()
  }, [])

  // WebSocket connection
  useEffect(() => {
    const ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      console.log('WebSocket connected')
      setConnected(true)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      if (data.type === 'update') {
        setStatus(data.status)
        setMetrics(data.metrics)
      } else if (data.type === 'new_trade') {
        setTrades(prev => [...prev, data.trade])
      }
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setConnected(false)
    }

    return () => ws.close()
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
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-xl">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Zap className="w-8 h-8 text-cyan-400" />
                <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                  ETH Trading Bot
                </h1>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
                <span className="text-sm text-slate-400">
                  {connected ? 'Live' : 'Disconnected'}
                </span>
              </div>
            </div>
            <div className="text-sm text-slate-400">
              {status?.last_update && new Date(status.last_update).toLocaleString()}
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-6 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Daily P&L"
            value={`$${metrics?.daily_pnl.toFixed(2) || '0.00'}`}
            change={`${((metrics?.daily_pnl || 0) / 10000 * 100).toFixed(2)}%`}
            trend={metrics?.daily_pnl && metrics.daily_pnl > 0 ? 'up' : 'down'}
            icon={<DollarSign className="w-6 h-6" />}
          />
          <StatCard
            title="Win Rate"
            value={`${metrics?.win_rate.toFixed(1) || '0'}%`}
            subtitle={`${metrics?.winning_trades || 0}/${metrics?.total_trades || 0} trades`}
            icon={<Target className="w-6 h-6" />}
            trend={metrics?.win_rate && metrics.win_rate > 60 ? 'up' : 'neutral'}
          />
          <StatCard
            title="ML Confidence"
            value={(status?.ml_confidence || 0.5).toFixed(2)}
            subtitle={status?.ml_confidence && status.ml_confidence > 0.6 ? 'High' : 'Medium'}
            icon={<Brain className="w-6 h-6" />}
            trend={status?.ml_confidence && status.ml_confidence > 0.6 ? 'up' : 'neutral'}
          />
          <StatCard
            title="Total Trades"
            value={metrics?.total_trades || 0}
            subtitle={`${status?.today_trades || 0} today`}
            icon={<Activity className="w-6 h-6" />}
          />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Performance Chart */}
          <div className="lg:col-span-2">
            <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6">
              <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-cyan-400" />
                Performance Analysis
              </h2>
              <PerformanceChart trades={trades} />
            </div>
          </div>

          {/* Live Trade Feed */}
          <div className="lg:col-span-1">
            <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6">
              <h2 className="text-xl font-semibold mb-6">Live Trade Feed</h2>
              <TradeFeed trades={trades.slice(-10).reverse()} />
            </div>
          </div>
        </div>

        {/* Additional Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
          <MetricCard
            title="Max Drawdown"
            value={`${metrics?.max_drawdown.toFixed(2) || '0'}%`}
            color="red"
          />
          <MetricCard
            title="Sharpe Ratio"
            value={(metrics?.sharpe_ratio || 0).toFixed(2)}
            color="blue"
          />
          <MetricCard
            title="ROI"
            value={`${metrics?.roi.toFixed(2) || '0'}%`}
            color="green"
          />
        </div>
      </div>
    </div>
  )
}

// Components
function StatCard({ title, value, change, subtitle, trend, icon }: any) {
  const trendColors = {
    up: 'text-green-400',
    down: 'text-red-400',
    neutral: 'text-slate-400'
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-slate-900/50 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 hover:border-cyan-500/50 transition-all"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="text-slate-400 text-sm font-medium">{title}</div>
        <div className={`${trend ? trendColors[trend] : 'text-cyan-400'}`}>
          {icon}
        </div>
      </div>
      <div className="text-3xl font-bold mb-2">{value}</div>
      {change && (
        <div className={`text-sm flex items-center gap-1 ${trendColors[trend || 'neutral']}`}>
          {trend === 'up' ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          {change}
        </div>
      )}
      {subtitle && <div className="text-sm text-slate-400 mt-1">{subtitle}</div>}
    </motion.div>
  )
}

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
            <stop offset="5%" stopColor="#00ff88" stopOpacity={0.3}/>
            <stop offset="95%" stopColor="#00ff88" stopOpacity={0}/>
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
            className={`p-4 rounded-xl border ${
              trade.action === 'BUY' 
                ? 'bg-green-500/10 border-green-500/30' 
                : 'bg-red-500/10 border-red-500/30'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className={`font-semibold ${
                trade.action === 'BUY' ? 'text-green-400' : 'text-red-400'
              }`}>
                {trade.action}
              </span>
              <span className="text-sm text-slate-400">
                {new Date(trade.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">${trade.price.toFixed(2)}</span>
              <span className="text-slate-400">{trade.qty.toFixed(4)} ETH</span>
            </div>
            {trade.pnl !== undefined && (
              <div className={`text-sm mt-2 font-medium ${
                trade.pnl > 0 ? 'text-green-400' : 'text-red-400'
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

function MetricCard({ title, value, color }: any) {
  const colors = {
    green: 'from-green-500/20 to-green-500/5 border-green-500/30',
    red: 'from-red-500/20 to-red-500/5 border-red-500/30',
    blue: 'from-blue-500/20 to-blue-500/5 border-blue-500/30'
  }

  return (
    <div className={`bg-gradient-to-br ${colors[color]} border rounded-2xl p-6`}>
      <div className="text-slate-400 text-sm mb-2">{title}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  )
}

export default App

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState, useEffect } from 'react'
import './index.css'

// Pages
import Dashboard from './pages/Dashboard'
import Trading from './pages/Trading'
import Settings from './pages/Settings'
import Sidebar from './components/Sidebar'

const API_URL = import.meta.env.VITE_API_URL || ''

// Types
export interface BotStatus {
  is_running: boolean
  pair: string
  price: number
  today_trades: number
  regime: string
  daily_pnl: number
  total_pnl: number
  win_rate: number
  total_trades: number
  paper_balance: number
  position: {
    entry_price: number
    quantity: number
    unrealized_pnl: number
  } | null
}

function AppLayout() {
  const [page, setPage] = useState('dashboard')
  const [status, setStatus] = useState<BotStatus | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v3/status`)
        if (res.ok) {
          const data = await res.json()
          setStatus(data)
        }
      } catch (err) {
        // Status API not available
      }
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 10000) // 10s refresh
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="app">
      <Sidebar activePage={page} onNavigate={setPage} />
      <main className="main-content">
        {page === 'dashboard' && <Dashboard status={status} />}
        {page === 'trading' && <Trading status={status} />}
        {page === 'settings' && <Settings />}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </BrowserRouter>
  )
}

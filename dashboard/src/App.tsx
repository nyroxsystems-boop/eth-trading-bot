import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
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
        if (res.ok) setStatus(await res.json())
      } catch { /* API may not be running yet */ }
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 15000) // 15s refresh
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

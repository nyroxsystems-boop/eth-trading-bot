import { useState, useEffect } from 'react'
import { Plus, Trash2, Settings, Play, Pause, TrendingUp, TrendingDown, X, Search, Star } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface PortfolioPair {
    id: number
    trading_pair: string
    pair_name: string
    pair_icon: string
    allocated_capital: number
    risk_per_trade: number
    max_trades_per_day: number
    take_profit_pct: number
    stop_loss_pct: number
    enabled: boolean
    total_pnl: number
    total_trades: number
    win_rate: number
    pnl_percent: number
}

interface PortfolioData {
    pairs: PortfolioPair[]
    total_pairs: number
    total_capital: number
    total_pnl: number
    total_pnl_percent: number
}

interface TradingPair {
    symbol: string
    name: string
    icon: string
    popular?: boolean
}

const MultiPairPortfolio = () => {
    const { token } = useAuth()
    const [portfolio, setPortfolio] = useState<PortfolioData>({
        pairs: [],
        total_pairs: 0,
        total_capital: 0,
        total_pnl: 0,
        total_pnl_percent: 0
    })
    const [loading, setLoading] = useState(true)
    const [showAddModal, setShowAddModal] = useState(false)
    const [showEditModal, setShowEditModal] = useState<PortfolioPair | null>(null)
    const [availablePairs, setAvailablePairs] = useState<TradingPair[]>([])
    const [popularPairs, setPopularPairs] = useState<TradingPair[]>([])
    const [searchQuery, setSearchQuery] = useState('')

    // Add pair form state
    const [newPair, setNewPair] = useState({
        trading_pair: '',
        allocated_capital: 100,
        risk_per_trade: 1,
        max_trades_per_day: 10,
        take_profit_pct: 2.5,
        stop_loss_pct: 1.5
    })

    useEffect(() => {
        fetchPortfolio()
        fetchAvailablePairs()
    }, [token])

    const fetchPortfolio = async () => {
        if (!token) return
        try {
            const res = await fetch(`${API_URL}/api/portfolio/pairs`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setPortfolio(data)
            }
        } catch (err) {
            console.error('Failed to fetch portfolio:', err)
        } finally {
            setLoading(false)
        }
    }

    const fetchAvailablePairs = async () => {
        try {
            const res = await fetch(`${API_URL}/api/trading/pairs${searchQuery ? `?search=${searchQuery}` : ''}`)
            if (res.ok) {
                const data = await res.json()
                setAvailablePairs(data.pairs || [])
                setPopularPairs(data.popular || [])
            }
        } catch (err) {
            console.error('Failed to fetch pairs:', err)
        }
    }

    const addPair = async () => {
        if (!token || !newPair.trading_pair) return
        try {
            const res = await fetch(`${API_URL}/api/portfolio/pairs`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(newPair)
            })
            if (res.ok) {
                setShowAddModal(false)
                setNewPair({
                    trading_pair: '',
                    allocated_capital: 100,
                    risk_per_trade: 1,
                    max_trades_per_day: 10,
                    take_profit_pct: 2.5,
                    stop_loss_pct: 1.5
                })
                fetchPortfolio()
            } else {
                const err = await res.json()
                alert(err.detail || 'Failed to add pair')
            }
        } catch (err) {
            console.error('Failed to add pair:', err)
        }
    }

    const updatePair = async () => {
        if (!token || !showEditModal) return
        try {
            const res = await fetch(`${API_URL}/api/portfolio/pairs/${showEditModal.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    allocated_capital: showEditModal.allocated_capital,
                    risk_per_trade: showEditModal.risk_per_trade,
                    max_trades_per_day: showEditModal.max_trades_per_day,
                    take_profit_pct: showEditModal.take_profit_pct,
                    stop_loss_pct: showEditModal.stop_loss_pct
                })
            })
            if (res.ok) {
                setShowEditModal(null)
                fetchPortfolio()
            }
        } catch (err) {
            console.error('Failed to update pair:', err)
        }
    }

    const deletePair = async (pairId: number) => {
        if (!token) return
        if (!confirm('Remove this pair from your portfolio?')) return
        try {
            const res = await fetch(`${API_URL}/api/portfolio/pairs/${pairId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                fetchPortfolio()
            }
        } catch (err) {
            console.error('Failed to delete pair:', err)
        }
    }

    const togglePair = async (pairId: number) => {
        if (!token) return
        try {
            const res = await fetch(`${API_URL}/api/portfolio/pairs/${pairId}/toggle`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                fetchPortfolio()
            }
        } catch (err) {
            console.error('Failed to toggle pair:', err)
        }
    }

    const selectPairForAdd = (pair: TradingPair) => {
        setNewPair(prev => ({
            ...prev,
            trading_pair: pair.symbol
        }))
    }

    // Filter pairs that are not already in portfolio
    const filteredAvailablePairs = availablePairs.filter(
        p => !portfolio.pairs.some(pp => pp.trading_pair === p.symbol)
    ).filter(p =>
        !searchQuery ||
        p.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.name.toLowerCase().includes(searchQuery.toLowerCase())
    )

    if (loading) {
        return (
            <div className="glass-card" style={{ padding: '48px', textAlign: 'center' }}>
                <div className="loading-spinner" />
                <p style={{ color: '#94A3B8', marginTop: '16px' }}>Loading portfolio...</p>
            </div>
        )
    }

    return (
        <div>
            {/* Portfolio Summary */}
            <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <div>
                        <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '4px' }}>
                            📊 My Trading Portfolio
                        </h2>
                        <p style={{ color: '#94A3B8', fontSize: '14px' }}>
                            {portfolio.total_pairs} active trading pairs
                        </p>
                    </div>
                    <button
                        onClick={() => setShowAddModal(true)}
                        style={{
                            padding: '12px 24px',
                            background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                            border: 'none',
                            borderRadius: '10px',
                            color: 'white',
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                        }}
                    >
                        <Plus size={20} /> Add Pair
                    </button>
                </div>

                {/* Summary Stats */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '16px' }}>
                    <div style={{ background: 'rgba(139, 92, 246, 0.1)', padding: '16px', borderRadius: '12px' }}>
                        <div style={{ fontSize: '12px', color: '#94A3B8', marginBottom: '4px' }}>Total Capital</div>
                        <div style={{ fontSize: '24px', fontWeight: 700 }}>${portfolio.total_capital.toLocaleString()}</div>
                    </div>
                    <div style={{
                        background: portfolio.total_pnl >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        padding: '16px',
                        borderRadius: '12px'
                    }}>
                        <div style={{ fontSize: '12px', color: '#94A3B8', marginBottom: '4px' }}>Total P&L</div>
                        <div style={{
                            fontSize: '24px',
                            fontWeight: 700,
                            color: portfolio.total_pnl >= 0 ? '#10B981' : '#EF4444'
                        }}>
                            {portfolio.total_pnl >= 0 ? '+' : ''}${portfolio.total_pnl.toFixed(2)}
                        </div>
                    </div>
                    <div style={{
                        background: portfolio.total_pnl_percent >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        padding: '16px',
                        borderRadius: '12px'
                    }}>
                        <div style={{ fontSize: '12px', color: '#94A3B8', marginBottom: '4px' }}>ROI</div>
                        <div style={{
                            fontSize: '24px',
                            fontWeight: 700,
                            color: portfolio.total_pnl_percent >= 0 ? '#10B981' : '#EF4444',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px'
                        }}>
                            {portfolio.total_pnl_percent >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
                            {portfolio.total_pnl_percent >= 0 ? '+' : ''}{portfolio.total_pnl_percent.toFixed(2)}%
                        </div>
                    </div>
                </div>
            </div>

            {/* Trading Pairs List */}
            {portfolio.pairs.length === 0 ? (
                <div className="glass-card" style={{ padding: '48px', textAlign: 'center' }}>
                    <div style={{ fontSize: '64px', marginBottom: '16px' }}>📈</div>
                    <h3 style={{ fontSize: '20px', marginBottom: '8px' }}>No Trading Pairs Yet</h3>
                    <p style={{ color: '#94A3B8', marginBottom: '24px' }}>
                        Add your first trading pair to start building your portfolio
                    </p>
                    <button
                        onClick={() => setShowAddModal(true)}
                        style={{
                            padding: '14px 28px',
                            background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                            border: 'none',
                            borderRadius: '10px',
                            color: 'white',
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px'
                        }}
                    >
                        <Plus size={20} /> Add Your First Pair
                    </button>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {portfolio.pairs.map(pair => (
                        <div
                            key={pair.id}
                            className="glass-card"
                            style={{
                                padding: '20px',
                                opacity: pair.enabled ? 1 : 0.6,
                                transition: 'all 0.3s'
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                {/* Pair Icon & Name */}
                                <div style={{
                                    fontSize: '32px',
                                    width: '56px',
                                    height: '56px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    background: 'rgba(139, 92, 246, 0.1)',
                                    borderRadius: '12px'
                                }}>
                                    {pair.pair_icon}
                                </div>
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <h3 style={{ fontSize: '18px', fontWeight: 600 }}>{pair.pair_name}</h3>
                                        <span style={{
                                            fontSize: '12px',
                                            color: '#64748B',
                                            background: 'rgba(100, 116, 139, 0.2)',
                                            padding: '2px 8px',
                                            borderRadius: '4px'
                                        }}>
                                            {pair.trading_pair}
                                        </span>
                                        {!pair.enabled && (
                                            <span style={{
                                                fontSize: '11px',
                                                color: '#F59E0B',
                                                background: 'rgba(245, 158, 11, 0.2)',
                                                padding: '2px 8px',
                                                borderRadius: '4px'
                                            }}>
                                                PAUSED
                                            </span>
                                        )}
                                    </div>
                                    <div style={{ display: 'flex', gap: '16px', marginTop: '4px', fontSize: '13px', color: '#94A3B8' }}>
                                        <span>💰 ${pair.allocated_capital}</span>
                                        <span>⚡ {pair.risk_per_trade}% risk</span>
                                        <span>🎯 TP {pair.take_profit_pct}%</span>
                                        <span>🛑 SL {pair.stop_loss_pct}%</span>
                                    </div>
                                </div>

                                {/* P&L */}
                                <div style={{ textAlign: 'right', minWidth: '120px' }}>
                                    <div style={{
                                        fontSize: '18px',
                                        fontWeight: 700,
                                        color: pair.total_pnl >= 0 ? '#10B981' : '#EF4444'
                                    }}>
                                        {pair.total_pnl >= 0 ? '+' : ''}${pair.total_pnl.toFixed(2)}
                                    </div>
                                    <div style={{
                                        fontSize: '13px',
                                        color: pair.pnl_percent >= 0 ? '#10B981' : '#EF4444'
                                    }}>
                                        {pair.pnl_percent >= 0 ? '+' : ''}{pair.pnl_percent.toFixed(2)}%
                                    </div>
                                </div>

                                {/* Actions */}
                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <button
                                        onClick={() => togglePair(pair.id)}
                                        style={{
                                            padding: '10px',
                                            background: pair.enabled ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                                            border: 'none',
                                            borderRadius: '8px',
                                            color: pair.enabled ? '#F59E0B' : '#10B981',
                                            cursor: 'pointer'
                                        }}
                                        title={pair.enabled ? 'Pause trading' : 'Resume trading'}
                                    >
                                        {pair.enabled ? <Pause size={18} /> : <Play size={18} />}
                                    </button>
                                    <button
                                        onClick={() => setShowEditModal(pair)}
                                        style={{
                                            padding: '10px',
                                            background: 'rgba(139, 92, 246, 0.2)',
                                            border: 'none',
                                            borderRadius: '8px',
                                            color: '#8B5CF6',
                                            cursor: 'pointer'
                                        }}
                                        title="Edit settings"
                                    >
                                        <Settings size={18} />
                                    </button>
                                    <button
                                        onClick={() => deletePair(pair.id)}
                                        style={{
                                            padding: '10px',
                                            background: 'rgba(239, 68, 68, 0.2)',
                                            border: 'none',
                                            borderRadius: '8px',
                                            color: '#EF4444',
                                            cursor: 'pointer'
                                        }}
                                        title="Remove pair"
                                    >
                                        <Trash2 size={18} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Add Pair Modal */}
            {showAddModal && (
                <div style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'rgba(0, 0, 0, 0.8)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000,
                    padding: '20px'
                }}>
                    <div style={{
                        background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
                        borderRadius: '16px',
                        padding: '32px',
                        width: '100%',
                        maxWidth: '500px',
                        maxHeight: '90vh',
                        overflowY: 'auto',
                        border: '1px solid rgba(139, 92, 246, 0.3)'
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                            <h2 style={{ fontSize: '22px', fontWeight: 700 }}>➕ Add Trading Pair</h2>
                            <button
                                onClick={() => setShowAddModal(false)}
                                style={{ background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer' }}
                            >
                                <X size={24} />
                            </button>
                        </div>

                        {/* Pair Selection */}
                        <div style={{ marginBottom: '20px' }}>
                            <label style={{ fontSize: '14px', color: '#94A3B8', marginBottom: '8px', display: 'block' }}>
                                Select Trading Pair
                            </label>

                            {/* Search */}
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                padding: '12px',
                                background: 'rgba(139, 92, 246, 0.1)',
                                borderRadius: '8px',
                                marginBottom: '12px'
                            }}>
                                <Search size={18} color="#94A3B8" />
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => {
                                        setSearchQuery(e.target.value)
                                        fetchAvailablePairs()
                                    }}
                                    placeholder="Search coins..."
                                    style={{
                                        flex: 1,
                                        background: 'transparent',
                                        border: 'none',
                                        outline: 'none',
                                        color: 'white'
                                    }}
                                />
                            </div>

                            {/* Selected pair display */}
                            {newPair.trading_pair && (
                                <div style={{
                                    padding: '12px',
                                    background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(236, 72, 153, 0.2) 100%)',
                                    borderRadius: '8px',
                                    marginBottom: '12px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px'
                                }}>
                                    <span style={{ fontSize: '24px' }}>
                                        {availablePairs.find(p => p.symbol === newPair.trading_pair)?.icon || '💰'}
                                    </span>
                                    <span style={{ fontWeight: 600 }}>{newPair.trading_pair}</span>
                                    <button
                                        onClick={() => setNewPair(prev => ({ ...prev, trading_pair: '' }))}
                                        style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer' }}
                                    >
                                        <X size={16} />
                                    </button>
                                </div>
                            )}

                            {/* Popular pairs */}
                            {!newPair.trading_pair && (
                                <>
                                    <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                        <Star size={12} /> Popular
                                    </div>
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '16px' }}>
                                        {popularPairs.filter(p => !portfolio.pairs.some(pp => pp.trading_pair === p.symbol)).slice(0, 8).map(pair => (
                                            <button
                                                key={pair.symbol}
                                                onClick={() => selectPairForAdd(pair)}
                                                style={{
                                                    padding: '8px 12px',
                                                    background: 'rgba(139, 92, 246, 0.15)',
                                                    border: 'none',
                                                    borderRadius: '20px',
                                                    color: 'white',
                                                    cursor: 'pointer',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '4px'
                                                }}
                                            >
                                                {pair.icon} {pair.symbol.replace('USDT', '')}
                                            </button>
                                        ))}
                                    </div>

                                    {/* All pairs list */}
                                    <div style={{ maxHeight: '150px', overflowY: 'auto' }}>
                                        {filteredAvailablePairs.slice(0, 20).map(pair => (
                                            <button
                                                key={pair.symbol}
                                                onClick={() => selectPairForAdd(pair)}
                                                style={{
                                                    width: '100%',
                                                    padding: '10px',
                                                    background: 'transparent',
                                                    border: 'none',
                                                    borderRadius: '8px',
                                                    color: 'white',
                                                    cursor: 'pointer',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '10px',
                                                    textAlign: 'left'
                                                }}
                                                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(139, 92, 246, 0.1)'}
                                                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                                            >
                                                <span style={{ fontSize: '20px' }}>{pair.icon}</span>
                                                <span>{pair.name}</span>
                                                <span style={{ color: '#64748B', marginLeft: 'auto' }}>{pair.symbol}</span>
                                            </button>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Settings */}
                        {newPair.trading_pair && (
                            <>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                                    <div>
                                        <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                            💰 Capital ($)
                                        </label>
                                        <input
                                            type="number"
                                            value={newPair.allocated_capital}
                                            onChange={(e) => setNewPair(prev => ({ ...prev, allocated_capital: parseFloat(e.target.value) || 0 }))}
                                            style={{
                                                width: '100%',
                                                padding: '12px',
                                                background: 'rgba(139, 92, 246, 0.1)',
                                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                                borderRadius: '8px',
                                                color: 'white'
                                            }}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                            ⚡ Risk per Trade (%)
                                        </label>
                                        <input
                                            type="number"
                                            step="0.1"
                                            value={newPair.risk_per_trade}
                                            onChange={(e) => setNewPair(prev => ({ ...prev, risk_per_trade: parseFloat(e.target.value) || 1 }))}
                                            style={{
                                                width: '100%',
                                                padding: '12px',
                                                background: 'rgba(139, 92, 246, 0.1)',
                                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                                borderRadius: '8px',
                                                color: 'white'
                                            }}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                            🎯 Take Profit (%)
                                        </label>
                                        <input
                                            type="number"
                                            step="0.1"
                                            value={newPair.take_profit_pct}
                                            onChange={(e) => setNewPair(prev => ({ ...prev, take_profit_pct: parseFloat(e.target.value) || 1.5 }))}
                                            style={{
                                                width: '100%',
                                                padding: '12px',
                                                background: 'rgba(139, 92, 246, 0.1)',
                                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                                borderRadius: '8px',
                                                color: 'white'
                                            }}
                                        />
                                    </div>
                                    <div>
                                        <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                            🛑 Stop Loss (%)
                                        </label>
                                        <input
                                            type="number"
                                            step="0.1"
                                            value={newPair.stop_loss_pct}
                                            onChange={(e) => setNewPair(prev => ({ ...prev, stop_loss_pct: parseFloat(e.target.value) || 1 }))}
                                            style={{
                                                width: '100%',
                                                padding: '12px',
                                                background: 'rgba(139, 92, 246, 0.1)',
                                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                                borderRadius: '8px',
                                                color: 'white'
                                            }}
                                        />
                                    </div>
                                </div>

                                <button
                                    onClick={addPair}
                                    style={{
                                        width: '100%',
                                        padding: '14px',
                                        background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                                        border: 'none',
                                        borderRadius: '10px',
                                        color: 'white',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        fontSize: '16px'
                                    }}
                                >
                                    Add to Portfolio
                                </button>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Edit Modal */}
            {showEditModal && (
                <div style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'rgba(0, 0, 0, 0.8)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000,
                    padding: '20px'
                }}>
                    <div style={{
                        background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
                        borderRadius: '16px',
                        padding: '32px',
                        width: '100%',
                        maxWidth: '450px',
                        border: '1px solid rgba(139, 92, 246, 0.3)'
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <span style={{ fontSize: '32px' }}>{showEditModal.pair_icon}</span>
                                <div>
                                    <h2 style={{ fontSize: '20px', fontWeight: 700 }}>{showEditModal.pair_name}</h2>
                                    <p style={{ color: '#64748B', fontSize: '13px' }}>{showEditModal.trading_pair}</p>
                                </div>
                            </div>
                            <button
                                onClick={() => setShowEditModal(null)}
                                style={{ background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer' }}
                            >
                                <X size={24} />
                            </button>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                            <div>
                                <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                    💰 Capital ($)
                                </label>
                                <input
                                    type="number"
                                    value={showEditModal.allocated_capital}
                                    onChange={(e) => setShowEditModal(prev => prev ? { ...prev, allocated_capital: parseFloat(e.target.value) || 0 } : null)}
                                    style={{
                                        width: '100%',
                                        padding: '12px',
                                        background: 'rgba(139, 92, 246, 0.1)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '8px',
                                        color: 'white'
                                    }}
                                />
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                    ⚡ Risk (%)
                                </label>
                                <input
                                    type="number"
                                    step="0.1"
                                    value={showEditModal.risk_per_trade}
                                    onChange={(e) => setShowEditModal(prev => prev ? { ...prev, risk_per_trade: parseFloat(e.target.value) || 1 } : null)}
                                    style={{
                                        width: '100%',
                                        padding: '12px',
                                        background: 'rgba(139, 92, 246, 0.1)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '8px',
                                        color: 'white'
                                    }}
                                />
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                    🎯 Take Profit (%)
                                </label>
                                <input
                                    type="number"
                                    step="0.1"
                                    value={showEditModal.take_profit_pct}
                                    onChange={(e) => setShowEditModal(prev => prev ? { ...prev, take_profit_pct: parseFloat(e.target.value) || 1.5 } : null)}
                                    style={{
                                        width: '100%',
                                        padding: '12px',
                                        background: 'rgba(139, 92, 246, 0.1)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '8px',
                                        color: 'white'
                                    }}
                                />
                            </div>
                            <div>
                                <label style={{ fontSize: '13px', color: '#94A3B8', marginBottom: '6px', display: 'block' }}>
                                    🛑 Stop Loss (%)
                                </label>
                                <input
                                    type="number"
                                    step="0.1"
                                    value={showEditModal.stop_loss_pct}
                                    onChange={(e) => setShowEditModal(prev => prev ? { ...prev, stop_loss_pct: parseFloat(e.target.value) || 1 } : null)}
                                    style={{
                                        width: '100%',
                                        padding: '12px',
                                        background: 'rgba(139, 92, 246, 0.1)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '8px',
                                        color: 'white'
                                    }}
                                />
                            </div>
                        </div>

                        <button
                            onClick={updatePair}
                            style={{
                                width: '100%',
                                padding: '14px',
                                background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                                border: 'none',
                                borderRadius: '10px',
                                color: 'white',
                                fontWeight: 600,
                                cursor: 'pointer',
                                fontSize: '16px'
                            }}
                        >
                            Save Changes
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}

export default MultiPairPortfolio

import { useState, useEffect, useRef } from 'react'
import { Search, ChevronDown, Star, TrendingUp } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TradingPair {
    symbol: string
    base?: string
    name: string
    icon: string
    popular?: boolean
}

interface TradingPairSelectorProps {
    onPairChange?: (pair: TradingPair) => void
}

export const TradingPairSelector = ({ onPairChange }: TradingPairSelectorProps) => {
    const { token } = useAuth()
    const [isOpen, setIsOpen] = useState(false)
    const [search, setSearch] = useState('')
    const [pairs, setPairs] = useState<TradingPair[]>([])
    const [popularPairs, setPopularPairs] = useState<TradingPair[]>([])
    const [currentPair, setCurrentPair] = useState<TradingPair>({
        symbol: 'ETHUSDT',
        name: 'Ethereum',
        icon: '🔷'
    })
    const [loading, setLoading] = useState(false)
    const dropdownRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        fetchCurrentPair()
        fetchPairs()
    }, [token])

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false)
            }
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    const fetchCurrentPair = async () => {
        if (!token) return
        try {
            const res = await fetch(`${API_URL}/api/settings/trading-pair`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setCurrentPair({
                    symbol: data.trading_pair,
                    name: data.name,
                    icon: data.icon
                })
            }
        } catch (err) {
            console.error('Failed to fetch trading pair:', err)
        }
    }

    const fetchPairs = async () => {
        try {
            const res = await fetch(`${API_URL}/api/trading/pairs${search ? `?search=${search}` : ''}`)
            if (res.ok) {
                const data = await res.json()
                setPairs(data.pairs || [])
                setPopularPairs(data.popular || [])
            }
        } catch (err) {
            console.error('Failed to fetch pairs:', err)
        }
    }

    const selectPair = async (pair: TradingPair) => {
        if (!token) return
        setLoading(true)
        try {
            const res = await fetch(`${API_URL}/api/settings/trading-pair`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ trading_pair: pair.symbol })
            })
            if (res.ok) {
                setCurrentPair(pair)
                setIsOpen(false)
                onPairChange?.(pair)
            }
        } catch (err) {
            console.error('Failed to set trading pair:', err)
        } finally {
            setLoading(false)
        }
    }

    // Filter pairs based on search
    const filteredPairs = search
        ? pairs.filter(p =>
            p.symbol.toLowerCase().includes(search.toLowerCase()) ||
            p.name.toLowerCase().includes(search.toLowerCase())
        )
        : pairs

    return (
        <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
            <h3 style={{
                fontSize: '18px',
                fontWeight: 600,
                marginBottom: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }}>
                <TrendingUp size={20} />
                Trading Pair
                <span style={{
                    marginLeft: 'auto',
                    fontSize: '14px',
                    fontWeight: 400,
                    color: '#94A3B8'
                }}>
                    What do you want to trade?
                </span>
            </h3>

            {/* Current Selection / Dropdown Trigger */}
            <div ref={dropdownRef} style={{ position: 'relative' }}>
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    style={{
                        width: '100%',
                        padding: '16px 20px',
                        background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(236, 72, 153, 0.15) 100%)',
                        border: '2px solid rgba(139, 92, 246, 0.3)',
                        borderRadius: '12px',
                        color: 'white',
                        fontSize: '18px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        transition: 'all 0.3s'
                    }}
                >
                    <span style={{ fontSize: '28px' }}>{currentPair.icon}</span>
                    <div style={{ flex: 1, textAlign: 'left' }}>
                        <div>{currentPair.name}</div>
                        <div style={{ fontSize: '14px', color: '#94A3B8', fontWeight: 400 }}>
                            {currentPair.symbol}
                        </div>
                    </div>
                    <ChevronDown
                        size={24}
                        style={{
                            transition: 'transform 0.3s',
                            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)'
                        }}
                    />
                </button>

                {/* Dropdown */}
                {isOpen && (
                    <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        right: 0,
                        marginTop: '8px',
                        background: 'rgba(15, 23, 42, 0.98)',
                        border: '1px solid rgba(139, 92, 246, 0.3)',
                        borderRadius: '12px',
                        boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
                        zIndex: 1000,
                        maxHeight: '400px',
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column'
                    }}>
                        {/* Search Bar */}
                        <div style={{ padding: '12px', borderBottom: '1px solid rgba(139, 92, 246, 0.2)' }}>
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                padding: '10px 14px',
                                background: 'rgba(139, 92, 246, 0.1)',
                                borderRadius: '8px',
                                border: '1px solid rgba(139, 92, 246, 0.2)'
                            }}>
                                <Search size={18} color="#94A3B8" />
                                <input
                                    type="text"
                                    value={search}
                                    onChange={(e) => {
                                        setSearch(e.target.value)
                                        fetchPairs()
                                    }}
                                    placeholder="Search coins... (ETH, BTC, SOL...)"
                                    style={{
                                        flex: 1,
                                        background: 'transparent',
                                        border: 'none',
                                        outline: 'none',
                                        color: 'white',
                                        fontSize: '14px'
                                    }}
                                    autoFocus
                                />
                            </div>
                        </div>

                        {/* Popular Pairs */}
                        {!search && (
                            <div style={{ padding: '12px', borderBottom: '1px solid rgba(139, 92, 246, 0.2)' }}>
                                <div style={{
                                    fontSize: '12px',
                                    color: '#94A3B8',
                                    marginBottom: '8px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px'
                                }}>
                                    <Star size={12} /> Popular
                                </div>
                                <div style={{
                                    display: 'flex',
                                    flexWrap: 'wrap',
                                    gap: '6px'
                                }}>
                                    {popularPairs.slice(0, 6).map(pair => (
                                        <button
                                            key={pair.symbol}
                                            onClick={() => selectPair(pair)}
                                            disabled={loading}
                                            style={{
                                                padding: '6px 12px',
                                                background: currentPair.symbol === pair.symbol
                                                    ? 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)'
                                                    : 'rgba(139, 92, 246, 0.15)',
                                                border: 'none',
                                                borderRadius: '20px',
                                                color: 'white',
                                                fontSize: '13px',
                                                cursor: 'pointer',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '4px',
                                                transition: 'all 0.2s'
                                            }}
                                        >
                                            {pair.icon} {pair.symbol.replace('USDT', '')}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* All Pairs List */}
                        <div style={{
                            flex: 1,
                            overflowY: 'auto',
                            padding: '8px'
                        }}>
                            {filteredPairs.length === 0 ? (
                                <div style={{
                                    padding: '20px',
                                    textAlign: 'center',
                                    color: '#64748B'
                                }}>
                                    No pairs found for "{search}"
                                </div>
                            ) : (
                                filteredPairs.map(pair => (
                                    <button
                                        key={pair.symbol}
                                        onClick={() => selectPair(pair)}
                                        disabled={loading}
                                        style={{
                                            width: '100%',
                                            padding: '12px',
                                            background: currentPair.symbol === pair.symbol
                                                ? 'rgba(139, 92, 246, 0.2)'
                                                : 'transparent',
                                            border: 'none',
                                            borderRadius: '8px',
                                            color: 'white',
                                            fontSize: '14px',
                                            cursor: 'pointer',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '12px',
                                            transition: 'all 0.2s'
                                        }}
                                        onMouseEnter={(e) => {
                                            if (currentPair.symbol !== pair.symbol) {
                                                e.currentTarget.style.background = 'rgba(139, 92, 246, 0.1)'
                                            }
                                        }}
                                        onMouseLeave={(e) => {
                                            if (currentPair.symbol !== pair.symbol) {
                                                e.currentTarget.style.background = 'transparent'
                                            }
                                        }}
                                    >
                                        <span style={{ fontSize: '24px' }}>{pair.icon}</span>
                                        <div style={{ flex: 1, textAlign: 'left' }}>
                                            <div style={{ fontWeight: 500 }}>{pair.name}</div>
                                            <div style={{ fontSize: '12px', color: '#64748B' }}>
                                                {pair.symbol}
                                            </div>
                                        </div>
                                        {pair.popular && (
                                            <Star size={14} color="#F59E0B" fill="#F59E0B" />
                                        )}
                                    </button>
                                ))
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Info */}
            <div style={{
                marginTop: '16px',
                padding: '12px',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                borderRadius: '8px',
                fontSize: '13px',
                color: '#10B981'
            }}>
                💡 The bot will automatically learn and optimize strategies for your selected trading pair.
            </div>
        </div>
    )
}

export default TradingPairSelector

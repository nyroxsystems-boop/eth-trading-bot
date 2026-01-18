import { useState, useEffect } from 'react'
import { Trophy, Users, TrendingUp, TrendingDown, Star, UserPlus, UserMinus, Settings2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TraderStats {
    user_id: number
    username: string
    total_pnl: number
    win_rate: number
    total_trades: number
    followers_count: number
    is_verified: boolean
    rank: number
    performance_30d: number
}

interface FollowRelation {
    leader_id: number
    copy_percentage: number
    max_position_size: number
    is_active: boolean
}

const LeaderboardView = () => {
    const [traders, setTraders] = useState<TraderStats[]>([])
    const [following, setFollowing] = useState<FollowRelation[]>([])
    const [selectedTrader, setSelectedTrader] = useState<TraderStats | null>(null)
    const [showFollowModal, setShowFollowModal] = useState(false)
    const [followSettings, setFollowSettings] = useState({ copy_pct: 0.5, max_size: 500 })
    const [loading, setLoading] = useState(true)
    const [activeTab, setActiveTab] = useState<'leaderboard' | 'following'>('leaderboard')

    useEffect(() => {
        fetchLeaderboard()
        fetchFollowing()
    }, [])

    const fetchLeaderboard = async () => {
        setLoading(true)
        try {
            const token = localStorage.getItem('token')
            const response = await fetch(`${API_URL}/api/copy-trading/leaderboard`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (response.ok) {
                const data = await response.json()
                setTraders(data.traders || [])
            } else {
                setTraders(generateMockTraders())
            }
        } catch {
            setTraders(generateMockTraders())
        } finally {
            setLoading(false)
        }
    }

    const fetchFollowing = async () => {
        try {
            const token = localStorage.getItem('token')
            const response = await fetch(`${API_URL}/api/copy-trading/following`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (response.ok) {
                const data = await response.json()
                setFollowing(data.following || [])
            }
        } catch {
            console.error('Failed to fetch following')
        }
    }

    const generateMockTraders = (): TraderStats[] => {
        const result: TraderStats[] = []
        for (let i = 0; i < 20; i++) {
            const rankFactor = 1 - (i / 20)
            result.push({
                user_id: 1000 + i,
                username: `CryptoMaster${1000 + i}`,
                total_pnl: Math.round((rankFactor * 50000) + (Math.random() * 5000)),
                win_rate: Math.min(0.85, 0.45 + (rankFactor * 0.25)),
                total_trades: Math.floor(Math.random() * 400 + 100),
                followers_count: Math.floor((rankFactor ** 2) * 1000),
                is_verified: i < 5,
                rank: i + 1,
                performance_30d: Math.round((rankFactor * 15) * 100) / 100
            })
        }
        return result
    }

    const isFollowingTrader = (traderId: number) => {
        return following.some(f => f.leader_id === traderId && f.is_active)
    }

    const handleFollow = async () => {
        if (!selectedTrader) return
        setFollowing(prev => [...prev, {
            leader_id: selectedTrader.user_id,
            copy_percentage: followSettings.copy_pct,
            max_position_size: followSettings.max_size,
            is_active: true
        }])
        setShowFollowModal(false)
    }

    const handleUnfollow = async (leaderId: number) => {
        setFollowing(prev => prev.filter(f => f.leader_id !== leaderId))
    }

    const getRankBadge = (rank: number) => {
        if (rank === 1) return { bg: 'linear-gradient(135deg, #FFD700, #FFA500)', text: '🥇' }
        if (rank === 2) return { bg: 'linear-gradient(135deg, #C0C0C0, #A9A9A9)', text: '🥈' }
        if (rank === 3) return { bg: 'linear-gradient(135deg, #CD7F32, #8B4513)', text: '🥉' }
        return { bg: 'var(--bg-tertiary)', text: `#${rank}` }
    }

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} style={{ padding: '32px' }}>
            <div style={{ marginBottom: '32px' }}>
                <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
                    <Trophy style={{ display: 'inline', marginRight: '12px', color: 'var(--accent-gold)' }} />
                    Copy Trading
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>Follow top traders and automatically copy their trades</p>
            </div>

            <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
                {(['leaderboard', 'following'] as const).map(tab => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        style={{
                            padding: '10px 20px',
                            borderRadius: '8px',
                            border: 'none',
                            background: activeTab === tab ? 'var(--primary-purple)' : 'var(--glass-bg)',
                            color: activeTab === tab ? 'white' : 'var(--text-secondary)',
                            cursor: 'pointer',
                            fontWeight: 500,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                        }}
                    >
                        {tab === 'leaderboard' ? <Trophy size={16} /> : <Users size={16} />}
                        {tab === 'leaderboard' ? 'Leaderboard' : `Following (${following.length})`}
                    </button>
                ))}
            </div>

            {activeTab === 'leaderboard' ? (
                <div className="glass-card" style={{ padding: '0', overflow: 'hidden' }}>
                    {loading ? (
                        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'var(--bg-tertiary)' }}>
                                    <th style={{ padding: '16px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>Rank</th>
                                    <th style={{ padding: '16px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>Trader</th>
                                    <th style={{ padding: '16px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>30D</th>
                                    <th style={{ padding: '16px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>Win Rate</th>
                                    <th style={{ padding: '16px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>P&L</th>
                                    <th style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {traders.map(trader => {
                                    const badge = getRankBadge(trader.rank)
                                    const isFollowed = isFollowingTrader(trader.user_id)
                                    return (
                                        <tr key={trader.user_id} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                            <td style={{ padding: '16px' }}>
                                                <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: badge.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: trader.rank <= 3 ? '16px' : '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                                                    {badge.text}
                                                </div>
                                            </td>
                                            <td style={{ padding: '16px' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'var(--gradient-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 600 }}>
                                                        {trader.username.charAt(0)}
                                                    </div>
                                                    <div>
                                                        <div style={{ fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                            {trader.username}
                                                            {trader.is_verified && <Star size={14} fill="var(--accent-gold)" color="var(--accent-gold)" />}
                                                        </div>
                                                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{trader.followers_count} followers</div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td style={{ padding: '16px', textAlign: 'right' }}>
                                                <span style={{ color: trader.performance_30d >= 0 ? 'var(--success)' : 'var(--error)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                                    {trader.performance_30d >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                                                    {trader.performance_30d >= 0 ? '+' : ''}{trader.performance_30d}%
                                                </span>
                                            </td>
                                            <td style={{ padding: '16px', textAlign: 'right', color: 'var(--text-primary)', fontWeight: 500 }}>
                                                {(trader.win_rate * 100).toFixed(1)}%
                                            </td>
                                            <td style={{ padding: '16px', textAlign: 'right', color: trader.total_pnl >= 0 ? 'var(--success)' : 'var(--error)', fontWeight: 600 }}>
                                                ${trader.total_pnl.toLocaleString()}
                                            </td>
                                            <td style={{ padding: '16px', textAlign: 'center' }}>
                                                <button
                                                    onClick={() => {
                                                        if (isFollowed) {
                                                            handleUnfollow(trader.user_id)
                                                        } else {
                                                            setSelectedTrader(trader)
                                                            setShowFollowModal(true)
                                                        }
                                                    }}
                                                    style={{
                                                        padding: '8px 16px',
                                                        borderRadius: '6px',
                                                        border: 'none',
                                                        background: isFollowed ? 'var(--error)' : 'var(--success)',
                                                        color: 'white',
                                                        cursor: 'pointer',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '6px',
                                                        fontSize: '13px'
                                                    }}
                                                >
                                                    {isFollowed ? <UserMinus size={14} /> : <UserPlus size={14} />}
                                                    {isFollowed ? 'Unfollow' : 'Follow'}
                                                </button>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    )}
                </div>
            ) : (
                <div>
                    {following.length === 0 ? (
                        <div className="glass-card" style={{ padding: '60px', textAlign: 'center' }}>
                            <Users size={48} color="var(--text-muted)" style={{ marginBottom: '16px' }} />
                            <h3 style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Not Following Anyone</h3>
                            <p style={{ color: 'var(--text-muted)', marginBottom: '24px' }}>Start following top traders</p>
                            <button onClick={() => setActiveTab('leaderboard')} style={{ padding: '12px 24px', borderRadius: '8px', border: 'none', background: 'var(--gradient-primary)', color: 'white', cursor: 'pointer' }}>
                                Browse Leaderboard
                            </button>
                        </div>
                    ) : (
                        <div style={{ display: 'grid', gap: '16px' }}>
                            {following.map(follow => {
                                const trader = traders.find(t => t.user_id === follow.leader_id)
                                return (
                                    <div key={follow.leader_id} className="glass-card" style={{ padding: '20px' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                                <div style={{ width: '50px', height: '50px', borderRadius: '50%', background: 'var(--gradient-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 600 }}>
                                                    {trader?.username.charAt(0) || 'T'}
                                                </div>
                                                <div>
                                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{trader?.username || `Trader #${follow.leader_id}`}</div>
                                                    <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Copy: {(follow.copy_percentage * 100).toFixed(0)}%</div>
                                                </div>
                                            </div>
                                            <div style={{ display: 'flex', gap: '8px' }}>
                                                <button style={{ padding: '8px', borderRadius: '6px', border: '1px solid var(--glass-border)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                                                    <Settings2 size={16} />
                                                </button>
                                                <button onClick={() => handleUnfollow(follow.leader_id)} style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', background: 'var(--error)', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                    <UserMinus size={14} />
                                                    Unfollow
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>
            )}

            <AnimatePresence>
                {showFollowModal && selectedTrader && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0, 0, 0, 0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '24px' }} onClick={() => setShowFollowModal(false)}>
                        <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }} className="glass-card" style={{ maxWidth: '420px', width: '100%', padding: '32px' }} onClick={e => e.stopPropagation()}>
                            <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>Follow {selectedTrader.username}</h2>
                            <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginBottom: '24px' }}>Configure copy settings</p>

                            <div style={{ marginBottom: '20px' }}>
                                <label style={{ display: 'block', color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '8px' }}>Copy Percentage</label>
                                <input type="range" min="0.1" max="1" step="0.1" value={followSettings.copy_pct} onChange={e => setFollowSettings(prev => ({ ...prev, copy_pct: parseFloat(e.target.value) }))} style={{ width: '100%' }} />
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: 'var(--text-muted)' }}>
                                    <span>10%</span>
                                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{(followSettings.copy_pct * 100).toFixed(0)}%</span>
                                    <span>100%</span>
                                </div>
                            </div>

                            <div style={{ marginBottom: '24px' }}>
                                <label style={{ display: 'block', color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '8px' }}>Max Position Size (USDT)</label>
                                <input type="number" value={followSettings.max_size} onChange={e => setFollowSettings(prev => ({ ...prev, max_size: parseFloat(e.target.value) || 0 }))} style={{ width: '100%', padding: '12px', background: 'var(--input-bg)', border: '1px solid var(--input-border)', borderRadius: '8px', color: 'var(--text-primary)' }} />
                            </div>

                            <div style={{ display: 'flex', gap: '12px' }}>
                                <button onClick={() => setShowFollowModal(false)} style={{ flex: 1, padding: '14px', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'transparent', color: 'var(--text-primary)', cursor: 'pointer' }}>Cancel</button>
                                <button onClick={handleFollow} style={{ flex: 2, padding: '14px', borderRadius: '8px', border: 'none', background: 'var(--success)', color: 'white', cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                                    <UserPlus size={18} />
                                    Start Copying
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    )
}

export default LeaderboardView

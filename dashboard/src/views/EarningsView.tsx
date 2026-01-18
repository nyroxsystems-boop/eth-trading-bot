import { useState, useEffect } from 'react'
import { DollarSign, TrendingUp, Users, Wallet, ArrowRight, Clock, CheckCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface LeaderEarnings {
    leader_id: number
    total_earned: number
    pending_earnings: number
    paid_earnings: number
    total_copied_trades: number
    profitable_trades: number
    total_profit_generated: number
    win_rate: number
}

interface FollowerSpending {
    follower_id: number
    total_fees_paid: number
    total_profit_from_copying: number
    net_result: number
    total_copied_trades: number
    roi: number
}

interface Commission {
    commission_id: string
    trade_id: string
    leader_id: number
    follower_id: number
    symbol: string
    trade_pnl: number
    gross_fee: number
    leader_amount: number
    status: string
    created_at: string
}

const EarningsView = () => {
    const [leaderEarnings, setLeaderEarnings] = useState<LeaderEarnings | null>(null)
    const [followerSpending, setFollowerSpending] = useState<FollowerSpending | null>(null)
    const [commissions, setCommissions] = useState<Commission[]>([])
    const [activeTab, setActiveTab] = useState<'leader' | 'copier'>('leader')
    const [loading, setLoading] = useState(true)
    const [payoutLoading, setPayoutLoading] = useState(false)

    useEffect(() => {
        fetchData()
    }, [])

    const fetchData = async () => {
        setLoading(true)
        const token = localStorage.getItem('token')

        // Default mock data for when API fails
        const mockLeaderEarnings: LeaderEarnings = {
            leader_id: 1,
            total_earned: 1250.50,
            pending_earnings: 340.25,
            paid_earnings: 910.25,
            total_copied_trades: 156,
            profitable_trades: 98,
            total_profit_generated: 12500.00,
            win_rate: 62.8
        }
        const mockFollowerSpending: FollowerSpending = {
            follower_id: 1,
            total_fees_paid: 125.00,
            total_profit_from_copying: 1250.00,
            net_result: 1125.00,
            total_copied_trades: 45,
            roi: 900
        }

        try {
            const [earningsRes, spendingRes, commissionsRes] = await Promise.all([
                fetch(`${API_URL}/api/revenue/leader-earnings`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                }),
                fetch(`${API_URL}/api/revenue/follower-spending`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                }),
                fetch(`${API_URL}/api/revenue/commissions`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                })
            ])

            // Leader earnings
            if (earningsRes.ok) {
                const data = await earningsRes.json()
                if (data.status === 'success' && data.earnings) {
                    setLeaderEarnings(data.earnings)
                } else {
                    setLeaderEarnings(mockLeaderEarnings)
                }
            } else {
                setLeaderEarnings(mockLeaderEarnings)
            }

            // Follower spending  
            if (spendingRes.ok) {
                const data = await spendingRes.json()
                if (data.status === 'success' && data.spending) {
                    setFollowerSpending(data.spending)
                } else {
                    setFollowerSpending(mockFollowerSpending)
                }
            } else {
                setFollowerSpending(mockFollowerSpending)
            }

            // Commissions
            if (commissionsRes.ok) {
                const data = await commissionsRes.json()
                setCommissions(data.commissions || [])
            } else {
                setCommissions([])
            }
        } catch (err) {
            console.error('Failed to fetch earnings data:', err)
            // Use mock data on error
            setLeaderEarnings(mockLeaderEarnings)
            setFollowerSpending(mockFollowerSpending)
            setCommissions([])
        } finally {
            setLoading(false)
        }
    }

    const requestPayout = async () => {
        setPayoutLoading(true)
        try {
            const token = localStorage.getItem('token')
            const response = await fetch(`${API_URL}/api/revenue/request-payout`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            })

            if (response.ok) {
                await fetchData()
            }
        } catch (err) {
            console.error('Payout request failed:', err)
        } finally {
            setPayoutLoading(false)
        }
    }

    if (loading) {
        return (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Loading earnings data...
            </div>
        )
    }

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} style={{ padding: '32px' }}>
            <div style={{ marginBottom: '32px' }}>
                <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
                    <DollarSign style={{ display: 'inline', marginRight: '12px', color: 'var(--success)' }} />
                    Earnings & Revenue
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                    Track your copy-trading earnings and fees
                </p>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
                <button
                    onClick={() => setActiveTab('leader')}
                    style={{
                        padding: '10px 20px',
                        borderRadius: '8px',
                        border: 'none',
                        background: activeTab === 'leader' ? 'var(--success)' : 'var(--glass-bg)',
                        color: activeTab === 'leader' ? 'white' : 'var(--text-secondary)',
                        cursor: 'pointer',
                        fontWeight: 500,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}
                >
                    <TrendingUp size={16} />
                    As Leader
                </button>
                <button
                    onClick={() => setActiveTab('copier')}
                    style={{
                        padding: '10px 20px',
                        borderRadius: '8px',
                        border: 'none',
                        background: activeTab === 'copier' ? 'var(--primary-purple)' : 'var(--glass-bg)',
                        color: activeTab === 'copier' ? 'white' : 'var(--text-secondary)',
                        cursor: 'pointer',
                        fontWeight: 500,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}
                >
                    <Users size={16} />
                    As Copier
                </button>
            </div>

            {activeTab === 'leader' && leaderEarnings && (
                <>
                    {/* Leader Stats */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Total Earned</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--success)' }}>
                                ${leaderEarnings.total_earned.toLocaleString()}
                            </div>
                        </div>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Pending Payout</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--accent-gold)' }}>
                                ${leaderEarnings.pending_earnings.toLocaleString()}
                            </div>
                        </div>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Profit Generated</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)' }}>
                                ${leaderEarnings.total_profit_generated.toLocaleString()}
                            </div>
                        </div>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Win Rate</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: leaderEarnings.win_rate >= 50 ? 'var(--success)' : 'var(--error)' }}>
                                {leaderEarnings.win_rate}%
                            </div>
                        </div>
                    </div>

                    {/* Payout Card */}
                    {leaderEarnings.pending_earnings >= 10 && (
                        <div className="glass-card" style={{ padding: '24px', marginBottom: '24px', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(139, 92, 246, 0.1))' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div>
                                    <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
                                        <Wallet style={{ display: 'inline', marginRight: '8px' }} />
                                        Ready for Payout
                                    </h3>
                                    <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                                        You have ${leaderEarnings.pending_earnings.toFixed(2)} available for withdrawal
                                    </p>
                                </div>
                                <button
                                    onClick={requestPayout}
                                    disabled={payoutLoading}
                                    style={{
                                        padding: '12px 24px',
                                        borderRadius: '8px',
                                        border: 'none',
                                        background: 'var(--success)',
                                        color: 'white',
                                        cursor: payoutLoading ? 'not-allowed' : 'pointer',
                                        fontWeight: 600,
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px'
                                    }}
                                >
                                    {payoutLoading ? 'Processing...' : 'Request Payout'}
                                    <ArrowRight size={18} />
                                </button>
                            </div>
                        </div>
                    )}

                    {/* How it Works */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px' }}>
                            How Earnings Work
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                            <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                <div style={{ fontSize: '24px', marginBottom: '8px' }}>💰</div>
                                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>10% Performance Fee</div>
                                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Charged on profitable copied trades</div>
                            </div>
                            <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                <div style={{ fontSize: '24px', marginBottom: '8px' }}>📊</div>
                                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>70% to You</div>
                                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>80% if you're verified</div>
                            </div>
                            <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                <div style={{ fontSize: '24px', marginBottom: '8px' }}>🏦</div>
                                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>Min $10 Payout</div>
                                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Request anytime above threshold</div>
                            </div>
                        </div>
                    </div>
                </>
            )}

            {activeTab === 'copier' && followerSpending && (
                <>
                    {/* Copier Stats */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Profit from Copying</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--success)' }}>
                                ${followerSpending.total_profit_from_copying.toLocaleString()}
                            </div>
                        </div>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Fees Paid</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-secondary)' }}>
                                ${followerSpending.total_fees_paid.toLocaleString()}
                            </div>
                        </div>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>Net Result</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: followerSpending.net_result >= 0 ? 'var(--success)' : 'var(--error)' }}>
                                ${followerSpending.net_result.toLocaleString()}
                            </div>
                        </div>
                        <div className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '8px' }}>ROI</div>
                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary-purple)' }}>
                                {followerSpending.roi}%
                            </div>
                        </div>
                    </div>

                    {/* Fee Breakdown */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px' }}>
                            Fee Breakdown
                        </h3>
                        <div style={{ padding: '16px', background: 'rgba(139, 92, 246, 0.05)', borderRadius: '12px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
                            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: '1.6' }}>
                                💡 <strong>How fees work:</strong> You only pay 10% of your <em>profits</em> when a copied trade closes in profit.
                                If a trade loses money, you pay nothing.
                            </p>
                            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: '1.6', marginTop: '12px' }}>
                                ✨ <strong>Elite Tier Benefit:</strong> Upgrade to Elite for 20% fee discount (only 8% instead of 10%).
                            </p>
                        </div>
                    </div>
                </>
            )}

            {/* Recent Commissions */}
            {commissions.length > 0 && (
                <div className="glass-card" style={{ padding: '24px', marginTop: '24px' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px' }}>
                        Recent Commissions
                    </h3>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                    <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>Date</th>
                                    <th style={{ padding: '12px', textAlign: 'left', color: 'var(--text-muted)', fontSize: '12px' }}>Symbol</th>
                                    <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>Trade P&L</th>
                                    <th style={{ padding: '12px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>Fee</th>
                                    <th style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {commissions.slice(0, 10).map(commission => (
                                    <tr key={commission.commission_id} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                        <td style={{ padding: '12px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                                            {new Date(commission.created_at).toLocaleDateString()}
                                        </td>
                                        <td style={{ padding: '12px', fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                                            {commission.symbol}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: commission.trade_pnl >= 0 ? 'var(--success)' : 'var(--error)', fontWeight: 600 }}>
                                            {commission.trade_pnl >= 0 ? '+' : ''}${commission.trade_pnl.toFixed(2)}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: 'var(--text-secondary)' }}>
                                            ${commission.gross_fee.toFixed(2)}
                                        </td>
                                        <td style={{ padding: '12px', textAlign: 'center' }}>
                                            {commission.status === 'paid' ? (
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--success)', fontSize: '12px' }}>
                                                    <CheckCircle size={14} /> Paid
                                                </span>
                                            ) : (
                                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--accent-gold)', fontSize: '12px' }}>
                                                    <Clock size={14} /> Pending
                                                </span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </motion.div>
    )
}

export default EarningsView

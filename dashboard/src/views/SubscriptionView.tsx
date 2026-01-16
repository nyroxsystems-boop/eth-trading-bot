import { useState, useEffect } from 'react'
import { Crown, Check, Zap } from 'lucide-react'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Tier {
    name: string
    max_accounts: number
    max_trading_pairs: number
    live_trading: boolean
    price: number
    features: string[]
}

interface Subscription {
    tier: string
    tier_name: string
    price: number
    features: string[]
    usage: any
    can_upgrade: boolean
}

const SubscriptionView = () => {
    const [subscription, setSubscription] = useState<Subscription | null>(null)
    const [tiers, setTiers] = useState<Record<string, Tier>>({})
    const [loading, setLoading] = useState(true)
    const [upgrading, setUpgrading] = useState(false)

    useEffect(() => {
        fetchData()
    }, [])

    const fetchData = async () => {
        try {
            const token = localStorage.getItem('token')
            const headers: HeadersInit = {
                'Content-Type': 'application/json'
            }

            if (token) {
                headers['Authorization'] = `Bearer ${token}`
            }

            const [subRes, tiersRes] = await Promise.all([
                fetch(`${API_URL}/api/subscription`, { headers }),
                fetch(`${API_URL}/api/subscription/tiers`)
            ])

            if (subRes.ok) {
                const subData = await subRes.json()
                setSubscription(subData)
            }

            if (tiersRes.ok) {
                const tiersData = await tiersRes.json()
                setTiers(tiersData.tiers || {})
            }
        } catch (err) {
            console.error('Failed to fetch subscription data:', err)
        } finally {
            setLoading(false)
        }
    }

    const handleUpgrade = async () => {
        setUpgrading(true)
        try {
            const token = localStorage.getItem('token')
            const res = await fetch(`${API_URL}/api/subscription/upgrade`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                }
            })

            if (res.ok) {
                alert('✅ Successfully upgraded to Premium!')
                fetchData()
            } else {
                const error = await res.json()
                alert(`❌ Upgrade failed: ${error.detail || 'Unknown error'}`)
            }
        } catch (err) {
            console.error('Failed to upgrade:', err)
            alert('❌ Error upgrading subscription')
        } finally {
            setUpgrading(false)
        }
    }

    if (loading) {
        return (
            <div style={{ padding: '24px', textAlign: 'center' }}>
                <div className="spinner" />
                <p style={{ marginTop: '16px', color: '#94A3B8' }}>Loading subscription data...</p>
            </div>
        )
    }

    const currentTier = subscription?.tier || 'free'
    const isPremium = currentTier === 'premium'

    return (
        <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
            {/* Header */}
            <div style={{ marginBottom: '32px', textAlign: 'center' }}>
                <h1 style={{
                    fontSize: '36px',
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    marginBottom: '8px'
                }}>
                    <Crown size={32} style={{ display: 'inline', marginRight: '8px', verticalAlign: 'middle' }} />
                    Subscription Plans
                </h1>
                <p style={{ color: '#94A3B8', fontSize: '18px' }}>
                    Choose the plan that fits your trading needs
                </p>
            </div>

            {/* Current Subscription Badge */}
            {subscription && (
                <div className="glass-card" style={{
                    padding: '20px',
                    marginBottom: '32px',
                    background: isPremium
                        ? 'linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(236, 72, 153, 0.2) 100%)'
                        : 'rgba(255, 255, 255, 0.05)'
                }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ fontSize: '14px', color: '#94A3B8', marginBottom: '4px' }}>
                                Current Plan
                            </div>
                            <div style={{ fontSize: '24px', fontWeight: 700 }}>
                                {subscription.tier_name}
                                {isPremium && <Crown size={20} style={{ marginLeft: '8px', color: '#F59E0B', display: 'inline' }} />}
                            </div>
                        </div>
                        <div style={{ fontSize: '32px', fontWeight: 700 }}>
                            ${subscription.price}
                            <span style={{ fontSize: '16px', color: '#94A3B8' }}>/month</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Pricing Cards */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                gap: '24px',
                marginBottom: '32px'
            }}>
                {/* Free Tier */}
                <div className="glass-card" style={{
                    padding: '32px',
                    border: currentTier === 'free' ? '2px solid #8B5CF6' : '1px solid rgba(255, 255, 255, 0.1)'
                }}>
                    <div style={{ marginBottom: '24px' }}>
                        <h3 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>
                            Free
                        </h3>
                        <div style={{ fontSize: '48px', fontWeight: 700, marginBottom: '8px' }}>
                            $0
                            <span style={{ fontSize: '18px', color: '#94A3B8' }}>/month</span>
                        </div>
                        <p style={{ color: '#94A3B8' }}>Perfect for getting started</p>
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        {tiers.free?.features.map((feature, i) => (
                            <div key={i} style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                marginBottom: '12px',
                                color: '#94A3B8'
                            }}>
                                <Check size={16} color="#10B981" />
                                <span>{feature}</span>
                            </div>
                        ))}
                    </div>

                    {currentTier === 'free' && (
                        <div style={{
                            padding: '12px',
                            background: 'rgba(139, 92, 246, 0.2)',
                            border: '1px solid rgba(139, 92, 246, 0.3)',
                            borderRadius: '8px',
                            textAlign: 'center',
                            fontWeight: 600
                        }}>
                            Current Plan
                        </div>
                    )}
                </div>

                {/* Premium Tier */}
                <div className="glass-card" style={{
                    padding: '32px',
                    border: currentTier === 'premium' ? '2px solid #F59E0B' : '2px solid rgba(139, 92, 246, 0.5)',
                    position: 'relative',
                    background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(236, 72, 153, 0.1) 100%)'
                }}>
                    {/* Popular Badge */}
                    <div style={{
                        position: 'absolute',
                        top: '-12px',
                        right: '24px',
                        background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                        padding: '6px 16px',
                        borderRadius: '20px',
                        fontSize: '12px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px'
                    }}>
                        <Zap size={12} style={{ display: 'inline', marginRight: '4px' }} />
                        Popular
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <h3 style={{
                            fontSize: '24px',
                            fontWeight: 700,
                            marginBottom: '8px',
                            background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent'
                        }}>
                            Premium
                            <Crown size={20} style={{ marginLeft: '8px', color: '#F59E0B', display: 'inline' }} />
                        </h3>
                        <div style={{ fontSize: '48px', fontWeight: 700, marginBottom: '8px' }}>
                            $29
                            <span style={{ fontSize: '18px', color: '#94A3B8' }}>/month</span>
                        </div>
                        <p style={{ color: '#94A3B8' }}>For serious traders</p>
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        {tiers.premium?.features.map((feature, i) => (
                            <div key={i} style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                marginBottom: '12px',
                                color: '#fff',
                                fontWeight: 500
                            }}>
                                <Check size={16} color="#10B981" />
                                <span>{feature}</span>
                            </div>
                        ))}
                    </div>

                    {currentTier === 'premium' ? (
                        <div style={{
                            padding: '12px',
                            background: 'rgba(245, 158, 11, 0.2)',
                            border: '1px solid rgba(245, 158, 11, 0.3)',
                            borderRadius: '8px',
                            textAlign: 'center',
                            fontWeight: 600,
                            color: '#F59E0B'
                        }}>
                            <Crown size={16} style={{ display: 'inline', marginRight: '4px' }} />
                            Current Plan
                        </div>
                    ) : (
                        <button
                            onClick={handleUpgrade}
                            disabled={upgrading}
                            style={{
                                width: '100%',
                                padding: '16px',
                                fontSize: '16px',
                                fontWeight: 700,
                                borderRadius: '8px',
                                border: 'none',
                                background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                                color: 'white',
                                cursor: upgrading ? 'not-allowed' : 'pointer',
                                transition: 'all 0.3s',
                                boxShadow: '0 4px 20px rgba(139, 92, 246, 0.4)'
                            }}
                        >
                            {upgrading ? '⏳ Upgrading...' : '🚀 Upgrade to Premium'}
                        </button>
                    )}
                </div>
            </div>

            {/* Usage Stats (if subscribed) */}
            {subscription?.usage && (
                <div className="glass-card" style={{ padding: '24px' }}>
                    <h3 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '20px' }}>
                        Current Usage
                    </h3>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                        gap: '20px'
                    }}>
                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '8px', textTransform: 'uppercase' }}>
                                Trading Pairs
                            </div>
                            <div style={{ fontSize: '24px', fontWeight: 700 }}>
                                {subscription.usage.trading_pairs?.used || 0} / {subscription.usage.trading_pairs?.limit || 1}
                            </div>
                            <div style={{
                                marginTop: '8px',
                                height: '4px',
                                background: 'rgba(255, 255, 255, 0.1)',
                                borderRadius: '2px',
                                overflow: 'hidden'
                            }}>
                                <div style={{
                                    height: '100%',
                                    width: `${((subscription.usage.trading_pairs?.used || 0) / (subscription.usage.trading_pairs?.limit || 1)) * 100}%`,
                                    background: 'linear-gradient(90deg, #4facfe 0%, #00f2fe 100%)',
                                    transition: 'width 0.3s'
                                }} />
                            </div>
                        </div>

                        <div>
                            <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '8px', textTransform: 'uppercase' }}>
                                Live Trading
                            </div>
                            <div style={{ fontSize: '24px', fontWeight: 700 }}>
                                {subscription.usage.live_trading?.allowed ? (
                                    <span style={{ color: '#10B981' }}>✅ Enabled</span>
                                ) : (
                                    <span style={{ color: '#F59E0B' }}>📝 Paper Only</span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* FAQ or Benefits Section */}
            <div style={{ marginTop: '48px', textAlign: 'center' }}>
                <h3 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '16px' }}>
                    Why Upgrade to Premium?
                </h3>
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
                    gap: '20px',
                    marginTop: '24px'
                }}>
                    <div className="glass-card" style={{ padding: '20px' }}>
                        <div style={{ fontSize: '32px', marginBottom: '12px' }}>💰</div>
                        <h4 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>Live Trading</h4>
                        <p style={{ color: '#94A3B8', fontSize: '14px' }}>
                            Trade with real money and earn real profits
                        </p>
                    </div>
                    <div className="glass-card" style={{ padding: '20px' }}>
                        <div style={{ fontSize: '32px', marginBottom: '12px' }}>📊</div>
                        <h4 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>10 Cryptocurrencies</h4>
                        <p style={{ color: '#94A3B8', fontSize: '14px' }}>
                            Diversify across multiple trading pairs
                        </p>
                    </div>
                    <div className="glass-card" style={{ padding: '20px' }}>
                        <div style={{ fontSize: '32px', marginBottom: '12px' }}>⚡</div>
                        <h4 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>Priority Support</h4>
                        <p style={{ color: '#94A3B8', fontSize: '14px' }}>
                            Get help when you need it most
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default SubscriptionView

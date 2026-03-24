import { useState, useEffect } from 'react'
import { Check, X, Zap, Star, Crown, Building2, ArrowRight } from 'lucide-react'
import { motion } from 'framer-motion'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface PricingTier {
    name: string
    display_name: string
    price: number
    price_yearly: number
    color: string
    features: string[]
    limitations: string[]
    live_trading: boolean
    ml_training: boolean
    api_access: boolean
}

const PricingView = () => {
    const [tiers, setTiers] = useState<Record<string, PricingTier>>({})
    const [billing, setBilling] = useState<'monthly' | 'yearly'>('monthly')
    const [currentTier, setCurrentTier] = useState('free')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchPricingData()
    }, [])

    const fetchPricingData = async () => {
        try {
            const response = await fetch(`${API_URL}/api/subscription/tiers`)
            if (response.ok) {
                const data = await response.json()
                setTiers(data.tiers)
                setCurrentTier(data.current_tier || 'free')
            }
        } catch (err) {
            console.error('Failed to fetch pricing:', err)
            // Fallback data
            setTiers({
                free: {
                    name: 'Free',
                    display_name: 'Starter',
                    price: 0,
                    price_yearly: 0,
                    color: '#64748B',
                    features: ['Paper Trading Only', '1 Trading Pair', 'Basic Dashboard'],
                    limitations: ['No Live Trading', 'No ML Features'],
                    live_trading: false,
                    ml_training: false,
                    api_access: false
                },
                basic: {
                    name: 'Basic',
                    display_name: 'Trader',
                    price: 29,
                    price_yearly: 290,
                    color: '#06B6D4',
                    features: ['Live Trading', '3 Trading Pairs', 'Telegram Alerts'],
                    limitations: ['No ML Training'],
                    live_trading: true,
                    ml_training: false,
                    api_access: false
                },
                pro: {
                    name: 'Pro',
                    display_name: 'Professional',
                    price: 99,
                    price_yearly: 990,
                    color: '#8B5CF6',
                    features: ['Unlimited Trades', '10 Pairs', 'ML Training', 'API Access'],
                    limitations: [],
                    live_trading: true,
                    ml_training: true,
                    api_access: true
                },
                enterprise: {
                    name: 'Enterprise',
                    display_name: 'Enterprise',
                    price: 299,
                    price_yearly: 2990,
                    color: '#F59E0B',
                    features: ['Everything Unlimited', 'White-Label', 'Dedicated Support'],
                    limitations: [],
                    live_trading: true,
                    ml_training: true,
                    api_access: true
                }
            })
        } finally {
            setLoading(false)
        }
    }

    const getTierIcon = (tierKey: string) => {
        switch (tierKey) {
            case 'free':
                return <Zap size={24} />
            case 'basic':
                return <Star size={24} />
            case 'pro':
                return <Crown size={24} />
            case 'enterprise':
                return <Building2 size={24} />
            default:
                return <Zap size={24} />
        }
    }

    const getPrice = (tier: PricingTier) => {
        if (billing === 'yearly') {
            return Math.round(tier.price_yearly / 12)
        }
        return tier.price
    }

    const handleSubscribe = async (tierKey: string) => {
        // In production: Redirect to Stripe Checkout
        console.log(`Subscribe to ${tierKey}`)
        alert(`Stripe Integration: Subscribing to ${tierKey} plan...`)
    }

    if (loading) {
        return (
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '400px'
            }}>
                <div className="spinner" />
            </div>
        )
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '32px' }}
        >
            {/* Header */}
            <div style={{ textAlign: 'center', marginBottom: '48px' }}>
                <h1 style={{
                    fontSize: '36px',
                    fontWeight: 700,
                    background: 'var(--gradient-primary)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    marginBottom: '16px'
                }}>
                    Choose Your Plan
                </h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '16px', maxWidth: '600px', margin: '0 auto' }}>
                    Start with our free plan and upgrade as you grow. All plans include our core trading engine.
                </p>

                {/* Billing Toggle */}
                <div style={{
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    gap: '12px',
                    marginTop: '32px'
                }}>
                    <span style={{
                        color: billing === 'monthly' ? 'var(--text-primary)' : 'var(--text-muted)',
                        fontWeight: billing === 'monthly' ? 600 : 400
                    }}>
                        Monthly
                    </span>
                    <button
                        onClick={() => setBilling(billing === 'monthly' ? 'yearly' : 'monthly')}
                        style={{
                            width: '56px',
                            height: '28px',
                            borderRadius: '14px',
                            background: billing === 'yearly' ? 'var(--primary-purple)' : 'var(--bg-tertiary)',
                            border: 'none',
                            cursor: 'pointer',
                            position: 'relative',
                            transition: 'all 0.3s ease'
                        }}
                    >
                        <div style={{
                            width: '22px',
                            height: '22px',
                            borderRadius: '50%',
                            background: 'white',
                            position: 'absolute',
                            top: '3px',
                            left: billing === 'yearly' ? '31px' : '3px',
                            transition: 'all 0.3s ease'
                        }} />
                    </button>
                    <span style={{
                        color: billing === 'yearly' ? 'var(--text-primary)' : 'var(--text-muted)',
                        fontWeight: billing === 'yearly' ? 600 : 400
                    }}>
                        Yearly
                    </span>
                    <span style={{
                        background: 'var(--success)',
                        color: 'white',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '12px',
                        fontWeight: 600
                    }}>
                        Save 17%
                    </span>
                </div>
            </div>

            {/* Pricing Cards */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '24px',
                maxWidth: '1200px',
                margin: '0 auto'
            }}>
                {Object.entries(tiers).map(([key, tier], index) => (
                    <motion.div
                        key={key}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className="glass-card"
                        style={{
                            padding: '32px',
                            position: 'relative',
                            borderColor: key === 'pro' ? 'var(--primary-purple)' : undefined,
                            transform: key === 'pro' ? 'scale(1.02)' : undefined
                        }}
                    >
                        {/* Popular Badge */}
                        {key === 'pro' && (
                            <div style={{
                                position: 'absolute',
                                top: '-12px',
                                left: '50%',
                                transform: 'translateX(-50%)',
                                background: 'var(--gradient-primary)',
                                color: 'white',
                                padding: '4px 16px',
                                borderRadius: '12px',
                                fontSize: '12px',
                                fontWeight: 600
                            }}>
                                Most Popular
                            </div>
                        )}

                        {/* Icon & Name */}
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '12px',
                            marginBottom: '16px'
                        }}>
                            <div style={{
                                width: '48px',
                                height: '48px',
                                borderRadius: '12px',
                                background: `${tier.color}20`,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: tier.color
                            }}>
                                {getTierIcon(key)}
                            </div>
                            <div>
                                <h3 style={{
                                    fontSize: '20px',
                                    fontWeight: 700,
                                    color: 'var(--text-primary)'
                                }}>
                                    {tier.display_name}
                                </h3>
                            </div>
                        </div>

                        {/* Price */}
                        <div style={{ marginBottom: '24px' }}>
                            <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                                <span style={{
                                    fontSize: '40px',
                                    fontWeight: 700,
                                    color: 'var(--text-primary)'
                                }}>
                                    ${getPrice(tier)}
                                </span>
                                {tier.price > 0 && (
                                    <span style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                                        /month
                                    </span>
                                )}
                            </div>
                            {tier.price > 0 && billing === 'yearly' && (
                                <p style={{
                                    color: 'var(--success)',
                                    fontSize: '13px',
                                    marginTop: '4px'
                                }}>
                                    ${tier.price_yearly} billed annually
                                </p>
                            )}
                        </div>

                        {/* Features */}
                        <ul style={{
                            listStyle: 'none',
                            padding: 0,
                            marginBottom: '24px',
                            minHeight: '200px'
                        }}>
                            {tier.features.map((feature, i) => (
                                <li key={i} style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '10px',
                                    color: 'var(--text-secondary)',
                                    fontSize: '14px',
                                    marginBottom: '12px'
                                }}>
                                    <Check size={18} color="var(--success)" />
                                    {feature}
                                </li>
                            ))}
                            {tier.limitations.map((limitation, i) => (
                                <li key={`lim-${i}`} style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '10px',
                                    color: 'var(--text-muted)',
                                    fontSize: '14px',
                                    marginBottom: '12px'
                                }}>
                                    <X size={18} color="var(--error)" />
                                    {limitation}
                                </li>
                            ))}
                        </ul>

                        {/* CTA Button */}
                        <button
                            onClick={() => handleSubscribe(key)}
                            disabled={currentTier === key}
                            style={{
                                width: '100%',
                                padding: '14px',
                                borderRadius: '10px',
                                cursor: currentTier === key ? 'default' : 'pointer',
                                fontWeight: 600,
                                fontSize: '14px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '8px',
                                background: currentTier === key
                                    ? 'var(--bg-tertiary)'
                                    : key === 'pro'
                                        ? 'var(--gradient-primary)'
                                        : 'transparent',
                                color: currentTier === key
                                    ? 'var(--text-muted)'
                                    : 'white',
                                border: key === 'pro' || currentTier === key
                                    ? 'none'
                                    : `1px solid ${tier.color}`,
                                transition: 'all 0.2s ease'
                            }}
                        >
                            {currentTier === key ? (
                                'Current Plan'
                            ) : (
                                <>
                                    {tier.price === 0 ? 'Get Started' : 'Upgrade Now'}
                                    <ArrowRight size={16} />
                                </>
                            )}
                        </button>
                    </motion.div>
                ))}
            </div>

            {/* FAQ or Help */}
            <div style={{
                textAlign: 'center',
                marginTop: '48px',
                color: 'var(--text-muted)',
                fontSize: '14px'
            }}>
                Need help choosing? <a href="mailto:support@ethbot.com" style={{ color: 'var(--primary-purple)' }}>Contact us</a>
            </div>
        </motion.div>
    )
}

export default PricingView

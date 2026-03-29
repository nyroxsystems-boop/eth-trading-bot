import { useState } from 'react'
import {
    Key, Settings, TrendingUp, Play, ChevronRight, ChevronLeft,
    Check, AlertTriangle, Wallet
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface OnboardingStep {
    id: string
    title: string
    description: string
    icon: React.ElementType
}

const STEPS: OnboardingStep[] = [
    {
        id: 'welcome',
        title: 'Welcome to ETH Trading Bot',
        description: 'Let\'s get you set up for automated trading in just a few steps.',
        icon: TrendingUp
    },
    {
        id: 'api_keys',
        title: 'Connect Your Binance Account',
        description: 'Enter your API keys to connect your Binance account.',
        icon: Key
    },
    {
        id: 'trading_pair',
        title: 'Choose Your Trading Pair',
        description: 'Select which cryptocurrency pair you want to trade.',
        icon: Wallet
    },
    {
        id: 'risk_settings',
        title: 'Set Your Risk Level',
        description: 'Configure how much risk you\'re comfortable with.',
        icon: Settings
    },
    {
        id: 'complete',
        title: 'You\'re All Set!',
        description: 'Your bot is ready. Start with paper trading to test.',
        icon: Check
    }
]

const TRADING_PAIRS = [
    { id: 'ETHUSDT', name: 'ETH/USDT', description: 'Ethereum - Most popular' },
    { id: 'BTCUSDT', name: 'BTC/USDT', description: 'Bitcoin - Highest volume' },
    { id: 'SOLUSDT', name: 'SOL/USDT', description: 'Solana - High volatility' }
]

const RISK_LEVELS = [
    { id: 'low', name: 'Conservative', risk: 0.005, description: '0.5% per trade, lower returns' },
    { id: 'medium', name: 'Balanced', risk: 0.01, description: '1% per trade, balanced approach' },
    { id: 'high', name: 'Aggressive', risk: 0.02, description: '2% per trade, higher risk/reward' }
]

interface OnboardingWizardProps {
    onComplete: () => void
    onSkip?: () => void
}

const OnboardingWizard = ({ onComplete, onSkip }: OnboardingWizardProps) => {
    const [currentStep, setCurrentStep] = useState(0)
    const [formData, setFormData] = useState({
        binanceApiKey: '',
        binanceApiSecret: '',
        tradingPair: 'ETHUSDT',
        riskLevel: 'medium',
        paperTrading: true
    })
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const step = STEPS[currentStep]
    const isFirstStep = currentStep === 0
    const isLastStep = currentStep === STEPS.length - 1

    const handleNext = async () => {
        setError('')

        // Validate current step
        if (step.id === 'api_keys' && !formData.paperTrading) {
            if (!formData.binanceApiKey || !formData.binanceApiSecret) {
                setError('Please enter your API keys or enable paper trading')
                return
            }
        }

        // Save settings on second-to-last step
        if (currentStep === STEPS.length - 2) {
            setLoading(true)
            try {
                const token = localStorage.getItem('token')

                // Save trading settings
                await fetch(`${API_URL}/api/settings/trading`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        capital: 100000,
                        risk_per_trade: RISK_LEVELS.find(r => r.id === formData.riskLevel)?.risk || 0.01,
                        max_trades_per_day: 15,
                        daily_target_pct: 1.0,
                        max_drawdown_day: 0.05,
                        tp_min: 0.01,
                        tp_max: 0.015,
                        stop_floor: 0.005
                    })
                })

                // Save API keys if provided
                if (!formData.paperTrading && formData.binanceApiKey) {
                    await fetch(`${API_URL}/api/user/api-keys`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`
                        },
                        body: JSON.stringify({
                            binance_api_key: formData.binanceApiKey,
                            binance_api_secret: formData.binanceApiSecret
                        })
                    })
                }
            } catch (err) {
                console.error('Failed to save settings:', err)
            } finally {
                setLoading(false)
            }
        }

        if (isLastStep) {
            localStorage.setItem('onboarding_complete', 'true')
            onComplete()
        } else {
            setCurrentStep(prev => prev + 1)
        }
    }

    const handleBack = () => {
        if (!isFirstStep) {
            setCurrentStep(prev => prev - 1)
        }
    }

    const renderStepContent = () => {
        switch (step.id) {
            case 'welcome':
                return (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <div style={{
                            width: '120px',
                            height: '120px',
                            borderRadius: '50%',
                            background: 'var(--gradient-primary)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '0 auto 24px',
                            boxShadow: '0 0 40px rgba(139, 92, 246, 0.3)'
                        }}>
                            <TrendingUp size={48} color="white" />
                        </div>
                        <h2 style={{ fontSize: '24px', marginBottom: '16px', color: 'var(--text-primary)' }}>
                            AI-Powered Trading
                        </h2>
                        <p style={{ color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                            Our machine learning algorithms analyze market patterns 24/7 to find the best trading opportunities for you.
                        </p>
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(3, 1fr)',
                            gap: '16px',
                            marginTop: '32px'
                        }}>
                            {['ML Powered', 'Risk Management', '24/7 Trading'].map((feature, i) => (
                                <div key={i} style={{
                                    padding: '16px',
                                    background: 'var(--glass-bg)',
                                    borderRadius: '12px',
                                    border: '1px solid var(--glass-border)'
                                }}>
                                    <Check size={20} color="var(--success)" style={{ marginBottom: '8px' }} />
                                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                                        {feature}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )

            case 'api_keys':
                return (
                    <div style={{ padding: '20px 0' }}>
                        {/* Paper Trading Toggle */}
                        <div style={{
                            padding: '16px',
                            background: formData.paperTrading ? 'rgba(16, 185, 129, 0.1)' : 'var(--glass-bg)',
                            border: `1px solid ${formData.paperTrading ? 'var(--success)' : 'var(--glass-border)'}`,
                            borderRadius: '12px',
                            marginBottom: '24px',
                            cursor: 'pointer'
                        }} onClick={() => setFormData(prev => ({ ...prev, paperTrading: !prev.paperTrading }))}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div>
                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                        Start with Paper Trading
                                    </div>
                                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                        Practice with virtual money - no risk
                                    </div>
                                </div>
                                <div style={{
                                    width: '24px',
                                    height: '24px',
                                    borderRadius: '50%',
                                    background: formData.paperTrading ? 'var(--success)' : 'var(--bg-tertiary)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}>
                                    {formData.paperTrading && <Check size={16} color="white" />}
                                </div>
                            </div>
                        </div>

                        {/* API Key Inputs */}
                        {!formData.paperTrading && (
                            <>
                                <div style={{ marginBottom: '16px' }}>
                                    <label style={{ display: 'block', color: 'var(--text-secondary)', marginBottom: '8px', fontSize: '14px' }}>
                                        Binance API Key
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.binanceApiKey}
                                        onChange={e => setFormData(prev => ({ ...prev, binanceApiKey: e.target.value }))}
                                        placeholder="Enter your API key"
                                        style={{
                                            width: '100%',
                                            padding: '12px',
                                            background: 'var(--input-bg)',
                                            border: '1px solid var(--input-border)',
                                            borderRadius: '8px',
                                            color: 'var(--text-primary)',
                                            fontSize: '14px'
                                        }}
                                    />
                                </div>
                                <div style={{ marginBottom: '16px' }}>
                                    <label style={{ display: 'block', color: 'var(--text-secondary)', marginBottom: '8px', fontSize: '14px' }}>
                                        Binance API Secret
                                    </label>
                                    <input
                                        type="password"
                                        value={formData.binanceApiSecret}
                                        onChange={e => setFormData(prev => ({ ...prev, binanceApiSecret: e.target.value }))}
                                        placeholder="Enter your API secret"
                                        style={{
                                            width: '100%',
                                            padding: '12px',
                                            background: 'var(--input-bg)',
                                            border: '1px solid var(--input-border)',
                                            borderRadius: '8px',
                                            color: 'var(--text-primary)',
                                            fontSize: '14px'
                                        }}
                                    />
                                </div>
                                <div style={{
                                    padding: '12px',
                                    background: 'rgba(245, 158, 11, 0.1)',
                                    border: '1px solid rgba(245, 158, 11, 0.3)',
                                    borderRadius: '8px',
                                    display: 'flex',
                                    alignItems: 'flex-start',
                                    gap: '10px'
                                }}>
                                    <AlertTriangle size={18} color="var(--warning)" style={{ flexShrink: 0, marginTop: '2px' }} />
                                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                                        Your keys are encrypted and stored securely. Enable only Spot trading permissions on Binance.
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                )

            case 'trading_pair':
                return (
                    <div style={{ padding: '20px 0' }}>
                        {TRADING_PAIRS.map(pair => (
                            <div
                                key={pair.id}
                                onClick={() => setFormData(prev => ({ ...prev, tradingPair: pair.id }))}
                                style={{
                                    padding: '16px',
                                    background: formData.tradingPair === pair.id ? 'rgba(139, 92, 246, 0.1)' : 'var(--glass-bg)',
                                    border: `1px solid ${formData.tradingPair === pair.id ? 'var(--primary-purple)' : 'var(--glass-border)'}`,
                                    borderRadius: '12px',
                                    marginBottom: '12px',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center'
                                }}
                            >
                                <div>
                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                        {pair.name}
                                    </div>
                                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                        {pair.description}
                                    </div>
                                </div>
                                {formData.tradingPair === pair.id && (
                                    <Check size={20} color="var(--primary-purple)" />
                                )}
                            </div>
                        ))}
                    </div>
                )

            case 'risk_settings':
                return (
                    <div style={{ padding: '20px 0' }}>
                        {RISK_LEVELS.map(level => (
                            <div
                                key={level.id}
                                onClick={() => setFormData(prev => ({ ...prev, riskLevel: level.id }))}
                                style={{
                                    padding: '16px',
                                    background: formData.riskLevel === level.id ? 'rgba(139, 92, 246, 0.1)' : 'var(--glass-bg)',
                                    border: `1px solid ${formData.riskLevel === level.id ? 'var(--primary-purple)' : 'var(--glass-border)'}`,
                                    borderRadius: '12px',
                                    marginBottom: '12px',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center'
                                }}
                            >
                                <div>
                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                        {level.name}
                                    </div>
                                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                        {level.description}
                                    </div>
                                </div>
                                {formData.riskLevel === level.id && (
                                    <Check size={20} color="var(--primary-purple)" />
                                )}
                            </div>
                        ))}
                    </div>
                )

            case 'complete':
                return (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <div style={{
                            width: '100px',
                            height: '100px',
                            borderRadius: '50%',
                            background: 'var(--success)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '0 auto 24px',
                            boxShadow: '0 0 40px rgba(16, 185, 129, 0.3)'
                        }}>
                            <Check size={48} color="white" />
                        </div>
                        <h2 style={{ fontSize: '24px', marginBottom: '16px', color: 'var(--text-primary)' }}>
                            Setup Complete!
                        </h2>
                        <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
                            Your bot is configured and ready to start trading.
                        </p>
                        <div style={{
                            padding: '16px',
                            background: 'var(--glass-bg)',
                            borderRadius: '12px',
                            textAlign: 'left'
                        }}>
                            <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                Your Settings:
                            </div>
                            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                • Trading Pair: <strong style={{ color: 'var(--text-primary)' }}>{formData.tradingPair}</strong><br />
                                • Risk Level: <strong style={{ color: 'var(--text-primary)' }}>{RISK_LEVELS.find(r => r.id === formData.riskLevel)?.name}</strong><br />
                                • Mode: <strong style={{ color: 'var(--text-primary)' }}>{formData.paperTrading ? 'Paper Trading' : 'Live Trading'}</strong>
                            </div>
                        </div>
                    </div>
                )

            default:
                return null
        }
    }

    return (
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
            padding: '24px'
        }}>
            <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="glass-card"
                style={{
                    maxWidth: '500px',
                    width: '100%',
                    padding: '32px'
                }}
            >
                {/* Progress Dots */}
                <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginBottom: '32px' }}>
                    {STEPS.map((_, i) => (
                        <div
                            key={i}
                            style={{
                                width: i === currentStep ? '24px' : '8px',
                                height: '8px',
                                borderRadius: '4px',
                                background: i <= currentStep ? 'var(--primary-purple)' : 'var(--bg-tertiary)',
                                transition: 'all 0.3s ease'
                            }}
                        />
                    ))}
                </div>

                {/* Step Title */}
                <h1 style={{
                    fontSize: '22px',
                    fontWeight: 700,
                    color: 'var(--text-primary)',
                    textAlign: 'center',
                    marginBottom: '8px'
                }}>
                    {step.title}
                </h1>
                <p style={{
                    color: 'var(--text-muted)',
                    textAlign: 'center',
                    fontSize: '14px',
                    marginBottom: '24px'
                }}>
                    {step.description}
                </p>

                {/* Error Message */}
                {error && (
                    <div style={{
                        padding: '12px',
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: '8px',
                        marginBottom: '16px',
                        color: 'var(--error)',
                        fontSize: '14px'
                    }}>
                        {error}
                    </div>
                )}

                {/* Step Content */}
                <AnimatePresence mode="wait">
                    <motion.div
                        key={step.id}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                    >
                        {renderStepContent()}
                    </motion.div>
                </AnimatePresence>

                {/* Navigation Buttons */}
                <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
                    {!isFirstStep && (
                        <button
                            onClick={handleBack}
                            style={{
                                flex: 1,
                                padding: '14px',
                                borderRadius: '10px',
                                border: '1px solid var(--glass-border)',
                                background: 'transparent',
                                color: 'var(--text-primary)',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '8px'
                            }}
                        >
                            <ChevronLeft size={18} />
                            Back
                        </button>
                    )}
                    <button
                        onClick={handleNext}
                        disabled={loading}
                        style={{
                            flex: 2,
                            padding: '14px',
                            borderRadius: '10px',
                            border: 'none',
                            background: isLastStep ? 'var(--success)' : 'var(--gradient-primary)',
                            color: 'white',
                            fontWeight: 600,
                            cursor: loading ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px'
                        }}
                    >
                        {loading ? 'Saving...' : isLastStep ? 'Start Trading' : 'Continue'}
                        {!isLastStep && <ChevronRight size={18} />}
                        {isLastStep && <Play size={18} />}
                    </button>
                </div>

                {/* Skip Link */}
                {isFirstStep && onSkip && (
                    <div style={{ textAlign: 'center', marginTop: '16px' }}>
                        <button
                            onClick={onSkip}
                            style={{
                                background: 'none',
                                border: 'none',
                                color: 'var(--text-muted)',
                                cursor: 'pointer',
                                fontSize: '13px'
                            }}
                        >
                            Skip onboarding
                        </button>
                    </div>
                )}
            </motion.div>
        </div>
    )
}

export default OnboardingWizard

import { useState, useEffect } from 'react'
import { Bot, DollarSign, MessageSquare, Brain, AlertTriangle, Key } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import '../styles/premium.css'
import '../styles/components.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SettingsView = () => {
    const { token } = useAuth()
    const [mode, setMode] = useState('paper')
    const [capital, setCapital] = useState(10000)
    const [telegramToken, setTelegramToken] = useState('')
    const [telegramChatId, setTelegramChatId] = useState('')
    const [binanceApiKey, setBinanceApiKey] = useState('')
    const [binanceApiSecret, setBinanceApiSecret] = useState('')
    const [hasBinanceKeys, setHasBinanceKeys] = useState(false)
    const [switching, setSwitching] = useState(false)

    useEffect(() => {
        fetchSettings()
        fetchApiKeys()
    }, [])

    const fetchSettings = async () => {
        try {
            const [modeRes, settingsRes] = await Promise.all([
                fetch(`${API_URL}/api/trading/mode`),
                fetch(`${API_URL}/api/settings/bot`)
            ])

            const modeData = await modeRes.json()
            const settingsData = await settingsRes.json()

            setMode(modeData.mode)
            setCapital(settingsData.trading_capital || 10000)
            setTelegramToken(settingsData.telegram_bot_token || '')
            setTelegramChatId(settingsData.telegram_chat_id || '')
        } catch (err) {
            console.error('Failed to fetch settings:', err)
        }
    }

    const fetchApiKeys = async () => {
        if (!token) return
        try {
            const res = await fetch(`${API_URL}/api/settings/api-keys`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setHasBinanceKeys(data.has_binance_keys || false)
                // Keys are masked, only show placeholder if they exist
                if (data.has_binance_keys) {
                    setBinanceApiKey(data.binance_api_key || '')
                    setBinanceApiSecret(data.binance_api_secret || '')
                }
            }
        } catch (err) {
            console.error('Failed to fetch API keys:', err)
        }
    }

    const saveBinanceKeys = async () => {
        if (!token) return
        try {
            const res = await fetch(`${API_URL}/api/settings/api-keys`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    binance_api_key: binanceApiKey,
                    binance_api_secret: binanceApiSecret
                })
            })

            if (res.ok) {
                alert('✅ Binance API Keys saved!')
                setHasBinanceKeys(true)
                fetchApiKeys() // Refresh to get masked version
            } else {
                const err = await res.json()
                alert(`❌ Failed: ${err.detail || 'Unknown error'}`)
            }
        } catch (err) {
            console.error('Failed to save API keys:', err)
            alert('❌ Error saving API keys')
        }
    }

    const switchMode = async () => {
        const newMode = mode === 'paper' ? 'live' : 'paper'

        // Confirmation for live trading
        if (newMode === 'live') {
            const confirmed = window.confirm(
                '⚠️ SWITCH TO LIVE TRADING?\n\n' +
                'Real money will be used!\n' +
                'Make sure you are ready!\n\n' +
                'Click OK to continue.'
            )
            if (!confirmed) return
        }

        setSwitching(true)
        try {
            const res = await fetch(`${API_URL}/api/trading/mode`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode })
            })

            if (res.ok) {
                setMode(newMode)
                alert(`✅ Switched to ${newMode.toUpperCase()} trading!`)
            } else {
                alert('❌ Failed to switch mode')
            }
        } catch (err) {
            console.error('Failed to switch mode:', err)
            alert('❌ Error switching mode')
        } finally {
            setSwitching(false)
        }
    }

    const saveCapital = async () => {
        try {
            const res = await fetch(`${API_URL}/api/capital`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ capital })
            })

            if (res.ok) {
                alert('✅ Capital updated!')
            } else {
                alert('❌ Failed to update capital')
            }
        } catch (err) {
            console.error('Failed to save capital:', err)
            alert('❌ Error saving capital')
        }
    }

    const saveTelegram = async () => {
        try {
            const res = await fetch(`${API_URL}/api/settings/telegram`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bot_token: telegramToken,
                    chat_id: telegramChatId
                })
            })

            if (res.ok) {
                alert('✅ Telegram settings updated!')
            } else {
                alert('❌ Failed to update Telegram settings')
            }
        } catch (err) {
            console.error('Failed to save Telegram:', err)
            alert('❌ Error saving Telegram settings')
        }
    }

    return (
        <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
            {/* Header */}
            <div style={{ marginBottom: '32px' }}>
                <h1 style={{ fontSize: '32px', fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: '8px' }}>
                    ⚙️ Bot Configuration
                </h1>
                <p style={{ color: '#94A3B8', fontSize: '16px' }}>Manage your trading bot settings</p>
            </div>

            {/* Bot Status & Mode Toggle */}
            <div className="glass-card" style={{ padding: '32px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                    <Bot size={32} />
                    <div>
                        <h3 style={{ fontSize: '20px', fontWeight: 600 }}>ETH Trading Bot</h3>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10B981' }} />
                            <span style={{ fontSize: '14px', color: '#10B981' }}>Running</span>
                            <span style={{ fontSize: '14px', color: '#64748B' }}>•</span>
                            <span style={{ fontSize: '14px', color: mode === 'paper' ? '#F59E0B' : '#EF4444' }}>
                                {mode === 'paper' ? '📝 Paper Trading' : '🚀 Live Trading'}
                            </span>
                        </div>
                    </div>
                </div>

                {/* BIG MODE TOGGLE BUTTON */}
                <button
                    onClick={switchMode}
                    disabled={switching}
                    style={{
                        width: '100%',
                        padding: '20px',
                        fontSize: '18px',
                        fontWeight: 700,
                        borderRadius: '12px',
                        border: 'none',
                        background: mode === 'paper'
                            ? 'linear-gradient(135deg, #10B981 0%, #059669 100%)'
                            : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                        color: 'white',
                        cursor: switching ? 'not-allowed' : 'pointer',
                        transition: 'all 0.3s',
                        boxShadow: '0 4px 20px rgba(139, 92, 246, 0.3)'
                    }}
                >
                    {switching ? (
                        '⏳ Switching...'
                    ) : mode === 'paper' ? (
                        '🚀 SWITCH TO LIVE TRADING'
                    ) : (
                        '📝 SWITCH TO PAPER TRADING'
                    )}
                </button>

                {mode === 'paper' && (
                    <div style={{ marginTop: '16px', padding: '12px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', display: 'flex', alignItems: 'start', gap: '8px' }}>
                        <AlertTriangle size={20} color="#F59E0B" style={{ flexShrink: 0, marginTop: '2px' }} />
                        <div style={{ fontSize: '13px', color: '#F59E0B' }}>
                            <strong>Paper Trading Mode:</strong> No real money is being used. Switch to Live Trading when you're ready to trade with real funds.
                        </div>
                    </div>
                )}

                {mode === 'live' && (
                    <div style={{ marginTop: '16px', padding: '12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', display: 'flex', alignItems: 'start', gap: '8px' }}>
                        <AlertTriangle size={20} color="#EF4444" style={{ flexShrink: 0, marginTop: '2px' }} />
                        <div style={{ fontSize: '13px', color: '#EF4444' }}>
                            <strong>Live Trading Active:</strong> Real money is being used! Monitor your bot carefully.
                        </div>
                    </div>
                )}
            </div>

            {/* Trading Capital */}
            <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <DollarSign size={20} />
                    Trading Capital
                </h3>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'end' }}>
                    <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>
                            Capital (USDT)
                        </label>
                        <input
                            type="number"
                            value={capital}
                            onChange={(e) => setCapital(parseFloat(e.target.value))}
                            style={{ width: '100%', padding: '12px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '8px', color: 'white', fontSize: '16px' }}
                        />
                    </div>
                    <button
                        onClick={saveCapital}
                        className="btn-primary"
                        style={{ padding: '12px 24px' }}
                    >
                        Save
                    </button>
                </div>
            </div>

            {/* Binance API Keys */}
            <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Key size={20} />
                    Binance API Keys
                    {hasBinanceKeys && (
                        <span style={{ marginLeft: 'auto', fontSize: '12px', padding: '4px 8px', background: 'rgba(16, 185, 129, 0.2)', color: '#10B981', borderRadius: '4px' }}>
                            ✓ Configured
                        </span>
                    )}
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>
                            API Key
                        </label>
                        <input
                            type="text"
                            value={binanceApiKey}
                            onChange={(e) => setBinanceApiKey(e.target.value)}
                            placeholder={hasBinanceKeys ? '••••••••••••••••' : 'Enter your Binance API Key'}
                            style={{ width: '100%', padding: '12px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '8px', color: 'white', fontSize: '14px' }}
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>
                            API Secret
                        </label>
                        <input
                            type="password"
                            value={binanceApiSecret}
                            onChange={(e) => setBinanceApiSecret(e.target.value)}
                            placeholder={hasBinanceKeys ? '••••••••••••••••' : 'Enter your Binance API Secret'}
                            style={{ width: '100%', padding: '12px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '8px', color: 'white', fontSize: '14px' }}
                        />
                    </div>
                    <button
                        onClick={saveBinanceKeys}
                        className="btn-primary"
                        style={{ alignSelf: 'flex-start' }}
                    >
                        {hasBinanceKeys ? 'Update Binance Keys' : 'Save Binance Keys'}
                    </button>
                    <div style={{ padding: '12px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', fontSize: '13px', color: '#F59E0B' }}>
                        ⚠️ Your API keys are encrypted and stored securely. Never share your API secret with anyone!
                    </div>
                </div>
            </div>

            {/* Telegram Settings */}
            <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <MessageSquare size={20} />
                    Telegram Notifications
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>
                            Bot Token
                        </label>
                        <input
                            type="text"
                            value={telegramToken}
                            onChange={(e) => setTelegramToken(e.target.value)}
                            placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
                            style={{ width: '100%', padding: '12px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '8px', color: 'white', fontSize: '14px' }}
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>
                            Chat ID
                        </label>
                        <input
                            type="text"
                            value={telegramChatId}
                            onChange={(e) => setTelegramChatId(e.target.value)}
                            placeholder="123456789"
                            style={{ width: '100%', padding: '12px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '8px', color: 'white', fontSize: '14px' }}
                        />
                    </div>
                    <button
                        onClick={saveTelegram}
                        className="btn-primary"
                        style={{ alignSelf: 'flex-start' }}
                    >
                        Save Telegram Settings
                    </button>
                </div>
            </div>

            {/* Auto-Learning Status (Read-only) */}
            <div className="glass-card" style={{ padding: '24px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Brain size={20} />
                    Auto-Learning System
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                    <div>
                        <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Status</div>
                        <div style={{ fontSize: '16px', fontWeight: 600, color: '#10B981' }}>✅ Enabled</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Testing Rate</div>
                        <div style={{ fontSize: '16px', fontWeight: 600 }}>10 strategies/hour</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '12px', color: '#64748B', marginBottom: '4px' }}>Auto-Apply</div>
                        <div style={{ fontSize: '16px', fontWeight: 600, color: '#10B981' }}>ON</div>
                    </div>
                </div>
                <div style={{ marginTop: '16px', padding: '12px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '8px', fontSize: '13px', color: '#94A3B8' }}>
                    💡 The bot automatically tests and applies better strategies. No manual tuning needed! Check the "Learning" page to monitor progress.
                </div>
            </div>
        </div>
    )
}

export default SettingsView

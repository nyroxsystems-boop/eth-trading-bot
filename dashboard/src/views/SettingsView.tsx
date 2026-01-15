import { useState, useEffect } from 'react'
import { Save, Loader, CheckCircle, AlertCircle } from 'lucide-react'
import '../styles/premium.css'
import '../styles/components.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Settings {
    telegram_bot_token: string
    telegram_chat_id: string
    trading_capital: number
    risk_per_trade: number
    max_trades_per_day: number
    daily_target_pct: number
    max_drawdown_day: number
    tp_min: number
    tp_max: number
    stop_floor: number
}

const SettingsView = () => {
    const [settings, setSettings] = useState<Settings>({
        telegram_bot_token: '',
        telegram_chat_id: '',
        trading_capital: 10000,
        risk_per_trade: 0.006,
        max_trades_per_day: 15,
        daily_target_pct: 1.0,
        max_drawdown_day: 0.05,
        tp_min: 0.010,
        tp_max: 0.015,
        stop_floor: 0.005
    })

    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle')

    useEffect(() => {
        loadSettings()
    }, [])

    const loadSettings = async () => {
        try {
            const [telegramRes, tradingRes] = await Promise.all([
                fetch(`${API_URL}/api/settings/telegram`),
                fetch(`${API_URL}/api/settings/trading`)
            ])

            const telegram = await telegramRes.json()
            const trading = await tradingRes.json()

            setSettings({
                telegram_bot_token: telegram.bot_token || '',
                telegram_chat_id: telegram.chat_id || '',
                trading_capital: trading.capital || 10000,
                risk_per_trade: trading.risk_per_trade || 0.006,
                max_trades_per_day: trading.max_trades_per_day || 15,
                daily_target_pct: trading.daily_target_pct || 1.0,
                max_drawdown_day: trading.max_drawdown_day || 0.05,
                tp_min: trading.tp_min || 0.010,
                tp_max: trading.tp_max || 0.015,
                stop_floor: trading.stop_floor || 0.005
            })
            setLoading(false)
        } catch (err) {
            console.error('Failed to load settings:', err)
            setLoading(false)
        }
    }

    const saveTelegramSettings = async () => {
        setSaving(true)
        try {
            const res = await fetch(`${API_URL}/api/settings/telegram`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bot_token: settings.telegram_bot_token,
                    chat_id: settings.telegram_chat_id
                })
            })

            if (res.ok) {
                setSaveStatus('success')
                setTimeout(() => setSaveStatus('idle'), 3000)
            } else {
                setSaveStatus('error')
            }
        } catch (err) {
            setSaveStatus('error')
        }
        setSaving(false)
    }

    const saveTradingSettings = async () => {
        setSaving(true)
        try {
            const res = await fetch(`${API_URL}/api/settings/trading`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    capital: settings.trading_capital,
                    risk_per_trade: settings.risk_per_trade,
                    max_trades_per_day: settings.max_trades_per_day,
                    daily_target_pct: settings.daily_target_pct,
                    max_drawdown_day: settings.max_drawdown_day,
                    tp_min: settings.tp_min,
                    tp_max: settings.tp_max,
                    stop_floor: settings.stop_floor
                })
            })

            if (res.ok) {
                setSaveStatus('success')
                setTimeout(() => setSaveStatus('idle'), 3000)
            } else {
                setSaveStatus('error')
            }
        } catch (err) {
            setSaveStatus('error')
        }
        setSaving(false)
    }

    if (loading) {
        return (
            <div className="settings-loading">
                <div className="spinner" />
                <p>Loading settings...</p>
            </div>
        )
    }

    return (
        <div className="settings-container">
            <div className="settings-header">
                <h1>Bot Configuration</h1>
                <p>Manage your trading bot and preferences</p>
            </div>

            <div className="settings-grid">
                {/* Telegram Notifications */}
                <div className="glass-card settings-card">
                    <div className="card-header">
                        <div className="card-icon" style={{ background: 'var(--gradient-primary)' }}>
                            🔔
                        </div>
                        <div>
                            <h3>Telegram Notifications</h3>
                            <p>Receive trade alerts and updates</p>
                        </div>
                    </div>

                    <div className="card-content">
                        <div className="form-group">
                            <label>Bot Token</label>
                            <input
                                type="text"
                                className="form-input"
                                value={settings.telegram_bot_token}
                                onChange={(e) => setSettings({ ...settings, telegram_bot_token: e.target.value })}
                                placeholder="Enter Telegram bot token"
                            />
                        </div>

                        <div className="form-group">
                            <label>Chat ID</label>
                            <input
                                type="text"
                                className="form-input"
                                value={settings.telegram_chat_id}
                                onChange={(e) => setSettings({ ...settings, telegram_chat_id: e.target.value })}
                                placeholder="Enter chat ID"
                            />
                        </div>

                        <button className="btn-primary" onClick={saveTelegramSettings} disabled={saving}>
                            {saving ? <Loader className="spin" size={16} /> : <Save size={16} />}
                            <span>Save Telegram Settings</span>
                        </button>
                    </div>
                </div>

                {/* Trading Capital */}
                <div className="glass-card settings-card">
                    <div className="card-header">
                        <div className="card-icon" style={{ background: 'var(--gradient-gold)' }}>
                            💰
                        </div>
                        <div>
                            <h3>Trading Capital</h3>
                            <p>Set your trading capital amount</p>
                        </div>
                    </div>

                    <div className="card-content">
                        <div className="capital-display">
                            <span className="capital-amount">${settings.trading_capital.toLocaleString()}</span>
                            <span className="capital-label">USDT</span>
                        </div>

                        <div className="form-group">
                            <label>Capital Amount</label>
                            <input
                                type="range"
                                min="1000"
                                max="50000"
                                step="1000"
                                value={settings.trading_capital}
                                onChange={(e) => setSettings({ ...settings, trading_capital: Number(e.target.value) })}
                                className="slider"
                            />
                            <div className="slider-labels">
                                <span>$1k</span>
                                <span>$50k</span>
                            </div>
                        </div>

                        <button className="btn-primary" onClick={saveTradingSettings} disabled={saving}>
                            {saving ? <Loader className="spin" size={16} /> : <Save size={16} />}
                            <span>Update Capital</span>
                        </button>
                    </div>
                </div>

                {/* Risk Management */}
                <div className="glass-card settings-card">
                    <div className="card-header">
                        <div className="card-icon" style={{ background: 'var(--gradient-secondary)' }}>
                            ⚙️
                        </div>
                        <div>
                            <h3>Risk Management</h3>
                            <p>Configure risk parameters</p>
                        </div>
                    </div>

                    <div className="card-content">
                        <div className="form-group">
                            <label>Risk per Trade: {(settings.risk_per_trade * 100).toFixed(2)}%</label>
                            <input
                                type="range"
                                min="0.003"
                                max="0.02"
                                step="0.001"
                                value={settings.risk_per_trade}
                                onChange={(e) => setSettings({ ...settings, risk_per_trade: Number(e.target.value) })}
                                className="slider"
                            />
                            <div className="slider-labels">
                                <span>0.3%</span>
                                <span>2.0%</span>
                            </div>
                        </div>

                        <div className="form-group">
                            <label>Max Trades per Day: {settings.max_trades_per_day}</label>
                            <input
                                type="range"
                                min="5"
                                max="30"
                                step="1"
                                value={settings.max_trades_per_day}
                                onChange={(e) => setSettings({ ...settings, max_trades_per_day: Number(e.target.value) })}
                                className="slider"
                            />
                            <div className="slider-labels">
                                <span>5</span>
                                <span>30</span>
                            </div>
                        </div>

                        <div className="form-group">
                            <label>Daily Target: {(settings.daily_target_pct).toFixed(1)}%</label>
                            <input
                                type="range"
                                min="0.5"
                                max="3.0"
                                step="0.1"
                                value={settings.daily_target_pct}
                                onChange={(e) => setSettings({ ...settings, daily_target_pct: Number(e.target.value) })}
                                className="slider"
                            />
                            <div className="slider-labels">
                                <span>0.5%</span>
                                <span>3.0%</span>
                            </div>
                        </div>

                        <button className="btn-primary" onClick={saveTradingSettings} disabled={saving}>
                            {saving ? <Loader className="spin" size={16} /> : <Save size={16} />}
                            <span>Save Risk Settings</span>
                        </button>
                    </div>
                </div>

                {/* Trading Parameters */}
                <div className="glass-card settings-card">
                    <div className="card-header">
                        <div className="card-icon" style={{ background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)' }}>
                            📊
                        </div>
                        <div>
                            <h3>Trading Parameters</h3>
                            <p>Fine-tune entry and exit points</p>
                        </div>
                    </div>

                    <div className="card-content">
                        <div className="form-group">
                            <label>Take Profit Min: {(settings.tp_min * 100).toFixed(2)}%</label>
                            <input
                                type="range"
                                min="0.005"
                                max="0.02"
                                step="0.001"
                                value={settings.tp_min}
                                onChange={(e) => setSettings({ ...settings, tp_min: Number(e.target.value) })}
                                className="slider"
                            />
                        </div>

                        <div className="form-group">
                            <label>Take Profit Max: {(settings.tp_max * 100).toFixed(2)}%</label>
                            <input
                                type="range"
                                min="0.01"
                                max="0.03"
                                step="0.001"
                                value={settings.tp_max}
                                onChange={(e) => setSettings({ ...settings, tp_max: Number(e.target.value) })}
                                className="slider"
                            />
                        </div>

                        <div className="form-group">
                            <label>Stop Loss: {(settings.stop_floor * 100).toFixed(2)}%</label>
                            <input
                                type="range"
                                min="0.003"
                                max="0.015"
                                step="0.001"
                                value={settings.stop_floor}
                                onChange={(e) => setSettings({ ...settings, stop_floor: Number(e.target.value) })}
                                className="slider"
                            />
                        </div>

                        <button className="btn-primary" onClick={saveTradingSettings} disabled={saving}>
                            {saving ? <Loader className="spin" size={16} /> : <Save size={16} />}
                            <span>Save Trading Params</span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Save Status Toast */}
            {saveStatus !== 'idle' && (
                <div className={`save-toast ${saveStatus}`}>
                    {saveStatus === 'success' ? (
                        <>
                            <CheckCircle size={20} />
                            <span>Settings saved successfully!</span>
                        </>
                    ) : (
                        <>
                            <AlertCircle size={20} />
                            <span>Failed to save settings</span>
                        </>
                    )}
                </div>
            )}

        </div>
    )
}

export default SettingsView

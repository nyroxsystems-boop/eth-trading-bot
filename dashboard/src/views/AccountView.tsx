import { useState, useEffect } from 'react'
import { User, Key, Shield, Bell } from 'lucide-react'
import { motion } from 'framer-motion'
import { useAuth } from '../contexts/AuthContext'
import '../styles/premium.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const AccountView = () => {
    const { user, token } = useAuth()
    const [hasApiKeys, setHasApiKeys] = useState(false)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchProfile()
    }, [])

    const fetchProfile = async () => {
        try {
            const res = await fetch(`${API_URL}/api/profile`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {}
            })
            if (res.ok) {
                const data = await res.json()
                setHasApiKeys(data.has_api_keys || false)
            }
        } catch (e) { console.warn('Profile fetch failed:', e) }
        setLoading(false)
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '24px' }}
        >
            <div style={{ marginBottom: '24px' }}>
                <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <User size={28} /> Account
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '4px' }}>
                    Manage your profile and settings
                </p>
            </div>

            {loading ? (
                <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>Loading...</div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
                    {/* Profile Card */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
                            <div style={{
                                width: '56px', height: '56px', borderRadius: '50%',
                                background: 'linear-gradient(135deg, #8b5cf6, #06b6d4)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: 'white', fontWeight: 700, fontSize: '22px'
                            }}>
                                {user?.username?.charAt(0)?.toUpperCase() || 'U'}
                            </div>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: '18px', color: 'var(--text-primary)' }}>
                                    {user?.username || 'User'}
                                </div>
                                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                    {user?.email || ''}
                                </div>
                            </div>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--glass-border)' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Role</span>
                                <span style={{ color: user?.role === 'admin' ? '#f59e0b' : 'var(--text-primary)', fontWeight: 600, fontSize: '13px' }}>
                                    {user?.role === 'admin' ? '👑 Admin' : '👤 User'}
                                </span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--glass-border)' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Tier</span>
                                <span style={{ color: '#8b5cf6', fontWeight: 600, fontSize: '13px' }}>
                                    {user?.subscription_tier || 'Free'}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* API Keys Card */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                            <Key size={20} style={{ color: '#06b6d4' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '16px' }}>API Keys</span>
                        </div>
                        <div style={{
                            padding: '16px', borderRadius: '10px',
                            background: hasApiKeys ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.08)',
                            border: `1px solid ${hasApiKeys ? 'rgba(16,185,129,0.2)' : 'rgba(245,158,11,0.2)'}`,
                            marginBottom: '16px'
                        }}>
                            <div style={{ fontWeight: 600, color: hasApiKeys ? '#10b981' : '#f59e0b', marginBottom: '4px' }}>
                                {hasApiKeys ? '✅ Binance Keys Configured' : '⚠️ No API Keys'}
                            </div>
                            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                {hasApiKeys ? 'Your Binance API keys are set up and ready for trading.' : 'Add your Binance API keys in Settings to enable live trading.'}
                            </div>
                        </div>
                        <button
                            onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'settings' } }))}
                            style={{
                                width: '100%', padding: '12px', borderRadius: '8px', border: 'none',
                                background: 'rgba(139,92,246,0.15)', color: '#a78bfa',
                                fontWeight: 600, cursor: 'pointer', fontSize: '13px'
                            }}
                        >
                            Manage in Settings →
                        </button>
                    </div>

                    {/* Security Card */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                            <Shield size={20} style={{ color: '#10b981' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '16px' }}>Security</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>2FA</span>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Coming Soon</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>JWT Auth</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>✅ Active</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>API Encryption</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>✅ Fernet</span>
                            </div>
                        </div>
                    </div>

                    {/* Notifications */}
                    <div className="glass-card" style={{ padding: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
                            <Bell size={20} style={{ color: '#f59e0b' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '16px' }}>Notifications</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Telegram</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>✅ Connected</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Trade Alerts</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>Enabled</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Daily Reports</span>
                                <span style={{ color: '#10b981', fontWeight: 600, fontSize: '13px' }}>18:00 CET</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </motion.div>
    )
}

export default AccountView

import { useState, useEffect } from 'react'
import { Plus, Trash2, Power, PowerOff, Check, X } from 'lucide-react'
import '../styles/premium.css'
import '../styles/components.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Account {
    id: number
    name: string
    api_key: string
    api_secret_masked: string
    capital: number
    dry_run: boolean
    active: boolean
    created_at: string
    last_active: string | null
}

const AccountsView = () => {
    const [accounts, setAccounts] = useState<Account[]>([])
    const [loading, setLoading] = useState(true)
    const [showAddForm, setShowAddForm] = useState(false)

    // Form state
    const [formData, setFormData] = useState({
        name: '',
        api_key: '',
        api_secret: '',
        capital: 10000,
        dry_run: true
    })

    const [validating, setValidating] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
        fetchAccounts()
    }, [])

    const fetchAccounts = async () => {
        try {
            const res = await fetch(`${API_URL}/api/accounts`)
            const data = await res.json()
            setAccounts(data.accounts || [])
            setLoading(false)
        } catch (err) {
            console.error('Failed to fetch accounts:', err)
            setLoading(false)
        }
    }

    const validateCredentials = async () => {
        if (!formData.api_key || !formData.api_secret) {
            setError('API Key and Secret are required')
            return false
        }

        setValidating(true)
        setError('')

        try {
            const res = await fetch(`${API_URL}/api/accounts/validate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_key: formData.api_key,
                    api_secret: formData.api_secret
                })
            })

            const data = await res.json()
            setValidating(false)

            if (!data.valid) {
                setError(data.message || 'Invalid credentials')
                return false
            }

            return true
        } catch (err) {
            setValidating(false)
            setError('Failed to validate credentials')
            return false
        }
    }

    const handleAddAccount = async () => {
        const valid = await validateCredentials()
        if (!valid) return

        try {
            const res = await fetch(`${API_URL}/api/accounts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            })

            if (!res.ok) {
                const data = await res.json()
                setError(data.detail || 'Failed to create account')
                return
            }

            // Reset form and refresh
            setFormData({
                name: '',
                api_key: '',
                api_secret: '',
                capital: 10000,
                dry_run: true
            })
            setShowAddForm(false)
            setError('')
            fetchAccounts()
        } catch (err) {
            setError('Failed to create account')
        }
    }

    const handleToggleAccount = async (id: number) => {
        try {
            await fetch(`${API_URL}/api/accounts/${id}/toggle`, {
                method: 'POST'
            })
            fetchAccounts()
        } catch (err) {
            console.error('Failed to toggle account:', err)
        }
    }

    const handleDeleteAccount = async (id: number) => {
        if (!confirm('Are you sure you want to delete this account? This will also delete all associated trades.')) {
            return
        }

        try {
            await fetch(`${API_URL}/api/accounts/${id}`, {
                method: 'DELETE'
            })
            fetchAccounts()
        } catch (err) {
            console.error('Failed to delete account:', err)
        }
    }

    if (loading) {
        return (
            <div style={{ padding: '24px', textAlign: 'center' }}>
                <div className="spinner" style={{ margin: '0 auto' }} />
                <p style={{ marginTop: '16px', color: '#94A3B8' }}>Loading accounts...</p>
            </div>
        )
    }

    return (
        <div style={{ padding: '24px', maxWidth: '1920px', margin: '0 auto' }}>
            {/* Header */}
            <div style={{ marginBottom: '32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h1 style={{ fontSize: '32px', fontWeight: 700, background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: '8px' }}>
                        💼 Trading Accounts
                    </h1>
                    <p style={{ color: '#94A3B8', fontSize: '16px' }}>Manage multiple Binance API accounts</p>
                </div>
                <button
                    onClick={() => setShowAddForm(!showAddForm)}
                    style={{
                        padding: '12px 24px',
                        background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                        border: 'none',
                        borderRadius: '12px',
                        color: 'white',
                        fontSize: '16px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}
                >
                    <Plus size={20} />
                    Add Account
                </button>
            </div>

            {/* Add Account Form */}
            {showAddForm && (
                <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>Add New Account</h3>

                    {error && (
                        <div style={{ padding: '12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', marginBottom: '16px', color: '#EF4444' }}>
                            {error}
                        </div>
                    )}

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>Account Name</label>
                            <input
                                type="text"
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                placeholder="My Trading Account"
                                style={{
                                    width: '100%',
                                    padding: '12px',
                                    background: 'rgba(139, 92, 246, 0.05)',
                                    border: '1px solid rgba(139, 92, 246, 0.2)',
                                    borderRadius: '8px',
                                    color: 'white',
                                    fontSize: '14px'
                                }}
                            />
                        </div>

                        <div>
                            <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>API Key</label>
                            <input
                                type="text"
                                value={formData.api_key}
                                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                                placeholder="Binance API Key"
                                style={{
                                    width: '100%',
                                    padding: '12px',
                                    background: 'rgba(139, 92, 246, 0.05)',
                                    border: '1px solid rgba(139, 92, 246, 0.2)',
                                    borderRadius: '8px',
                                    color: 'white',
                                    fontSize: '14px'
                                }}
                            />
                        </div>

                        <div>
                            <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>API Secret</label>
                            <input
                                type="password"
                                value={formData.api_secret}
                                onChange={(e) => setFormData({ ...formData, api_secret: e.target.value })}
                                placeholder="Binance API Secret"
                                style={{
                                    width: '100%',
                                    padding: '12px',
                                    background: 'rgba(139, 92, 246, 0.05)',
                                    border: '1px solid rgba(139, 92, 246, 0.2)',
                                    borderRadius: '8px',
                                    color: 'white',
                                    fontSize: '14px'
                                }}
                            />
                        </div>

                        <div>
                            <label style={{ display: 'block', fontSize: '14px', color: '#94A3B8', marginBottom: '8px' }}>Initial Capital (USDT)</label>
                            <input
                                type="number"
                                value={formData.capital}
                                onChange={(e) => setFormData({ ...formData, capital: parseFloat(e.target.value) })}
                                style={{
                                    width: '100%',
                                    padding: '12px',
                                    background: 'rgba(139, 92, 246, 0.05)',
                                    border: '1px solid rgba(139, 92, 246, 0.2)',
                                    borderRadius: '8px',
                                    color: 'white',
                                    fontSize: '14px'
                                }}
                            />
                        </div>
                    </div>

                    <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                            <input
                                type="checkbox"
                                checked={formData.dry_run}
                                onChange={(e) => setFormData({ ...formData, dry_run: e.target.checked })}
                            />
                            <span style={{ fontSize: '14px', color: '#94A3B8' }}>Paper Trading Mode (Recommended)</span>
                        </label>
                    </div>

                    <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
                        <button
                            onClick={handleAddAccount}
                            disabled={validating}
                            style={{
                                padding: '12px 24px',
                                background: validating ? '#64748B' : 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                                border: 'none',
                                borderRadius: '8px',
                                color: 'white',
                                fontSize: '14px',
                                fontWeight: 600,
                                cursor: validating ? 'not-allowed' : 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px'
                            }}
                        >
                            <Check size={16} />
                            {validating ? 'Validating...' : 'Create Account'}
                        </button>
                        <button
                            onClick={() => {
                                setShowAddForm(false)
                                setError('')
                            }}
                            style={{
                                padding: '12px 24px',
                                background: 'rgba(239, 68, 68, 0.1)',
                                border: '1px solid rgba(239, 68, 68, 0.3)',
                                borderRadius: '8px',
                                color: '#EF4444',
                                fontSize: '14px',
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px'
                            }}
                        >
                            <X size={16} />
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Accounts List */}
            <div style={{ display: 'grid', gap: '16px' }}>
                {accounts.length === 0 ? (
                    <div className="glass-card" style={{ padding: '48px', textAlign: 'center' }}>
                        <p style={{ fontSize: '18px', color: '#64748B', marginBottom: '8px' }}>No accounts yet</p>
                        <p style={{ fontSize: '14px', color: '#94A3B8' }}>Click "Add Account" to get started</p>
                    </div>
                ) : (
                    accounts.map((account) => (
                        <div key={account.id} className="glass-card" style={{ padding: '20px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                                        <h3 style={{ fontSize: '18px', fontWeight: 600 }}>{account.name}</h3>
                                        <span style={{
                                            padding: '4px 12px',
                                            borderRadius: '12px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            background: account.active ? 'rgba(16, 185, 129, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                                            color: account.active ? '#10B981' : '#64748B'
                                        }}>
                                            {account.active ? '● Active' : '○ Inactive'}
                                        </span>
                                        <span style={{
                                            padding: '4px 12px',
                                            borderRadius: '12px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            background: account.dry_run ? 'rgba(59, 130, 246, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                                            color: account.dry_run ? '#3B82F6' : '#EF4444'
                                        }}>
                                            {account.dry_run ? '📝 Paper' : '🔴 Live'}
                                        </span>
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', fontSize: '14px', color: '#94A3B8' }}>
                                        <div>
                                            <span style={{ color: '#64748B' }}>API Key:</span> {account.api_key.substring(0, 8)}...
                                        </div>
                                        <div>
                                            <span style={{ color: '#64748B' }}>Capital:</span> ${account.capital.toLocaleString()}
                                        </div>
                                        <div>
                                            <span style={{ color: '#64748B' }}>Created:</span> {new Date(account.created_at).toLocaleDateString()}
                                        </div>
                                    </div>
                                </div>

                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <button
                                        onClick={() => handleToggleAccount(account.id)}
                                        style={{
                                            padding: '8px 16px',
                                            background: account.active ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                                            border: `1px solid ${account.active ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                                            borderRadius: '8px',
                                            color: account.active ? '#EF4444' : '#10B981',
                                            fontSize: '14px',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '6px'
                                        }}
                                    >
                                        {account.active ? <PowerOff size={16} /> : <Power size={16} />}
                                        {account.active ? 'Disable' : 'Enable'}
                                    </button>
                                    <button
                                        onClick={() => handleDeleteAccount(account.id)}
                                        style={{
                                            padding: '8px 16px',
                                            background: 'rgba(239, 68, 68, 0.1)',
                                            border: '1px solid rgba(239, 68, 68, 0.3)',
                                            borderRadius: '8px',
                                            color: '#EF4444',
                                            fontSize: '14px',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '6px'
                                        }}
                                    >
                                        <Trash2 size={16} />
                                        Delete
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}

export default AccountsView

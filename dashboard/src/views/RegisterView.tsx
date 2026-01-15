import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { UserPlus } from 'lucide-react'
import '../styles/premium.css'

const RegisterView = () => {
    const { register } = useAuth()
    const [email, setEmail] = useState('')
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')

        if (password !== confirmPassword) {
            setError('Passwords do not match')
            return
        }

        if (password.length < 8) {
            setError('Password must be at least 8 characters')
            return
        }

        setLoading(true)

        try {
            await register(email, username, password)
            // Redirect handled by App.tsx
        } catch (err: any) {
            setError(err.message || 'Registration failed')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
            padding: '24px'
        }}>
            <div className="glass-card" style={{
                maxWidth: '400px',
                width: '100%',
                padding: '48px 32px'
            }}>
                {/* Logo */}
                <div style={{ textAlign: 'center', marginBottom: '32px' }}>
                    <div style={{
                        width: '64px',
                        height: '64px',
                        borderRadius: '16px',
                        background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '0 auto 16px',
                        fontSize: '32px',
                        fontWeight: 700
                    }}>
                        E
                    </div>
                    <h1 style={{
                        fontSize: '28px',
                        fontWeight: 700,
                        background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                        marginBottom: '8px'
                    }}>
                        Create Account
                    </h1>
                    <p style={{ color: '#94A3B8', fontSize: '14px' }}>
                        Start your trading journey
                    </p>
                </div>

                {/* Error Message */}
                {error && (
                    <div style={{
                        padding: '12px',
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: '8px',
                        marginBottom: '24px',
                        color: '#EF4444',
                        fontSize: '14px'
                    }}>
                        {error}
                    </div>
                )}

                {/* Register Form */}
                <form onSubmit={handleSubmit}>
                    <div style={{ marginBottom: '16px' }}>
                        <label style={{
                            display: 'block',
                            fontSize: '14px',
                            color: '#94A3B8',
                            marginBottom: '8px',
                            fontWeight: 500
                        }}>
                            Email
                        </label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            style={{
                                width: '100%',
                                padding: '12px 16px',
                                background: 'rgba(139, 92, 246, 0.05)',
                                border: '1px solid rgba(139, 92, 246, 0.2)',
                                borderRadius: '8px',
                                color: 'white',
                                fontSize: '14px',
                                outline: 'none'
                            }}
                        />
                    </div>

                    <div style={{ marginBottom: '16px' }}>
                        <label style={{
                            display: 'block',
                            fontSize: '14px',
                            color: '#94A3B8',
                            marginBottom: '8px',
                            fontWeight: 500
                        }}>
                            Username
                        </label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            required
                            style={{
                                width: '100%',
                                padding: '12px 16px',
                                background: 'rgba(139, 92, 246, 0.05)',
                                border: '1px solid rgba(139, 92, 246, 0.2)',
                                borderRadius: '8px',
                                color: 'white',
                                fontSize: '14px',
                                outline: 'none'
                            }}
                        />
                    </div>

                    <div style={{ marginBottom: '16px' }}>
                        <label style={{
                            display: 'block',
                            fontSize: '14px',
                            color: '#94A3B8',
                            marginBottom: '8px',
                            fontWeight: 500
                        }}>
                            Password
                        </label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            style={{
                                width: '100%',
                                padding: '12px 16px',
                                background: 'rgba(139, 92, 246, 0.05)',
                                border: '1px solid rgba(139, 92, 246, 0.2)',
                                borderRadius: '8px',
                                color: 'white',
                                fontSize: '14px',
                                outline: 'none'
                            }}
                        />
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <label style={{
                            display: 'block',
                            fontSize: '14px',
                            color: '#94A3B8',
                            marginBottom: '8px',
                            fontWeight: 500
                        }}>
                            Confirm Password
                        </label>
                        <input
                            type="password"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            required
                            style={{
                                width: '100%',
                                padding: '12px 16px',
                                background: 'rgba(139, 92, 246, 0.05)',
                                border: '1px solid rgba(139, 92, 246, 0.2)',
                                borderRadius: '8px',
                                color: 'white',
                                fontSize: '14px',
                                outline: 'none'
                            }}
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        style={{
                            width: '100%',
                            padding: '14px',
                            background: loading ? '#64748B' : 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                            border: 'none',
                            borderRadius: '8px',
                            color: 'white',
                            fontSize: '16px',
                            fontWeight: 600,
                            cursor: loading ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px'
                        }}
                    >
                        <UserPlus size={20} />
                        {loading ? 'Creating account...' : 'Sign Up'}
                    </button>
                </form>

                {/* Login Link */}
                <div style={{
                    marginTop: '24px',
                    textAlign: 'center',
                    fontSize: '14px',
                    color: '#94A3B8'
                }}>
                    Already have an account?{' '}
                    <a
                        href="/login"
                        style={{
                            color: '#8B5CF6',
                            textDecoration: 'none',
                            fontWeight: 600
                        }}
                    >
                        Sign in
                    </a>
                </div>
            </div>
        </div>
    )
}

export default RegisterView

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

interface User {
    id: number
    email: string
    username: string
    role: string
    subscription_tier: string
}

interface AuthContextType {
    user: User | null
    token: string | null
    login: (emailOrUsername: string, password: string) => Promise<void>
    register: (email: string, username: string, password: string) => Promise<void>
    logout: () => void
    isAuthenticated: boolean
    isAdmin: boolean
    loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const API_URL = import.meta.env.VITE_API_URL || ''

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const [user, setUser] = useState<User | null>(null)
    const [token, setToken] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        // Check for stored token on mount
        const storedToken = localStorage.getItem('auth_token')
        if (storedToken) {
            fetchCurrentUser(storedToken)
        } else {
            setLoading(false)
        }
    }, [])

    const fetchCurrentUser = async (authToken: string) => {
        try {
            const res = await fetch(`${API_URL}/api/auth/me`, {
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            })

            if (res.ok) {
                const userData = await res.json()
                setUser(userData)
                setToken(authToken)
            } else {
                // Token invalid, clear it
                localStorage.removeItem('auth_token')
                setToken(null)
                setUser(null)
            }
        } catch (err) {
            console.error('Failed to fetch user:', err)
            localStorage.removeItem('auth_token')
        } finally {
            setLoading(false)
        }
    }

    const login = async (emailOrUsername: string, password: string) => {
        const res = await fetch(`${API_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email_or_username: emailOrUsername,
                password
            })
        })

        if (!res.ok) {
            const error = await res.json()
            throw new Error(error.detail || 'Login failed')
        }

        const data = await res.json()

        // API returns user data directly with user_id, not nested under 'user'
        const userData: User = {
            id: data.user_id,
            email: data.email,
            username: data.username,
            role: data.role,
            subscription_tier: 'free' // Default, will be fetched from /api/auth/me
        }

        setToken(data.token)
        setUser(userData)
        localStorage.setItem('auth_token', data.token)

        // Fetch full user data including subscription_tier
        await fetchCurrentUser(data.token)
    }

    const register = async (email: string, username: string, password: string) => {
        const res = await fetch(`${API_URL}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, username, password })
        })

        if (!res.ok) {
            const error = await res.json()
            throw new Error(error.detail || 'Registration failed')
        }

        // Auto-login after registration
        await login(email, password)
    }

    const logout = async () => {
        if (token) {
            try {
                await fetch(`${API_URL}/api/auth/logout`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                })
            } catch (err) {
                console.error('Logout error:', err)
            }
        }

        setUser(null)
        setToken(null)
        localStorage.removeItem('auth_token')
    }

    const value = {
        user,
        token,
        login,
        register,
        logout,
        isAuthenticated: !!user,
        isAdmin: user?.role === 'admin',
        loading
    }

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
    const context = useContext(AuthContext)
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider')
    }
    return context
}

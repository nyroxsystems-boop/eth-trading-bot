import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Users, Shield, DollarSign, Activity, AlertTriangle,
    Power, PlayCircle, Trash2, UserCheck, UserX, Crown,
    Server, Database, Zap, RefreshCw, Bot,
    Terminal, Cpu, Settings, TrendingUp, Clock, Brain,
    CheckCircle, XCircle, Loader2
} from 'lucide-react';
import '../styles/premium.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface User {
    id: number;
    email: string;
    username: string;
    role: string;
    subscription_tier: string;
    active: boolean;
    has_api_keys: boolean;
    trading_enabled: boolean;
    created_at: string;
    last_login: string | null;
}

interface AdminDashboardProps {
    activeTab?: string;
}

// Fetch with timeout helper
const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeoutMs = 8000) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timeout);
        return res;
    } catch (e: any) {
        clearTimeout(timeout);
        if (e.name === 'AbortError') throw new Error('Request timeout');
        throw e;
    }
};

const AdminDashboardView = ({ activeTab = 'overview' }: AdminDashboardProps) => {
    // Independent state per section
    const [users, setUsers] = useState<User[]>([]);
    const [analytics, setAnalytics] = useState<any>(null);
    const [revenue, setRevenue] = useState<any>(null);
    const [systemHealth, setSystemHealth] = useState<any>(null);
    const [emergencyActive, setEmergencyActive] = useState(false);
    const [botStatus, setBotStatus] = useState<any>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [learningStats, setLearningStats] = useState<any>(null);

    // Per-section loading states
    const [loadingUsers, setLoadingUsers] = useState(true);
    const [loadingAnalytics, setLoadingAnalytics] = useState(true);
    const [loadingHealth, setLoadingHealth] = useState(true);
    const [loadingLogs, setLoadingLogs] = useState(true);
    const [loadingRevenue, setLoadingRevenue] = useState(true);
    const [loadingBot, setLoadingBot] = useState(true);

    const [error, setError] = useState<string | null>(null);
    const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

    const getToken = () => localStorage.getItem('auth_token') || localStorage.getItem('token');
    const headers = () => ({ 'Authorization': `Bearer ${getToken()}` });

    // === INDEPENDENT FETCHERS (each section loads independently) ===

    const fetchUsers = useCallback(async () => {
        setLoadingUsers(true);
        try {
            const res = await fetchWithTimeout(`${API_URL}/api/admin/users`, { headers: headers() });
            if (res.ok) {
                const data = await res.json();
                setUsers(data.users || []);
            }
        } catch (e) { console.warn('Users fetch failed:', e); }
        setLoadingUsers(false);
    }, []);

    const fetchAnalytics = useCallback(async () => {
        setLoadingAnalytics(true);
        try {
            const [analyticsRes, emergencyRes] = await Promise.allSettled([
                fetchWithTimeout(`${API_URL}/api/admin/analytics`, { headers: headers() }),
                fetchWithTimeout(`${API_URL}/api/admin/emergency/status`, { headers: headers() }),
            ]);
            if (analyticsRes.status === 'fulfilled' && analyticsRes.value.ok)
                setAnalytics(await analyticsRes.value.json());
            if (emergencyRes.status === 'fulfilled' && emergencyRes.value.ok) {
                const data = await emergencyRes.value.json();
                setEmergencyActive(data.trading_stopped);
            }
        } catch (e) { console.warn('Analytics fetch failed:', e); }
        setLoadingAnalytics(false);
    }, []);

    const fetchHealth = useCallback(async () => {
        setLoadingHealth(true);
        try {
            const res = await fetchWithTimeout(`${API_URL}/api/admin/system/health`, { headers: headers() });
            if (res.ok) setSystemHealth(await res.json());
        } catch (e) { console.warn('Health fetch failed:', e); }
        setLoadingHealth(false);
    }, []);

    const fetchRevenue = useCallback(async () => {
        setLoadingRevenue(true);
        try {
            const res = await fetchWithTimeout(`${API_URL}/api/admin/revenue`, { headers: headers() });
            if (res.ok) setRevenue(await res.json());
        } catch (e) { console.warn('Revenue fetch failed:', e); }
        setLoadingRevenue(false);
    }, []);

    const fetchLogs = useCallback(async () => {
        setLoadingLogs(true);
        try {
            const res = await fetchWithTimeout(`${API_URL}/api/logs?lines=50`, { headers: headers() });
            if (res.ok) {
                const data = await res.json();
                setLogs(data.logs || data.lines || []);
            }
        } catch (e) { console.warn('Logs fetch failed:', e); }
        setLoadingLogs(false);
    }, []);

    const fetchBot = useCallback(async () => {
        setLoadingBot(true);
        try {
            const [statusRes, learningRes] = await Promise.allSettled([
                fetchWithTimeout(`${API_URL}/api/status`, { headers: headers() }),
                fetchWithTimeout(`${API_URL}/api/learning/stats`, { headers: headers() }),
            ]);
            if (statusRes.status === 'fulfilled' && statusRes.value.ok)
                setBotStatus(await statusRes.value.json());
            if (learningRes.status === 'fulfilled' && learningRes.value.ok)
                setLearningStats(await learningRes.value.json());
        } catch (e) { console.warn('Bot fetch failed:', e); }
        setLoadingBot(false);
    }, []);

    const fetchAll = useCallback(async () => {
        const token = getToken();
        if (!token) { setError('Not authenticated'); return; }
        setLastRefresh(new Date());
        // Fire all independently — each manages its own loading state
        fetchUsers();
        fetchAnalytics();
        fetchHealth();
        fetchRevenue();
        fetchLogs();
        fetchBot();
    }, [fetchUsers, fetchAnalytics, fetchHealth, fetchRevenue, fetchLogs, fetchBot]);

    useEffect(() => {
        fetchAll();
        const interval = setInterval(fetchAll, 30000);
        return () => clearInterval(interval);
    }, [fetchAll]);

    const toggleEmergency = async () => {
        const token = getToken();
        const endpoint = emergencyActive ? 'resume' : 'stop-all';
        try {
            const res = await fetchWithTimeout(`${API_URL}/api/admin/emergency/${endpoint}`, {
                method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setEmergencyActive(data.trading_stopped);
            }
        } catch (err) { console.error('Emergency toggle failed:', err); }
    };

    const toggleUser = async (userId: number) => {
        const token = getToken();
        try {
            const res = await fetchWithTimeout(`${API_URL}/api/admin/users/${userId}/toggle`, {
                method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) fetchUsers();
        } catch (err) { console.error('Toggle user failed:', err); }
    };

    const deleteUser = async (userId: number) => {
        if (!confirm('Are you sure you want to delete this user?')) return;
        const token = getToken();
        try {
            await fetchWithTimeout(`${API_URL}/api/admin/users/${userId}`, {
                method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` }
            });
            fetchUsers();
        } catch (err) { console.error('Delete user failed:', err); }
    };

    if (error) {
        return (
            <div className="error-container">
                <AlertTriangle size={48} />
                <h2>Access Denied</h2>
                <p>{error}</p>
            </div>
        );
    }

    // === SECTION LOADING SPINNER ===
    const SectionLoader = ({ label }: { label: string }) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '24px', color: '#94a3b8' }}>
            <Loader2 size={18} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: '14px' }}>Loading {label}...</span>
        </div>
    );

    // === STATUS PILL ===
    const StatusPill = ({ ok, label }: { ok: boolean; label: string }) => (
        <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 600,
            background: ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
            color: ok ? '#10b981' : '#ef4444',
            border: `1px solid ${ok ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`
        }}>
            {ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {label}
        </div>
    );

    // ========== TAB RENDERERS ==========

    const renderOverview = () => (
        <>
            {/* Emergency Control */}
            <motion.div
                className={`emergency-control ${emergencyActive ? 'active' : ''}`}
                initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
            >
                <div className="emergency-status">
                    <AlertTriangle size={24} />
                    <span>{emergencyActive ? '🚨 EMERGENCY STOP ACTIVE' : '✅ Trading Active'}</span>
                </div>
                <button onClick={toggleEmergency} className={`emergency-btn ${emergencyActive ? 'resume' : 'stop'}`}>
                    {emergencyActive ? (<><PlayCircle size={18} /> Resume Trading</>) : (<><Power size={18} /> Emergency Stop</>)}
                </button>
            </motion.div>

            {/* Stats Grid */}
            {loadingAnalytics ? <SectionLoader label="Analytics" /> : (
                <div className="admin-stats-grid">
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon users"><Users size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">{analytics?.total_users || 0}</span>
                            <span className="stat-label">Total Users</span>
                        </div>
                    </motion.div>
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon active"><UserCheck size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">{analytics?.active_users || 0}</span>
                            <span className="stat-label">Active Users</span>
                        </div>
                    </motion.div>
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon trading"><Zap size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">{analytics?.users_with_api_keys || 0}</span>
                            <span className="stat-label">Trading Users</span>
                        </div>
                    </motion.div>
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon revenue"><DollarSign size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">${revenue?.mrr?.toFixed(2) || '0.00'}</span>
                            <span className="stat-label">MRR</span>
                        </div>
                    </motion.div>
                </div>
            )}

            {/* Learning Stats */}
            {!loadingBot && learningStats && (
                <motion.div className="glass-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                    style={{ marginBottom: '20px' }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                        <Brain size={20} /> Auto-Learning Status
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
                        {[
                            { label: 'Total Tested', value: learningStats?.stats?.total_tested?.toLocaleString() || '0', color: '#06b6d4' },
                            { label: 'Best Score', value: learningStats?.stats?.best_score?.toFixed(1) || '0', color: '#f59e0b' },
                            { label: 'Applied', value: learningStats?.stats?.total_applied || '0', color: '#10b981' },
                            { label: 'Today', value: learningStats?.stats?.today_tested || '0', color: '#8b5cf6' },
                            { label: 'This Hour', value: learningStats?.stats?.this_hour_tested || '0', color: '#ec4899' },
                        ].map(s => (
                            <div key={s.label} style={{
                                padding: '16px', borderRadius: '12px',
                                background: `${s.color}08`, border: `1px solid ${s.color}20`
                            }}>
                                <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>{s.label}</div>
                                <div style={{ fontSize: '22px', fontWeight: 700, color: s.color }}>{s.value}</div>
                            </div>
                        ))}
                    </div>
                </motion.div>
            )}

            {/* System Health */}
            {loadingHealth ? <SectionLoader label="System Health" /> : (
                <motion.div className="glass-card health-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <h3><Server size={20} /> System Health</h3>
                    <div className="health-grid">
                        <div className={`health-item ${systemHealth?.services?.database?.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                            <Database size={18} />
                            <span>Database</span>
                            <StatusPill ok={systemHealth?.services?.database?.status === 'healthy'} label={systemHealth?.services?.database?.status || 'unknown'} />
                        </div>
                        <div className={`health-item ${systemHealth?.services?.api?.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                            <Activity size={18} />
                            <span>API</span>
                            <StatusPill ok={systemHealth?.services?.api?.status === 'healthy'} label={systemHealth?.services?.api?.status || 'unknown'} />
                        </div>
                        <div className="health-item">
                            <AlertTriangle size={18} />
                            <span>Emergency</span>
                            <StatusPill ok={!emergencyActive} label={emergencyActive ? 'STOPPED' : 'OK'} />
                        </div>
                    </div>
                </motion.div>
            )}

            {/* Users Table on Overview */}
            {renderUsers()}
        </>
    );

    const renderUsers = () => (
        <motion.div className="glass-card users-table-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <h3><Users size={20} /> User Management ({loadingUsers ? '...' : `${users.length} users`})</h3>
            {loadingUsers ? <SectionLoader label="Users" /> : (
                <div className="users-table-container">
                    <table className="users-table">
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Email</th>
                                <th>Role</th>
                                <th>Tier</th>
                                <th>Status</th>
                                <th>API Keys</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map(user => (
                                <tr key={user.id} className={!user.active ? 'inactive' : ''}>
                                    <td>
                                        <div className="user-cell">
                                            {user.role === 'admin' && <Crown size={14} className="admin-badge" />}
                                            {user.username}
                                        </div>
                                    </td>
                                    <td>{user.email}</td>
                                    <td><span className={`role-badge ${user.role}`}>{user.role}</span></td>
                                    <td><span className={`tier-badge ${user.subscription_tier}`}>{user.subscription_tier}</span></td>
                                    <td>
                                        <span className={`status-badge ${user.active ? 'active' : 'inactive'}`}>
                                            {user.active ? 'Active' : 'Disabled'}
                                        </span>
                                    </td>
                                    <td>
                                        {user.has_api_keys ? (
                                            <span className="api-keys-badge has-keys">🔑 Configured</span>
                                        ) : (
                                            <span className="api-keys-badge no-keys">No Keys</span>
                                        )}
                                    </td>
                                    <td>
                                        <div className="action-buttons">
                                            <button onClick={() => toggleUser(user.id)}
                                                className={`action-btn ${user.active ? 'disable' : 'enable'}`}
                                                title={user.active ? 'Disable User' : 'Enable User'}>
                                                {user.active ? <UserX size={16} /> : <UserCheck size={16} />}
                                            </button>
                                            {user.role !== 'admin' && (
                                                <button onClick={() => deleteUser(user.id)}
                                                    className="action-btn delete" title="Delete User">
                                                    <Trash2 size={16} />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </motion.div>
    );

    const renderSystem = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {loadingHealth ? <SectionLoader label="System Status" /> : (
                <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                        <Cpu size={20} /> System Status
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                        <div style={{ padding: '16px', borderRadius: '12px', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Database</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: systemHealth?.services?.database?.status === 'healthy' ? '#10b981' : '#ef4444' }}>
                                {systemHealth?.services?.database?.status === 'healthy' ? '● Online' : '● Offline'}
                            </div>
                            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>{systemHealth?.services?.database?.type || 'PostgreSQL'}</div>
                        </div>
                        <div style={{ padding: '16px', borderRadius: '12px', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>API Server</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: systemHealth?.services?.api?.status === 'healthy' ? '#10b981' : '#ef4444' }}>
                                {systemHealth?.services?.api?.status === 'healthy' ? '● Online' : '● Offline'}
                            </div>
                            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>FastAPI / Uvicorn</div>
                        </div>
                        <div style={{ padding: '16px', borderRadius: '12px', background: emergencyActive ? 'rgba(239,68,68,0.1)' : 'rgba(16,185,129,0.1)', border: `1px solid ${emergencyActive ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)'}` }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Emergency Stop</div>
                            <div style={{ fontSize: '18px', fontWeight: 700, color: emergencyActive ? '#ef4444' : '#10b981' }}>
                                {emergencyActive ? '🚨 ACTIVE' : '✅ Clear'}
                            </div>
                        </div>
                    </div>
                </motion.div>
            )}

            {/* Learning Engine Stats */}
            {!loadingBot && learningStats && (
                <motion.div className="glass-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                        <Brain size={20} /> Learning Engine
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                        {[
                            { label: 'Strategies Tested', value: learningStats?.stats?.total_tested?.toLocaleString() || '0', icon: <TrendingUp size={16} />, color: '#06b6d4' },
                            { label: 'Best Score', value: learningStats?.stats?.best_score?.toFixed(1) || '0', icon: <Crown size={16} />, color: '#f59e0b' },
                            { label: 'Applied', value: learningStats?.stats?.total_applied || '0', icon: <CheckCircle size={16} />, color: '#10b981' },
                            { label: 'This Hour', value: learningStats?.stats?.this_hour_tested || '0', icon: <Clock size={16} />, color: '#8b5cf6' },
                        ].map(s => (
                            <div key={s.label} style={{
                                padding: '16px', borderRadius: '12px',
                                background: `${s.color}08`, border: `1px solid ${s.color}20`,
                                display: 'flex', flexDirection: 'column', gap: '8px'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#94a3b8', fontSize: '12px' }}>
                                    {s.icon} {s.label}
                                </div>
                                <div style={{ fontSize: '22px', fontWeight: 700, color: s.color }}>{s.value}</div>
                            </div>
                        ))}
                    </div>
                </motion.div>
            )}
        </div>
    );

    const renderBot = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <motion.div className={`emergency-control ${emergencyActive ? 'active' : ''}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <div className="emergency-status">
                    <Bot size={24} />
                    <span>{emergencyActive ? '🚨 BOT STOPPED' : '🤖 Bot Running'}</span>
                </div>
                <button onClick={toggleEmergency} className={`emergency-btn ${emergencyActive ? 'resume' : 'stop'}`}>
                    {emergencyActive ? (<><PlayCircle size={18} /> Resume Bot</>) : (<><Power size={18} /> Stop Bot</>)}
                </button>
            </motion.div>

            {loadingBot ? <SectionLoader label="Bot Status" /> : (
                <motion.div className="glass-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                        <Activity size={20} /> Bot Status
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                        {botStatus && Object.entries(botStatus).slice(0, 8).map(([key, val]) => (
                            <div key={key} style={{ padding: '12px', borderRadius: '8px', background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.1)' }}>
                                <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>{key.replace(/_/g, ' ')}</div>
                                <div style={{ fontSize: '16px', fontWeight: 600, color: '#e2e8f0', marginTop: '4px' }}>{String(val)}</div>
                            </div>
                        ))}
                        {!botStatus && (
                            <div style={{ padding: '20px', color: '#94a3b8', gridColumn: '1 / -1', textAlign: 'center' }}>
                                Bot status data not available — bot may not be running
                            </div>
                        )}
                    </div>
                </motion.div>
            )}

            {/* Learning Top Strategies in Bot Tab */}
            {learningStats?.strategies && learningStats.strategies.length > 0 && (
                <motion.div className="glass-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                        <TrendingUp size={20} /> Top Strategies
                    </h3>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                            <thead>
                                <tr style={{ color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase' }}>
                                    <th style={{ padding: '8px', textAlign: 'left' }}>#</th>
                                    <th style={{ padding: '8px', textAlign: 'right' }}>Score</th>
                                    <th style={{ padding: '8px', textAlign: 'right' }}>Win Rate</th>
                                    <th style={{ padding: '8px', textAlign: 'right' }}>ROI</th>
                                    <th style={{ padding: '8px', textAlign: 'center' }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {learningStats.strategies.slice(0, 5).map((s: any, i: number) => (
                                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                        <td style={{ padding: '10px 8px', color: i === 0 ? '#f59e0b' : '#e2e8f0', fontWeight: i === 0 ? 700 : 400 }}>
                                            {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
                                        </td>
                                        <td style={{ padding: '10px 8px', textAlign: 'right', color: '#06b6d4', fontWeight: 700 }}>
                                            {s.score?.toFixed(1)}
                                        </td>
                                        <td style={{ padding: '10px 8px', textAlign: 'right', color: (s.metrics?.win_rate || 0) > 60 ? '#10b981' : '#e2e8f0' }}>
                                            {s.metrics?.win_rate?.toFixed(1) || '0'}%
                                        </td>
                                        <td style={{ padding: '10px 8px', textAlign: 'right', color: (s.metrics?.roi || 0) > 0 ? '#10b981' : '#ef4444' }}>
                                            {s.metrics?.roi > 0 ? '+' : ''}{s.metrics?.roi?.toFixed(2) || '0'}%
                                        </td>
                                        <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                                            {s.applied ? (
                                                <span style={{ color: '#10b981', fontSize: '11px', fontWeight: 600, padding: '2px 8px', background: 'rgba(16,185,129,0.1)', borderRadius: '4px' }}>Active</span>
                                            ) : '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </motion.div>
            )}
        </div>
    );

    const renderLogs = () => (
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#e2e8f0', margin: 0 }}>
                    <Terminal size={20} /> Live Logs
                </h3>
                <button onClick={fetchLogs} style={{ padding: '6px 12px', borderRadius: '6px', background: 'rgba(139,92,246,0.2)', border: '1px solid rgba(139,92,246,0.3)', color: '#a78bfa', cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <RefreshCw size={14} /> Refresh
                </button>
            </div>
            {loadingLogs ? <SectionLoader label="Logs" /> : (
                <div style={{
                    background: '#0f172a', borderRadius: '8px', padding: '16px', fontFamily: 'monospace', fontSize: '12px',
                    maxHeight: '600px', overflowY: 'auto', border: '1px solid rgba(51,65,85,0.5)', lineHeight: '1.8'
                }}>
                    {logs.length > 0 ? logs.map((line, i) => (
                        <div key={i} style={{
                            color: line.includes('ERR') || line.includes('FAIL') || line.includes('❌') ? '#ef4444' :
                                   line.includes('WARN') || line.includes('⚠') ? '#f59e0b' :
                                   line.includes('BUY') || line.includes('SELL') || line.includes('✅') ? '#10b981' :
                                   line.includes('ML') || line.includes('🧠') || line.includes('🏆') ? '#a78bfa' :
                                   line.includes('📊') || line.includes('📈') ? '#06b6d4' : '#94a3b8',
                            borderBottom: '1px solid rgba(51,65,85,0.2)', paddingBottom: '2px'
                        }}>
                            {line}
                        </div>
                    )) : (
                        <div style={{ color: '#64748b', textAlign: 'center', padding: '40px' }}>No logs available</div>
                    )}
                </div>
            )}
        </motion.div>
    );

    const renderRevenue = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {loadingRevenue ? <SectionLoader label="Revenue" /> : (
                <div className="admin-stats-grid">
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon revenue"><DollarSign size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">${revenue?.mrr?.toFixed(2) || '0.00'}</span>
                            <span className="stat-label">Monthly Recurring Revenue</span>
                        </div>
                    </motion.div>
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon active"><UserCheck size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">{revenue?.active_subscriptions || 0}</span>
                            <span className="stat-label">Active Subscriptions</span>
                        </div>
                    </motion.div>
                    <motion.div className="glass-card stat-card" whileHover={{ scale: 1.02 }}>
                        <div className="stat-icon trading"><Zap size={24} /></div>
                        <div className="stat-content">
                            <span className="stat-value">{analytics?.users_with_api_keys || 0}</span>
                            <span className="stat-label">Paying Traders</span>
                        </div>
                    </motion.div>
                </div>
            )}
            {revenue?.status === 'warning' && (
                <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    style={{ padding: '20px', borderLeft: '3px solid #f59e0b' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f59e0b', fontSize: '14px' }}>
                        <AlertTriangle size={18} />
                        <span>Stripe not configured — revenue tracking is disabled. Set STRIPE_SECRET_KEY to enable.</span>
                    </div>
                </motion.div>
            )}
        </div>
    );

    const renderDatabase = () => (
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                <Database size={20} /> Database
            </h3>
            {loadingHealth ? <SectionLoader label="Database" /> : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                    <div style={{ padding: '20px', borderRadius: '12px', background: 'rgba(6,182,212,0.05)', border: '1px solid rgba(6,182,212,0.15)' }}>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Type</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: '#06b6d4' }}>{systemHealth?.services?.database?.type || 'PostgreSQL'}</div>
                    </div>
                    <div style={{ padding: '20px', borderRadius: '12px', background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Status</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: '#10b981' }}>
                            {systemHealth?.services?.database?.status === 'healthy' ? '● Connected' : '● Disconnected'}
                        </div>
                    </div>
                    <div style={{ padding: '20px', borderRadius: '12px', background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.15)' }}>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Users</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: '#a78bfa' }}>{analytics?.total_users || 0}</div>
                    </div>
                    <div style={{ padding: '20px', borderRadius: '12px', background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.15)' }}>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Strategies</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: '#f59e0b' }}>{learningStats?.stats?.total_tested?.toLocaleString() || '0'}</div>
                    </div>
                </div>
            )}
        </motion.div>
    );

    const renderSettings = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                    <Settings size={20} /> Admin Settings
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div style={{ padding: '16px', borderRadius: '12px', background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.1)' }}>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>🤖 Auto-Learning</div>
                        <div style={{ fontSize: '13px', color: '#94a3b8' }}>
                            Status: <span style={{ color: '#10b981', fontWeight: 600 }}>Active</span> — The bot continuously tests new strategy parameters against real Binance data and auto-applies the best performers.
                        </div>
                    </div>
                    <div style={{ padding: '16px', borderRadius: '12px', background: 'rgba(6,182,212,0.05)', border: '1px solid rgba(6,182,212,0.1)' }}>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>📊 Strategy Scoring v8</div>
                        <div style={{ fontSize: '13px', color: '#94a3b8', lineHeight: '1.6' }}>
                            Kill Gate: WR {'<'} 55% = Score 0<br />
                            Fake Gates: WR ≥ 99.5%, WR ≥ 90% with {'<'}20 trades, WR ≥ 80% with {'<'}10 trades<br />
                            Scoring: WR×5 + ROI×100 + Tier Bonuses + PF + Sharpe - Drawdown<br />
                            Walk-Forward: 70% train / 30% test validation
                        </div>
                    </div>
                    <div style={{ padding: '16px', borderRadius: '12px', background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.1)' }}>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>🛡️ Safety Thresholds</div>
                        <div style={{ fontSize: '13px', color: '#94a3b8', lineHeight: '1.6' }}>
                            Min Score Improvement: 0.5% (v10)<br />
                            Min Win Rate: 55%<br />
                            Max Drawdown: 15%<br />
                            Min ROI: 1.0%<br />
                            WR Regression Protection: ±0.5%
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );

    const tabTitles: Record<string, string> = {
        overview: 'Admin Overview',
        users: 'User Management',
        system: 'System Health',
        bot: 'Bot Control',
        logs: 'Live Logs',
        revenue: 'Revenue & Billing',
        database: 'Database',
        settings: 'Settings',
    };

    return (
        <div className="admin-dashboard">
            <div className="page-header">
                <div className="header-content">
                    <Shield className="header-icon" size={32} />
                    <div>
                        <h1>{tabTitles[activeTab] || 'Admin Dashboard'}</h1>
                        <p style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            System Management & Monitoring
                            <span style={{ fontSize: '11px', color: '#64748b' }}>
                                Last refresh: {lastRefresh.toLocaleTimeString()}
                            </span>
                        </p>
                    </div>
                </div>
                <button onClick={fetchAll} className="refresh-btn">
                    <RefreshCw size={18} />
                    Refresh
                </button>
            </div>

            <AnimatePresence mode="wait">
                {activeTab === 'overview' && renderOverview()}
                {activeTab === 'users' && renderUsers()}
                {activeTab === 'system' && renderSystem()}
                {activeTab === 'bot' && renderBot()}
                {activeTab === 'logs' && renderLogs()}
                {activeTab === 'revenue' && renderRevenue()}
                {activeTab === 'database' && renderDatabase()}
                {activeTab === 'settings' && renderSettings()}
            </AnimatePresence>
        </div>
    );
};

export default AdminDashboardView;

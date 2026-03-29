import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
    Users, Shield, DollarSign, Activity, AlertTriangle,
    Power, PlayCircle, Trash2, UserCheck, UserX, Crown,
    Server, Database, Zap, RefreshCw, Bot,
    Terminal, Cpu
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

interface Analytics {
    total_users: number;
    active_users: number;
    users_with_api_keys: number;
}

interface Revenue {
    mrr: number;
    active_subscriptions: number;
    status: string;
}

interface SystemHealth {
    services: {
        database?: { status: string; type?: string };
        api?: { status: string };
        redis?: { status: string };
    };
    emergency_stop_active: boolean;
}

interface AdminDashboardProps {
    activeTab?: string;
}

const AdminDashboardView = ({ activeTab = 'overview' }: AdminDashboardProps) => {
    const [users, setUsers] = useState<User[]>([]);
    const [analytics, setAnalytics] = useState<Analytics | null>(null);
    const [revenue, setRevenue] = useState<Revenue | null>(null);
    const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
    const [emergencyActive, setEmergencyActive] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [botStatus, setBotStatus] = useState<any>(null);

    const getToken = () => localStorage.getItem('auth_token') || localStorage.getItem('token');

    const fetchData = async () => {
        const token = getToken();
        if (!token) {
            setError('Not authenticated');
            return;
        }

        try {
            const headers = { 'Authorization': `Bearer ${token}` };

            const [usersRes, analyticsRes, revenueRes, healthRes, emergencyRes] = await Promise.all([
                fetch(`${API_URL}/api/admin/users`, { headers }),
                fetch(`${API_URL}/api/admin/analytics`, { headers }),
                fetch(`${API_URL}/api/admin/revenue`, { headers }),
                fetch(`${API_URL}/api/admin/system/health`, { headers }),
                fetch(`${API_URL}/api/admin/emergency/status`, { headers })
            ]);

            if (usersRes.ok) {
                const data = await usersRes.json();
                setUsers(data.users || []);
            }
            if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
            if (revenueRes.ok) setRevenue(await revenueRes.json());
            if (healthRes.ok) setSystemHealth(await healthRes.json());
            if (emergencyRes.ok) {
                const data = await emergencyRes.json();
                setEmergencyActive(data.trading_stopped);
            }

            // Fetch bot status
            try {
                const statusRes = await fetch(`${API_URL}/api/status`, { headers });
                if (statusRes.ok) setBotStatus(await statusRes.json());
            } catch { /* ignore */ }

            // Fetch logs
            try {
                const logsRes = await fetch(`${API_URL}/api/logs?lines=50`, { headers });
                if (logsRes.ok) {
                    const data = await logsRes.json();
                    setLogs(data.logs || data.lines || []);
                }
            } catch { /* ignore */ }

            setLoading(false);
        } catch (err) {
            setError('Failed to fetch admin data');
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    const toggleEmergency = async () => {
        const token = getToken();
        const endpoint = emergencyActive ? 'resume' : 'stop-all';

        try {
            const res = await fetch(`${API_URL}/api/admin/emergency/${endpoint}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setEmergencyActive(data.trading_stopped);
            }
        } catch (err) {
            console.error('Emergency toggle failed:', err);
        }
    };

    const toggleUser = async (userId: number) => {
        const token = getToken();
        try {
            const res = await fetch(`${API_URL}/api/admin/users/${userId}/toggle`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) fetchData();
        } catch (err) {
            console.error('Toggle user failed:', err);
        }
    };

    const deleteUser = async (userId: number) => {
        if (!confirm('Are you sure you want to delete this user?')) return;
        const token = getToken();
        try {
            await fetch(`${API_URL}/api/admin/users/${userId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            fetchData();
        } catch (err) {
            console.error('Delete user failed:', err);
        }
    };

    if (loading) {
        return (
            <div className="loading-container">
                <div className="loading-spinner" />
                <p>Loading Admin Dashboard...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="error-container">
                <AlertTriangle size={48} />
                <h2>Access Denied</h2>
                <p>{error}</p>
            </div>
        );
    }

    // ========== TAB RENDERERS ==========

    const renderOverview = () => (
        <>
            {/* Emergency Control */}
            <motion.div
                className={`emergency-control ${emergencyActive ? 'active' : ''}`}
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
            >
                <div className="emergency-status">
                    <AlertTriangle size={24} />
                    <span>{emergencyActive ? '🚨 EMERGENCY STOP ACTIVE' : '✅ Trading Active'}</span>
                </div>
                <button
                    onClick={toggleEmergency}
                    className={`emergency-btn ${emergencyActive ? 'resume' : 'stop'}`}
                >
                    {emergencyActive ? (
                        <><PlayCircle size={18} /> Resume Trading</>
                    ) : (
                        <><Power size={18} /> Emergency Stop</>
                    )}
                </button>
            </motion.div>

            {/* Stats Grid */}
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

            {/* System Health */}
            <motion.div className="glass-card health-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <h3><Server size={20} /> System Health</h3>
                <div className="health-grid">
                    <div className={`health-item ${systemHealth?.services?.database?.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                        <Database size={18} />
                        <span>Database</span>
                        <span className="health-status">{systemHealth?.services?.database?.status || 'unknown'}</span>
                    </div>
                    <div className={`health-item ${systemHealth?.services?.api?.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                        <Activity size={18} />
                        <span>API</span>
                        <span className="health-status">{systemHealth?.services?.api?.status || 'unknown'}</span>
                    </div>
                    <div className="health-item">
                        <AlertTriangle size={18} />
                        <span>Emergency</span>
                        <span className="health-status">{systemHealth?.emergency_stop_active ? 'STOPPED' : 'OK'}</span>
                    </div>
                </div>
            </motion.div>
        </>
    );

    const renderUsers = () => (
        <motion.div className="glass-card users-table-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <h3><Users size={20} /> User Management ({users.length} users)</h3>
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
                                        <button
                                            onClick={() => toggleUser(user.id)}
                                            className={`action-btn ${user.active ? 'disable' : 'enable'}`}
                                            title={user.active ? 'Disable User' : 'Enable User'}
                                        >
                                            {user.active ? <UserX size={16} /> : <UserCheck size={16} />}
                                        </button>
                                        {user.role !== 'admin' && (
                                            <button
                                                onClick={() => deleteUser(user.id)}
                                                className="action-btn delete"
                                                title="Delete User"
                                            >
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
        </motion.div>
    );

    const renderSystem = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
                </div>
            </motion.div>
        </div>
    );

    const renderLogs = () => (
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#e2e8f0', margin: 0 }}>
                    <Terminal size={20} /> Live Logs
                </h3>
                <button onClick={fetchData} style={{ padding: '6px 12px', borderRadius: '6px', background: 'rgba(139,92,246,0.2)', border: '1px solid rgba(139,92,246,0.3)', color: '#a78bfa', cursor: 'pointer', fontSize: '12px' }}>
                    <RefreshCw size={14} style={{ display: 'inline', marginRight: '4px' }} /> Refresh
                </button>
            </div>
            <div style={{
                background: '#0f172a', borderRadius: '8px', padding: '16px', fontFamily: 'monospace', fontSize: '12px',
                maxHeight: '600px', overflowY: 'auto', border: '1px solid rgba(51,65,85,0.5)', lineHeight: '1.8'
            }}>
                {logs.length > 0 ? logs.map((line, i) => (
                    <div key={i} style={{
                        color: line.includes('ERR') || line.includes('FAIL') ? '#ef4444' :
                               line.includes('WARN') ? '#f59e0b' :
                               line.includes('BUY') || line.includes('SELL') ? '#10b981' :
                               line.includes('ML') ? '#a78bfa' : '#94a3b8',
                        borderBottom: '1px solid rgba(51,65,85,0.2)', paddingBottom: '2px'
                    }}>
                        {line}
                    </div>
                )) : (
                    <div style={{ color: '#64748b', textAlign: 'center', padding: '40px' }}>No logs available</div>
                )}
            </div>
        </motion.div>
    );

    const renderRevenue = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
        </div>
    );

    const renderDatabase = () => (
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', color: '#e2e8f0' }}>
                <Database size={20} /> Database
            </h3>
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
            </div>
        </motion.div>
    );

    const tabTitles: Record<string, string> = {
        overview: 'Admin Overview',
        users: 'User Management',
        system: 'System Health',
        bot: 'Bot Control',
        logs: 'Live Logs',
        revenue: 'Revenue & Billing',
        database: 'Database',
    };

    return (
        <div className="admin-dashboard">
            <div className="page-header">
                <div className="header-content">
                    <Shield className="header-icon" size={32} />
                    <div>
                        <h1>{tabTitles[activeTab] || 'Admin Dashboard'}</h1>
                        <p>System Management & Monitoring</p>
                    </div>
                </div>
                <button onClick={fetchData} className="refresh-btn">
                    <RefreshCw size={18} />
                    Refresh
                </button>
            </div>

            {activeTab === 'overview' && renderOverview()}
            {activeTab === 'users' && renderUsers()}
            {activeTab === 'system' && renderSystem()}
            {activeTab === 'bot' && renderBot()}
            {activeTab === 'logs' && renderLogs()}
            {activeTab === 'revenue' && renderRevenue()}
            {activeTab === 'database' && renderDatabase()}

            {/* Show users table on overview too */}
            {activeTab === 'overview' && renderUsers()}
        </div>
    );
};

export default AdminDashboardView;


import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
    Users, Shield, DollarSign, Activity, AlertTriangle,
    Power, PlayCircle, Trash2, UserCheck, UserX, Crown,
    Server, Database, Zap, RefreshCw
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

const AdminDashboardView = () => {
    const [users, setUsers] = useState<User[]>([]);
    const [analytics, setAnalytics] = useState<Analytics | null>(null);
    const [revenue, setRevenue] = useState<Revenue | null>(null);
    const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
    const [emergencyActive, setEmergencyActive] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

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

    return (
        <div className="admin-dashboard">
            <div className="page-header">
                <div className="header-content">
                    <Shield className="header-icon" size={32} />
                    <div>
                        <h1>Admin Dashboard</h1>
                        <p>System Management & Monitoring</p>
                    </div>
                </div>
                <button onClick={fetchData} className="refresh-btn">
                    <RefreshCw size={18} />
                    Refresh
                </button>
            </div>

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
            <motion.div
                className="glass-card health-card"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
            >
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

            {/* Users Table */}
            <motion.div
                className="glass-card users-table-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
            >
                <h3><Users size={20} /> User Management</h3>
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
        </div>
    );
};

export default AdminDashboardView;

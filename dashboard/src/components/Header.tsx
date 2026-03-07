import { useState } from 'react'
import { Bell, User, Settings, LogOut, TrendingUp } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import { LanguageSwitcher } from '../contexts/LanguageContext'
import { useAuth } from '../contexts/AuthContext'
import '../styles/premium.css'
import '../styles/components.css'

interface Notification {
    id: string
    type: 'trade' | 'alert' | 'info'
    title: string
    message: string
    timestamp: string
    read: boolean
}

interface HeaderProps {
    onSettingsClick?: () => void
}

const Header = ({ onSettingsClick }: HeaderProps) => {
    const { logout } = useAuth()
    const [showNotifications, setShowNotifications] = useState(false)
    const [showUserMenu, setShowUserMenu] = useState(false)
    const [notifications, setNotifications] = useState<Notification[]>([
        {
            id: '1',
            type: 'trade',
            title: 'Trade Executed',
            message: 'BUY 0.15 ETH @ $3,230.12',
            timestamp: '2 min ago',
            read: false
        },
        {
            id: '2',
            type: 'alert',
            title: 'Daily Target Reached',
            message: 'Congratulations! You hit 1% daily target',
            timestamp: '1 hour ago',
            read: false
        },
        {
            id: '3',
            type: 'info',
            title: 'Bot Optimized',
            message: 'Parameters adjusted for better performance',
            timestamp: '3 hours ago',
            read: true
        }
    ])

    const unreadCount = notifications.filter(n => !n.read).length

    const markAllAsRead = () => {
        setNotifications(notifications.map(n => ({ ...n, read: true })))
    }

    const getNotificationIcon = (type: string) => {
        switch (type) {
            case 'trade':
                return '💰'
            case 'alert':
                return '🎯'
            case 'info':
                return 'ℹ️'
            default:
                return '📢'
        }
    }

    return (
        <header className="header-container">
            <div className="header-content">
                {/* Logo */}
                <div className="header-logo">
                    <div className="logo-icon">
                        <TrendingUp size={24} />
                    </div>
                    <span className="logo-text">ETH Trading Bot</span>
                </div>

                {/* Right Side */}
                <div className="header-actions">
                    {/* Language Switcher */}
                    <LanguageSwitcher />

                    {/* Theme Toggle */}
                    <ThemeToggle />

                    {/* Notification Bell */}
                    <div className="header-action-item">
                        <button
                            className="icon-button"
                            onClick={() => setShowNotifications(!showNotifications)}
                        >
                            <Bell size={20} />
                            {unreadCount > 0 && (
                                <span className="notification-badge">{unreadCount}</span>
                            )}
                        </button>

                        {/* Notifications Dropdown */}
                        {showNotifications && (
                            <div className="dropdown-menu notifications-menu">
                                <div className="dropdown-header">
                                    <h3>Notifications</h3>
                                    {unreadCount > 0 && (
                                        <button className="text-button" onClick={markAllAsRead}>
                                            Mark all as read
                                        </button>
                                    )}
                                </div>

                                <div className="notifications-list">
                                    {notifications.length === 0 ? (
                                        <div className="empty-state">
                                            <Bell size={40} opacity={0.3} />
                                            <p>No notifications</p>
                                        </div>
                                    ) : (
                                        notifications.map((notif) => (
                                            <div
                                                key={notif.id}
                                                className={`notification-item ${!notif.read ? 'unread' : ''}`}
                                            >
                                                <div className="notification-icon">
                                                    {getNotificationIcon(notif.type)}
                                                </div>
                                                <div className="notification-content">
                                                    <h4>{notif.title}</h4>
                                                    <p>{notif.message}</p>
                                                    <span className="notification-time">{notif.timestamp}</span>
                                                </div>
                                                {!notif.read && <div className="unread-dot" />}
                                            </div>
                                        ))
                                    )}
                                </div>

                                <div className="dropdown-footer">
                                    <button className="text-button">View all notifications</button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* User Profile */}
                    <div className="header-action-item">
                        <button
                            className="icon-button user-button"
                            onClick={() => setShowUserMenu(!showUserMenu)}
                        >
                            <User size={20} />
                        </button>

                        {/* User Menu Dropdown */}
                        {showUserMenu && (
                            <div className="dropdown-menu user-menu">
                                <div className="user-info">
                                    <div className="user-avatar">
                                        <User size={24} />
                                    </div>
                                    <div className="user-details">
                                        <h4>Trading Account</h4>
                                        <p>Paper Trading Mode</p>
                                    </div>
                                </div>

                                <div className="menu-divider" />

                                <div className="menu-items">
                                    <button className="menu-item" onClick={onSettingsClick}>
                                        <Settings size={18} />
                                        <span>Settings</span>
                                    </button>
                                    <button className="menu-item">
                                        <TrendingUp size={18} />
                                        <span>Performance</span>
                                    </button>
                                    <button className="menu-item danger" onClick={() => { logout(); setShowUserMenu(false) }}>
                                        <LogOut size={18} />
                                        <span>Logout</span>
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

        </header>
    )
}

export default Header

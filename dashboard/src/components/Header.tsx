import { useState } from 'react'
import { Bell, User, Settings, LogOut, TrendingUp } from 'lucide-react'
import '../styles/premium.css'

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
                                    <button className="menu-item danger">
                                        <LogOut size={18} />
                                        <span>Logout</span>
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <style jsx>{`
        .header-container {
          position: sticky;
          top: 0;
          z-index: 100;
          background: var(--glass-bg);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border-bottom: 1px solid var(--glass-border);
        }

        .header-content {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 24px;
          max-width: 1920px;
          margin: 0 auto;
        }

        .header-logo {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .logo-icon {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--gradient-primary);
          border-radius: 12px;
          color: white;
        }

        .logo-text {
          font-size: 18px;
          font-weight: 700;
          background: var(--gradient-primary);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .header-action-item {
          position: relative;
        }

        .icon-button {
          position: relative;
          width: 44px;
          height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(139, 92, 246, 0.1);
          border: 1px solid rgba(139, 92, 246, 0.2);
          border-radius: 12px;
          color: var(--text-primary);
          cursor: pointer;
          transition: all 0.3s ease;
        }

        .icon-button:hover {
          background: rgba(139, 92, 246, 0.2);
          border-color: rgba(139, 92, 246, 0.4);
          transform: translateY(-2px);
        }

        .notification-badge {
          position: absolute;
          top: -4px;
          right: -4px;
          width: 20px;
          height: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--gradient-gold);
          border-radius: 50%;
          font-size: 11px;
          font-weight: 700;
          color: white;
          border: 2px solid var(--bg-primary);
        }

        .dropdown-menu {
          position: absolute;
          top: calc(100% + 8px);
          right: 0;
          width: 360px;
          background: var(--glass-bg);
          backdrop-filter: blur(20px);
          border: 1px solid var(--glass-border);
          border-radius: 16px;
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
          animation: fadeIn 0.2s ease-out;
        }

        .dropdown-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px;
          border-bottom: 1px solid var(--glass-border);
        }

        .dropdown-header h3 {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .text-button {
          background: none;
          border: none;
          color: var(--primary-purple);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: color 0.2s;
        }

        .text-button:hover {
          color: var(--primary-pink);
        }

        .notifications-list {
          max-height: 400px;
          overflow-y: auto;
        }

        .notification-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 16px;
          border-bottom: 1px solid rgba(139, 92, 246, 0.1);
          cursor: pointer;
          transition: background 0.2s;
        }

        .notification-item:hover {
          background: rgba(139, 92, 246, 0.05);
        }

        .notification-item.unread {
          background: rgba(139, 92, 246, 0.08);
        }

        .notification-icon {
          font-size: 24px;
          flex-shrink: 0;
        }

        .notification-content {
          flex: 1;
        }

        .notification-content h4 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin-bottom: 4px;
        }

        .notification-content p {
          font-size: 13px;
          color: var(--text-secondary);
          margin-bottom: 4px;
        }

        .notification-time {
          font-size: 12px;
          color: var(--text-muted);
        }

        .unread-dot {
          width: 8px;
          height: 8px;
          background: var(--primary-purple);
          border-radius: 50%;
          flex-shrink: 0;
          margin-top: 6px;
        }

        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 48px 24px;
          color: var(--text-muted);
        }

        .empty-state p {
          margin-top: 12px;
          font-size: 14px;
        }

        .dropdown-footer {
          padding: 12px 16px;
          border-top: 1px solid var(--glass-border);
          text-align: center;
        }

        .user-menu {
          width: 280px;
        }

        .user-info {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px;
        }

        .user-avatar {
          width: 48px;
          height: 48px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--gradient-primary);
          border-radius: 50%;
          color: white;
        }

        .user-details h4 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin-bottom: 4px;
        }

        .user-details p {
          font-size: 12px;
          color: var(--text-secondary);
        }

        .menu-divider {
          height: 1px;
          background: var(--glass-border);
          margin: 0 16px;
        }

        .menu-items {
          padding: 8px;
        }

        .menu-item {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          background: none;
          border: none;
          border-radius: 8px;
          color: var(--text-primary);
          font-size: 14px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .menu-item:hover {
          background: rgba(139, 92, 246, 0.1);
        }

        .menu-item.danger {
          color: var(--error);
        }

        .menu-item.danger:hover {
          background: rgba(239, 68, 68, 0.1);
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
        </header>
    )
}

export default Header

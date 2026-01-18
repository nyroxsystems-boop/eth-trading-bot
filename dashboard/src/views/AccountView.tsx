import { useState } from 'react'
import { Users, Crown, Settings } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import '../styles/premium.css'

// Import existing views
import AccountsView from './AccountsView'
import SubscriptionView from './SubscriptionView'
import SettingsView from './SettingsView'

type TabType = 'accounts' | 'subscription' | 'settings'

const AccountView = () => {
    const [activeTab, setActiveTab] = useState<TabType>('accounts')

    const tabs = [
        { id: 'accounts' as TabType, label: 'Accounts', icon: Users },
        { id: 'subscription' as TabType, label: 'Subscription', icon: Crown },
        { id: 'settings' as TabType, label: 'Settings', icon: Settings },
    ]

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ padding: '24px' }}
        >
            {/* Tab Navigation */}
            <div style={{
                display: 'flex',
                gap: '8px',
                marginBottom: '24px',
                padding: '6px',
                background: 'var(--bg-tertiary)',
                borderRadius: '14px',
                width: 'fit-content'
            }}>
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '12px 20px',
                            background: activeTab === tab.id ? 'var(--glass-bg)' : 'transparent',
                            border: 'none',
                            borderRadius: '10px',
                            color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
                            fontSize: '14px',
                            fontWeight: 500,
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                            boxShadow: activeTab === tab.id ? '0 2px 8px rgba(0,0,0,0.15)' : 'none'
                        }}
                    >
                        <tab.icon size={18} />
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <AnimatePresence mode="wait">
                <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.2 }}
                >
                    {activeTab === 'accounts' && <AccountsView />}
                    {activeTab === 'subscription' && <SubscriptionView />}
                    {activeTab === 'settings' && <SettingsView />}
                </motion.div>
            </AnimatePresence>
        </motion.div>
    )
}

export default AccountView

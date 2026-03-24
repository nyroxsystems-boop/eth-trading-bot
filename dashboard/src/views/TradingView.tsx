import { useState } from 'react'
import { Bot, Beaker } from 'lucide-react'
import { motion } from 'framer-motion'
import '../styles/premium.css'

// Import existing views
import BotsView from './BotsView'
import StrategyLabView from './StrategyLabView'

type TabType = 'bots' | 'strategy'

const TradingView = () => {
    const [activeTab, setActiveTab] = useState<TabType>('bots')

    const tabs = [
        { id: 'bots' as TabType, label: 'Bots', icon: Bot },
        { id: 'strategy' as TabType, label: 'Strategy Lab', icon: Beaker },
    ]

    return (
        <div style={{ padding: '24px' }}>
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
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
            <div key={activeTab}>
                {activeTab === 'bots' && <BotsView />}
                {activeTab === 'strategy' && <StrategyLabView />}
            </div>
        </motion.div>
        </div>
    )
}

export default TradingView

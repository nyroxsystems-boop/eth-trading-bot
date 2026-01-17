import { motion } from 'framer-motion'
import MultiPairPortfolio from '../components/MultiPairPortfolio'
import '../styles/premium.css'

export default function PortfolioView() {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}
        >
            {/* Header */}
            <div style={{ marginBottom: '24px' }}>
                <h1 style={{
                    fontSize: '32px',
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    marginBottom: '8px'
                }}>
                    📊 My Trading Portfolio
                </h1>
                <p style={{ color: '#94A3B8', fontSize: '16px' }}>
                    Manage your trading pairs with individual settings for each
                </p>
            </div>

            {/* Multi-Pair Portfolio Component */}
            <MultiPairPortfolio />
        </motion.div>
    )
}

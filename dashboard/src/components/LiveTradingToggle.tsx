import React, { useState } from 'react'
import './LiveTradingToggle.css'

interface LiveTradingToggleProps {
    currentMode: 'paper' | 'live'
    canEnableLive: boolean
    requiresUpgrade: boolean
    onToggle: () => Promise<void>
    onUpgrade: () => void
}

export const LiveTradingToggle: React.FC<LiveTradingToggleProps> = ({
    currentMode,
    canEnableLive,
    requiresUpgrade,
    onToggle,
    onUpgrade
}) => {
    const [showConfirmModal, setShowConfirmModal] = useState(false)
    const [understood, setUnderstood] = useState(false)
    const [loading, setLoading] = useState(false)

    const handleToggleClick = () => {
        if (currentMode === 'paper') {
            // Switching to LIVE - show confirmation
            if (requiresUpgrade) {
                onUpgrade()
                return
            }
            if (!canEnableLive) {
                alert('Complete a 30-day test phase before enabling live trading')
                return
            }
            setShowConfirmModal(true)
        } else {
            // Switching to PAPER - no confirmation needed
            handleConfirm()
        }
    }

    const handleConfirm = async () => {
        setLoading(true)
        try {
            await onToggle()
            setShowConfirmModal(false)
            setUnderstood(false)
        } catch (error) {
            console.error('Failed to toggle mode:', error)
            alert('Failed to switch trading mode. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    return (
        <>
            <div className="live-trading-toggle">
                <div className="toggle-header">
                    <h3>Trading Mode</h3>
                    <span className={`mode-badge ${currentMode}`}>
                        {currentMode === 'paper' ? '📄 PAPER TRADING' : '💰 LIVE TRADING'}
                    </span>
                </div>

                <div className="toggle-description">
                    {currentMode === 'paper' ? (
                        <p>
                            <strong>Paper Trading Mode:</strong> All trades are simulated. No real money is used.
                            {canEnableLive && !requiresUpgrade && (
                                <span className="ready-badge">✅ Ready for Live Trading</span>
                            )}
                        </p>
                    ) : (
                        <p className="warning">
                            <strong>⚠️ Live Trading Active:</strong> Real money is being used for trades!
                        </p>
                    )}
                </div>

                <div className="toggle-control">
                    <label className="switch">
                        <input
                            type="checkbox"
                            checked={currentMode === 'live'}
                            onChange={handleToggleClick}
                            disabled={loading}
                        />
                        <span className="slider"></span>
                    </label>
                    <span className="toggle-label">
                        {currentMode === 'paper' ? 'Enable Live Trading' : 'Switch to Paper Trading'}
                    </span>
                </div>

                {requiresUpgrade && currentMode === 'paper' && (
                    <div className="upgrade-prompt">
                        <p>🔒 Live trading requires Premium subscription</p>
                        <button onClick={onUpgrade} className="upgrade-button">
                            Upgrade to Premium
                        </button>
                    </div>
                )}
            </div>

            {/* Confirmation Modal */}
            {showConfirmModal && (
                <div className="modal-overlay" onClick={() => !loading && setShowConfirmModal(false)}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>⚠️ Enable Live Trading?</h2>
                        </div>

                        <div className="modal-body">
                            <div className="warning-box">
                                <p><strong>You are about to enable LIVE trading with REAL money!</strong></p>
                                <ul>
                                    <li>Real funds will be used for trades</li>
                                    <li>You can lose money</li>
                                    <li>Past performance does not guarantee future results</li>
                                    <li>Always trade responsibly</li>
                                </ul>
                            </div>

                            <label className="checkbox-label">
                                <input
                                    type="checkbox"
                                    checked={understood}
                                    onChange={(e) => setUnderstood(e.target.checked)}
                                    disabled={loading}
                                />
                                <span>I understand the risks and want to proceed</span>
                            </label>
                        </div>

                        <div className="modal-footer">
                            <button
                                onClick={() => setShowConfirmModal(false)}
                                className="btn-cancel"
                                disabled={loading}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirm}
                                className="btn-confirm"
                                disabled={!understood || loading}
                            >
                                {loading ? 'Switching...' : 'Enable Live Trading'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    )
}

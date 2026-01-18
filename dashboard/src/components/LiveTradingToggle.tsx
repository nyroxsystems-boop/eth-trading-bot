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

    const handleModeSelect = (mode: 'paper' | 'live') => {
        if (mode === currentMode) return

        if (mode === 'live') {
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
            <div className="trading-mode-card">
                <div className="mode-header">
                    <span className="mode-title">Trading Mode</span>
                    {requiresUpgrade && (
                        <span className="premium-badge" onClick={onUpgrade}>
                            🔒 Premium
                        </span>
                    )}
                </div>

                {/* Segmented Control */}
                <div className="segmented-control">
                    <button
                        className={`segment ${currentMode === 'paper' ? 'active paper' : ''}`}
                        onClick={() => handleModeSelect('paper')}
                        disabled={loading}
                    >
                        <span className="segment-icon">📄</span>
                        <span className="segment-label">Paper</span>
                    </button>
                    <button
                        className={`segment ${currentMode === 'live' ? 'active live' : ''}`}
                        onClick={() => handleModeSelect('live')}
                        disabled={loading}
                    >
                        <span className="segment-icon">💰</span>
                        <span className="segment-label">Live</span>
                    </button>
                    <div className={`segment-slider ${currentMode}`}></div>
                </div>

                {/* Status Message */}
                <div className={`mode-status ${currentMode}`}>
                    {currentMode === 'paper' ? (
                        <>
                            <span className="status-dot paper"></span>
                            Simulated trading • No real funds used
                        </>
                    ) : (
                        <>
                            <span className="status-dot live"></span>
                            Real trading active • Use caution
                        </>
                    )}
                </div>

                {canEnableLive && !requiresUpgrade && currentMode === 'paper' && (
                    <div className="ready-hint">
                        ✅ Ready for live trading
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

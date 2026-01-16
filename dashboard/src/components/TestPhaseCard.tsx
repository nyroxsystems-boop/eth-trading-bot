import React from 'react'
import './TestPhaseCard.css'

interface TestPhase {
    symbol: string
    start_date: string
    days_elapsed: number
    days_remaining: number
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number
    total_pnl: number
    sharpe_ratio: number
    max_drawdown: number
    completed: boolean
    ready_for_live: boolean
    performance_score: number
}

interface TestPhaseCardProps {
    phase: TestPhase
}

export const TestPhaseCard: React.FC<TestPhaseCardProps> = ({ phase }) => {
    const progressPercent = (phase.days_elapsed / 30) * 100

    return (
        <div className="test-phase-card">
            <div className="card-header">
                <h3>{phase.symbol}</h3>
                {phase.ready_for_live && (
                    <span className="ready-badge">✅ Ready for Live</span>
                )}
                {phase.completed && !phase.ready_for_live && (
                    <span className="completed-badge">⏱️ Completed</span>
                )}
            </div>

            <div className="progress-section">
                <div className="progress-header">
                    <span>Day {phase.days_elapsed} of 30</span>
                    <span>{phase.days_remaining} days remaining</span>
                </div>
                <div className="progress-bar">
                    <div
                        className="progress-fill"
                        style={{ width: `${progressPercent}%` }}
                    />
                </div>
            </div>

            <div className="metrics-grid">
                <div className="metric">
                    <div className="metric-label">Win Rate</div>
                    <div className={`metric-value ${phase.win_rate >= 0.6 ? 'good' : 'warning'}`}>
                        {(phase.win_rate * 100).toFixed(1)}%
                    </div>
                    <div className="metric-target">Target: ≥60%</div>
                </div>

                <div className="metric">
                    <div className="metric-label">Total PnL</div>
                    <div className={`metric-value ${phase.total_pnl > 0 ? 'good' : 'bad'}`}>
                        ${phase.total_pnl.toFixed(2)}
                    </div>
                    <div className="metric-target">Target: Positive</div>
                </div>

                <div className="metric">
                    <div className="metric-label">Trades</div>
                    <div className={`metric-value ${phase.total_trades >= 20 ? 'good' : 'warning'}`}>
                        {phase.total_trades}
                    </div>
                    <div className="metric-target">Target: ≥20</div>
                </div>

                <div className="metric">
                    <div className="metric-label">Sharpe Ratio</div>
                    <div className={`metric-value ${phase.sharpe_ratio >= 1.0 ? 'good' : 'warning'}`}>
                        {phase.sharpe_ratio.toFixed(2)}
                    </div>
                    <div className="metric-target">Target: ≥1.0</div>
                </div>
            </div>

            <div className="performance-score">
                <div className="score-label">Performance Score</div>
                <div className="score-bar">
                    <div
                        className={`score-fill ${phase.performance_score >= 70 ? 'excellent' : phase.performance_score >= 50 ? 'good' : 'poor'}`}
                        style={{ width: `${phase.performance_score}%` }}
                    >
                        <span>{phase.performance_score.toFixed(0)}/100</span>
                    </div>
                </div>
            </div>

            <div className="trade-stats">
                <span className="stat-item win">{phase.winning_trades} Wins</span>
                <span className="stat-item loss">{phase.losing_trades} Losses</span>
                <span className="stat-item">Max DD: {(phase.max_drawdown * 100).toFixed(1)}%</span>
            </div>
        </div>
    )
}

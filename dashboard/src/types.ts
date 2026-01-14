export interface Trade {
    timestamp: string
    action: string
    qty: number
    price: number
    pnl?: number
}

export interface Metrics {
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number
    total_pnl: number
    daily_pnl: number
    avg_win: number
    avg_loss: number
    sharpe_ratio: number
    max_drawdown: number
    roi: number
}

export interface BotStatus {
    is_running: boolean
    today_trades: number
    ml_confidence: number
    sentiment_score: number
    regime: string
    last_update: string
}

export interface CandleData {
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

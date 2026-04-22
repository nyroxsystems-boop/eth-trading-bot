import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Shield, Bell, Sliders } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

export default function Settings() {
  const [config, setConfig] = useState({
    pair: 'Dynamic',
    interval: '5m',
    paper_mode: true,
    risk_per_trade: 1.0,
    tp_min: 1.5,
    tp_max: 2.5,
    stop_floor: 1.2,
    max_trades_per_day: 15,
    entry_score_min: 0.20,
    rsi_min: 30,
    rsi_max: 75,
    use_ml: true,
    ml_threshold: 0.52,
    loop_sleep_seconds: 120,
  })

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v3/config`)
      if (res.ok) setConfig(await res.json())
    } catch {}
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-title">Settings</div>
        <div className="page-subtitle">Bot configuration & parameters</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* Trading Parameters */}
        <div className="card animate-in">
          <div className="settings-title">
            <Sliders size={18} color="var(--accent)" />
            Trading Parameters
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Trading Pairs</div>
              <div className="setting-desc">Dynamic top-volume selection</div>
            </div>
            <div className="setting-value" style={{ color: 'var(--accent)' }}>
              {config.pair === 'Dynamic' || config.pair?.includes('Pairs') ? '🔄 Auto-Scan' : config.pair}
            </div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Interval</div>
              <div className="setting-desc">Candle timeframe</div>
            </div>
            <div className="setting-value">{config.interval}</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Mode</div>
              <div className="setting-desc">Paper or Live trading</div>
            </div>
            <span className={`badge ${config.paper_mode ? 'badge-active' : 'badge-pending'}`}>
              {config.paper_mode ? 'Paper' : 'Live'}
            </span>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Max Trades/Day</div>
              <div className="setting-desc">Daily trade limit</div>
            </div>
            <div className="setting-value">{config.max_trades_per_day}</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Loop Sleep</div>
              <div className="setting-desc">Seconds between scans</div>
            </div>
            <div className="setting-value">{config.loop_sleep_seconds}s</div>
          </div>
        </div>

        {/* Risk Management */}
        <div className="card animate-in">
          <div className="settings-title">
            <Shield size={18} color="var(--green)" />
            Risk Management
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Risk per Trade</div>
              <div className="setting-desc">Percentage of equity</div>
            </div>
            <div className="setting-value">{config.risk_per_trade}%</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Take Profit</div>
              <div className="setting-desc">Min-Max range</div>
            </div>
            <div className="setting-value">{config.tp_min}% – {config.tp_max}%</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Stop Loss Floor</div>
              <div className="setting-desc">Minimum SL distance</div>
            </div>
            <div className="setting-value">{config.stop_floor}%</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">RSI Range</div>
              <div className="setting-desc">Entry filter</div>
            </div>
            <div className="setting-value">{config.rsi_min} – {config.rsi_max}</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Entry Score Min</div>
              <div className="setting-desc">Minimum signal score</div>
            </div>
            <div className="setting-value">{config.entry_score_min}</div>
          </div>
        </div>

        {/* ML Settings */}
        <div className="card animate-in">
          <div className="settings-title">
            <SettingsIcon size={18} color="var(--accent-secondary)" />
            ML Configuration
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">ML Enabled</div>
              <div className="setting-desc">Use ML predictions for signals</div>
            </div>
            <span className={`badge ${config.use_ml ? 'badge-active' : 'badge-inactive'}`}>
              {config.use_ml ? 'Active' : 'Disabled'}
            </span>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">ML Threshold</div>
              <div className="setting-desc">Minimum confidence for entry</div>
            </div>
            <div className="setting-value">{(config.ml_threshold * 100).toFixed(0)}%</div>
          </div>
        </div>

        {/* System Info */}
        <div className="card animate-in">
          <div className="settings-title">
            <Bell size={18} color="var(--amber)" />
            System
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Version</div>
              <div className="setting-desc">Bot engine version</div>
            </div>
            <div className="setting-value">v3.0</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Architecture</div>
              <div className="setting-desc">Trading engine type</div>
            </div>
            <div className="setting-value">Clean Core</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Signal Engine</div>
              <div className="setting-desc">9 signal checks</div>
            </div>
            <div className="setting-value">Active</div>
          </div>
          <div className="setting-row">
            <div>
              <div className="setting-label">Guards</div>
              <div className="setting-desc">Pre-trade checks</div>
            </div>
            <div className="setting-value">3 (lean)</div>
          </div>
        </div>
      </div>
    </div>
  )
}

"""
Jarvis Anomaly Detection Module
Detects unusual patterns and behaviors in the trading system
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class AnomalyType(Enum):
    LOSS_STREAK = "loss_streak"
    HIGH_FREQUENCY = "high_frequency_trading"
    LARGE_DRAWDOWN = "large_drawdown"
    API_RATE_LIMIT = "api_rate_limit"
    UNUSUAL_VOLUME = "unusual_volume"
    PRICE_SPIKE = "price_spike"
    CONNECTION_ISSUES = "connection_issues"


@dataclass
class Anomaly:
    type: AnomalyType
    severity: str  # low, medium, high, critical
    detected_at: datetime
    details: Dict
    resolved: bool = False


class AnomalyDetector:
    """
    Detects anomalies in trading behavior and system metrics
    """
    
    def __init__(self):
        self.anomalies: List[Anomaly] = []
        self.thresholds = {
            # Trading anomalies
            "max_consecutive_losses": 5,
            "max_trades_per_minute": 3,
            "max_daily_drawdown_pct": 5.0,
            "max_single_loss_pct": 2.0,
            
            # System anomalies
            "max_api_errors_per_minute": 10,
            "max_response_time_ms": 5000,
            "min_balance_change_alert_pct": 10.0,
        }
        
        # Tracking state
        self.recent_trades: List[Dict] = []
        self.recent_api_errors: List[datetime] = []
        self.consecutive_losses = 0
        self.daily_starting_balance = 0
        self.current_balance = 0
        
        print("🔍 Jarvis Anomaly Detector initialized")
    
    def record_trade(self, trade: Dict) -> List[Anomaly]:
        """Record a trade and check for anomalies"""
        anomalies_found = []
        
        self.recent_trades.append({
            **trade,
            "timestamp": datetime.now()
        })
        
        # Keep only last 100 trades
        if len(self.recent_trades) > 100:
            self.recent_trades = self.recent_trades[-100:]
        
        # Check for loss streak
        if trade.get("pnl", 0) < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        if self.consecutive_losses >= self.thresholds["max_consecutive_losses"]:
            anomaly = Anomaly(
                type=AnomalyType.LOSS_STREAK,
                severity="high",
                detected_at=datetime.now(),
                details={
                    "consecutive_losses": self.consecutive_losses,
                    "threshold": self.thresholds["max_consecutive_losses"]
                }
            )
            self.anomalies.append(anomaly)
            anomalies_found.append(anomaly)
        
        # Check for high frequency trading
        one_minute_ago = datetime.now() - timedelta(minutes=1)
        recent = [t for t in self.recent_trades if t["timestamp"] > one_minute_ago]
        if len(recent) > self.thresholds["max_trades_per_minute"]:
            anomaly = Anomaly(
                type=AnomalyType.HIGH_FREQUENCY,
                severity="medium",
                detected_at=datetime.now(),
                details={
                    "trades_per_minute": len(recent),
                    "threshold": self.thresholds["max_trades_per_minute"]
                }
            )
            self.anomalies.append(anomaly)
            anomalies_found.append(anomaly)
        
        # Check for large single loss
        loss_pct = abs(trade.get("pnl_pct", 0))
        if trade.get("pnl", 0) < 0 and loss_pct > self.thresholds["max_single_loss_pct"]:
            anomaly = Anomaly(
                type=AnomalyType.LARGE_DRAWDOWN,
                severity="high",
                detected_at=datetime.now(),
                details={
                    "loss_pct": loss_pct,
                    "threshold": self.thresholds["max_single_loss_pct"],
                    "trade": trade
                }
            )
            self.anomalies.append(anomaly)
            anomalies_found.append(anomaly)
        
        return anomalies_found
    
    def record_balance(self, balance: float) -> Optional[Anomaly]:
        """Record balance and check for drawdown anomaly"""
        if self.daily_starting_balance == 0:
            self.daily_starting_balance = balance
        
        self.current_balance = balance
        
        # Calculate daily drawdown
        if self.daily_starting_balance > 0:
            drawdown_pct = ((self.daily_starting_balance - balance) / self.daily_starting_balance) * 100
            
            if drawdown_pct > self.thresholds["max_daily_drawdown_pct"]:
                anomaly = Anomaly(
                    type=AnomalyType.LARGE_DRAWDOWN,
                    severity="critical",
                    detected_at=datetime.now(),
                    details={
                        "drawdown_pct": drawdown_pct,
                        "starting_balance": self.daily_starting_balance,
                        "current_balance": balance,
                        "threshold": self.thresholds["max_daily_drawdown_pct"]
                    }
                )
                self.anomalies.append(anomaly)
                return anomaly
        
        return None
    
    def record_api_error(self) -> Optional[Anomaly]:
        """Record an API error and check for rate limiting"""
        self.recent_api_errors.append(datetime.now())
        
        # Keep only errors from last minute
        one_minute_ago = datetime.now() - timedelta(minutes=1)
        self.recent_api_errors = [e for e in self.recent_api_errors if e > one_minute_ago]
        
        if len(self.recent_api_errors) > self.thresholds["max_api_errors_per_minute"]:
            anomaly = Anomaly(
                type=AnomalyType.API_RATE_LIMIT,
                severity="high",
                detected_at=datetime.now(),
                details={
                    "errors_per_minute": len(self.recent_api_errors),
                    "threshold": self.thresholds["max_api_errors_per_minute"]
                }
            )
            self.anomalies.append(anomaly)
            return anomaly
        
        return None
    
    def check_price_spike(self, price: float, avg_price: float) -> Optional[Anomaly]:
        """Check for unusual price movements"""
        if avg_price == 0:
            return None
        
        change_pct = abs((price - avg_price) / avg_price) * 100
        
        if change_pct > 5.0:  # 5% spike
            anomaly = Anomaly(
                type=AnomalyType.PRICE_SPIKE,
                severity="medium" if change_pct < 10 else "high",
                detected_at=datetime.now(),
                details={
                    "current_price": price,
                    "avg_price": avg_price,
                    "change_pct": change_pct
                }
            )
            self.anomalies.append(anomaly)
            return anomaly
        
        return None
    
    def get_recent_anomalies(self, limit: int = 20, 
                             since: Optional[datetime] = None) -> List[Dict]:
        """Get recent anomalies"""
        anomalies = self.anomalies
        
        if since:
            anomalies = [a for a in anomalies if a.detected_at > since]
        
        return [
            {
                "type": a.type.value,
                "severity": a.severity,
                "detected_at": a.detected_at.isoformat(),
                "details": a.details,
                "resolved": a.resolved
            }
            for a in sorted(anomalies, key=lambda x: x.detected_at, reverse=True)[:limit]
        ]
    
    def get_summary(self) -> Dict:
        """Get anomaly detection summary"""
        last_hour = datetime.now() - timedelta(hours=1)
        recent = [a for a in self.anomalies if a.detected_at > last_hour]
        
        by_type = {}
        by_severity = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        
        for anomaly in recent:
            type_name = anomaly.type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
            by_severity[anomaly.severity] = by_severity.get(anomaly.severity, 0) + 1
        
        return {
            "total_anomalies_last_hour": len(recent),
            "by_type": by_type,
            "by_severity": by_severity,
            "consecutive_losses": self.consecutive_losses,
            "daily_drawdown_pct": self._calculate_daily_drawdown(),
            "thresholds": self.thresholds
        }
    
    def _calculate_daily_drawdown(self) -> float:
        """Calculate current daily drawdown percentage"""
        if self.daily_starting_balance <= 0:
            return 0.0
        return ((self.daily_starting_balance - self.current_balance) / 
                self.daily_starting_balance) * 100
    
    def reset_daily(self):
        """Reset daily tracking (call at start of each trading day)"""
        self.daily_starting_balance = self.current_balance
        self.consecutive_losses = 0
        print("🔍 Jarvis Anomaly Detector: Daily reset complete")


# Singleton instance
_detector_instance: Optional[AnomalyDetector] = None

def get_anomaly_detector() -> AnomalyDetector:
    """Get or create anomaly detector instance"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AnomalyDetector()
    return _detector_instance

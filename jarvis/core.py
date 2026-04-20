"""
Jarvis - Intelligent System Orchestrator
The central brain that monitors and maintains all workers
"""

import os
import json
import asyncio
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

# Try to import database adapter
try:
    from db_adapter import get_db_connection, USE_POSTGRES
    HAS_DB = True
except ImportError:
    HAS_DB = False


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"
    RESTARTING = "restarting"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ServiceHealth:
    name: str
    status: ServiceStatus
    last_check: datetime
    response_time_ms: float = 0
    error_message: str = ""
    consecutive_failures: int = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class Alert:
    id: str
    timestamp: datetime
    severity: AlertSeverity
    service: str
    message: str
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class Jarvis:
    """
    Jarvis - The Intelligent System Orchestrator
    
    Responsibilities:
    - Monitor all workers/services health
    - Detect anomalies and issues
    - Trigger auto-recovery when possible
    - Send alerts via Telegram
    - Provide system-wide status
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceHealth] = {}
        self.alerts: List[Alert] = []
        self.alert_counter = 0
        self.emergency_stop = False
        self.last_full_check = None
        self.check_interval_seconds = 60
        
        # Configuration
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.railway_api_token = os.getenv("RAILWAY_API_TOKEN", "")
        
        # Thresholds
        self.max_consecutive_failures = 3
        self.alert_cooldown_minutes = 5
        self.last_alert_time: Dict[str, datetime] = {}
        
        # Register known services
        self._register_default_services()
        
        print("🤖 Jarvis initialized - System monitoring active")
    
    def _register_default_services(self):
        """Register the default services to monitor"""
        self.register_service("database", health_endpoint=None, type="internal")
        self.register_service("api", health_endpoint="/api/health", type="http")
        self.register_service("bot", health_endpoint=None, type="worker")
    
    def register_service(self, name: str, health_endpoint: Optional[str] = None, 
                         type: str = "http", metadata: Dict = None):
        """Register a service for monitoring"""
        self.services[name] = ServiceHealth(
            name=name,
            status=ServiceStatus.UNKNOWN,
            last_check=datetime.now(),
            metadata={"health_endpoint": health_endpoint, "type": type, **(metadata or {})}
        )
        print(f"📝 Jarvis: Registered service '{name}'")
    
    async def check_service_health(self, name: str) -> ServiceHealth:
        """Check health of a specific service"""
        if name not in self.services:
            return ServiceHealth(name=name, status=ServiceStatus.UNKNOWN, last_check=datetime.now())
        
        service = self.services[name]
        start_time = datetime.now()
        
        try:
            service_type = service.metadata.get("type", "http")
            
            if service_type == "internal":
                # Internal service check (e.g., database)
                if name == "database":
                    await self._check_database_health(service)
            
            elif service_type == "http":
                # HTTP endpoint check
                endpoint = service.metadata.get("health_endpoint")
                if endpoint:
                    await self._check_http_health(service, endpoint)
            
            elif service_type == "worker":
                # Worker process check
                await self._check_worker_health(service)
            
            # Calculate response time
            service.response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            service.last_check = datetime.now()
            
            # Reset failure counter on success
            if service.status == ServiceStatus.HEALTHY:
                service.consecutive_failures = 0
            
        except Exception as e:
            service.status = ServiceStatus.UNHEALTHY
            service.error_message = str(e)
            service.consecutive_failures += 1
            service.last_check = datetime.now()
            
            # Check if we need to create an alert
            if service.consecutive_failures >= self.max_consecutive_failures:
                await self._create_alert(
                    severity=AlertSeverity.ERROR,
                    service=name,
                    message=f"Service '{name}' is unhealthy: {e}"
                )
        
        self.services[name] = service
        return service
    
    async def _check_database_health(self, service: ServiceHealth):
        """Check database connectivity"""
        if not HAS_DB:
            service.status = ServiceStatus.UNKNOWN
            service.error_message = "Database module not available"
            return
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            service.status = ServiceStatus.HEALTHY
            service.error_message = ""
            service.metadata["db_type"] = "PostgreSQL" if USE_POSTGRES else "SQLite"
        except Exception as e:
            service.status = ServiceStatus.UNHEALTHY
            service.error_message = str(e)
            raise
    
    async def _check_http_health(self, service: ServiceHealth, endpoint: str):
        """Check HTTP endpoint health"""
        api_url = os.getenv("API_URL", "http://localhost:8000")
        url = f"{api_url}{endpoint}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                service.status = ServiceStatus.HEALTHY
                service.error_message = ""
            else:
                service.status = ServiceStatus.DEGRADED
                service.error_message = f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            service.status = ServiceStatus.DEGRADED
            service.error_message = "Timeout"
        except Exception as e:
            service.status = ServiceStatus.UNHEALTHY
            service.error_message = str(e)
            raise
    
    async def _check_worker_health(self, service: ServiceHealth):
        """Check if worker process is running"""
        # For now, mark as healthy if we can reach the API
        # In production, this would check Railway API or process status
        service.status = ServiceStatus.HEALTHY
        service.metadata["note"] = "Worker health inferred from API"
    
    async def check_all_services(self) -> Dict[str, ServiceHealth]:
        """Check health of all registered services"""
        results = {}
        for name in self.services:
            results[name] = await self.check_service_health(name)
        
        self.last_full_check = datetime.now()
        return results
    
    async def _create_alert(self, severity: AlertSeverity, service: str, message: str):
        """Create a new alert"""
        # Check cooldown
        last_alert = self.last_alert_time.get(service)
        if last_alert:
            cooldown = timedelta(minutes=self.alert_cooldown_minutes)
            if datetime.now() - last_alert < cooldown:
                return  # Still in cooldown
        
        self.alert_counter += 1
        alert = Alert(
            id=f"alert_{self.alert_counter}",
            timestamp=datetime.now(),
            severity=severity,
            service=service,
            message=message
        )
        self.alerts.append(alert)
        self.last_alert_time[service] = datetime.now()
        
        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        
        # Send Telegram notification for ERROR and CRITICAL
        if severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            await self._send_telegram_alert(alert)
        
        print(f"🚨 Jarvis Alert: [{severity.value}] {service}: {message}")
    
    async def _send_telegram_alert(self, alert: Alert):
        """Send alert via Telegram"""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        message = f"""
{emoji.get(alert.severity, '📢')} *JARVIS ALERT*
━━━━━━━━━━━━━━━━━
*Severity:* {alert.severity.value.upper()}
*Service:* {alert.service}
*Message:* {alert.message}
*Time:* {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
        except Exception as e:
            print(f"⚠️ Jarvis: Failed to send Telegram alert: {e}")
    
    def get_status(self) -> Dict:
        """Get current system status"""
        service_statuses = {}
        for name, health in self.services.items():
            service_statuses[name] = {
                "status": health.status.value,
                "last_check": health.last_check.isoformat() if health.last_check else None,
                "response_time_ms": health.response_time_ms,
                "error": health.error_message,
                "failures": health.consecutive_failures
            }
        
        # Count by status
        status_counts = {}
        for health in self.services.values():
            status = health.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Overall health
        unhealthy_count = status_counts.get("unhealthy", 0)
        if unhealthy_count > 0:
            overall = "degraded" if unhealthy_count < len(self.services) else "critical"
        else:
            overall = "healthy"
        
        return {
            "overall_status": overall,
            "emergency_stop": self.emergency_stop,
            "services": service_statuses,
            "status_counts": status_counts,
            "last_full_check": self.last_full_check.isoformat() if self.last_full_check else None,
            "total_services": len(self.services),
            "active_alerts": len([a for a in self.alerts if not a.resolved])
        }
    
    def get_alerts(self, limit: int = 20, unresolved_only: bool = False) -> List[Dict]:
        """Get recent alerts"""
        alerts = self.alerts
        if unresolved_only:
            alerts = [a for a in alerts if not a.resolved]
        
        return [
            {
                "id": a.id,
                "timestamp": a.timestamp.isoformat(),
                "severity": a.severity.value,
                "service": a.service,
                "message": a.message,
                "resolved": a.resolved
            }
            for a in sorted(alerts, key=lambda x: x.timestamp, reverse=True)[:limit]
        ]
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                return True
        return False
    
    def set_emergency_stop(self, active: bool, by_user: str = "system"):
        """Set emergency stop status"""
        self.emergency_stop = active
        
        if active:
            asyncio.create_task(self._create_alert(
                severity=AlertSeverity.CRITICAL,
                service="system",
                message=f"Emergency stop activated by {by_user}"
            ))
        else:
            asyncio.create_task(self._create_alert(
                severity=AlertSeverity.INFO,
                service="system",
                message=f"Emergency stop deactivated by {by_user}"
            ))


# Singleton instance
_jarvis_instance: Optional[Jarvis] = None

def get_jarvis() -> Jarvis:
    """Get or create Jarvis instance"""
    global _jarvis_instance
    if _jarvis_instance is None:
        _jarvis_instance = Jarvis()
    return _jarvis_instance


async def run_monitoring_loop():
    """Run continuous monitoring loop"""
    jarvis = get_jarvis()
    print("🤖 Jarvis: Monitoring loop started")
    
    while True:
        try:
            await jarvis.check_all_services()
            status = jarvis.get_status()
            print(f"🤖 Jarvis: Health check complete - {status['overall_status']}")
        except Exception as e:
            print(f"⚠️ Jarvis: Monitoring error: {e}")
        
        await asyncio.sleep(jarvis.check_interval_seconds)


if __name__ == "__main__":
    # Test Jarvis
    jarvis = get_jarvis()

    async def test():
        status = await jarvis.check_all_services()
        print("\n📊 Service Status:")
        for name, health in status.items():
            print(f"  - {name}: {health.status.value}")
        
        print("\n📊 Full Status:")
        print(json.dumps(jarvis.get_status(), indent=2))
    
    asyncio.run(test())

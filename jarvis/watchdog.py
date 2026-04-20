"""
Jarvis Watchdog Service
Runs continuously to monitor all system components
Deploy as a separate Railway service
"""

import os
import sys
import asyncio
import signal
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis import get_jarvis, get_anomaly_detector


class JarvisWatchdog:
    """
    Continuous monitoring service that:
    - Checks health of all services every 60 seconds
    - Sends alerts on issues
    - Tracks system metrics
    - Can trigger auto-recovery
    """
    
    def __init__(self):
        self.jarvis = get_jarvis()
        self.anomaly_detector = get_anomaly_detector()
        self.running = True
        self.check_interval = int(os.getenv("WATCHDOG_INTERVAL", 60))
        self.startup_time = datetime.now()
        
        # Statistics
        self.total_checks = 0
        self.failed_checks = 0
        self.alerts_sent = 0
        
        print("🤖 Jarvis Watchdog initializing...")
        print(f"   Check interval: {self.check_interval}s")
    
    async def start(self):
        """Start the watchdog monitoring loop"""
        print("🤖 Jarvis Watchdog ONLINE")
        print(f"   Monitoring {len(self.jarvis.services)} services")
        print("=" * 50)
        
        # Initial health check
        await self._run_health_check()
        
        # Send startup notification
        await self._send_startup_notification()
        
        # Main loop
        while self.running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._run_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Watchdog error: {e}")
                self.failed_checks += 1
        
        print("🤖 Jarvis Watchdog shutting down...")
    
    async def _run_health_check(self):
        """Run a complete health check cycle"""
        self.total_checks += 1
        start_time = datetime.now()
        
        print(f"\n[{start_time.strftime('%H:%M:%S')}] 🔍 Health check #{self.total_checks}")
        
        # Check all services
        results = await self.jarvis.check_all_services()
        
        # Analyze results
        healthy = 0
        unhealthy = 0
        for name, health in results.items():
            status_icon = "✅" if health.status.value == "healthy" else "❌"
            print(f"   {status_icon} {name}: {health.status.value} ({health.response_time_ms:.0f}ms)")
            
            if health.status.value == "healthy":
                healthy += 1
            else:
                unhealthy += 1
        
        # Get overall status
        status = self.jarvis.get_status()
        
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        print(f"   📊 Overall: {status['overall_status']} | Check took {elapsed:.0f}ms")
        
        # Check for anomalies
        anomalies = self.anomaly_detector.get_summary()
        if anomalies['total_anomalies_last_hour'] > 0:
            print(f"   ⚠️ Anomalies detected: {anomalies['total_anomalies_last_hour']} in last hour")
        
        return status
    
    async def _send_startup_notification(self):
        """Send notification that watchdog is online"""
        try:
            import requests
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            
            if token and chat_id:
                message = f"""
🤖 *JARVIS WATCHDOG ONLINE*
━━━━━━━━━━━━━━━━━
*Started:* {self.startup_time.strftime('%Y-%m-%d %H:%M:%S')}
*Services:* {len(self.jarvis.services)} monitored
*Interval:* {self.check_interval}s
━━━━━━━━━━━━━━━━━
System monitoring active ✅
"""
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                    timeout=10
                )
                print("📱 Startup notification sent to Telegram")
        except Exception as e:
            print(f"⚠️ Could not send Telegram notification: {e}")
    
    def stop(self):
        """Stop the watchdog"""
        self.running = False
    
    def get_stats(self):
        """Get watchdog statistics"""
        uptime = datetime.now() - self.startup_time
        return {
            "uptime_seconds": uptime.total_seconds(),
            "uptime_human": str(uptime).split('.')[0],
            "total_checks": self.total_checks,
            "failed_checks": self.failed_checks,
            "success_rate": ((self.total_checks - self.failed_checks) / max(self.total_checks, 1)) * 100,
            "alerts_sent": self.alerts_sent
        }


# Global instance
_watchdog: JarvisWatchdog = None


def get_watchdog() -> JarvisWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = JarvisWatchdog()
    return _watchdog


async def main():
    """Main entry point"""
    watchdog = get_watchdog()
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        print("\n⚠️ Shutdown signal received")
        watchdog.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start watchdog
    await watchdog.start()
    
    # Print final stats
    stats = watchdog.get_stats()
    print("\n📊 Final Statistics:")
    print(f"   Uptime: {stats['uptime_human']}")
    print(f"   Checks: {stats['total_checks']} (Success: {stats['success_rate']:.1f}%)")


if __name__ == "__main__":
    print("=" * 50)
    print("    JARVIS WATCHDOG SERVICE")
    print("    Intelligent System Monitoring")
    print("=" * 50)
    
    asyncio.run(main())

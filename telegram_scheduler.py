#!/usr/bin/env python3
"""
Telegram Daily Report Scheduler

Sends a daily report at 18:00 to Telegram.
Can be run manually or via system scheduler.

Usage:
    python telegram_scheduler.py          # Send report now
    python telegram_scheduler.py --daemon  # Run as daemon (waits until 18:00)
"""

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

def send_daily_report():
    """Send the daily Telegram report"""
    print(f"📱 Sending daily report at {datetime.now().strftime('%H:%M:%S')}")
    
    # Import and execute daily report
    try:
        from daily_telegram_report import main as send_report
        sys.argv = ['daily_telegram_report.py', '--daily', '--days', '7']
        send_report()
        print("✅ Report sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to send report: {e}")
        return False

def run_daemon(target_hour=18, target_minute=0):
    """Run as daemon, sending report at specified time"""
    print(f"🤖 Telegram Daemon started. Will send report at {target_hour:02d}:{target_minute:02d}")
    
    last_sent_date = None
    
    while True:
        now = datetime.now()
        
        # Check if it's time to send and we haven't sent today
        if (now.hour == target_hour and 
            now.minute >= target_minute and 
            now.date() != last_sent_date):
            
            if send_daily_report():
                last_sent_date = now.date()
            
            # Wait 1 hour to avoid double sending
            time.sleep(3600)
        else:
            # Check every minute
            time.sleep(60)

def create_launchd_plist():
    """Create macOS LaunchAgent plist for auto-start"""
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ethbot.telegram-report</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{PROJECT_ROOT}/daily_telegram_report.py</string>
        <string>--daily</string>
        <string>--days</string>
        <string>7</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{PROJECT_ROOT}/logs/telegram_scheduler.log</string>
    <key>StandardErrorPath</key>
    <string>{PROJECT_ROOT}/logs/telegram_scheduler.log</string>
    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>LOG_DIR</key>
        <string>{PROJECT_ROOT}/logs</string>
    </dict>
</dict>
</plist>
"""
    
    plist_path = Path.home() / "Library/LaunchAgents/com.ethbot.telegram-report.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)
    
    print(f"✅ LaunchAgent created: {plist_path}")
    print(f"\n📌 To activate:")
    print(f"   launchctl load {plist_path}")
    print(f"\n📌 To deactivate:")
    print(f"   launchctl unload {plist_path}")
    print(f"\n📌 To test now:")
    print(f"   launchctl start com.ethbot.telegram-report")
    
    return plist_path

def main():
    parser = argparse.ArgumentParser(description='Telegram Daily Report Scheduler')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--install', action='store_true', help='Install macOS LaunchAgent')
    parser.add_argument('--hour', type=int, default=18, help='Hour to send (default: 18)')
    parser.add_argument('--minute', type=int, default=0, help='Minute to send (default: 0)')
    args = parser.parse_args()
    
    if args.install:
        create_launchd_plist()
    elif args.daemon:
        run_daemon(args.hour, args.minute)
    else:
        # Send report now
        send_daily_report()

if __name__ == "__main__":
    main()

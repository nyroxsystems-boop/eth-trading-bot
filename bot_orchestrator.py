"""
Bot Orchestrator - Manages multiple trading bot instances
Each active account gets its own bot process
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import Dict, List
from datetime import datetime
import threading

from account_manager import AccountManager

# Bot process tracking
bot_processes: Dict[int, subprocess.Popen] = {}
bot_threads: Dict[int, threading.Thread] = {}
shutdown_flag = False


class BotOrchestrator:
    """Orchestrates multiple bot instances"""
    
    def __init__(self):
        self.account_manager = AccountManager()
        self.running = False
        
    def start_bot_for_account(self, account_id: int) -> bool:
        """Start a bot instance for a specific account"""
        account = self.account_manager.get_account(account_id)
        if not account:
            print(f"❌ Account {account_id} not found")
            return False
        
        if not account['active']:
            print(f"⚠️ Account {account['name']} is not active")
            return False
        
        # Check if bot is already running
        if account_id in bot_processes and bot_processes[account_id].poll() is None:
            print(f"⚠️ Bot for account {account['name']} is already running")
            return False
        
        print(f"🚀 Starting bot for account: {account['name']} (ID: {account_id})")
        
        # Set environment variables for this bot instance
        env = os.environ.copy()
        env['ACCOUNT_ID'] = str(account_id)
        env['ACCOUNT_NAME'] = account['name']
        env['BINANCE_API_KEY'] = account['api_key']
        env['BINANCE_API_SECRET'] = account['api_secret']
        env['PAPER_BASE_USDT'] = str(account['capital'])
        env['DRY_RUN'] = 'true' if account['dry_run'] else 'false'
        
        # Start bot process
        try:
            process = subprocess.Popen(
                [sys.executable, 'eth_master_bot.py'],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=Path(__file__).parent
            )
            
            bot_processes[account_id] = process
            print(f"✅ Bot started for {account['name']} (PID: {process.pid})")
            
            # Update last active timestamp
            self.account_manager.update_last_active(account_id)
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to start bot for {account['name']}: {e}")
            return False
    
    def stop_bot_for_account(self, account_id: int) -> bool:
        """Stop a bot instance for a specific account"""
        if account_id not in bot_processes:
            print(f"⚠️ No bot running for account {account_id}")
            return False
        
        process = bot_processes[account_id]
        
        if process.poll() is not None:
            # Process already terminated
            del bot_processes[account_id]
            return True
        
        account = self.account_manager.get_account(account_id)
        account_name = account['name'] if account else f"ID {account_id}"
        
        print(f"🛑 Stopping bot for account: {account_name}")
        
        try:
            # Graceful shutdown
            process.terminate()
            
            # Wait up to 10 seconds for graceful shutdown
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if not responding
                print(f"⚠️ Force killing bot for {account_name}")
                process.kill()
                process.wait()
            
            del bot_processes[account_id]
            print(f"✅ Bot stopped for {account_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping bot for {account_name}: {e}")
            return False
    
    def restart_bot_for_account(self, account_id: int) -> bool:
        """Restart a bot instance"""
        self.stop_bot_for_account(account_id)
        time.sleep(2)  # Brief pause
        return self.start_bot_for_account(account_id)
    
    def monitor_bots(self):
        """Monitor bot processes and restart if crashed"""
        while self.running and not shutdown_flag:
            # Get all active accounts
            active_accounts = self.account_manager.list_accounts(active_only=True)
            
            for account in active_accounts:
                account_id = account['id']
                
                # Check if bot should be running
                if account_id in bot_processes:
                    process = bot_processes[account_id]
                    
                    # Check if process crashed
                    if process.poll() is not None:
                        print(f"⚠️ Bot for {account['name']} crashed (exit code: {process.returncode})")
                        print(f"🔄 Restarting bot for {account['name']}...")
                        
                        # Remove dead process
                        del bot_processes[account_id]
                        
                        # Wait a bit before restart (exponential backoff could be added)
                        time.sleep(5)
                        
                        # Restart
                        self.start_bot_for_account(account_id)
                else:
                    # Bot should be running but isn't
                    print(f"🔄 Starting bot for {account['name']} (was not running)")
                    self.start_bot_for_account(account_id)
            
            # Check for bots that shouldn't be running (account deactivated)
            for account_id in list(bot_processes.keys()):
                account = self.account_manager.get_account(account_id)
                if not account or not account['active']:
                    print(f"🛑 Stopping bot for deactivated account {account_id}")
                    self.stop_bot_for_account(account_id)
            
            # Sleep before next check
            time.sleep(30)  # Check every 30 seconds
    
    def start_all(self):
        """Start bots for all active accounts"""
        print("🚀 Starting Bot Orchestrator...")
        self.running = True
        
        # Start bots for all active accounts
        active_accounts = self.account_manager.list_accounts(active_only=True)
        
        if not active_accounts:
            print("⚠️ No active accounts found")
            return
        
        print(f"📊 Found {len(active_accounts)} active account(s)")
        
        for account in active_accounts:
            self.start_bot_for_account(account['id'])
            time.sleep(2)  # Stagger starts
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_bots, daemon=True)
        monitor_thread.start()
        
        print("✅ Bot Orchestrator running")
        print(f"📊 Managing {len(bot_processes)} bot instance(s)")
    
    def stop_all(self):
        """Stop all bot instances"""
        print("🛑 Stopping all bots...")
        self.running = False
        
        for account_id in list(bot_processes.keys()):
            self.stop_bot_for_account(account_id)
        
        print("✅ All bots stopped")
    
    def get_status(self) -> List[Dict]:
        """Get status of all bot instances"""
        status = []
        
        for account_id, process in bot_processes.items():
            account = self.account_manager.get_account(account_id)
            
            status.append({
                "account_id": account_id,
                "account_name": account['name'] if account else "Unknown",
                "pid": process.pid,
                "running": process.poll() is None,
                "exit_code": process.returncode
            })
        
        return status


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global shutdown_flag
    print("\n🛑 Shutdown signal received...")
    shutdown_flag = True
    
    if orchestrator:
        orchestrator.stop_all()
    
    sys.exit(0)


# Global orchestrator instance
orchestrator = None


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create orchestrator
    orchestrator = BotOrchestrator()
    
    # Start all bots
    orchestrator.start_all()
    
    # Keep main thread alive
    try:
        while not shutdown_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

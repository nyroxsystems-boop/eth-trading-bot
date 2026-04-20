#!/usr/bin/env python3
"""
Auto-Learning Master Service
Coordinates continuous backtesting and auto-apply
"""

import asyncio
import os
from datetime import datetime

from continuous_backtester import ContinuousBacktester
from auto_apply import AutoApply

class AutoLearningService:
    def __init__(self):
        self.enabled = os.getenv("AUTO_LEARNING_ENABLED", "true").lower() == "true"
        self.auto_apply_enabled = os.getenv("AUTO_APPLY_ENABLED", "true").lower() == "true"
        self.strategies_per_hour = int(os.getenv("STRATEGIES_PER_HOUR", "10"))
        
        self.backtester = ContinuousBacktester(
            strategies_per_hour=self.strategies_per_hour
        )
        self.auto_apply = AutoApply()
        
        print(f"""
╔══════════════════════════════════════════════════════════╗
║          AUTO-LEARNING SYSTEM INITIALIZED                ║
╠══════════════════════════════════════════════════════════╣
║  Auto-Learning: {'ENABLED' if self.enabled else 'DISABLED'}                              ║
║  Auto-Apply:    {'ENABLED' if self.auto_apply_enabled else 'DISABLED'}                              ║
║  Strategies/Hour: {self.strategies_per_hour}                                   ║
╚══════════════════════════════════════════════════════════╝
        """)
    
    async def run_backtest_cycle(self):
        """Run one backtest cycle"""
        if not self.enabled:
            return
        
        try:
            await self.backtester.run_cycle()
        except Exception as e:
            print(f"Error in backtest cycle: {e}")
    
    def run_auto_apply(self):
        """Check and apply best strategy"""
        if not self.auto_apply_enabled:
            return
        
        try:
            self.auto_apply.check_and_apply()
        except Exception as e:
            print(f"Error in auto-apply: {e}")
    
    async def run_continuous(self):
        """Main loop: backtest every hour, auto-apply after each cycle"""
        print("\n🚀 Starting Auto-Learning Service...")
        print(f"⏰ {datetime.now()}\n")
        
        while True:
            try:
                # Run backtest cycle
                print(f"\n{'='*60}")
                print(f"BACKTEST CYCLE - {datetime.now()}")
                print(f"{'='*60}\n")
                
                await self.run_backtest_cycle()
                
                # After backtesting, check if should apply new strategy
                if self.auto_apply_enabled:
                    print(f"\n{'='*60}")
                    print(f"AUTO-APPLY CHECK - {datetime.now()}")
                    print(f"{'='*60}\n")
                    
                    self.run_auto_apply()
                
                # Wait 1 hour
                print("\n⏸️  Waiting 1 hour until next cycle...")
                print(f"   Next cycle: {datetime.now().replace(hour=(datetime.now().hour + 1) % 24, minute=0, second=0)}\n")
                
                await asyncio.sleep(3600)
                
            except KeyboardInterrupt:
                print("\n\n⛔ Auto-Learning Service stopped by user")
                break
            except Exception as e:
                print(f"\n❌ Error in main loop: {e}")
                print("   Retrying in 1 minute...\n")
                await asyncio.sleep(60)

def main():
    """Entry point"""
    service = AutoLearningService()
    
    try:
        asyncio.run(service.run_continuous())
    except KeyboardInterrupt:
        print("\n\nShutting down Auto-Learning Service...")

if __name__ == "__main__":
    main()
